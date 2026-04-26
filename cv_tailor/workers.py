"""QThread workers: profile build, single-job tailor, bulk runner."""
import os
import re
import threading
import time
from datetime import datetime

from anthropic import APIConnectionError, AuthenticationError
from PyQt5.QtCore import QThread, pyqtSignal

from .claude_client import (_session_stats, claude_call_cached,
                            print_session_summary, reset_session_stats)
from .constants import BULK_DELAY_SEC, MAX_TOKENS_UNIFIED, PROFILE_SCHEMA
from .docx_builder import DocxBuilder
from .extract import extract_text_from_file
from .profile import (ProfileManager, compress_profile, validate_cv_output)
from .prompts import UNIFIED_SYSTEM
from .utils import build_output_path, parse_json_response, strip_hard_gap


class UnifiedWorker(QThread):
    """Single-call fit assessment + CV generation."""
    progress = pyqtSignal(int)
    result = pyqtSignal(dict, dict, str)  # fit, cv, hard_gap
    error = pyqtSignal(str)

    def __init__(self, client, profile, company, title, jd):
        """Store inputs."""
        super().__init__()
        self.client = client
        self.profile = profile
        self.company = company
        self.title = title
        self.jd = jd

    def run(self):
        """Execute the combined assessment+generation call."""
        compact = compress_profile(self.profile)
        cached_user = f"CANDIDATE PROFILE:\n{compact}"
        fresh_user = (f"COMPANY: {self.company}\nTITLE: {self.title}\n"
                      f"JOB DESCRIPTION:\n{self.jd}\n\n"
                      f"Generate the tailored CV.")
        self.progress.emit(15)
        try:
            text = claude_call_cached(self.client, UNIFIED_SYSTEM,
                                      cached_user, fresh_user,
                                      MAX_TOKENS_UNIFIED,
                                      call_name="fit_and_cv_generation")
            self.progress.emit(80)
            data = self._parse(text)
            fit = data.get("fit") or {}
            cv = validate_cv_output(data.get("cv") or {}, self.profile)
            hard_gap = data.get("hard_gap", "") or ""
            self.progress.emit(100)
            self.result.emit(fit, cv, hard_gap)
        except AuthenticationError:
            self.error.emit("Invalid API key — check Settings")
        except APIConnectionError:
            self.error.emit("Connection failed — check internet")
        except Exception as e:
            self.error.emit(str(e))

    def _parse(self, text):
        """Parse JSON; on failure retry once with an explicit format reminder."""
        body, _ = strip_hard_gap(text)
        try:
            return parse_json_response(body)
        except Exception:
            pass
        retry_suffix = (
            "\nIMPORTANT: Return ONLY a raw JSON object. No markdown, "
            "no backticks, no explanation. Start your response with { "
            "and end with }"
        )
        cached_user = f"CANDIDATE PROFILE:\n{compress_profile(self.profile)}"
        fresh_user = (f"COMPANY: {self.company}\nTITLE: {self.title}\n"
                      f"JOB DESCRIPTION:\n{self.jd}\n\n"
                      f"Generate the tailored CV.")
        text2 = claude_call_cached(
            self.client,
            UNIFIED_SYSTEM + retry_suffix,
            cached_user, fresh_user,
            MAX_TOKENS_UNIFIED,
            call_name="fit_and_cv_generation (retry)",
        )
        body2, _ = strip_hard_gap(text2)
        try:
            return parse_json_response(body2)
        except Exception as exc:
            raise ValueError(
                "CV generation failed — Claude returned unexpected format. "
                "Check console for details. Try again."
            ) from exc


class ProfileBuildWorker(QThread):
    """Build or merge a profile in the background."""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, files, mode, existing=None):
        """Store inputs."""
        super().__init__()
        self.client = client
        self.files = files
        self.mode = mode
        self.existing = existing

    def run(self):
        """Extract texts and call ProfileManager."""
        try:
            texts = []
            total = max(1, len(self.files))
            for i, f in enumerate(self.files):
                self.status.emit(f"Reading {os.path.basename(f)}…")
                texts.append(extract_text_from_file(f))
                self.progress.emit(int((i + 1) / total * 50))
            self.status.emit("Calling Claude…")
            pm = ProfileManager(self.client)
            if self.mode == "new":
                profile = pm.build_new(texts)
            else:
                profile = pm.merge(self.existing or PROFILE_SCHEMA, texts)
            self.progress.emit(100)
            self.done.emit(profile)
        except AuthenticationError:
            self.error.emit("Invalid API key — check Settings")
        except APIConnectionError:
            self.error.emit("Connection failed — check internet")
        except Exception as e:
            self.error.emit(str(e))


def parse_bulk_input(text):
    """Parse bulk input into list of (company, title, jd) tuples."""
    jobs = []
    blocks = re.split(r"\n\s*---\s*\n", text.strip())
    for block in blocks:
        if not block.strip():
            continue
        comp = re.search(r"COMPANY\s*:\s*(.+)", block, re.I)
        title = re.search(r"TITLE\s*:\s*(.+)", block, re.I)
        jd_m = re.search(r"JD\s*:\s*\n?(.+)", block, re.I | re.S)
        if comp and title and jd_m:
            jobs.append((comp.group(1).strip(), title.group(1).strip(),
                         jd_m.group(1).strip()))
    return jobs


class BulkRunner(QThread):
    """Sequentially assess+generate with RED pause support. One API call
    per job via UNIFIED_SYSTEM."""
    row_update = pyqtSignal(int, str, str)
    waiting_for_decision = pyqtSignal(int, str, list)
    done = pyqtSignal()

    def __init__(self, client, profile, output_folder, jobs):
        """Store inputs."""
        super().__init__()
        self.client = client
        self.profile = profile
        self.output = output_folder
        self.jobs = jobs
        self._stop = False
        self._decision_event = threading.Event()
        self._decision = None
        self.results = []

    def stop(self):
        """Request stop — unblocks any pending decision wait."""
        self._stop = True
        self._decision_event.set()

    def submit_decision(self, decision):
        """Called from GUI with 'generate' or 'skip'."""
        self._decision = decision
        self._decision_event.set()

    def run(self):
        """Main loop."""
        reset_session_stats()
        for i, (company, title, jd) in enumerate(self.jobs):
            if self._stop:
                break
            row_result = {"Company": company, "Title": title,
                          "Fit": "", "Fit Score": "", "Fit Summary": "",
                          "Strengths": "", "Gaps": "", "Hard Gaps": "",
                          "Status": "", "Gap Note": "", "Filename": "",
                          "Date": datetime.now().strftime("%Y-%m-%d")}
            self.row_update.emit(i, "Status", "Assessing & drafting")
            fit, cv, hard_gap = self._unified(company, title, jd)
            if fit is None:
                self.row_update.emit(i, "Status", "✗ Error")
                row_result["Status"] = "Error"
                self.results.append(row_result)
                time.sleep(BULK_DELAY_SEC)
                continue

            level = (fit.get("fit") or "yellow").lower()
            icon = {"green": "🟢 Strong", "yellow": "🟡 Partial",
                    "red": "🔴 Poor"}.get(level, "🟡 Partial")
            self.row_update.emit(i, "Fit", icon)
            row_result["Fit"] = icon
            row_result["Fit Score"] = str(fit.get("score", ""))
            row_result["Fit Summary"] = fit.get("summary", "")
            row_result["Strengths"] = "; ".join(fit.get("strengths", []))
            row_result["Gaps"] = "; ".join(fit.get("gaps", []))
            row_result["Hard Gaps"] = "; ".join(fit.get("hard_gaps", []))

            if level == "red":
                self.row_update.emit(i, "Status", "⚠ Poor Fit — waiting...")
                self._decision_event.clear()
                self._decision = None
                self.waiting_for_decision.emit(
                    i, fit.get("summary", ""), fit.get("hard_gaps", []))
                self._decision_event.wait()
                if self._stop:
                    row_result["Status"] = "Skipped"
                    self.results.append(row_result)
                    break
                if self._decision != "generate":
                    self.row_update.emit(i, "Status", "✗ Skipped")
                    row_result["Status"] = "Skipped"
                    self.results.append(row_result)
                    time.sleep(BULK_DELAY_SEC)
                    continue

            self.row_update.emit(i, "Status", "Writing DOCX")
            try:
                path = build_output_path(self.output, company, title)
                DocxBuilder.build(self.profile, cv or {}, path)
                self.row_update.emit(i, "Status", "✓ Done")
                self.row_update.emit(i, "Filename", os.path.basename(path))
                row_result["Status"] = "Done"
                row_result["Filename"] = os.path.basename(path)
                if hard_gap:
                    self.row_update.emit(i, "Gap", f"⚠ {hard_gap}")
                    row_result["Gap Note"] = hard_gap
            except Exception as e:
                self.row_update.emit(i, "Status", f"✗ Error: {e}")
                row_result["Status"] = f"Error: {e}"
            self.results.append(row_result)
            _session_stats["jobs"] += 1
            time.sleep(BULK_DELAY_SEC)
        print_session_summary()
        self.done.emit()

    def _unified(self, company, title, jd):
        """Single combined fit+CV call. Returns (fit, cv, hard_gap) or
        (None, None, '') on error."""
        compact = compress_profile(self.profile)
        cached_user = f"CANDIDATE PROFILE:\n{compact}"
        fresh_user = (f"COMPANY: {company}\nTITLE: {title}\n"
                      f"JOB DESCRIPTION:\n{jd}\n\n"
                      f"Generate the tailored CV.")
        try:
            text = claude_call_cached(self.client, UNIFIED_SYSTEM,
                                      cached_user, fresh_user,
                                      MAX_TOKENS_UNIFIED,
                                      call_name="fit_and_cv_generation")
            body, _ = strip_hard_gap(text)
            data = parse_json_response(body)
            return (data.get("fit") or {},
                    validate_cv_output(data.get("cv") or {}, self.profile),
                    data.get("hard_gap", "") or "")
        except AuthenticationError:
            return None, None, ""
        except APIConnectionError:
            return None, None, ""
        except Exception:
            retry_suffix = (
                "\nIMPORTANT: Return ONLY a raw JSON object. No markdown, "
                "no backticks, no explanation. Start your response with { "
                "and end with }"
            )
            try:
                text = claude_call_cached(
                    self.client, UNIFIED_SYSTEM + retry_suffix,
                    cached_user, fresh_user, MAX_TOKENS_UNIFIED,
                    call_name="fit_and_cv_generation (retry)")
                body, _ = strip_hard_gap(text)
                data = parse_json_response(body)
                return (data.get("fit") or {},
                        validate_cv_output(data.get("cv") or {}, self.profile),
                        data.get("hard_gap", "") or "")
            except Exception:
                return None, None, ""

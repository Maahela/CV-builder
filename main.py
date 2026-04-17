"""CV Tailor — desktop app that tailors CVs to job descriptions via Claude."""
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
from anthropic import (Anthropic, APIConnectionError, AuthenticationError,
                       RateLimitError)
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPalette, QTextCursor
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QFrame, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QProgressBar,
                             QPushButton, QScrollArea, QSplitter, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

APP_VERSION = "1.0.0"
MODEL_NAME = "claude-sonnet-4-5"
MAX_TOKENS = 8000
CONFIG_FILE = "config.json"
PROFILE_FILE = "master_profile.json"
DEFAULT_OUTPUT = "output"
COMPANY_MAX = 25
TITLE_MAX = 35
BULK_DELAY_SEC = 1.0
RATE_LIMIT_RETRY_SEC = 5

BG = "#0d1117"
FG = "#e6edf3"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#388bfd"
GREEN = "#238636"
YELLOW = "#9e6a03"
RED = "#da3633"

PROFILE_SCHEMA = {
    "name": "", "contact": {"email": "", "phone": "", "linkedin": "",
                            "github": "", "website": ""},
    "summary": "", "experience": [], "education": [],
    "skills": {"languages": [], "frontend": [], "backend": [],
               "databases": [], "cloud": [], "ai_integrations": [],
               "third_party_apis": [], "erp": [], "other": []},
    "projects": [], "certifications": [], "volunteering": [],
    "achievements": [], "interests": []
}

SKILL_CATEGORIES = [
    ("languages", "Languages"), ("frontend", "Frontend"),
    ("backend", "Backend"), ("databases", "Databases"),
    ("cloud", "Cloud & DevOps"), ("ai_integrations", "AI / Integrations"),
    ("third_party_apis", "Third-Party APIs"), ("erp", "ERP"),
]


# ─── Config / IO helpers ─────────────────────────────────────────────────

def load_config():
    """Return config dict (creates defaults if missing)."""
    if not os.path.exists(CONFIG_FILE):
        return {"api_key": "", "output_folder": DEFAULT_OUTPUT}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"api_key": "", "output_folder": DEFAULT_OUTPUT}


def save_config(cfg):
    """Write config dict to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_profile():
    """Return master profile dict, or empty schema if none."""
    if not os.path.exists(PROFILE_FILE):
        return None
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_profile(profile):
    """Persist master profile to JSON."""
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def extract_text_from_file(path):
    """Extract raw text from PDF, DOCX, or TXT."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            with pdfplumber.open(path) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        if ext == ".docx":
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        return f"[parse error: {e}]"
    return ""


def sanitize_filename_part(text, maxlen):
    """Turn text into safe filename segment."""
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]", "", text)
    return text[:maxlen] or "Unknown"


def build_output_path(output_folder, company, title):
    """Return non-colliding output path for today's CV."""
    os.makedirs(output_folder, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    base = f"{date}_{sanitize_filename_part(company, COMPANY_MAX)}_" \
           f"{sanitize_filename_part(title, TITLE_MAX)}"
    path = os.path.join(output_folder, base + ".docx")
    i = 2
    while os.path.exists(path):
        path = os.path.join(output_folder, f"{base}_{i}.docx")
        i += 1
    return path


def parse_json_response(text):
    """Extract JSON object from Claude response, stripping fences if any."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    return json.loads(text[start:end + 1])


def open_file_native(path):
    """Open a file with OS default application."""
    try:
        os.startfile(path)
    except Exception:
        subprocess.Popen(["cmd", "/c", "start", "", path], shell=False)


# ─── ProfileManager ──────────────────────────────────────────────────────

class ProfileManager:
    """Build and merge the master profile via Claude."""

    def __init__(self, client):
        """Hold Anthropic client."""
        self.client = client

    def build_new(self, texts):
        """Create a fresh profile from extracted document texts."""
        combined = "\n\n---\n\n".join(texts)
        schema_str = json.dumps(PROFILE_SCHEMA, indent=2)
        system = (
            "Extract ALL information from these CV documents and return "
            "a single unified master profile as JSON matching the exact "
            "schema provided. Return ONLY valid JSON, no markdown fences, "
            "no commentary.\n\nSCHEMA:\n" + schema_str
        )
        msg = self.client.messages.create(
            model=MODEL_NAME, max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": combined}],
        )
        return parse_json_response(msg.content[0].text)

    def merge(self, existing, texts):
        """Merge new document texts into existing profile."""
        combined = "\n\n---\n\n".join(texts)
        system = (
            "Merge new CV information into the existing master profile. "
            "Add new roles, projects, skills. Deduplicate — never add "
            "something already present. Never remove existing data. "
            "Return the complete updated profile as JSON. Return ONLY "
            "valid JSON."
        )
        user = (f"EXISTING PROFILE:\n{json.dumps(existing, indent=2)}"
                f"\n\nNEW DOCUMENTS:\n{combined}")
        msg = self.client.messages.create(
            model=MODEL_NAME, max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return parse_json_response(msg.content[0].text)


# ─── DocxBuilder ─────────────────────────────────────────────────────────

class DocxBuilder:
    """Produce a formatted .docx CV from tailored JSON data."""

    @staticmethod
    def _set_bottom_border(paragraph):
        """Add a bottom border to a paragraph (used for section headers)."""
        p = paragraph._p
        pPr = p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "000000")
        pBdr.append(bottom)
        pPr.append(pBdr)

    @staticmethod
    def _add_run(paragraph, text, *, bold=False, italic=False,
                 size=10.5, color=None, font="Calibri"):
        """Append a styled run to a paragraph."""
        run = paragraph.add_run(text)
        run.font.name = font
        run.font.size = Pt(size)
        run.bold = bold
        run.italic = italic
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        return run

    @staticmethod
    def _set_page(doc):
        """Set A4, 2cm margins."""
        for section in doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.left_margin = Cm(2)
            section.right_margin = Cm(2)
            section.top_margin = Cm(2)
            section.bottom_margin = Cm(2)

    @classmethod
    def _section_header(cls, doc, text):
        """Add an ALL CAPS section header with bottom border."""
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(8)
        pf.space_after = Pt(4)
        cls._add_run(p, text.upper(), bold=True, size=11, color="000000")
        cls._set_bottom_border(p)
        return p

    @classmethod
    def _title_with_date(cls, doc, title, date_str, italic_title=False):
        """Add bold title left + date right with tab stop at 16cm."""
        p = doc.add_paragraph()
        p.paragraph_format.tab_stops.add_tab_stop(
            Cm(16), WD_TAB_ALIGNMENT.RIGHT)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        cls._add_run(p, title, bold=True, italic=italic_title, size=11)
        if date_str:
            p.add_run("\t")
            cls._add_run(p, date_str, size=10)
        return p

    @classmethod
    def _subline(cls, doc, text, *, italic=True, color="444444"):
        """Add an italic subline (company / tech stack)."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        cls._add_run(p, text, italic=italic, size=10.5, color=color)
        return p

    @classmethod
    def _bullets(cls, doc, items):
        """Add a bullet list using ListBullet style."""
        for b in items:
            if not b:
                continue
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(0.5)
            p.paragraph_format.first_line_indent = Cm(-0.5)
            for r in p.runs:
                r.font.name = "Calibri"
                r.font.size = Pt(10.5)
            if not p.runs:
                cls._add_run(p, b, size=10.5)
            else:
                p.runs[0].text = b
        if items:
            doc.paragraphs[-1].paragraph_format.space_after = Pt(6)

    @classmethod
    def _header_block(cls, doc, profile):
        """Name + contact line + hr."""
        name = profile.get("name", "") or ""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        cls._add_run(p, name, bold=True, size=18)

        contact = profile.get("contact", {}) or {}
        parts = [contact.get(k, "") for k in
                 ("email", "phone", "linkedin", "github", "website")]
        parts = [p for p in parts if p]
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_before = Pt(0)
        p2.paragraph_format.space_after = Pt(0)
        cls._add_run(p2, " | ".join(parts), size=10, color="555555")
        cls._set_bottom_border(p2)
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(6)

    @classmethod
    def _skills_table(cls, doc, skills):
        """Two-column borderless table of skill categories."""
        rows = [(label, skills.get(key, []))
                for key, label in SKILL_CATEGORIES
                if skills.get(key)]
        if not rows:
            return
        table = doc.add_table(rows=len(rows), cols=2)
        table.autofit = False
        for row_i, (label, values) in enumerate(rows):
            left = table.cell(row_i, 0)
            right = table.cell(row_i, 1)
            left.width = Cm(3.5)
            right.width = Cm(13.5)
            lp = left.paragraphs[0]
            lp.paragraph_format.space_before = Pt(1)
            lp.paragraph_format.space_after = Pt(1)
            cls._add_run(lp, f"{label}:", bold=True, size=10.5)
            rp = right.paragraphs[0]
            rp.paragraph_format.space_before = Pt(1)
            rp.paragraph_format.space_after = Pt(1)
            cls._add_run(rp, ", ".join(values), size=10.5)

    @classmethod
    def build(cls, profile, cv_data, output_path):
        """Build the full CV document."""
        doc = Document()
        cls._set_page(doc)

        merged = {**profile, **{k: v for k, v in cv_data.items() if v}}
        merged["name"] = profile.get("name", "") or cv_data.get("name", "")
        merged["contact"] = profile.get("contact", {}) or \
            cv_data.get("contact", {})

        cls._header_block(doc, merged)

        summary = cv_data.get("summary") or profile.get("summary")
        if summary:
            cls._section_header(doc, "Summary")
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            cls._add_run(p, summary, size=10.5)

        experience = cv_data.get("experience") or []
        if experience:
            cls._section_header(doc, "Experience")
            for role in experience:
                dates = cls._fmt_dates(role.get("start"), role.get("end"),
                                       role.get("current"))
                cls._title_with_date(doc, role.get("title", ""), dates)
                comp = role.get("company", "")
                loc = role.get("location", "")
                sub = comp + (f" — {loc}" if loc else "")
                if sub.strip():
                    cls._subline(doc, sub)
                cls._bullets(doc, role.get("achievements", []))

        projects = cv_data.get("projects") or []
        if projects:
            cls._section_header(doc, "Projects")
            for proj in projects:
                year = proj.get("year", "") or ""
                cls._title_with_date(doc, proj.get("name", ""), str(year))
                tech = proj.get("tech") or []
                if isinstance(tech, list):
                    tech = ", ".join(tech)
                if tech:
                    cls._subline(doc, tech)
                desc = proj.get("description")
                bullets = proj.get("bullets") or (
                    [desc] if desc else [])
                cls._bullets(doc, bullets)

        skills = cv_data.get("skills") or profile.get("skills") or {}
        if any(skills.get(k) for k, _ in SKILL_CATEGORIES):
            cls._section_header(doc, "Technical Skills")
            cls._skills_table(doc, skills)

        volunteering = cv_data.get("volunteering") or []
        if volunteering:
            cls._section_header(doc, "Volunteering & Leadership")
            for v in volunteering:
                cls._title_with_date(doc, v.get("role", ""),
                                     v.get("period", ""))
                if v.get("org"):
                    cls._subline(doc, v.get("org", ""))
                cls._bullets(doc, v.get("bullets", []))

        achievements = cv_data.get("achievements") or []
        if achievements:
            cls._section_header(doc, "Achievements")
            cls._bullets(doc, achievements)

        education = cv_data.get("education") or profile.get("education") or []
        if education:
            cls._section_header(doc, "Education")
            for ed in education:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                cls._add_run(p, ed.get("degree", ""), bold=True, size=11)
                p2 = doc.add_paragraph()
                p2.paragraph_format.tab_stops.add_tab_stop(
                    Cm(16), WD_TAB_ALIGNMENT.RIGHT)
                p2.paragraph_format.space_before = Pt(0)
                p2.paragraph_format.space_after = Pt(4)
                cls._add_run(p2, ed.get("institution", ""),
                             italic=True, size=10.5, color="444444")
                if ed.get("year"):
                    p2.add_run("\t")
                    cls._add_run(p2, str(ed.get("year", "")), size=10)

        doc.save(output_path)

    @staticmethod
    def _fmt_dates(start, end, current):
        """Format a role date range."""
        if current:
            end = "Present"
        if start and end:
            return f"{start} — {end}"
        return start or end or ""


# ─── Workers ─────────────────────────────────────────────────────────────

class FitWorker(QThread):
    """Assess candidate-JD fit via Claude."""
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client, profile, jd):
        """Store inputs."""
        super().__init__()
        self.client = client
        self.profile = profile
        self.jd = jd

    def run(self):
        """Execute the fit assessment call."""
        system = (
            "You are a recruitment expert assessing how well a candidate's "
            "profile matches a job description.\n\n"
            "Evaluate: core tech skills, years/depth, domain, seniority, "
            "hard requirements.\n\n"
            "Return JSON EXACTLY:\n"
            "{\"fit\":\"green|yellow|red\",\"score\":0-100,"
            "\"summary\":\"one sentence\",\"strengths\":[...],"
            "\"gaps\":[...],\"hard_gaps\":[...]}\n\n"
            "GREEN 70-100: strong match. YELLOW 40-69: partial, "
            "transferable. RED 0-39: fundamental misalignment.\n"
            "Be honest. A React dev applying to Java backend is RED. "
            "Return ONLY the JSON, no fences."
        )
        user = (f"CANDIDATE PROFILE:\n{json.dumps(self.profile)}"
                f"\n\nJOB DESCRIPTION:\n{self.jd}")
        try:
            msg = self._call(system, user)
            try:
                data = parse_json_response(msg.content[0].text)
            except Exception:
                msg = self._call(system + "\nSTRICT: ONLY JSON.", user)
                try:
                    data = parse_json_response(msg.content[0].text)
                except Exception:
                    data = {"fit": "yellow", "score": 50,
                            "summary": "Parse failed — defaulted to yellow.",
                            "strengths": [], "gaps": [], "hard_gaps": []}
            self.result.emit(data)
        except AuthenticationError:
            self.error.emit("Invalid API key — check Settings")
        except APIConnectionError:
            self.error.emit("Connection failed — check internet")
        except RateLimitError:
            time.sleep(RATE_LIMIT_RETRY_SEC)
            try:
                msg = self._call(system, user)
                self.result.emit(parse_json_response(msg.content[0].text))
            except Exception as e:
                self.error.emit(f"Rate limited: {e}")
        except Exception as e:
            self.error.emit(str(e))

    def _call(self, system, user):
        """Single Anthropic call."""
        return self.client.messages.create(
            model=MODEL_NAME, max_tokens=2000, system=system,
            messages=[{"role": "user", "content": user}])


class CVWorker(QThread):
    """Generate tailored CV data via Claude."""
    progress = pyqtSignal(int)
    result = pyqtSignal(dict, str)  # cv_data, hard_gap
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
        """Execute CV generation call."""
        system = (
            "You are an expert CV writer. Generate a tailored CV for the "
            "job using the candidate's master profile.\n\n"
            "SECTION ORDER: 1.Summary 2.Experience 3.Projects (relevant "
            "only) 4.Technical Skills 5.Volunteering 6.Achievements "
            "7.Education.\n\n"
            "RULES: mirror JD keywords naturally, prioritise relevant "
            "experience, strong action verbs, quantify when data exists, "
            "NEVER invent roles/companies/projects, must fit 2 pages.\n\n"
            "GAPS: learnable gaps — include, frame as fast-learning. "
            "Hard gaps — generate anyway, reframe existing experience. "
            "After JSON, new line: HARD_GAP: [one sentence] if applicable. "
            "NEVER put HARD_GAP inside CV content.\n\n"
            "OUTPUT: JSON matching master profile schema (same structure, "
            "tailored content). Optional HARD_GAP line after. No fences."
        )
        user = (f"COMPANY: {self.company}\nTITLE: {self.title}\n"
                f"JD:\n{self.jd}\n\nMASTER PROFILE:\n"
                f"{json.dumps(self.profile)}")
        self.progress.emit(20)
        try:
            msg = self._call(system, user)
            self.progress.emit(80)
            text = msg.content[0].text
            hard_gap = ""
            m = re.search(r"HARD_GAP\s*:\s*(.+)", text)
            if m:
                hard_gap = m.group(1).strip()
                text = text[:m.start()]
            try:
                cv = parse_json_response(text)
            except Exception:
                msg = self._call(system + "\nSTRICT: ONLY JSON.", user)
                text = msg.content[0].text
                m = re.search(r"HARD_GAP\s*:\s*(.+)", text)
                if m:
                    hard_gap = m.group(1).strip()
                    text = text[:m.start()]
                cv = parse_json_response(text)
            self.progress.emit(100)
            self.result.emit(cv, hard_gap)
        except AuthenticationError:
            self.error.emit("Invalid API key — check Settings")
        except APIConnectionError:
            self.error.emit("Connection failed — check internet")
        except RateLimitError:
            time.sleep(RATE_LIMIT_RETRY_SEC)
            try:
                msg = self._call(system, user)
                self.result.emit(parse_json_response(msg.content[0].text), "")
            except Exception as e:
                self.error.emit(f"Rate limited: {e}")
        except Exception as e:
            self.error.emit(str(e))

    def _call(self, system, user):
        """Single Anthropic call."""
        return self.client.messages.create(
            model=MODEL_NAME, max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": user}])


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


# ─── Tabs ────────────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    """API key and output folder configuration."""
    config_changed = pyqtSignal()

    def __init__(self, cfg):
        """Build UI."""
        super().__init__()
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Anthropic API Key"))
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(cfg.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.show_btn = QPushButton("Show")
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(self._toggle_show)
        key_row.addWidget(self.key_edit)
        key_row.addWidget(self.show_btn)
        layout.addLayout(key_row)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Output Folder"))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(cfg.get("output_folder", DEFAULT_OUTPUT))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        layout.addSpacing(15)
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save)
        self.saved_lbl = QLabel("")
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.saved_lbl)
        save_row.addStretch()
        layout.addLayout(save_row)

        layout.addStretch()
        ver = QLabel(f"CV Tailor v{APP_VERSION}")
        ver.setStyleSheet("color:#8b949e;")
        layout.addWidget(ver)

    def _toggle_show(self, checked):
        """Toggle API key visibility."""
        self.key_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password)
        self.show_btn.setText("Hide" if checked else "Show")

    def _browse(self):
        """Pick output folder."""
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder",
                                             self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)

    def _save(self):
        """Save config to disk."""
        self.cfg["api_key"] = self.key_edit.text().strip()
        self.cfg["output_folder"] = self.folder_edit.text().strip() \
            or DEFAULT_OUTPUT
        save_config(self.cfg)
        os.makedirs(self.cfg["output_folder"], exist_ok=True)
        self.saved_lbl.setText("Saved ✓")
        self.saved_lbl.setStyleSheet(f"color:{GREEN};")
        self.config_changed.emit()


class ProfileTab(QWidget):
    """Build/merge master profile, view summary."""
    profile_changed = pyqtSignal()

    def __init__(self, get_client, get_profile, set_profile):
        """Build UI."""
        super().__init__()
        self.get_client = get_client
        self.get_profile = get_profile
        self.set_profile = set_profile
        self.files = []
        self.worker = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(15, 15, 15, 15)

        # LEFT
        left = QGroupBox("Build / Update Profile")
        lv = QVBoxLayout(left)
        pick = QPushButton("Add Files (PDF, DOCX, TXT)…")
        pick.clicked.connect(self._pick_files)
        lv.addWidget(pick)
        self.file_list = QListWidget()
        lv.addWidget(self.file_list)
        btn_row = QHBoxLayout()
        self.build_btn = QPushButton("Build New Profile")
        self.merge_btn = QPushButton("Merge Into Profile")
        self.build_btn.clicked.connect(lambda: self._run("new"))
        self.merge_btn.clicked.connect(lambda: self._run("merge"))
        btn_row.addWidget(self.build_btn)
        btn_row.addWidget(self.merge_btn)
        lv.addLayout(btn_row)
        self.progress = QProgressBar()
        lv.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        lv.addWidget(self.log)
        view_raw = QPushButton("View Raw JSON")
        view_raw.clicked.connect(self._view_raw)
        lv.addWidget(view_raw)

        # RIGHT
        right = QGroupBox("Current Profile Summary")
        rv = QVBoxLayout(right)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        rv.addWidget(self.summary)
        clear = QPushButton("Clear Profile")
        clear.clicked.connect(self._clear)
        rv.addWidget(clear)

        outer.addWidget(left, 1)
        outer.addWidget(right, 1)
        self.refresh_summary()

    def _pick_files(self):
        """Add files to the queue."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select CV Documents", "",
            "Documents (*.pdf *.docx *.txt)")
        for f in files:
            if f not in self.files:
                self.files.append(f)
                item = QListWidgetItem(os.path.basename(f))
                item.setData(Qt.UserRole, f)
                self.file_list.addItem(item)

    def _run(self, mode):
        """Kick off build/merge worker."""
        client = self.get_client()
        if not client:
            QMessageBox.warning(self, "No API Key",
                                "Set your API key in Settings first.")
            return
        if not self.files:
            QMessageBox.warning(self, "No Files", "Add at least one file.")
            return
        self.build_btn.setEnabled(False)
        self.merge_btn.setEnabled(False)
        self.log.append(f"\n— {mode.upper()} —")
        self.progress.setValue(0)
        existing = self.get_profile() if mode == "merge" else None
        self.worker = ProfileBuildWorker(client, self.files, mode, existing)
        self.worker.status.connect(lambda s: self.log.append(s))
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_done(self, profile):
        """Persist profile and update UI."""
        save_profile(profile)
        self.set_profile(profile)
        roles = len(profile.get("experience") or [])
        projs = len(profile.get("projects") or [])
        skills = sum(len(profile.get("skills", {}).get(k, []))
                     for k, _ in SKILL_CATEGORIES)
        self.log.append(f"Done — {roles} roles, {skills} skills, "
                        f"{projs} projects.")
        self.build_btn.setEnabled(True)
        self.merge_btn.setEnabled(True)
        self.refresh_summary()
        self.profile_changed.emit()

    def _on_error(self, msg):
        """Show error in log."""
        self.log.append(f"ERROR: {msg}")
        self.build_btn.setEnabled(True)
        self.merge_btn.setEnabled(True)

    def _view_raw(self):
        """Open master_profile.json in Notepad."""
        if os.path.exists(PROFILE_FILE):
            subprocess.Popen(["notepad.exe", PROFILE_FILE])
        else:
            QMessageBox.information(self, "No Profile",
                                    "No profile file yet.")

    def _clear(self):
        """Clear profile after confirmation."""
        r = QMessageBox.question(self, "Clear Profile",
                                 "Delete the master profile?")
        if r == QMessageBox.Yes:
            if os.path.exists(PROFILE_FILE):
                os.remove(PROFILE_FILE)
            self.set_profile(None)
            self.refresh_summary()
            self.profile_changed.emit()

    def refresh_summary(self):
        """Refresh the right-hand summary panel."""
        p = self.get_profile()
        if not p:
            self.summary.setPlainText("No profile loaded.")
            return
        contact = p.get("contact", {}) or {}
        lines = [f"Name: {p.get('name', '')}",
                 f"Email: {contact.get('email', '')}",
                 f"Phone: {contact.get('phone', '')}",
                 f"LinkedIn: {contact.get('linkedin', '')}",
                 f"GitHub: {contact.get('github', '')}", ""]
        roles = p.get("experience") or []
        lines.append(f"Roles ({len(roles)}):")
        for r in roles:
            lines.append(f"  • {r.get('title', '')} @ {r.get('company', '')}")
        projs = p.get("projects") or []
        lines.append(f"\nProjects ({len(projs)}):")
        for pr in projs:
            lines.append(f"  • {pr.get('name', '')}")
        lines.append("\nSkills:")
        for k, label in SKILL_CATEGORIES:
            vals = p.get("skills", {}).get(k) or []
            if vals:
                lines.append(f"  {label}: {', '.join(vals)}")
        self.summary.setPlainText("\n".join(lines))


class SingleJobTab(QWidget):
    """Paste one JD, assess, generate CV."""

    def __init__(self, get_client, get_profile, get_output):
        """Build UI."""
        super().__init__()
        self.get_client = get_client
        self.get_profile = get_profile
        self.get_output = get_output
        self.fit_worker = None
        self.cv_worker = None
        self.output_path = None
        self.pending_red = None

        v = QVBoxLayout(self)
        v.setContentsMargins(15, 15, 15, 15)
        form = QFormLayout()
        self.company = QLineEdit()
        self.title = QLineEdit()
        form.addRow("Company:", self.company)
        form.addRow("Job Title:", self.title)
        v.addLayout(form)

        v.addWidget(QLabel("Paste the full job description here:"))
        self.jd = QTextEdit()
        self.jd.textChanged.connect(self._update_state)
        v.addWidget(self.jd)
        self.charlbl = QLabel("0 characters")
        v.addWidget(self.charlbl)

        self.company.textChanged.connect(self._update_state)
        self.title.textChanged.connect(self._update_state)

        self.go_btn = QPushButton("Assess & Generate CV")
        self.go_btn.clicked.connect(self._start)
        v.addWidget(self.go_btn)

        self.phase_lbl = QLabel("")
        v.addWidget(self.phase_lbl)
        self.progress = QProgressBar()
        v.addWidget(self.progress)

        self.fit_box = QLabel("")
        self.fit_box.setWordWrap(True)
        self.fit_box.setVisible(False)
        v.addWidget(self.fit_box)

        self.red_row = QWidget()
        rh = QHBoxLayout(self.red_row)
        self.anyway_btn = QPushButton("Generate Anyway")
        self.skip_btn = QPushButton("Skip This Job")
        self.anyway_btn.clicked.connect(self._red_generate)
        self.skip_btn.clicked.connect(self._red_skip)
        rh.addWidget(self.anyway_btn)
        rh.addWidget(self.skip_btn)
        rh.addStretch()
        self.red_row.setVisible(False)
        v.addWidget(self.red_row)

        self.file_lbl = QLabel("")
        v.addWidget(self.file_lbl)
        file_row = QHBoxLayout()
        self.open_file_btn = QPushButton("Open File")
        self.open_folder_btn = QPushButton("Open Output Folder")
        self.open_file_btn.clicked.connect(
            lambda: self.output_path and open_file_native(self.output_path))
        self.open_folder_btn.clicked.connect(
            lambda: open_file_native(self.get_output()))
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        file_row.addWidget(self.open_file_btn)
        file_row.addWidget(self.open_folder_btn)
        file_row.addStretch()
        v.addLayout(file_row)

        self.gap_banner = QLabel("")
        self.gap_banner.setWordWrap(True)
        self.gap_banner.setVisible(False)
        v.addWidget(self.gap_banner)

        self._update_state()

    def _update_state(self):
        """Enable Go button only if all fields filled."""
        self.charlbl.setText(f"{len(self.jd.toPlainText())} characters")
        ok = (self.company.text().strip() and self.title.text().strip()
              and self.jd.toPlainText().strip())
        self.go_btn.setEnabled(bool(ok))

    def _start(self):
        """Kick off fit assessment."""
        client = self.get_client()
        profile = self.get_profile()
        if not client:
            QMessageBox.warning(self, "No API Key", "Set your API key.")
            return
        if not profile:
            QMessageBox.warning(self, "No Profile",
                                "Build your master profile first.")
            return
        self.fit_box.setVisible(False)
        self.red_row.setVisible(False)
        self.file_lbl.setText("")
        self.gap_banner.setVisible(False)
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        self.go_btn.setEnabled(False)
        self.phase_lbl.setText("Assessing fit…")
        self.progress.setRange(0, 0)
        self.fit_worker = FitWorker(client, profile,
                                    self.jd.toPlainText())
        self.fit_worker.result.connect(self._on_fit)
        self.fit_worker.error.connect(self._on_error)
        self.fit_worker.start()

    def _on_fit(self, data):
        """Handle fit result."""
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        fit = data.get("fit", "yellow").lower()
        summary = data.get("summary", "")
        gaps = data.get("gaps", []) or []
        hard = data.get("hard_gaps", []) or []
        if fit == "green":
            self._show_fit(GREEN,
                           f"Strong fit — generating your CV\n{summary}")
            self._start_cv()
        elif fit == "yellow":
            g = "; ".join(gaps) if gaps else "minor"
            self._show_fit(YELLOW,
                           f"Partial fit — {g} — generating anyway\n"
                           f"{summary}")
            self._start_cv()
        else:
            reason = summary + ("\nHard gaps: " + "; ".join(hard)
                                if hard else "")
            self._show_fit(RED, f"Poor fit — {reason}")
            self.red_row.setVisible(True)
            self.phase_lbl.setText("Waiting for your decision…")
            self.pending_red = True

    def _show_fit(self, color, text):
        """Display the fit box."""
        self.fit_box.setText(text)
        self.fit_box.setStyleSheet(
            f"background:{color};color:white;padding:10px;border-radius:4px;")
        self.fit_box.setVisible(True)

    def _red_generate(self):
        """User overrode RED."""
        self.red_row.setVisible(False)
        self._start_cv()

    def _red_skip(self):
        """User skipped RED."""
        self.red_row.setVisible(False)
        self.phase_lbl.setText("Skipped.")
        self.progress.setValue(0)
        self.go_btn.setEnabled(True)

    def _start_cv(self):
        """Kick off CV generation."""
        client = self.get_client()
        profile = self.get_profile()
        self.phase_lbl.setText("Generating CV…")
        self.progress.setValue(0)
        self.cv_worker = CVWorker(client, profile, self.company.text(),
                                  self.title.text(), self.jd.toPlainText())
        self.cv_worker.progress.connect(self.progress.setValue)
        self.cv_worker.result.connect(self._on_cv)
        self.cv_worker.error.connect(self._on_error)
        self.cv_worker.start()

    def _on_cv(self, cv_data, hard_gap):
        """Write DOCX and show result."""
        try:
            profile = self.get_profile()
            self.output_path = build_output_path(self.get_output(),
                                                 self.company.text(),
                                                 self.title.text())
            DocxBuilder.build(profile, cv_data, self.output_path)
            self.phase_lbl.setText("Done.")
            self.file_lbl.setText(
                f"Generated: {os.path.basename(self.output_path)}")
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
            if hard_gap:
                self.gap_banner.setText(f"⚠ Hard gap: {hard_gap}")
                self.gap_banner.setStyleSheet(
                    f"background:{YELLOW};color:white;padding:8px;"
                    "border-radius:4px;")
                self.gap_banner.setVisible(True)
        except Exception as e:
            self._on_error(f"DOCX build failed: {e}")
        self.go_btn.setEnabled(True)

    def _on_error(self, msg):
        """Show error state."""
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.phase_lbl.setText(f"Error: {msg}")
        self.go_btn.setEnabled(True)


# ─── Bulk Tab ────────────────────────────────────────────────────────────

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
    """Sequentially assess+generate a list of jobs, with RED pause support."""
    row_update = pyqtSignal(int, str, str)  # row, column_name, value
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
        self.results = []  # dicts per row for CSV

    def stop(self):
        """Request stop after current job."""
        self._stop = True
        self._decision_event.set()

    def submit_decision(self, decision):
        """Called from GUI with 'generate' or 'skip'."""
        self._decision = decision
        self._decision_event.set()

    def run(self):
        """Main loop."""
        for i, (company, title, jd) in enumerate(self.jobs):
            if self._stop:
                break
            row_result = {"Company": company, "Title": title,
                          "Fit": "", "Fit Score": "", "Fit Summary": "",
                          "Strengths": "", "Gaps": "", "Hard Gaps": "",
                          "Status": "", "Gap Note": "", "Filename": "",
                          "Date": datetime.now().strftime("%Y-%m-%d")}
            self.row_update.emit(i, "Status", "Assessing")
            fit = self._assess(jd)
            if not fit:
                self.row_update.emit(i, "Status", "✗ Error")
                row_result["Status"] = "Error"
                self.results.append(row_result)
                continue
            level = fit.get("fit", "yellow").lower()
            icon = {"green": "🟢 Strong", "yellow": "🟡 Partial",
                    "red": "🔴 Poor"}.get(level, "🟡 Partial")
            self.row_update.emit(i, "Fit", icon)
            row_result["Fit"] = icon
            row_result["Fit Score"] = str(fit.get("score", ""))
            row_result["Fit Summary"] = fit.get("summary", "")
            row_result["Strengths"] = "; ".join(fit.get("strengths", []))
            row_result["Gaps"] = "; ".join(fit.get("gaps", []))
            row_result["Hard Gaps"] = "; ".join(fit.get("hard_gaps", []))

            proceed = True
            if level == "red":
                self.row_update.emit(
                    i, "Status", "⚠ Poor Fit — waiting...")
                self._decision_event.clear()
                self._decision = None
                self.waiting_for_decision.emit(
                    i, fit.get("summary", ""), fit.get("hard_gaps", []))
                self._decision_event.wait()
                if self._stop:
                    break
                proceed = (self._decision == "generate")
                if not proceed:
                    self.row_update.emit(i, "Status", "✗ Skipped")
                    row_result["Status"] = "Skipped"
                    self.results.append(row_result)
                    time.sleep(BULK_DELAY_SEC)
                    continue

            self.row_update.emit(i, "Status", "Generating")
            cv, hard_gap = self._generate(company, title, jd)
            if cv is None:
                self.row_update.emit(i, "Status", "✗ Error")
                row_result["Status"] = "Error"
                self.results.append(row_result)
                time.sleep(BULK_DELAY_SEC)
                continue
            try:
                path = build_output_path(self.output, company, title)
                DocxBuilder.build(self.profile, cv, path)
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
            time.sleep(BULK_DELAY_SEC)
        self.done.emit()

    def _assess(self, jd):
        """Synchronous fit call."""
        system = (
            "You are a recruitment expert. Return JSON: "
            "{\"fit\":\"green|yellow|red\",\"score\":0-100,"
            "\"summary\":\"\",\"strengths\":[],\"gaps\":[],"
            "\"hard_gaps\":[]}. GREEN 70-100, YELLOW 40-69, RED 0-39. "
            "Be honest. Return ONLY JSON.")
        user = (f"CANDIDATE PROFILE:\n{json.dumps(self.profile)}"
                f"\n\nJOB DESCRIPTION:\n{jd}")
        try:
            msg = self.client.messages.create(
                model=MODEL_NAME, max_tokens=2000, system=system,
                messages=[{"role": "user", "content": user}])
            return parse_json_response(msg.content[0].text)
        except RateLimitError:
            time.sleep(RATE_LIMIT_RETRY_SEC)
            try:
                msg = self.client.messages.create(
                    model=MODEL_NAME, max_tokens=2000, system=system,
                    messages=[{"role": "user", "content": user}])
                return parse_json_response(msg.content[0].text)
            except Exception:
                return {"fit": "yellow", "score": 50,
                        "summary": "Rate-limited, defaulted",
                        "strengths": [], "gaps": [], "hard_gaps": []}
        except Exception:
            return None

    def _generate(self, company, title, jd):
        """Synchronous CV call."""
        system = (
            "Expert CV writer. SECTIONS: Summary, Experience, Projects "
            "(relevant), Technical Skills, Volunteering, Achievements, "
            "Education. Mirror JD language. Never invent. 2 pages. "
            "Output JSON matching master profile schema. Optional "
            "HARD_GAP line after JSON. No fences.")
        user = (f"COMPANY: {company}\nTITLE: {title}\nJD:\n{jd}"
                f"\n\nMASTER PROFILE:\n{json.dumps(self.profile)}")
        try:
            msg = self.client.messages.create(
                model=MODEL_NAME, max_tokens=MAX_TOKENS, system=system,
                messages=[{"role": "user", "content": user}])
            text = msg.content[0].text
            hard = ""
            m = re.search(r"HARD_GAP\s*:\s*(.+)", text)
            if m:
                hard = m.group(1).strip()
                text = text[:m.start()]
            return parse_json_response(text), hard
        except Exception:
            return None, ""


class BulkTab(QWidget):
    """Bulk-process many JDs at once."""

    COLS = ["#", "Company", "Title", "Fit", "Status", "Gap", "Filename"]

    def __init__(self, get_client, get_profile, get_output):
        """Build UI."""
        super().__init__()
        self.get_client = get_client
        self.get_profile = get_profile
        self.get_output = get_output
        self.runner = None
        self.pending_rows = {}  # row -> inline widget

        v = QVBoxLayout(self)
        v.setContentsMargins(15, 15, 15, 15)

        self.instructions = QTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.setMaximumHeight(140)
        self.instructions.setPlainText(
            "Format (separate jobs with ---):\n\n"
            "COMPANY: Google\nTITLE: Software Engineer\nJD:\n"
            "[full job description here]\n---\n"
            "COMPANY: Meta\nTITLE: Full Stack Developer\nJD:\n"
            "[full job description here]\n---")
        v.addWidget(self.instructions)

        self.input = QTextEdit()
        self.input.textChanged.connect(self._update_count)
        v.addWidget(self.input)

        self.count_lbl = QLabel("0 jobs detected")
        v.addWidget(self.count_lbl)

        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self.start_btn)
        ctrl.addWidget(self.stop_btn)
        ctrl.addStretch()
        v.addLayout(ctrl)

        self.progress = QProgressBar()
        v.addWidget(self.progress)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row)
        v.addWidget(self.table)

        self.summary_lbl = QLabel("")
        v.addWidget(self.summary_lbl)

        bot = QHBoxLayout()
        open_out = QPushButton("Open Output Folder")
        open_out.clicked.connect(
            lambda: open_file_native(self.get_output()))
        export = QPushButton("Export Status CSV")
        export.clicked.connect(self._export_csv)
        bot.addWidget(open_out)
        bot.addWidget(export)
        bot.addStretch()
        v.addLayout(bot)

    def _update_count(self):
        """Refresh detected job count."""
        n = len(parse_bulk_input(self.input.toPlainText()))
        self.count_lbl.setText(f"{n} jobs detected")

    def _start(self):
        """Begin bulk run."""
        client = self.get_client()
        profile = self.get_profile()
        if not client or not profile:
            QMessageBox.warning(self, "Missing",
                                "Set API key and build profile first.")
            return
        jobs = parse_bulk_input(self.input.toPlainText())
        if not jobs:
            QMessageBox.warning(self, "No Jobs", "No jobs parsed.")
            return
        self.table.setRowCount(0)
        for i, (c, t, _) in enumerate(jobs):
            self.table.insertRow(i)
            self._set(i, 0, str(i + 1))
            self._set(i, 1, c)
            self._set(i, 2, t)
            self._set(i, 3, "")
            self._set(i, 4, "Queued")
            self._set(i, 5, "")
            self._set(i, 6, "")
        self.progress.setMaximum(len(jobs))
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.runner = BulkRunner(client, profile, self.get_output(), jobs)
        self.runner.row_update.connect(self._on_row)
        self.runner.waiting_for_decision.connect(self._on_red)
        self.runner.done.connect(self._on_done)
        self.runner.start()

    def _stop(self):
        """Request stop."""
        if self.runner:
            self.runner.stop()
        self.stop_btn.setEnabled(False)

    def _set(self, row, col, text):
        """Set a cell by index."""
        item = QTableWidgetItem(text)
        self.table.setItem(row, col, item)

    def _col_index(self, name):
        """Map column name to index."""
        mapping = {"Status": 4, "Fit": 3, "Gap": 5, "Filename": 6}
        return mapping.get(name, 4)

    def _on_row(self, row, col_name, value):
        """Update a row cell."""
        col = self._col_index(col_name)
        item = self.table.item(row, col)
        if item:
            item.setText(value)
        if col_name == "Status":
            if value.startswith("✓"):
                self.progress.setValue(self.progress.value() + 1)
            elif value.startswith("✗"):
                self.progress.setValue(self.progress.value() + 1)
                if "Skipped" not in value:
                    self._highlight_row(row, "#3d1a1a")
            if "Poor Fit" in value:
                self._highlight_row(row, "#3d1a1a")

    def _highlight_row(self, row, color):
        """Paint an entire row."""
        for c in range(self.table.columnCount()):
            it = self.table.item(row, c)
            if it:
                it.setBackground(QColor(color))

    def _on_red(self, row, summary, hard_gaps):
        """Show inline Generate/Skip buttons in the row."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        gen = QPushButton("Generate Anyway")
        skp = QPushButton("Skip")
        gen.clicked.connect(lambda: self._decide(row, "generate"))
        skp.clicked.connect(lambda: self._decide(row, "skip"))
        h.addWidget(gen)
        h.addWidget(skp)
        self.table.setCellWidget(row, 4, w)
        self.pending_rows[row] = w

    def _decide(self, row, choice):
        """Deliver user's RED decision to the runner."""
        if row in self.pending_rows:
            self.table.removeCellWidget(row, 4)
            del self.pending_rows[row]
        if self.runner:
            self.runner.submit_decision(choice)

    def _on_done(self):
        """Finalise UI after runner completes."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        done = skipped = errors = gaps = 0
        for r in self.runner.results if self.runner else []:
            if r["Status"] == "Done":
                done += 1
            elif r["Status"] == "Skipped":
                skipped += 1
            elif r["Status"].startswith("Error"):
                errors += 1
            if r["Gap Note"]:
                gaps += 1
        self.summary_lbl.setText(
            f"{done} done · {skipped} skipped · {errors} errors · "
            f"{gaps} with gaps")

    def _open_row(self, row, _col):
        """Open the CV file when a Done row is double-clicked."""
        status_item = self.table.item(row, 4)
        fname_item = self.table.item(row, 6)
        if status_item and "Done" in status_item.text() and fname_item:
            path = os.path.join(self.get_output(), fname_item.text())
            if os.path.exists(path):
                open_file_native(path)

    def _export_csv(self):
        """Export results to CSV."""
        if not self.runner or not self.runner.results:
            QMessageBox.information(self, "No Data", "Nothing to export.")
            return
        date = datetime.now().strftime("%Y-%m-%d")
        default = os.path.join(self.get_output(),
                               f"cv_tailor_status_{date}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default,
                                              "CSV (*.csv)")
        if not path:
            return
        cols = ["Date", "Company", "Title", "Fit", "Fit Score",
                "Fit Summary", "Strengths", "Gaps", "Hard Gaps",
                "Status", "Gap Note", "Filename"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in self.runner.results:
                w.writerow({c: r.get(c, "") for c in cols})
        QMessageBox.information(self, "Exported", f"Saved to {path}")


# ─── MainWindow ──────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Top-level window holding all tabs."""

    def __init__(self):
        """Build UI."""
        super().__init__()
        self.setWindowTitle("CV Tailor")
        self.resize(1150, 800)
        self.cfg = load_config()
        self.profile = load_profile()
        os.makedirs(self.cfg.get("output_folder", DEFAULT_OUTPUT),
                    exist_ok=True)
        self._client = None
        self._build_ui()
        self._apply_theme()
        self._refresh_banner()

    def _build_ui(self):
        """Construct tabs."""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            f"background:{RED};color:white;padding:8px;")
        self.banner.setVisible(False)
        v.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.settings_tab = SettingsTab(self.cfg)
        self.settings_tab.config_changed.connect(self._on_config)

        self.profile_tab = ProfileTab(
            self._get_client, lambda: self.profile, self._set_profile)
        self.profile_tab.profile_changed.connect(self._refresh_banner)

        self.single_tab = SingleJobTab(
            self._get_client, lambda: self.profile,
            lambda: self.cfg.get("output_folder", DEFAULT_OUTPUT))
        self.bulk_tab = BulkTab(
            self._get_client, lambda: self.profile,
            lambda: self.cfg.get("output_folder", DEFAULT_OUTPUT))

        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.profile_tab, "Profile")
        self.tabs.addTab(self.single_tab, "Single Job")
        self.tabs.addTab(self.bulk_tab, "Bulk Jobs")
        v.addWidget(self.tabs)
        self.setCentralWidget(container)

    def _get_client(self):
        """Return or create the Anthropic client."""
        key = self.cfg.get("api_key", "").strip()
        if not key:
            return None
        if self._client is None:
            try:
                self._client = Anthropic(api_key=key)
            except Exception:
                return None
        return self._client

    def _set_profile(self, profile):
        """Update profile reference."""
        self.profile = profile

    def _on_config(self):
        """Re-create client after settings change."""
        self._client = None
        self._refresh_banner()

    def _refresh_banner(self):
        """Show red banner if API key missing."""
        if not self.cfg.get("api_key", "").strip():
            self.banner.setText(
                "⚠ No API key set — add one in Settings to enable "
                "CV generation.")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

    def _apply_theme(self):
        """Apply dark theme stylesheet."""
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{BG}; color:{FG}; }}
            QTabWidget::pane {{ border:1px solid {BORDER}; }}
            QTabBar::tab {{
                background:{PANEL}; color:{FG};
                padding:8px 20px; border:1px solid {BORDER};
            }}
            QTabBar::tab:selected {{ background:{BG}; border-bottom:none; }}
            QLineEdit, QTextEdit, QListWidget, QTableWidget, QComboBox {{
                background:{PANEL}; color:{FG}; border:1px solid {BORDER};
                padding:4px; selection-background-color:{ACCENT};
            }}
            QPushButton {{
                background:{PANEL}; color:{FG}; border:1px solid {BORDER};
                padding:6px 14px; border-radius:3px;
            }}
            QPushButton:hover {{ background:#21262d; }}
            QPushButton:disabled {{ color:#6e7681; }}
            QGroupBox {{
                border:1px solid {BORDER}; margin-top:8px; padding-top:8px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; left:10px; padding:0 4px;
            }}
            QProgressBar {{
                background:{PANEL}; border:1px solid {BORDER};
                text-align:center; color:{FG};
            }}
            QProgressBar::chunk {{ background:{ACCENT}; }}
            QHeaderView::section {{
                background:{PANEL}; color:{FG}; padding:4px;
                border:1px solid {BORDER};
            }}
            QLabel {{ color:{FG}; }}
        """)


def main():
    """Entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

"""Single-job tab — paste one JD, assess + generate in one call."""
import os

from PyQt5.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QProgressBar, QPushButton,
                             QVBoxLayout, QWidget)

from ..constants import GREEN, RED, YELLOW
from ..docx_builder import DocxBuilder
from ..tracker import find_existing_application, write_tracker_row
from ..utils import build_output_path, open_file_native
from ..workers import UnifiedWorker
from .widgets import PlainTextEdit


class SingleJobTab(QWidget):
    """Paste one JD, assess + generate in a single call."""

    def __init__(self, get_client, get_profile, get_output):
        """Build UI."""
        super().__init__()
        self.get_client = get_client
        self.get_profile = get_profile
        self.get_output = get_output
        self.worker = None
        self.output_path = None
        self._cached = None  # (fit, cv, hard_gap) pending RED decision

        v = QVBoxLayout(self)
        v.setContentsMargins(15, 15, 15, 15)
        form = QFormLayout()
        self.company = QLineEdit()
        self.title = QLineEdit()
        form.addRow("Company:", self.company)
        form.addRow("Job Title:", self.title)
        v.addLayout(form)

        v.addWidget(QLabel("Paste the full job description here:"))
        self.jd = PlainTextEdit()
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
        """Kick off unified assess+generate call."""
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
        self.phase_lbl.setText("Assessing fit & drafting CV…")
        self.progress.setValue(0)
        self.worker = UnifiedWorker(client, profile, self.company.text(),
                                    self.title.text(), self.jd.toPlainText())
        self.worker.progress.connect(self.progress.setValue)
        self.worker.result.connect(self._on_result)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_result(self, fit, cv, hard_gap):
        """Handle unified result: render fit + gate on RED."""
        level = (fit.get("fit") or "yellow").lower()
        summary = fit.get("summary", "")
        gaps = fit.get("gaps", []) or []
        hard = fit.get("hard_gaps", []) or []
        self._cached = (fit, cv, hard_gap)

        if level == "green":
            self._show_fit(GREEN, f"Strong fit — generating your CV\n{summary}")
            self._write_cv()
        elif level == "yellow":
            g = "; ".join(gaps) if gaps else "minor"
            self._show_fit(YELLOW,
                           f"Partial fit — {g} — generating anyway\n{summary}")
            self._write_cv()
        else:
            reason = summary + ("\nHard gaps: " + "; ".join(hard)
                                if hard else "")
            self._show_fit(RED, f"Poor fit — {reason}")
            self.red_row.setVisible(True)
            self.phase_lbl.setText("Waiting for your decision…")

    def _show_fit(self, color, text):
        """Display the fit box."""
        self.fit_box.setText(text)
        self.fit_box.setStyleSheet(
            f"background:{color};color:white;padding:10px;border-radius:4px;")
        self.fit_box.setVisible(True)

    def _red_generate(self):
        """User overrode RED — write CV from cache."""
        self.red_row.setVisible(False)
        self._write_cv()

    def _red_skip(self):
        """User skipped RED."""
        self.red_row.setVisible(False)
        self.phase_lbl.setText("Skipped.")
        self._cached = None
        self.go_btn.setEnabled(True)

    def _write_cv(self):
        """Write cached CV data to DOCX."""
        if not self._cached:
            self.go_btn.setEnabled(True)
            return
        fit, cv, hard_gap = self._cached
        try:
            profile = self.get_profile()
            self.output_path = build_output_path(self.get_output(),
                                                 self.company.text(),
                                                 self.title.text())
            DocxBuilder.build(profile, cv, self.output_path)
            self.phase_lbl.setText("Done.")
            self.file_lbl.setText(
                f"Generated: {os.path.basename(self.output_path)}")
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
            self._record_to_tracker(fit, hard_gap)
            if hard_gap:
                self.gap_banner.setText(f"⚠ Hard gap: {hard_gap}")
                self.gap_banner.setStyleSheet(
                    f"background:{YELLOW};color:white;padding:8px;"
                    "border-radius:4px;")
                self.gap_banner.setVisible(True)
        except Exception as e:
            self._on_error(f"DOCX build failed: {e}")
        self.go_btn.setEnabled(True)

    def _record_to_tracker(self, fit, hard_gap):
        """Append a row to job_applications.xlsx with duplicate prompt."""
        company = self.company.text().strip()
        role = self.title.text().strip()
        output = self.get_output()
        existing = find_existing_application(output, company, role)
        if existing:
            _, _, prev_date = existing
            answer = QMessageBox.question(
                self, "Possible Duplicate",
                f"You may have already applied to this role.\n"
                f"{company} — {role} was applied to on {prev_date}.\n\n"
                f"Add another entry anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        try:
            write_tracker_row(output, {
                "company": company,
                "role": role,
                "fit": (fit or {}).get("fit", ""),
                "fit_score": (fit or {}).get("score", ""),
                "fit_summary": (fit or {}).get("summary", ""),
                "hard_gap": hard_gap or "",
                "cv_filename": os.path.basename(self.output_path),
            })
            if hasattr(self, "tracker_updated") and self.tracker_updated:
                self.tracker_updated()
        except Exception as e:
            print(f"[tracker] write failed: {e}")

    def _on_error(self, msg):
        """Show error state."""
        self.progress.setValue(0)
        self.phase_lbl.setText(f"Error: {msg}")
        self.go_btn.setEnabled(True)

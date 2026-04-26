"""Profile tab — build/merge master profile, view summary."""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QProgressBar, QPushButton, QTextEdit,
                             QVBoxLayout, QWidget)

from ..config import save_profile
from ..constants import PROFILE_FILE, SKILL_CATEGORIES
from ..utils import open_file_native
from ..workers import ProfileBuildWorker
from .profile_editor import ProfileEditorDialog


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
        edit_btn = QPushButton("Edit Profile…")
        edit_btn.clicked.connect(self._edit_profile)
        lv.addWidget(edit_btn)
        view_raw = QPushButton("Open Raw JSON in External Editor")
        view_raw.clicked.connect(self._view_raw)
        lv.addWidget(view_raw)

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
        """Open master_profile.json with the OS default editor."""
        if os.path.exists(PROFILE_FILE):
            open_file_native(PROFILE_FILE)
        else:
            QMessageBox.information(self, "No Profile", "No profile yet.")

    def _edit_profile(self):
        """Open the structured profile editor dialog."""
        profile = self.get_profile()
        if not profile:
            QMessageBox.information(self, "No Profile",
                                    "Build your master profile first.")
            return
        dlg = ProfileEditorDialog(profile, self)
        if dlg.exec_() == dlg.Accepted:
            updated = dlg.result_profile()
            save_profile(updated)
            self.set_profile(updated)
            self.refresh_summary()
            self.profile_changed.emit()

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

"""Structured editor for master_profile.json.

Tabs:
  Personal    — name, summary, contact fields
  Experience  — list of roles with form below
  Projects    — list of projects with form below
  Skills      — comma-separated values per category
  Education   — list of degrees with form below
  Volunteering— list of roles with form below
  Achievements— one bullet per line
  Raw JSON    — full text editor with Apply (validates JSON)

Save commits all tabs back into the profile dict.
"""
import copy
import json

from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPushButton,
                             QSplitter, QTabWidget, QTextEdit, QVBoxLayout,
                             QWidget)

from ..constants import SKILL_LABELS

# ─── Field schemas for the four list-of-dicts sections ─────────────────────

EXPERIENCE_FIELDS = [
    ("title", "Title", "line"),
    ("company", "Company", "line"),
    ("location", "Location", "line"),
    ("start_date", "Start Date", "line"),
    ("end_date", "End Date", "line"),
    ("responsibilities", "Responsibilities (one per line)", "lines"),
]

PROJECT_FIELDS = [
    ("name", "Name", "line"),
    ("description", "Description", "multiline"),
    ("technologies", "Technologies (comma-separated)", "csv"),
    ("link", "Link", "line"),
    ("highlights", "Highlights (one per line)", "lines"),
]

EDUCATION_FIELDS = [
    ("degree", "Degree", "line"),
    ("institution", "Institution", "line"),
    ("location", "Location", "line"),
    ("start_date", "Start Date", "line"),
    ("end_date", "End Date", "line"),
    ("details", "Details", "multiline"),
]

VOLUNTEERING_FIELDS = [
    ("role", "Role", "line"),
    ("organization", "Organization", "line"),
    ("start_date", "Start Date", "line"),
    ("end_date", "End Date", "line"),
    ("description", "Description", "multiline"),
]

DISPLAY_KEYS = {
    "experience": "title",
    "projects": "name",
    "education": "degree",
    "volunteering": "role",
}


class EntryListEditor(QWidget):
    """Generic editor for a list of dicts: list on left, form on right."""

    def __init__(self, entries, fields, display_key):
        super().__init__()
        self.fields = fields
        self.display_key = display_key
        self.entries = [dict(e) for e in (entries or []) if isinstance(e, dict)]
        self._current = -1

        outer = QVBoxLayout(self)
        split = QSplitter()
        outer.addWidget(split)

        # Left: list + add/remove/move
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        lv.addWidget(self.list)
        btn_row = QHBoxLayout()
        for label, slot in (("Add", self._add), ("Remove", self._remove),
                            ("↑", self._up), ("↓", self._down)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        lv.addLayout(btn_row)
        split.addWidget(left)

        # Right: form
        right = QWidget()
        self.form_layout = QFormLayout(right)
        self.field_widgets = {}
        for key, label, kind in fields:
            if kind == "line":
                w = QLineEdit()
                w.editingFinished.connect(self._commit_current)
            elif kind == "multiline":
                w = QTextEdit()
                w.textChanged.connect(self._mark_dirty)
            elif kind == "csv":
                w = QLineEdit()
                w.editingFinished.connect(self._commit_current)
            elif kind == "lines":
                w = QTextEdit()
                w.textChanged.connect(self._mark_dirty)
            else:
                w = QLineEdit()
            self.field_widgets[key] = (w, kind)
            self.form_layout.addRow(label, w)
        split.addWidget(right)
        split.setSizes([220, 480])

        self._refresh_list()

    def _label_for(self, entry):
        return (entry.get(self.display_key) or "(untitled)").strip() \
            or "(untitled)"

    def _refresh_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.entries:
            self.list.addItem(QListWidgetItem(self._label_for(e)))
        self.list.blockSignals(False)
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self._current = -1
            self._populate_form({})

    def _on_select(self, row):
        # commit any pending edits to previous entry first
        self._commit_current()
        self._current = row
        if 0 <= row < len(self.entries):
            self._populate_form(self.entries[row])
        else:
            self._populate_form({})

    def _populate_form(self, entry):
        for key, (w, kind) in self.field_widgets.items():
            val = entry.get(key, "")
            if kind == "line":
                w.setText(str(val or ""))
            elif kind == "multiline":
                w.blockSignals(True)
                w.setPlainText(str(val or ""))
                w.blockSignals(False)
            elif kind == "csv":
                if isinstance(val, list):
                    w.setText(", ".join(str(x) for x in val))
                else:
                    w.setText(str(val or ""))
            elif kind == "lines":
                w.blockSignals(True)
                if isinstance(val, list):
                    w.setPlainText("\n".join(str(x) for x in val))
                else:
                    w.setPlainText(str(val or ""))
                w.blockSignals(False)

    def _read_form(self):
        out = {}
        for key, (w, kind) in self.field_widgets.items():
            if kind == "line":
                out[key] = w.text().strip()
            elif kind == "multiline":
                out[key] = w.toPlainText().strip()
            elif kind == "csv":
                parts = [p.strip() for p in w.text().split(",")]
                out[key] = [p for p in parts if p]
            elif kind == "lines":
                lines = [l.strip() for l in w.toPlainText().split("\n")]
                out[key] = [l for l in lines if l]
        return out

    def _mark_dirty(self):
        # Multi-line widgets need explicit commit on text change.
        if 0 <= self._current < len(self.entries):
            self.entries[self._current] = self._read_form()
            new_label = self._label_for(self.entries[self._current])
            it = self.list.item(self._current)
            if it and it.text() != new_label:
                it.setText(new_label)

    def _commit_current(self):
        if 0 <= self._current < len(self.entries):
            self.entries[self._current] = self._read_form()
            new_label = self._label_for(self.entries[self._current])
            it = self.list.item(self._current)
            if it and it.text() != new_label:
                it.setText(new_label)

    def _add(self):
        self._commit_current()
        new = {k: ("" if kind != "csv" and kind != "lines" else [])
               for k, _, kind in self.fields}
        self.entries.append(new)
        self._refresh_list()
        self.list.setCurrentRow(len(self.entries) - 1)

    def _remove(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.entries):
            self.entries.pop(row)
            self._current = -1
            self._refresh_list()

    def _up(self):
        row = self.list.currentRow()
        if row > 0:
            self._commit_current()
            self.entries[row - 1], self.entries[row] = \
                self.entries[row], self.entries[row - 1]
            self._refresh_list()
            self.list.setCurrentRow(row - 1)

    def _down(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.entries) - 1:
            self._commit_current()
            self.entries[row + 1], self.entries[row] = \
                self.entries[row], self.entries[row + 1]
            self._refresh_list()
            self.list.setCurrentRow(row + 1)

    def collect(self):
        """Return current entries list."""
        self._commit_current()
        return [e for e in self.entries if any(v for v in e.values())]


class ProfileEditorDialog(QDialog):
    """Edit a profile dict in a tabbed UI. Returns the updated dict on accept."""

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Profile")
        self.resize(900, 650)
        self._profile = copy.deepcopy(profile or {})
        self._result = None

        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs)

        self._build_personal_tab()
        self.exp_editor = EntryListEditor(
            self._profile.get("experience"), EXPERIENCE_FIELDS,
            DISPLAY_KEYS["experience"])
        self.tabs.addTab(self.exp_editor, "Experience")
        self.proj_editor = EntryListEditor(
            self._profile.get("projects"), PROJECT_FIELDS,
            DISPLAY_KEYS["projects"])
        self.tabs.addTab(self.proj_editor, "Projects")
        self._build_skills_tab()
        self.edu_editor = EntryListEditor(
            self._profile.get("education"), EDUCATION_FIELDS,
            DISPLAY_KEYS["education"])
        self.tabs.addTab(self.edu_editor, "Education")
        self.vol_editor = EntryListEditor(
            self._profile.get("volunteering"), VOLUNTEERING_FIELDS,
            DISPLAY_KEYS["volunteering"])
        self.tabs.addTab(self.vol_editor, "Volunteering")
        self._build_achievements_tab()
        self._build_raw_tab()

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    # ─── Tab builders ──────────────────────────────────────────────────────

    def _build_personal_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        contact = self._profile.get("contact") or {}
        self.name_edit = QLineEdit(self._profile.get("name", "") or "")
        self.summary_edit = QTextEdit()
        self.summary_edit.setPlainText(self._profile.get("summary", "") or "")
        self.summary_edit.setMaximumHeight(120)
        self.email_edit = QLineEdit(contact.get("email", "") or "")
        self.phone_edit = QLineEdit(contact.get("phone", "") or "")
        self.linkedin_edit = QLineEdit(contact.get("linkedin", "") or "")
        self.github_edit = QLineEdit(contact.get("github", "") or "")
        self.website_edit = QLineEdit(contact.get("website", "") or "")
        form.addRow("Name", self.name_edit)
        form.addRow("Summary", self.summary_edit)
        form.addRow("Email", self.email_edit)
        form.addRow("Phone", self.phone_edit)
        form.addRow("LinkedIn", self.linkedin_edit)
        form.addRow("GitHub", self.github_edit)
        form.addRow("Website", self.website_edit)
        self.tabs.addTab(w, "Personal")

    def _build_skills_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        skills = self._profile.get("skills") or {}
        self.skill_edits = {}
        # Show every label even if empty so the user can add.
        for key, label in SKILL_LABELS.items():
            edit = QLineEdit(", ".join(skills.get(key, []) or []))
            self.skill_edits[key] = edit
            form.addRow(label, edit)
        # Plus any non-standard keys present in the profile
        for key in skills:
            if key not in self.skill_edits:
                edit = QLineEdit(", ".join(skills.get(key, []) or []))
                self.skill_edits[key] = edit
                form.addRow(key, edit)
        self.tabs.addTab(w, "Skills")

    def _build_achievements_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("One achievement per line:"))
        self.ach_edit = QTextEdit()
        self.ach_edit.setPlainText(
            "\n".join(self._profile.get("achievements") or []))
        v.addWidget(self.ach_edit)
        self.tabs.addTab(w, "Achievements")

    def _build_raw_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Raw profile JSON. Click Apply to load these contents into the "
            "other tabs (overwrites unsaved changes there)."))
        self.raw_edit = QTextEdit()
        self.raw_edit.setPlainText(
            json.dumps(self._profile, indent=2, ensure_ascii=False))
        v.addWidget(self.raw_edit)
        apply_btn = QPushButton("Apply Raw JSON to Tabs")
        apply_btn.clicked.connect(self._apply_raw)
        v.addWidget(apply_btn)
        self.tabs.addTab(w, "Raw JSON")

    # ─── Save / apply ──────────────────────────────────────────────────────

    def _apply_raw(self):
        try:
            data = json.loads(self.raw_edit.toPlainText())
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Parse error: {e}")
            return
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid JSON",
                                "Top-level must be a JSON object.")
            return
        self._profile = data
        # Rebuild all tabs by re-creating the dialog's contents in place.
        self.tabs.clear()
        self._build_personal_tab()
        self.exp_editor = EntryListEditor(
            self._profile.get("experience"), EXPERIENCE_FIELDS,
            DISPLAY_KEYS["experience"])
        self.tabs.addTab(self.exp_editor, "Experience")
        self.proj_editor = EntryListEditor(
            self._profile.get("projects"), PROJECT_FIELDS,
            DISPLAY_KEYS["projects"])
        self.tabs.addTab(self.proj_editor, "Projects")
        self._build_skills_tab()
        self.edu_editor = EntryListEditor(
            self._profile.get("education"), EDUCATION_FIELDS,
            DISPLAY_KEYS["education"])
        self.tabs.addTab(self.edu_editor, "Education")
        self.vol_editor = EntryListEditor(
            self._profile.get("volunteering"), VOLUNTEERING_FIELDS,
            DISPLAY_KEYS["volunteering"])
        self.tabs.addTab(self.vol_editor, "Volunteering")
        self._build_achievements_tab()
        self._build_raw_tab()

    def _collect(self):
        out = copy.deepcopy(self._profile)
        out["name"] = self.name_edit.text().strip()
        out["summary"] = self.summary_edit.toPlainText().strip()
        contact = out.get("contact") or {}
        contact["email"] = self.email_edit.text().strip()
        contact["phone"] = self.phone_edit.text().strip()
        contact["linkedin"] = self.linkedin_edit.text().strip()
        contact["github"] = self.github_edit.text().strip()
        contact["website"] = self.website_edit.text().strip()
        out["contact"] = contact

        out["experience"] = self.exp_editor.collect()
        out["projects"] = self.proj_editor.collect()
        out["education"] = self.edu_editor.collect()
        out["volunteering"] = self.vol_editor.collect()

        skills = {}
        for key, edit in self.skill_edits.items():
            parts = [p.strip() for p in edit.text().split(",")]
            parts = [p for p in parts if p]
            if parts:
                skills[key] = parts
        out["skills"] = skills

        ach = [l.strip() for l in self.ach_edit.toPlainText().split("\n")]
        out["achievements"] = [a for a in ach if a]
        return out

    def _on_save(self):
        try:
            self._result = self._collect()
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save: {e}")
            return
        self.accept()

    def result_profile(self):
        """Return the collected profile dict after Save."""
        return self._result if self._result is not None else self._profile

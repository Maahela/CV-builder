"""Settings tab — API key, output folder, theme."""
import os

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

from ..config import save_config
from ..constants import APP_VERSION, DEFAULT_OUTPUT, GREEN, RED


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
        stored_key = cfg.get("api_key", "")
        display_key = stored_key if stored_key.startswith("sk-ant-") else ""
        self.key_edit = QLineEdit(display_key)
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

        layout.addSpacing(15)
        theme_lbl = QLabel("Appearance")
        layout.addWidget(theme_lbl)
        theme = cfg.get("theme", "dark")
        self.theme_btn = QPushButton(
            "☀️ Light Mode" if theme == "dark" else "🌙 Dark Mode")
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        layout.addStretch()
        ver = QLabel(f"CV Tailor v{APP_VERSION}")
        ver.setStyleSheet("color:#8b949e;")
        layout.addWidget(ver)

    def _toggle_theme(self):
        """Toggle between dark and light theme and persist the choice."""
        self.cfg["theme"] = "light" if self.cfg.get("theme", "dark") == "dark" else "dark"
        self.theme_btn.setText(
            "☀️ Light Mode" if self.cfg["theme"] == "dark" else "🌙 Dark Mode")
        save_config(self.cfg)
        self.config_changed.emit()

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
        """Save config to disk, rejecting keys with wrong prefix."""
        key = self.key_edit.text().strip()
        if key and not key.startswith("sk-ant-"):
            self.saved_lbl.setText(
                "Invalid API key format — should start with sk-ant-")
            self.saved_lbl.setStyleSheet(f"color:{RED};")
            return
        self.cfg["api_key"] = key
        self.cfg["output_folder"] = self.folder_edit.text().strip() \
            or DEFAULT_OUTPUT
        save_config(self.cfg)
        os.makedirs(self.cfg["output_folder"], exist_ok=True)
        self.saved_lbl.setText("Saved ✓")
        self.saved_lbl.setStyleSheet(f"color:{GREEN};")
        self.config_changed.emit()

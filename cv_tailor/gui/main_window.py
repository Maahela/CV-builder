"""Main application window and entry point."""
import os
import sys

from anthropic import Anthropic
from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QTabWidget,
                             QVBoxLayout, QWidget)

from ..config import load_config, load_profile
from ..constants import DEFAULT_OUTPUT, RED
from .bulk_tab import BulkTab
from .profile_tab import ProfileTab
from .settings_tab import SettingsTab
from .single_job_tab import SingleJobTab
from .styles import DARK_STYLESHEET, LIGHT_STYLESHEET


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
        self._apply_theme()
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
        """Apply theme stylesheet based on saved config."""
        theme = self.cfg.get("theme", "dark")
        QApplication.instance().setStyleSheet(
            DARK_STYLESHEET if theme == "dark" else LIGHT_STYLESHEET)


def main():
    """Entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

"""Tracker tab — read-only view of job_applications.xlsx."""
import os
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from ..tracker import (HEADERS, compute_summary, export_csv,
                       get_tracker_path, read_all_rows)
from ..utils import jds_folder, open_file_native


FIT_COLORS = {
    "Green": ("#d4edda", "#2ea44f"),
    "Yellow": ("#fff3cd", "#d29922"),
    "Red": ("#ffdce0", "#da3633"),
}


class TrackerTab(QWidget):
    """Live read-only view of the job application tracker."""

    def __init__(self, get_output):
        """Build UI."""
        super().__init__()
        self.get_output = get_output

        v = QVBoxLayout(self)
        v.setContentsMargins(15, 15, 15, 15)

        self.summary_lbl = QLabel("Total: 0  |  Active: 0  |  "
                                  "Interviews: 0  |  Offers: 0  |  "
                                  "Rejected: 0")
        self.summary_lbl.setStyleSheet("font-weight:bold;padding:6px;")
        v.addWidget(self.summary_lbl)

        ctrl = QHBoxLayout()
        self.open_btn = QPushButton("Open in Excel")
        self.refresh_btn = QPushButton("Refresh")
        self.export_btn = QPushButton("Export CSV")
        self.view_jd_btn = QPushButton("View JD")
        self.view_jd_btn.setEnabled(False)
        self.open_jds_btn = QPushButton("Open JDs Folder")
        self.open_btn.clicked.connect(self._open_excel)
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self._export_csv)
        self.view_jd_btn.clicked.connect(self._view_jd)
        self.open_jds_btn.clicked.connect(self._open_jds_folder)
        ctrl.addWidget(self.open_btn)
        ctrl.addWidget(self.refresh_btn)
        ctrl.addWidget(self.export_btn)
        ctrl.addWidget(self.view_jd_btn)
        ctrl.addWidget(self.open_jds_btn)
        ctrl.addStretch()
        v.addLayout(ctrl)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        v.addWidget(self.table)

        self.refresh()

    def refresh(self):
        """Reload data from disk."""
        rows = read_all_rows(self.get_output())
        self.table.setRowCount(0)
        for r_idx, rec in enumerate(rows):
            self.table.insertRow(r_idx)
            for c_idx, col in enumerate(HEADERS):
                val = rec.get(col, "")
                item = QTableWidgetItem("" if val is None else str(val))
                if col == "Fit" and val in FIT_COLORS:
                    bg, fg = FIT_COLORS[val]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r_idx, c_idx, item)
        self.table.resizeColumnsToContents()
        s = compute_summary(rows)
        self.summary_lbl.setText(
            f"Total: {s['Total']}  |  Active: {s['Active']}  |  "
            f"Interviews: {s['Interviews']}  |  Offers: {s['Offers']}  |  "
            f"Rejected: {s['Rejected']}")

    def _open_excel(self):
        """Open job_applications.xlsx in default app."""
        path = get_tracker_path(self.get_output())
        if not os.path.exists(path):
            QMessageBox.information(
                self, "No Tracker Yet",
                "The tracker file does not exist yet — generate a CV first.")
            return
        open_file_native(path)

    def _open_jds_folder(self):
        """Open the /jds subfolder in the OS file manager (creating it
        first if it doesn't yet exist)."""
        folder = jds_folder(self.get_output())
        os.makedirs(folder, exist_ok=True)
        open_file_native(folder)

    def _on_selection_changed(self):
        """Toggle View JD button based on selection."""
        self.view_jd_btn.setEnabled(bool(self.table.selectionModel()
                                         and self.table.selectionModel()
                                         .selectedRows()))

    def _view_jd(self):
        """Open the selected row's JD .txt in Notepad (or default editor)."""
        rows = (self.table.selectionModel().selectedRows()
                if self.table.selectionModel() else [])
        if not rows:
            return
        row = rows[0].row()
        try:
            jd_col = HEADERS.index("JD File")
        except ValueError:
            return
        item = self.table.item(row, jd_col)
        jd_name = (item.text().strip() if item else "")
        if not jd_name:
            QMessageBox.information(
                self, "No JD File",
                "This row has no JD file recorded.")
            return
        output = self.get_output()
        # Try the recorded path first (may already include "jds/" prefix),
        # then jds/<basename>, then the legacy main-folder location.
        bare = os.path.basename(jd_name)
        candidates = [
            os.path.join(output, jd_name.replace("/", os.sep)),
            os.path.join(jds_folder(output), bare),
            os.path.join(output, bare),
        ]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if path is None:
            QMessageBox.information(
                self, "Not Found",
                "JD file not found — it may have been moved or deleted.")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["notepad.exe", path])
            else:
                open_file_native(path)
        except Exception:
            open_file_native(path)

    def _export_csv(self):
        """Save CSV copy of tracker to output folder."""
        try:
            path = export_csv(self.get_output())
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

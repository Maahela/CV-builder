"""Tracker tab — read-only view of job_applications.xlsx."""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from ..tracker import (HEADERS, compute_summary, export_csv,
                       get_tracker_path, read_all_rows)
from ..utils import open_file_native


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
        self.open_btn.clicked.connect(self._open_excel)
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self._export_csv)
        ctrl.addWidget(self.open_btn)
        ctrl.addWidget(self.refresh_btn)
        ctrl.addWidget(self.export_btn)
        ctrl.addStretch()
        v.addLayout(ctrl)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
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

    def _export_csv(self):
        """Save CSV copy of tracker to output folder."""
        try:
            path = export_csv(self.get_output())
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

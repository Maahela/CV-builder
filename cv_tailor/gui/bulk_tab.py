"""Bulk tab — paste many JDs, run sequentially, export CSV."""
import csv
import os
from datetime import datetime

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QProgressBar, QPushButton,
                             QTableWidget, QTableWidgetItem, QTextEdit,
                             QVBoxLayout, QWidget)

from ..utils import open_file_native
from ..workers import BulkRunner, parse_bulk_input
from .widgets import PlainTextEdit


class BulkTab(QWidget):
    """Bulk-process many JDs at once."""

    COLS = ["#", "Company", "Title", "Fit", "Status", "Gap", "Filename"]

    def __init__(self, get_client, get_profile, get_output):
        """Build UI."""
        super().__init__()
        self.get_client = get_client
        self.get_profile = get_profile
        self.get_output = get_output
        self.tracker_updated_cb = None
        self.runner = None
        self.pending_rows = {}

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

        self.input = PlainTextEdit()
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
        self.runner.duplicate_found.connect(self._on_duplicate)
        if self.tracker_updated_cb:
            self.runner.tracker_updated.connect(self.tracker_updated_cb)
        self.runner.done.connect(self._on_done)
        self.runner.start()

    def _stop(self):
        """Request stop."""
        if self.runner:
            self.runner.stop()
        self.stop_btn.setEnabled(False)

    def _set(self, row, col, text):
        """Set a cell by index."""
        self.table.setItem(row, col, QTableWidgetItem(text))

    def _col_index(self, name):
        """Map column name to index."""
        return {"Status": 4, "Fit": 3, "Gap": 5, "Filename": 6}.get(name, 4)

    def _on_row(self, row, col_name, value):
        """Update a row cell."""
        col = self._col_index(col_name)
        item = self.table.item(row, col)
        if item:
            item.setText(value)
        if col_name == "Status":
            if value.startswith("✓") or value.startswith("✗"):
                self.progress.setValue(self.progress.value() + 1)
                if value.startswith("✗") and "Skipped" not in value:
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

    def _on_duplicate(self, row, company, role, prev_date):
        """Prompt user about duplicate; relay decision to runner."""
        ans = QMessageBox.question(
            self, "Possible Duplicate",
            f"You may have already applied to this role.\n"
            f"{company} — {role} was applied to on {prev_date}.\n\n"
            f"Add another entry anyway?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if self.runner:
            self.runner.submit_duplicate_decision(
                "add" if ans == QMessageBox.Yes else "skip")

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

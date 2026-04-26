"""Shared Qt widgets."""
from PyQt5.QtWidgets import QTextEdit


class PlainTextEdit(QTextEdit):
    """QTextEdit that always pastes as plain text, stripping clipboard formatting."""

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

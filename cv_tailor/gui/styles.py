"""Dark and light Qt stylesheets."""

DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #0d1117; color: #e6edf3; }
QTabWidget::pane { border: 1px solid #21262d; background-color: #0d1117; }
QTabBar::tab {
    background-color: #161b22; color: #8b949e;
    padding: 8px 16px; border: 1px solid #21262d; border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #0d1117; color: #e6edf3;
    border-bottom: 2px solid #2ea44f;
}
QTextEdit, QPlainTextEdit {
    background-color: #161b22; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px; padding: 8px;
    selection-background-color: #1f6feb; selection-color: #ffffff;
}
QLineEdit {
    background-color: #161b22; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px;
}
QPushButton {
    background-color: #21262d; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 6px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
QPushButton:disabled { color: #6e7681; }
QPushButton#primary { background-color: #2ea44f; color: #ffffff; border-color: #2ea44f; }
QPushButton#primary:hover { background-color: #3fb950; }
QPushButton#danger { background-color: #da3633; color: #ffffff; border-color: #da3633; }
QProgressBar {
    background-color: #21262d; border: none; border-radius: 3px;
    text-align: center; color: #e6edf3;
}
QProgressBar::chunk { background-color: #388bfd; border-radius: 3px; }
QTableWidget {
    background-color: #161b22; color: #e6edf3;
    gridline-color: #21262d; border: 1px solid #21262d;
}
QTableWidget::item:selected { background-color: #1f6feb; }
QListWidget {
    background-color: #161b22; color: #e6edf3; border: 1px solid #30363d;
}
QListWidget::item:selected { background-color: #1f6feb; }
QHeaderView::section {
    background-color: #21262d; color: #8b949e;
    border: none; padding: 6px; font-weight: 600;
}
QScrollBar:vertical { background: #0d1117; width: 8px; }
QScrollBar::handle:vertical { background: #30363d; border-radius: 4px; }
QLabel { color: #e6edf3; }
QGroupBox {
    color: #8b949e; border: 1px solid #21262d;
    border-radius: 6px; margin-top: 8px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
"""

LIGHT_STYLESHEET = """
QMainWindow, QWidget { background-color: #ffffff; color: #1a1a2e; }
QTabWidget::pane { border: 1px solid #d0d7de; background-color: #ffffff; }
QTabBar::tab {
    background-color: #f6f8fa; color: #57606a;
    padding: 8px 16px; border: 1px solid #d0d7de; border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #ffffff; color: #1a1a2e;
    border-bottom: 2px solid #2ea44f;
}
QTextEdit, QPlainTextEdit {
    background-color: #f6f8fa; color: #1a1a2e;
    border: 1px solid #d0d7de; border-radius: 6px; padding: 8px;
    selection-background-color: #0969da; selection-color: #ffffff;
}
QLineEdit {
    background-color: #ffffff; color: #1a1a2e;
    border: 1px solid #d0d7de; border-radius: 6px; padding: 6px 10px;
}
QPushButton {
    background-color: #f6f8fa; color: #1a1a2e;
    border: 1px solid #d0d7de; border-radius: 6px;
    padding: 6px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #eaeef2; border-color: #8c959f; }
QPushButton:disabled { color: #8c959f; }
QPushButton#primary { background-color: #2ea44f; color: #ffffff; border-color: #2ea44f; }
QPushButton#primary:hover { background-color: #3fb950; }
QPushButton#danger { background-color: #da3633; color: #ffffff; border-color: #da3633; }
QProgressBar {
    background-color: #eaeef2; border: none; border-radius: 3px;
    text-align: center; color: #1a1a2e;
}
QProgressBar::chunk { background-color: #2ea44f; border-radius: 3px; }
QTableWidget {
    background-color: #ffffff; color: #1a1a2e;
    gridline-color: #d0d7de; border: 1px solid #d0d7de;
}
QTableWidget::item:selected { background-color: #0969da; color: #ffffff; }
QListWidget {
    background-color: #f6f8fa; color: #1a1a2e; border: 1px solid #d0d7de;
}
QListWidget::item:selected { background-color: #0969da; color: #ffffff; }
QHeaderView::section {
    background-color: #f6f8fa; color: #57606a;
    border: none; padding: 6px; font-weight: 600;
}
QScrollBar:vertical { background: #f6f8fa; width: 8px; }
QScrollBar::handle:vertical { background: #d0d7de; border-radius: 4px; }
QLabel { color: #1a1a2e; }
QGroupBox {
    color: #57606a; border: 1px solid #d0d7de;
    border-radius: 6px; margin-top: 8px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
"""

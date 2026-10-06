"""Application-wide look: palette, font and stylesheet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#2F6FED"
TEXT = "#1F2328"
MUTED = "#667085"
BORDER = "#DFE3E8"
WINDOW = "#F4F6F8"
SURFACE = "#FFFFFF"
DANGER = "#D92D20"
WARNING = "#F59E0B"
SUCCESS = "#1E8E3E"

INPUT_HEIGHT = 32

STYLESHEET = f"""
QToolTip {{
    color: {TEXT};
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}

QTabWidget::pane {{
    border: none;
    border-top: 1px solid {BORDER};
}}
QTabBar::tab {{
    padding: 9px 20px;
    margin-right: 2px;
    color: {MUTED};
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {ACCENT};
    font-weight: 600;
    border-bottom: 3px solid {ACCENT};
}}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLabel#fieldLabel, QLabel#cardTitle {{ color: {MUTED}; font-size: 9pt; }}
QLabel#cardValue {{ font-size: 18pt; font-weight: 600; }}
QLabel#cardDetail {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-size: 12pt; font-weight: 600; }}
QLabel#monthLabel {{ font-size: 14pt; font-weight: 600; }}
QLabel#errorLabel {{ color: {DANGER}; }}
QLabel#hintLabel, QLabel#emptyLabel {{ color: {MUTED}; }}
QLabel#footerLabel {{ font-weight: 600; }}

QLineEdit[invalid="true"] {{
    border: 1px solid {DANGER};
    border-radius: 3px;
    padding: 0 3px;
}}

QPushButton#primaryButton {{
    color: white;
    background: {ACCENT};
    border: none;
    border-radius: 5px;
    padding: 0 20px;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background: #255FD3; }}
QPushButton#primaryButton:pressed {{ background: #1E4FB3; }}
QPushButton#primaryButton:focus {{ border: 2px solid #9DBBF8; }}

QTableView {{
    background: {SURFACE};
    alternate-background-color: #F8FAFC;
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: transparent;
    selection-background-color: #DCE8FD;
    selection-color: {TEXT};
    outline: 0;
}}
QTableView::item {{ padding: 4px 8px; }}
QHeaderView::section {{
    background: #EEF1F5;
    color: {TEXT};
    font-weight: 600;
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}

QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: 0;
}}
QListWidget::item {{ padding: 6px 8px; border: none; }}
QListWidget::item:selected {{ background: #DCE8FD; color: {TEXT}; }}

QToolButton#monthButton {{ font-size: 15pt; padding-bottom: 4px; }}

QLabel#budgetName {{ font-size: 11pt; font-weight: 600; }}
QLabel#budgetPercent {{ color: {MUTED}; font-weight: 600; }}
QProgressBar {{
    background: #E9EDF2;
    border: none;
    border-radius: 5px;
}}
QProgressBar::chunk {{ border-radius: 5px; background: {SUCCESS}; }}
QProgressBar[level="warning"]::chunk {{ background: {WARNING}; }}
QProgressBar[level="over"]::chunk {{ background: {DANGER}; }}

QScrollArea {{ background: transparent; }}

QFrame#toast {{
    background: #1F2937;
    border-radius: 8px;
    border-left: 5px solid {ACCENT};
}}
QFrame#toast[level="near"] {{ border-left: 5px solid {WARNING}; }}
QFrame#toast[level="over"] {{ border-left: 5px solid {DANGER}; }}
QLabel#toastTitle {{ color: #FFFFFF; font-weight: 600; }}
QLabel#toastBody {{ color: #E5E7EB; }}
QToolButton#toastClose {{
    color: #CBD5E1;
    background: transparent;
    border: none;
    padding: 2px 4px;
}}
QToolButton#toastClose:hover {{ color: #FFFFFF; }}

QStatusBar {{ color: {MUTED}; border-top: 1px solid {BORDER}; }}
"""


def apply_style(app: QApplication) -> None:
    """Give the app a consistent light look regardless of the Windows theme."""
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:  # Qt older than 6.8
        pass

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: WINDOW,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: "#F8FAFC",
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: "#FBFCFD",
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.ToolTipBase: SURFACE,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: "#98A2B3",
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#A0A8B4"))
    app.setPalette(palette)

    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

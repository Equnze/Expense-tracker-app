"""A small notification that appears over the window without blocking it."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

INFO = "info"
NEAR = "near"
OVER = "over"

VISIBLE_MS = 9000
MARGIN = 16
WIDTH = 380


class Toast(QFrame):
    """Shows a title and message in the window's bottom-right corner for a few
    seconds. Messages arriving while it is visible are added to it."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFixedWidth(WIDTH)
        self._bottom_offset = 0
        self._lines: list[str] = []

        self.title = QLabel()
        self.title.setObjectName("toastTitle")
        self.body = QLabel()
        self.body.setObjectName("toastBody")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        close = QToolButton()
        close.setObjectName("toastClose")
        close.setText("✕")
        close.setToolTip("Dismiss")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)

        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 14)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.body)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def set_bottom_offset(self, pixels: int) -> None:
        """Keep clear of something at the bottom of the window (the status bar)."""
        self._bottom_offset = pixels
        self.reposition()

    def show_message(self, title: str, message: str, level: str = INFO) -> None:
        if self.isVisible() and self.title.text() == title:
            self._lines.append(message)
        else:
            self._lines = [message]
        # The most serious level among stacked messages decides the color.
        if not (self.isVisible() and self.property("level") == OVER):
            self.setProperty("level", level)
            self.style().unpolish(self)
            self.style().polish(self)
        self.title.setText(title)
        self.body.setText("\n".join(self._lines))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(VISIBLE_MS)

    def hideEvent(self, event) -> None:
        self._lines = []
        super().hideEvent(event)

    def reposition(self) -> None:
        parent = self.parentWidget()
        self.move(
            parent.width() - self.width() - MARGIN,
            parent.height() - self.height() - MARGIN - self._bottom_offset,
        )

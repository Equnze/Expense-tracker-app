"""Small reusable widgets."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from expense_tracker.models import Category
from expense_tracker.ui.style import INPUT_HEIGHT

_icon_cache: dict[str, QIcon] = {}


def color_icon(color: str) -> QIcon:
    """Return a small round swatch icon for a hex color."""
    icon = _icon_cache.get(color)
    if icon is None:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        icon = QIcon(pixmap)
        # Keep the true color on selected rows instead of Qt's tinted version.
        icon.addPixmap(pixmap, QIcon.Mode.Selected)
        _icon_cache[color] = icon
    return icon


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def make_date_edit(parent: QWidget | None = None) -> QDateEdit:
    edit = QDateEdit(parent)
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd MMM yyyy")
    edit.setDate(QDate.currentDate())
    edit.setMinimumHeight(INPUT_HEIGHT)
    return edit


def fill_category_combo(
    combo: QComboBox, categories: Iterable[Category], selected_id: int | None
) -> None:
    """Replace a combo's items with the given categories, keeping the selection."""
    combo.blockSignals(True)
    combo.clear()
    for category in categories:
        label = category.name + (" (archived)" if category.is_archived else "")
        combo.addItem(color_icon(category.color), label, category.id)
    index = combo.findData(selected_id)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def set_invalid(widget: QWidget, invalid: bool) -> None:
    """Toggle the red "invalid" outline defined in the stylesheet."""
    if bool(widget.property("invalid")) == invalid:
        return
    widget.setProperty("invalid", invalid)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Card(QFrame):
    """A bordered panel showing a title, a large value and a line of detail."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        self.detail = QLabel("")
        self.detail.setObjectName("cardDetail")
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addStretch(1)


class CategoryFilterButton(QPushButton):
    """Drop-down with a checkbox per category. Nothing checked means "all"."""

    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(INPUT_HEIGHT)
        self.setMinimumWidth(170)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._checks: dict[int, QCheckBox] = {}
        self._update_text()

    def set_categories(self, categories: Iterable[Category]) -> None:
        selected = self.selected_ids()
        self._menu.clear()
        self._checks = {}
        for category in categories:
            label = category.name + (" (archived)" if category.is_archived else "")
            # "&" would otherwise be read as a keyboard-mnemonic marker.
            box = QCheckBox(label.replace("&", "&&"), self._menu)
            box.setIcon(color_icon(category.color))
            box.setStyleSheet("QCheckBox { padding: 5px 14px 5px 10px; }")
            box.setChecked(category.id in selected)
            box.toggled.connect(self._on_toggled)
            action = QWidgetAction(self._menu)
            action.setDefaultWidget(box)
            self._menu.addAction(action)
            self._checks[category.id] = box
        self._update_text()

    def selected_ids(self) -> set[int]:
        return {cid for cid, box in self._checks.items() if box.isChecked()}

    def clear_selection(self) -> None:
        """Uncheck everything without emitting ``selection_changed``."""
        for box in self._checks.values():
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        self._update_text()

    def _on_toggled(self) -> None:
        self._update_text()
        self.selection_changed.emit()

    def _update_text(self) -> None:
        checked = [box for box in self._checks.values() if box.isChecked()]
        if not checked:
            self.setText("All categories")
        elif len(checked) == 1:
            self.setText(checked[0].text())
        else:
            self.setText(f"{len(checked)} categories")

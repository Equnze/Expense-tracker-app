"""Filter controls above the expense table."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from expense_tracker.models import PAYMENT_METHODS, ExpenseFilter
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import INPUT_HEIGHT
from expense_tracker.ui.widgets import CategoryFilterButton, make_date_edit
from expense_tracker.utils.dates import CUSTOM, DATE_PRESETS, THIS_MONTH, preset_range

ALL_METHODS = "All payment methods"


class FilterBar(QWidget):
    filters_changed = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx

        self.preset = QComboBox()
        self.preset.addItems(DATE_PRESETS)
        self.date_from = make_date_edit()
        today = QDate.currentDate()
        self.date_from.setDate(QDate(today.year(), today.month(), 1))
        self.date_to = make_date_edit()
        self._to_label = QLabel("to")
        self.categories = CategoryFilterButton()
        self.payment = QComboBox()
        self.payment.addItem(ALL_METHODS)
        self.payment.addItems(PAYMENT_METHODS)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search description or tags…")
        self.search.setClearButtonEnabled(True)
        self.clear_button = QPushButton("Clear filters")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in (
            self.preset,
            self.date_from,
            self._to_label,
            self.date_to,
            self.categories,
            self.payment,
        ):
            layout.addWidget(widget)
        layout.addWidget(self.search, 1)
        layout.addWidget(self.clear_button)
        for widget in (self.preset, self.payment, self.search, self.clear_button):
            widget.setMinimumHeight(INPUT_HEIGHT)

        self.preset.currentIndexChanged.connect(self._on_preset_changed)
        self.date_from.dateChanged.connect(self.filters_changed)
        self.date_to.dateChanged.connect(self.filters_changed)
        self.categories.selection_changed.connect(self.filters_changed)
        self.payment.currentIndexChanged.connect(self.filters_changed)
        self.search.textChanged.connect(self.filters_changed)
        self.clear_button.clicked.connect(self.clear)

        self.reload_categories()
        self._show_custom_range(False)
        ctx.categories_changed.connect(self.reload_categories)

    def reload_categories(self) -> None:
        self.categories.set_categories(self._ctx.categories.list())

    def current_filter(self) -> ExpenseFilter:
        if self.preset.currentText() == CUSTOM:
            first = self.date_from.date().toPython()
            second = self.date_to.date().toPython()
            start, end = min(first, second), max(first, second)
        else:
            start, end = preset_range(self.preset.currentText(), date.today())
        method = self.payment.currentText()
        return ExpenseFilter(
            start_date=start,
            end_date=end,
            category_ids=self.categories.selected_ids(),
            payment_method=None if method == ALL_METHODS else method,
            search=self.search.text().strip(),
        )

    def clear(self) -> None:
        """Reset every filter to its default and announce the change once."""
        self.blockSignals(True)
        self.preset.setCurrentText(THIS_MONTH)
        self.categories.clear_selection()
        self.payment.setCurrentIndex(0)
        self.search.clear()
        self.blockSignals(False)
        self.filters_changed.emit()

    def _on_preset_changed(self) -> None:
        self._show_custom_range(self.preset.currentText() == CUSTOM)
        self.filters_changed.emit()

    def _show_custom_range(self, visible: bool) -> None:
        for widget in (self.date_from, self._to_label, self.date_to):
            widget.setVisible(visible)

"""Dialog for editing an existing expense."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from expense_tracker.models import PAYMENT_METHODS, Expense
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import INPUT_HEIGHT
from expense_tracker.ui.widgets import fill_category_combo, make_date_edit, set_invalid
from expense_tracker.utils.money import MoneyError, format_plain, parse_cents


class ExpenseDialog(QDialog):
    """Edits the given expense in place; the caller saves it when accepted."""

    def __init__(self, ctx: AppContext, expense: Expense, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.expense = expense
        self.setWindowTitle("Edit expense")
        self.setMinimumWidth(420)

        self.amount = QLineEdit(format_plain(expense.amount_cents))
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date = make_date_edit()
        self.date.setDate(
            QDate(expense.date.year, expense.date.month, expense.date.day)
        )
        self.category = QComboBox()
        # An archived category stays selectable for the expense that already uses it.
        choices = [
            category
            for category in ctx.categories.list()
            if not category.is_archived or category.id == expense.category_id
        ]
        fill_category_combo(self.category, choices, expense.category_id)
        self.description = QLineEdit(expense.description)
        self.description.setMaxLength(200)
        self.payment = QComboBox()
        self.payment.addItems(PAYMENT_METHODS)
        if expense.payment_method and expense.payment_method not in PAYMENT_METHODS:
            self.payment.addItem(expense.payment_method)
        self.payment.setCurrentText(expense.payment_method)
        self.error = QLabel("")
        self.error.setObjectName("errorLabel")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        for title, widget in (
            (f"Amount ({ctx.currency})", self.amount),
            ("Date", self.date),
            ("Category", self.category),
            ("Description", self.description),
            ("Payment method", self.payment),
        ):
            widget.setMinimumHeight(INPUT_HEIGHT)
            form.addRow(title, widget)
        form.addRow("", self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.amount.textChanged.connect(self._clear_error)
        self.amount.selectAll()

    def accept(self) -> None:
        try:
            cents = parse_cents(self.amount.text(), self._ctx.currency)
        except MoneyError as exc:
            self.error.setText(str(exc))
            set_invalid(self.amount, True)
            self.amount.setFocus()
            self.amount.selectAll()
            return
        self.expense.amount_cents = cents
        self.expense.date = self.date.date().toPython()
        self.expense.category_id = self.category.currentData()
        self.expense.description = self.description.text()
        self.expense.payment_method = self.payment.currentText()
        super().accept()

    def _clear_error(self) -> None:
        self.error.setText("")
        set_invalid(self.amount, False)

"""The quick-add form at the top of the Expenses tab."""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from expense_tracker.models import PAYMENT_METHODS
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import INPUT_HEIGHT
from expense_tracker.ui.widgets import (
    field_label,
    fill_category_combo,
    make_date_edit,
    set_invalid,
)
from expense_tracker.utils.money import MoneyError, parse_cents


class QuickAddForm(QFrame):
    """Amount, date, category, description and payment method with an Add button."""

    expense_added = Signal(object)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setObjectName("card")

        self.amount = QLineEdit()
        self.amount.setPlaceholderText("0.00")
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.amount.setFixedWidth(120)
        self.date = make_date_edit()
        self.date.setFixedWidth(135)
        self.category = QComboBox()
        self.category.setMinimumWidth(190)
        self.description = QLineEdit()
        self.description.setPlaceholderText("What was it for? (optional)")
        self.description.setMaxLength(200)
        self.payment = QComboBox()
        self.payment.addItems(PAYMENT_METHODS)
        self.payment.setMinimumWidth(140)
        self.add_button = QPushButton("Add")
        self.add_button.setObjectName("primaryButton")
        self.add_button.setToolTip("Add expense (Enter)")
        self.error = QLabel("")
        self.error.setObjectName("errorLabel")

        fields = [
            ("Amount", self.amount),
            ("Date", self.date),
            ("Category", self.category),
            ("Description", self.description),
            ("Payment method", self.payment),
        ]
        layout = QGridLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(4)
        for column, (title, widget) in enumerate(fields):
            widget.setMinimumHeight(INPUT_HEIGHT)
            widget.installEventFilter(self)
            layout.addWidget(field_label(title), 0, column)
            layout.addWidget(widget, 1, column)
        self.add_button.setMinimumHeight(INPUT_HEIGHT)
        layout.addWidget(self.add_button, 1, len(fields))
        layout.addWidget(self.error, 2, 0, 1, len(fields) + 1)
        layout.setColumnStretch(3, 1)

        self.add_button.clicked.connect(self.submit)
        self.amount.textChanged.connect(self._clear_error)
        self.category.currentIndexChanged.connect(self._clear_error)

        self.reload_categories(ctx.expense_service.last_category_id())
        last_payment = ctx.expense_service.last_payment_method()
        if last_payment in PAYMENT_METHODS:
            self.payment.setCurrentText(last_payment)
        ctx.categories_changed.connect(self.reload_categories)
        ctx.settings_changed.connect(self._update_amount_hint)
        self._update_amount_hint()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Enter in any field saves the expense.
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self.submit()
            return True
        return super().eventFilter(watched, event)

    def focus_amount(self) -> None:
        self.amount.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.amount.selectAll()

    def reload_categories(self, selected_id: int | None = None) -> None:
        if selected_id is None:
            selected_id = self.category.currentData()
        active = self._ctx.categories.list(include_archived=False)
        fill_category_combo(self.category, active, selected_id)

    def submit(self) -> None:
        try:
            cents = parse_cents(self.amount.text(), self._ctx.currency)
        except MoneyError as exc:
            self._show_error(str(exc), self.amount)
            return
        category_id = self.category.currentData()
        if category_id is None:
            self._show_error("Add a category in Settings first.", self.category)
            return

        expense = self._ctx.expense_service.add(
            cents,
            self.date.date().toPython(),
            category_id,
            self.description.text(),
            self.payment.currentText(),
        )
        self.amount.clear()
        self.description.clear()
        self.date.setDate(QDate.currentDate())
        self._clear_error()
        self.amount.setFocus()
        self._ctx.data_changed.emit()
        self.expense_added.emit(expense)

    def _show_error(self, message: str, widget) -> None:
        self.error.setText(message)
        set_invalid(self.amount, widget is self.amount)
        widget.setFocus()
        if widget is self.amount:
            self.amount.selectAll()

    def _clear_error(self) -> None:
        self.error.setText("")
        set_invalid(self.amount, False)

    def _update_amount_hint(self) -> None:
        self.amount.setToolTip(f"Amount in {self._ctx.currency}, e.g. 12.50")

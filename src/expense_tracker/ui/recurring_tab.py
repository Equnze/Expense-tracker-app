"""Recurring tab: manage rules for rent, subscriptions and other repeating costs."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.models import (
    FREQUENCIES,
    MONTHLY,
    PAYMENT_METHODS,
    Expense,
    RecurringExpense,
)
from expense_tracker.services.recurring import (
    RecurringError,
    describe_schedule,
    due_dates,
    next_due,
)
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import INPUT_HEIGHT, MUTED
from expense_tracker.ui.widgets import (
    color_icon,
    fill_category_combo,
    make_date_edit,
    set_invalid,
)
from expense_tracker.utils.dates import format_display
from expense_tracker.utils.money import MoneyError, format_plain, parse_cents

_ID_ROLE = Qt.ItemDataRole.UserRole
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
DESCRIPTION, CATEGORY, AMOUNT, SCHEDULE, NEXT_DUE, STATUS = range(6)


def _to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def generated_message(expenses: list[Expense], ctx: AppContext, limit: int = 4) -> str:
    """List generated expenses for a notification, e.g. ``Rent  $1,250.00  (01 Oct)``."""
    lines = [
        f"{expense.description or 'Recurring expense'}  "
        f"{ctx.money(expense.amount_cents)}  ({expense.date.day:02d} "
        f"{expense.date.strftime('%b')})"
        for expense in expenses[:limit]
    ]
    if len(expenses) > limit:
        lines.append(f"…and {len(expenses) - limit} more")
    return "\n".join(lines)


class RecurringDialog(QDialog):
    """Creates or edits a recurring rule. The caller saves ``self.rule``."""

    def __init__(
        self, ctx: AppContext, rule: RecurringExpense | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._is_new = rule is None
        today = date.today()
        self.rule = rule or RecurringExpense(
            amount_cents=0,
            category_id=0,
            frequency=MONTHLY,
            start_date=today,
            day_of_month=today.day,
            payment_method=ctx.expense_service.last_payment_method() or "",
        )
        self.setWindowTitle(
            "Add recurring expense" if self._is_new else "Edit recurring expense"
        )
        self.setMinimumWidth(460)

        self.amount = QLineEdit(
            format_plain(self.rule.amount_cents) if self.rule.amount_cents else ""
        )
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.amount.setPlaceholderText("0.00")
        self.category = QComboBox()
        choices = [
            category
            for category in ctx.categories.list()
            if not category.is_archived or category.id == self.rule.category_id
        ]
        fill_category_combo(
            self.category,
            choices,
            self.rule.category_id or ctx.expense_service.last_category_id(),
        )
        self.description = QLineEdit(self.rule.description)
        self.description.setMaxLength(200)
        self.description.setPlaceholderText("e.g. Rent, Netflix, Gym")
        self.payment = QComboBox()
        self.payment.addItems(PAYMENT_METHODS)
        if self.rule.payment_method in PAYMENT_METHODS:
            self.payment.setCurrentText(self.rule.payment_method)
        self.frequency = QComboBox()
        for frequency in FREQUENCIES:
            self.frequency.addItem(frequency.capitalize(), frequency)
        self.frequency.setCurrentIndex(self.frequency.findData(self.rule.frequency))
        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.day.setValue(self.rule.day_of_month or self.rule.start_date.day)
        self.day_label = QLabel("Day of month")
        self.start = make_date_edit()
        self.start.setDate(_to_qdate(self.rule.start_date))
        self.has_end = QCheckBox("Ends on")
        self.has_end.setChecked(self.rule.end_date is not None)
        self.end = make_date_edit()
        self.end.setDate(_to_qdate(self.rule.end_date or self.rule.start_date))
        self.end.setEnabled(self.has_end.isChecked())
        self.hint = QLabel("")
        self.hint.setObjectName("hintLabel")
        self.hint.setWordWrap(True)
        self.error = QLabel("")
        self.error.setObjectName("errorLabel")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        form.addRow(f"Amount ({ctx.currency})", self.amount)
        form.addRow("Category", self.category)
        form.addRow("Description", self.description)
        form.addRow("Payment method", self.payment)
        form.addRow("Repeats", self.frequency)
        form.addRow(self.day_label, self.day)
        form.addRow("Starts on", self.start)
        form.addRow(self.has_end, self.end)
        form.addRow("", self.hint)
        form.addRow("", self.error)
        for widget in (
            self.amount,
            self.category,
            self.description,
            self.payment,
            self.frequency,
            self.day,
        ):
            widget.setMinimumHeight(INPUT_HEIGHT)

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
        self.frequency.currentIndexChanged.connect(self._update_hint)
        self.day.valueChanged.connect(self._update_hint)
        self.start.dateChanged.connect(self._on_start_changed)
        self.has_end.toggled.connect(self.end.setEnabled)
        self.has_end.toggled.connect(self._update_hint)
        self.end.dateChanged.connect(self._update_hint)
        self._update_hint()

    def _on_start_changed(self, value: QDate) -> None:
        # For a new rule the day of the month follows the start date.
        if self._is_new:
            self.day.setValue(value.day())
        self._update_hint()

    def _draft(self, amount_cents: int) -> RecurringExpense:
        """Build a rule from the form, keeping the stored rule's history."""
        frequency = self.frequency.currentData()
        return RecurringExpense(
            id=self.rule.id,
            amount_cents=amount_cents,
            category_id=self.category.currentData() or 0,
            description=self.description.text(),
            payment_method=self.payment.currentText(),
            frequency=frequency,
            day_of_month=self.day.value() if frequency == MONTHLY else None,
            start_date=self.start.date().toPython(),
            end_date=self.end.date().toPython() if self.has_end.isChecked() else None,
            last_generated_date=self.rule.last_generated_date,
            is_active=self.rule.is_active,
        )

    def _update_hint(self) -> None:
        is_monthly = self.frequency.currentData() == MONTHLY
        self.day.setVisible(is_monthly)
        self.day_label.setVisible(is_monthly)

        draft = self._draft(1)
        upcoming = next_due(draft)
        today = date.today()
        parts = [describe_schedule(draft) + "."]
        if upcoming is None:
            parts.append("Nothing more will be added (it has ended).")
        else:
            already_due = len(due_dates(draft, today))
            if already_due == 1 and draft.is_active:
                parts.append(
                    f"Saving adds 1 expense now, dated {format_display(upcoming)}."
                )
            elif already_due and draft.is_active:
                parts.append(
                    f"Saving adds {already_due} expenses now, dated from "
                    f"{format_display(upcoming)} up to today."
                )
            else:
                parts.append(f"Next: {format_display(upcoming)}.")
        self.hint.setText(" ".join(parts))

    def _clear_error(self) -> None:
        self.error.setText("")
        set_invalid(self.amount, False)

    def accept(self) -> None:
        try:
            cents = parse_cents(self.amount.text(), self._ctx.currency)
        except MoneyError as exc:
            self.error.setText(str(exc))
            set_invalid(self.amount, True)
            self.amount.setFocus()
            return
        draft = self._draft(cents)
        if not draft.category_id:
            self.error.setText("Add a category in Settings first.")
            return
        try:
            if self._is_new:
                self._ctx.recurring_service.add(draft)
            else:
                self._ctx.recurring_service.update(draft)
        except RecurringError as exc:
            self.error.setText(str(exc))
            return
        self.rule = draft
        super().accept()


class RecurringTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._rules: dict[int, RecurringExpense] = {}

        title = QLabel("Recurring expenses")
        title.setObjectName("monthLabel")
        hint = QLabel(
            "These are added to your expenses automatically when they come due, "
            "each time you open the app. Anything missed while the app was closed "
            "is caught up."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)

        self.add_button = QPushButton("Add…")
        self.add_button.setObjectName("primaryButton")
        self.edit_button = QPushButton("Edit…")
        self.pause_button = QPushButton("Pause")
        self.delete_button = QPushButton("Delete…")
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(title)
        header.addStretch(1)
        for button in (
            self.edit_button,
            self.pause_button,
            self.delete_button,
            self.add_button,
        ):
            button.setMinimumHeight(INPUT_HEIGHT)
            button.setMinimumWidth(90)
            header.addWidget(button)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Description", "Category", "Amount", "Repeats", "Next due", "Status"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        table_header = self.table.horizontalHeader()
        table_header.setHighlightSections(False)
        table_header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        table_header.setSectionResizeMode(DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(AMOUNT).setTextAlignment(_RIGHT)
        for column, width in (
            (CATEGORY, 190),
            (AMOUNT, 120),
            (SCHEDULE, 230),
            (NEXT_DUE, 120),
            (STATUS, 90),
        ):
            self.table.setColumnWidth(column, width)

        self.empty_label = QLabel(
            "No recurring expenses yet.\nAdd your rent, subscriptions and other "
            "regular bills so you never have to type them in again."
        )
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label, 1)

        self.add_button.clicked.connect(self.add_rule)
        self.edit_button.clicked.connect(self.edit_rule)
        self.pause_button.clicked.connect(self.toggle_paused)
        self.delete_button.clicked.connect(self.delete_rule)
        self.table.itemDoubleClicked.connect(self.edit_rule)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        ctx.data_changed.connect(self.refresh)
        ctx.categories_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._selected_id()
        rules = self._ctx.recurring_service.list()
        self._rules = {rule.id: rule for rule in rules}
        categories = {category.id: category for category in self._ctx.categories.list()}

        self.table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            category = categories.get(rule.category_id)
            upcoming = next_due(rule)
            if upcoming is None:
                status = "Ended"
            else:
                status = "Active" if rule.is_active else "Paused"
            cells = [
                QTableWidgetItem(rule.description or "(no description)"),
                QTableWidgetItem(category.name if category else ""),
                QTableWidgetItem(self._ctx.money(rule.amount_cents)),
                QTableWidgetItem(describe_schedule(rule)),
                QTableWidgetItem(
                    format_display(upcoming) if upcoming and rule.is_active else "—"
                ),
                QTableWidgetItem(status),
            ]
            if category:
                cells[CATEGORY].setIcon(color_icon(category.color))
            cells[AMOUNT].setTextAlignment(_RIGHT)
            cells[DESCRIPTION].setData(_ID_ROLE, rule.id)
            for column, cell in enumerate(cells):
                if status != "Active":
                    cell.setForeground(QColor(MUTED))
                self.table.setItem(row, column, cell)
            if rule.id == selected_id:
                self.table.selectRow(row)

        self.table.setVisible(bool(rules))
        self.empty_label.setVisible(not rules)
        self._update_buttons()

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        item = self.table.item(row, DESCRIPTION) if row >= 0 else None
        return item.data(_ID_ROLE) if item and item.isSelected() else None

    def _selected(self) -> RecurringExpense | None:
        return self._rules.get(self._selected_id())

    def _update_buttons(self) -> None:
        rule = self._selected()
        for button in (self.edit_button, self.pause_button, self.delete_button):
            button.setEnabled(rule is not None)
        self.pause_button.setText("Resume" if rule and not rule.is_active else "Pause")

    def select_rule(self, rule_id: int) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, DESCRIPTION).data(_ID_ROLE) == rule_id:
                self.table.selectRow(row)
                return

    def add_rule(self) -> None:
        self._run_dialog(RecurringDialog(self._ctx, None, self))

    def edit_rule(self, *_args) -> None:
        rule = self._selected()
        if rule is not None:
            self._run_dialog(RecurringDialog(self._ctx, rule, self))

    def _run_dialog(self, dialog: RecurringDialog) -> None:
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        rule_id = dialog.rule.id
        dialog.deleteLater()
        if accepted:
            self._after_change("Recurring expense saved", rule_id)

    def _after_change(self, message: str, rule_id: int | None = None) -> None:
        """Generate anything now due, refresh every tab and report what happened."""
        generated = self._ctx.recurring_service.generate_due(date.today())
        if generated:
            count = len(generated)
            message += f" — added {count} expense{'' if count == 1 else 's'}"
        self._ctx.data_changed.emit()
        if rule_id is not None:
            self.select_rule(rule_id)
        self._ctx.status_message.emit(message)

    def toggle_paused(self) -> None:
        rule = self._selected()
        if rule is None:
            return
        self._ctx.recurring_service.set_active(
            rule.id, not rule.is_active, date.today()
        )
        self._after_change("Paused" if rule.is_active else "Resumed", rule.id)

    def delete_rule(self) -> None:
        rule = self._selected()
        if rule is None:
            return
        name = rule.description or "this recurring expense"
        answer = QMessageBox.question(
            self,
            "Delete recurring expense",
            f"Delete “{name}”?\n\nExpenses it has already added are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._ctx.recurring_service.delete(rule.id)
        self._ctx.data_changed.emit()
        self._ctx.status_message.emit("Recurring expense deleted")

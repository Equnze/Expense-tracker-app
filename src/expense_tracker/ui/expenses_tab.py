"""Expenses tab: quick-add form, filters, table and totals footer."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.models import Expense
from expense_tracker.services.expenses import UndoError
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.expense_dialog import ExpenseDialog
from expense_tracker.ui.expense_form import QuickAddForm
from expense_tracker.ui.expense_table import ExpenseTableView
from expense_tracker.ui.filter_bar import FilterBar
from expense_tracker.ui.style import INPUT_HEIGHT


def _count_label(count: int) -> str:
    return f"{count:,} expense{'' if count == 1 else 's'}"


class ExpensesTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._visible_ids: set[int] = set()

        self.form = QuickAddForm(ctx)
        self.filters = FilterBar(ctx)
        self.table = ExpenseTableView()
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setToolTip("Delete the selected expenses (Delete)")
        self.undo_button = QPushButton("Undo delete")
        self.undo_button.setToolTip("Bring back the last deleted expenses (Ctrl+Z)")
        self.footer = QLabel("")
        self.footer.setObjectName("footerLabel")

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        for button in (self.delete_button, self.undo_button):
            button.setMinimumHeight(INPUT_HEIGHT)
            bottom.addWidget(button)
        bottom.addStretch(1)
        bottom.addWidget(self.footer)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(10)
        layout.addWidget(self.form)
        layout.addWidget(self.filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

        self.form.expense_added.connect(self._on_expense_added)
        self.filters.filters_changed.connect(self.refresh)
        self.table.edit_requested.connect(self.edit_expense)
        self.table.delete_requested.connect(self.delete_selected)
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        self.delete_button.clicked.connect(self.delete_selected)
        self.undo_button.clicked.connect(self.undo_delete)
        ctx.data_changed.connect(self.refresh)
        ctx.categories_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)

        self.refresh()

    def refresh(self) -> None:
        expenses = self._ctx.expenses.list(self.filters.current_filter())
        categories = {category.id: category for category in self._ctx.categories.list()}
        self.table.source_model.set_rows(expenses, categories, self._ctx.currency)
        self._visible_ids = {expense.id for expense in expenses}
        total = sum(expense.amount_cents for expense in expenses)
        self.footer.setText(
            f"{_count_label(len(expenses))}   ·   Total {self._ctx.money(total)}"
        )
        self._update_buttons()

    def edit_expense(self, expense_id: int) -> None:
        expense = self._ctx.expenses.get(expense_id)
        if expense is None:
            return
        dialog = ExpenseDialog(self._ctx, expense, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._ctx.expense_service.update(dialog.expense)
            self._ctx.data_changed.emit()
            self._ctx.status_message.emit("Expense updated")

    def delete_selected(self) -> None:
        ids = self.table.selected_ids()
        if not ids:
            self._ctx.status_message.emit("Select one or more expenses to delete")
            return
        what = "this expense" if len(ids) == 1 else f"these {len(ids)} expenses"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Delete expenses")
        box.setText(f"Delete {what}?")
        box.setInformativeText("You can undo this with Ctrl+Z.")
        delete = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(delete)
        box.exec()
        if box.clickedButton() is not delete:
            return

        count = self._ctx.expense_service.delete(ids)
        self._ctx.data_changed.emit()
        self._ctx.status_message.emit(
            f"Deleted {_count_label(count)} — press Ctrl+Z to undo"
        )
        self.table.setFocus()

    def undo_delete(self) -> None:
        if not self._ctx.expense_service.can_undo_delete:
            self._ctx.status_message.emit("Nothing to undo")
            return
        try:
            count = self._ctx.expense_service.undo_delete()
        except UndoError as exc:
            self._update_buttons()
            self._ctx.status_message.emit(str(exc))
            return
        self._ctx.data_changed.emit()
        self._ctx.status_message.emit(f"Restored {_count_label(count)}")

    def _on_expense_added(self, expense: Expense) -> None:
        message = "Expense added"
        if expense.id not in self._visible_ids:
            message += " (hidden by the current filters)"
        self._ctx.status_message.emit(message)

    def _update_buttons(self) -> None:
        self.delete_button.setEnabled(bool(self.table.selected_ids()))
        self.undo_button.setEnabled(self._ctx.expense_service.can_undo_delete)

"""Expenses tab: quick-add form, filters, table and totals footer."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.models import Expense
from expense_tracker.services.expenses import UndoError
from expense_tracker.services.exporter import export_expenses
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.expense_dialog import ExpenseDialog
from expense_tracker.ui.expense_form import QuickAddForm
from expense_tracker.ui.expense_table import ExpenseTableView
from expense_tracker.ui.filter_bar import FilterBar
from expense_tracker.ui.import_wizard import ImportWizard
from expense_tracker.ui.style import INPUT_HEIGHT
from expense_tracker.ui.toast import NEAR, OVER

EXPORT_DIR_KEY = "last_export_dir"
EXCEL_FILTER = "Excel workbook (*.xlsx)"
CSV_FILTER = "CSV file (*.csv)"

log = logging.getLogger(__name__)


def _count_label(count: int) -> str:
    return f"{count:,} expense{'' if count == 1 else 's'}"


class ExpensesTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._visible_ids: set[int] = set()
        self._expenses: list[Expense] = []

        self.form = QuickAddForm(ctx)
        self.filters = FilterBar(ctx)
        self.table = ExpenseTableView()
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setToolTip("Delete the selected expenses (Delete)")
        self.undo_button = QPushButton("Undo delete")
        self.undo_button.setToolTip("Bring back the last deleted expenses (Ctrl+Z)")
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip(
            "Save the expenses shown in the list as an Excel or CSV file"
        )
        self.import_button = QPushButton("Import CSV…")
        self.import_button.setToolTip("Add expenses from a bank statement CSV file")
        self.footer = QLabel("")
        self.footer.setObjectName("footerLabel")

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        for button in (
            self.delete_button,
            self.undo_button,
            self.export_button,
            self.import_button,
        ):
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
        self.export_button.clicked.connect(self.export_filtered)
        self.import_button.clicked.connect(self.import_csv)
        ctx.data_changed.connect(self.refresh)
        ctx.categories_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)

        self.refresh()

    def refresh(self) -> None:
        expenses = self._ctx.expenses.list(self.filters.current_filter())
        categories = {category.id: category for category in self._ctx.categories.list()}
        self.table.source_model.set_rows(expenses, categories, self._ctx.currency)
        self._expenses = expenses
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
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        dialog.deleteLater()
        if accepted:
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
        confirmed = box.clickedButton() is delete
        box.deleteLater()
        if not confirmed:
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

    def import_csv(self) -> None:
        """Run the CSV import wizard."""
        wizard = ImportWizard(self._ctx, self)
        wizard.exec()
        imported = wizard.summary.imported
        wizard.deleteLater()
        if imported:
            self._ctx.status_message.emit(f"Imported {_count_label(imported)}")

    def export_filtered(self) -> None:
        """Ask where to save, then export the expenses currently shown."""
        if not self._expenses:
            self._ctx.status_message.emit("There are no expenses to export")
            return
        folder = self._ctx.settings.get(EXPORT_DIR_KEY) or str(Path.home() / "Documents")
        suggested = Path(folder) / f"expenses-{date.today().isoformat()}.xlsx"
        chosen, selected_filter = QFileDialog.getSaveFileName(
            self, "Export expenses", str(suggested), f"{EXCEL_FILTER};;{CSV_FILTER}"
        )
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() not in (".xlsx", ".csv"):
            path = path.with_name(
                path.name + (".csv" if selected_filter == CSV_FILTER else ".xlsx")
            )
        self.export_to(path)

    def export_to(self, path: Path) -> bool:
        """Export the expenses currently shown to ``path``. Returns success."""
        categories = {category.id: category for category in self._ctx.categories.list()}
        try:
            export_expenses(path, self._expenses, categories, self._ctx.currency)
        except OSError:
            log.exception("Could not export to %s", path)
            QMessageBox.warning(
                self,
                "Export failed",
                f"Couldn't save {path.name}.\n\nIf the file is open in another "
                "program, close it and try again, or choose a different folder.",
            )
            return False
        self._ctx.settings.set(EXPORT_DIR_KEY, str(path.parent))
        count = len(self._expenses)
        self._ctx.status_message.emit(
            f"Exported {count:,} row{'' if count == 1 else 's'} to {path.name}"
        )
        return True

    def _on_expense_added(self, expense: Expense) -> None:
        message = "Expense added"
        if expense.id not in self._visible_ids:
            message += " (hidden by the current filters)"
        self._ctx.status_message.emit(message)
        for alert in self._ctx.budget_service.alerts_for(expense):
            self._ctx.notification.emit(
                "Budget alert",
                alert.message(self._ctx.money),
                OVER if alert.is_over else NEAR,
            )

    def _update_buttons(self) -> None:
        self.delete_button.setEnabled(bool(self.table.selected_ids()))
        self.undo_button.setEnabled(self._ctx.expense_service.can_undo_delete)
        self.export_button.setEnabled(bool(self._expenses))

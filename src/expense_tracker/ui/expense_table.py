"""Expense table: model, sorting and the view's keyboard/mouse handling."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPoint,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableView

from expense_tracker.models import Category, Expense
from expense_tracker.ui.widgets import color_icon
from expense_tracker.utils.dates import format_display
from expense_tracker.utils.money import format_cents

DATE, CATEGORY, DESCRIPTION, PAYMENT, AMOUNT = range(5)
HEADERS = ["Date", "Category", "Description", "Payment Method", "Amount"]
SORT_ROLE = Qt.ItemDataRole.UserRole + 1


class ExpenseTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._expenses: list[Expense] = []
        self._categories: dict[int, Category] = {}
        self._currency = "$"

    def set_rows(
        self, expenses: list[Expense], categories: dict[int, Category], currency: str
    ) -> None:
        self.beginResetModel()
        self._expenses = expenses
        self._categories = categories
        self._currency = currency
        self.endResetModel()

    def expense_at(self, row: int) -> Expense:
        return self._expenses[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._expenses)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return HEADERS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(self._alignment(section))
        return None

    @staticmethod
    def _alignment(column: int) -> Qt.AlignmentFlag:
        horizontal = (
            Qt.AlignmentFlag.AlignRight
            if column == AMOUNT
            else Qt.AlignmentFlag.AlignLeft
        )
        return horizontal | Qt.AlignmentFlag.AlignVCenter

    def _category_name(self, expense: Expense) -> str:
        category = self._categories.get(expense.category_id)
        return category.name if category else ""

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        expense = self._expenses[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if column == DATE:
                return format_display(expense.date)
            if column == CATEGORY:
                return self._category_name(expense)
            if column == DESCRIPTION:
                return expense.description
            if column == PAYMENT:
                return expense.payment_method
            return format_cents(expense.amount_cents, self._currency)

        if role == SORT_ROLE:
            if column == DATE:
                # The id breaks ties so same-day expenses keep their entry order.
                return f"{expense.date.isoformat()}{expense.id:012d}"
            if column == CATEGORY:
                return self._category_name(expense).lower()
            if column == DESCRIPTION:
                return expense.description.lower()
            if column == PAYMENT:
                return expense.payment_method.lower()
            return expense.amount_cents

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(self._alignment(column))

        if role == Qt.ItemDataRole.DecorationRole and column == CATEGORY:
            category = self._categories.get(expense.category_id)
            return color_icon(category.color) if category else None

        if role == Qt.ItemDataRole.ToolTipRole and column == DESCRIPTION:
            if expense.recurring_id is not None:
                return f"{expense.description}\n(Added by a recurring expense)".strip()
            return expense.description or None

        return None


class ExpenseTableView(QTableView):
    """Sortable, multi-select table that asks its owner to edit or delete rows."""

    edit_requested = Signal(int)
    delete_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.source_model = ExpenseTableModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self.source_model)
        self._proxy.setSortRole(SORT_ROLE)
        self.setModel(self._proxy)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTabKeyNavigation(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        for column, width in ((DATE, 120), (CATEGORY, 200), (PAYMENT, 150), (AMOUNT, 130)):
            self.setColumnWidth(column, width)

        self.setSortingEnabled(True)
        self.sortByColumn(DATE, Qt.SortOrder.DescendingOrder)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_clicked)

    def selected_ids(self) -> list[int]:
        rows = self.selectionModel().selectedRows()
        return [
            self.source_model.expense_at(self._proxy.mapToSource(index).row()).id
            for index in rows
        ]

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                self._on_double_clicked(index)
                return
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        source = self._proxy.mapToSource(index)
        self.edit_requested.emit(self.source_model.expense_at(source.row()).id)

    def _show_context_menu(self, position: QPoint) -> None:
        index = self.indexAt(position)
        if not index.isValid():
            return
        count = len(self.selected_ids())
        menu = QMenu(self)
        edit = menu.addAction("Edit…")
        edit.setEnabled(count == 1)
        delete = menu.addAction("Delete" if count == 1 else f"Delete {count} expenses")
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is edit:
            self._on_double_clicked(index)
        elif chosen is delete:
            self.delete_requested.emit()

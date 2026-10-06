"""Budgets tab: a progress bar per budget for the current month."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.services.budgets import OVER, BudgetError, BudgetStatus
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import DANGER, INPUT_HEIGHT, MUTED, SUCCESS
from expense_tracker.ui.widgets import color_icon, set_invalid
from expense_tracker.utils.dates import month_label
from expense_tracker.utils.money import MoneyError, format_plain, parse_cents

OVERALL_CHOICE = "Overall (all spending)"


class BudgetDialog(QDialog):
    """Sets the monthly limit for a category or for all spending."""

    def __init__(
        self, ctx: AppContext, category_id: int | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setWindowTitle("Set budget")
        self.setMinimumWidth(400)

        self.target = QComboBox()
        self.target.setMinimumHeight(INPUT_HEIGHT)
        self.target.addItem(OVERALL_CHOICE, None)
        for category in ctx.categories.list():
            has_budget = ctx.budget_service.limit_for(category.id) is not None
            if category.is_archived and not has_budget:
                continue
            self.target.addItem(color_icon(category.color), category.name, category.id)
        self.target.setCurrentIndex(max(self.target.findData(category_id), 0))
        self.amount = QLineEdit()
        self.amount.setMinimumHeight(INPUT_HEIGHT)
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.amount.setPlaceholderText("0.00")
        self.error = QLabel("")
        self.error.setObjectName("errorLabel")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        form.addRow("Budget for", self.target)
        form.addRow(f"Monthly limit ({ctx.currency})", self.amount)
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

        self.target.currentIndexChanged.connect(self._show_existing_limit)
        self.amount.textChanged.connect(self._clear_error)
        self._show_existing_limit()
        self.amount.setFocus()

    def _show_existing_limit(self) -> None:
        limit = self._ctx.budget_service.limit_for(self.target.currentData())
        self.amount.setText(format_plain(limit) if limit else "")
        self.amount.selectAll()

    def _clear_error(self) -> None:
        self.error.setText("")
        set_invalid(self.amount, False)

    def accept(self) -> None:
        try:
            cents = parse_cents(self.amount.text(), self._ctx.currency)
            self._ctx.budget_service.set_limit(self.target.currentData(), cents)
        except (MoneyError, BudgetError) as exc:
            self.error.setText(str(exc))
            set_invalid(self.amount, True)
            self.amount.setFocus()
            return
        super().accept()


class BudgetRow(QFrame):
    """One budget: name, progress bar, spent / limit and what is left."""

    def __init__(self, status: BudgetStatus, ctx: AppContext) -> None:
        super().__init__()
        self.setObjectName("card")
        self.status = status
        money = ctx.money

        icon = QLabel()
        icon.setPixmap(color_icon(status.color).pixmap(14, 14))
        self.name = QLabel(status.name)
        self.name.setObjectName("budgetName")
        self.percent = QLabel(f"{int(status.percent)}%")
        self.percent.setObjectName("budgetPercent")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(min(100, int(status.percent)))
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setProperty("level", status.level)

        self.spent = QLabel(
            f"{money(status.spent_cents)} of {money(status.limit_cents)}"
        )
        if status.level == OVER:
            remaining_text = f"{money(-status.remaining_cents)} over"
            remaining_color = DANGER
        else:
            remaining_text = f"{money(status.remaining_cents)} left"
            remaining_color = SUCCESS if status.remaining_cents else MUTED
        self.remaining = QLabel(remaining_text)
        self.remaining.setStyleSheet(f"color: {remaining_color}; font-weight: 600;")

        self.edit_button = QPushButton("Edit…")
        self.remove_button = QPushButton("Remove")

        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(icon)
        title.addWidget(self.name)
        title.addStretch(1)
        title.addWidget(self.percent)
        amounts = QHBoxLayout()
        amounts.addWidget(self.spent)
        amounts.addStretch(1)
        amounts.addWidget(self.remaining)

        layout = QGridLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(6)
        layout.addLayout(title, 0, 0)
        layout.addWidget(self.bar, 1, 0)
        layout.addLayout(amounts, 2, 0)
        layout.addWidget(self.edit_button, 0, 1, 3, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.remove_button, 0, 2, 3, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.setColumnStretch(0, 1)


class BudgetsTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.rows: list[BudgetRow] = []

        self.title = QLabel()
        self.title.setObjectName("monthLabel")
        self.add_button = QPushButton("Set budget…")
        self.add_button.setObjectName("primaryButton")
        self.add_button.setMinimumHeight(INPUT_HEIGHT)
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.add_button)

        hint = QLabel(
            "Green is under 75% of the limit, amber is 75–100%, red is over. "
            "Budgets reset at the start of each month."
        )
        hint.setObjectName("hintLabel")

        self.empty_label = QLabel(
            "No budgets yet.\nSet a monthly limit for a category, or for all your "
            "spending, to see how you are doing here."
        )
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        content = QWidget()
        self._rows_layout = QVBoxLayout(content)
        self._rows_layout.setContentsMargins(0, 0, 6, 0)
        self._rows_layout.setSpacing(10)
        self._rows_layout.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 10, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(hint)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self.empty_label, 1)

        self.add_button.clicked.connect(lambda: self.edit_budget(None))
        ctx.data_changed.connect(self.refresh)
        ctx.categories_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        today = date.today()
        self.title.setText(f"Budgets for {month_label(today.year, today.month)}")
        for row in self.rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows = []
        for status in self._ctx.budget_service.statuses(today.year, today.month):
            row = BudgetRow(status, self._ctx)
            row.edit_button.clicked.connect(
                lambda _=False, cid=status.category_id: self.edit_budget(cid)
            )
            row.remove_button.clicked.connect(
                lambda _=False, s=status: self.remove_budget(s)
            )
            self._rows_layout.insertWidget(len(self.rows), row)
            self.rows.append(row)
        self._scroll.setVisible(bool(self.rows))
        self.empty_label.setVisible(not self.rows)

    def edit_budget(self, category_id: int | None) -> None:
        dialog = BudgetDialog(self._ctx, category_id, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        dialog.deleteLater()
        if accepted:
            self.refresh()
            self._ctx.status_message.emit("Budget saved")

    def remove_budget(self, status: BudgetStatus) -> None:
        answer = QMessageBox.question(
            self,
            "Remove budget",
            f"Remove the {status.name} budget? Your expenses are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._ctx.budget_service.remove(status.category_id)
        self.refresh()
        self._ctx.status_message.emit(f"Removed the {status.name} budget")

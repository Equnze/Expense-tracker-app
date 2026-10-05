"""Dashboard tab: monthly summary cards and category breakdown."""

from __future__ import annotations

from datetime import date
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.services.summary import MonthSummary, month_summary
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import DANGER, INPUT_HEIGHT, MUTED, SUCCESS
from expense_tracker.ui.widgets import Card, color_icon
from expense_tracker.utils.dates import month_label, shift_month

_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class DashboardTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        today = date.today()
        self._year, self._month = today.year, today.month

        self.previous_button = QToolButton()
        self.previous_button.setText("‹")
        self.previous_button.setToolTip("Previous month")
        self.next_button = QToolButton()
        self.next_button.setText("›")
        self.next_button.setToolTip("Next month")
        for button in (self.previous_button, self.next_button):
            button.setObjectName("monthButton")
            button.setFixedSize(INPUT_HEIGHT, INPUT_HEIGHT)
        self.month_label = QLabel()
        self.month_label.setObjectName("monthLabel")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setMinimumWidth(190)
        self.today_button = QPushButton("This month")
        self.today_button.setMinimumHeight(INPUT_HEIGHT)

        selector = QHBoxLayout()
        selector.setSpacing(8)
        selector.addWidget(self.previous_button)
        selector.addWidget(self.month_label)
        selector.addWidget(self.next_button)
        selector.addSpacing(8)
        selector.addWidget(self.today_button)
        selector.addStretch(1)

        self.total_card = Card("Total spent")
        self.change_card = Card("Compared to last month")
        self.average_card = Card("Average per day")
        self.top_card = Card("Top categories")
        self.top_card.value.hide()
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for card in (self.total_card, self.change_card, self.average_card):
            card.setMinimumHeight(118)
            cards.addWidget(card, 1)
        cards.addWidget(self.top_card, 1)

        breakdown_title = QLabel("Spending by category")
        breakdown_title.setObjectName("sectionTitle")
        self.breakdown = QTableWidget(0, 3)
        self.breakdown.setHorizontalHeaderLabels(["Category", "Amount", "% of total"])
        self.breakdown.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.breakdown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.breakdown.setAlternatingRowColors(True)
        self.breakdown.setShowGrid(False)
        self.breakdown.verticalHeader().setVisible(False)
        self.breakdown.verticalHeader().setDefaultSectionSize(34)
        header = self.breakdown.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.breakdown.setColumnWidth(1, 160)
        self.breakdown.setColumnWidth(2, 130)
        self.breakdown.horizontalHeaderItem(0).setTextAlignment(_LEFT)
        for column in (1, 2):
            self.breakdown.horizontalHeaderItem(column).setTextAlignment(_RIGHT)
        self.empty_label = QLabel()
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)
        layout.addLayout(selector)
        layout.addLayout(cards)
        layout.addSpacing(4)
        layout.addWidget(breakdown_title)
        layout.addWidget(self.breakdown, 1)
        layout.addWidget(self.empty_label, 1)

        self.previous_button.clicked.connect(lambda: self._shift(-1))
        self.next_button.clicked.connect(lambda: self._shift(1))
        self.today_button.clicked.connect(self._go_to_today)
        ctx.data_changed.connect(self.refresh)
        ctx.categories_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)

        self.refresh()

    def _shift(self, delta: int) -> None:
        self._year, self._month = shift_month(self._year, self._month, delta)
        self.refresh()

    def _go_to_today(self) -> None:
        today = date.today()
        self._year, self._month = today.year, today.month
        self.refresh()

    def refresh(self) -> None:
        today = date.today()
        summary = month_summary(
            self._ctx.expenses, self._ctx.categories, self._year, self._month, today
        )
        self.month_label.setText(month_label(self._year, self._month))
        self.today_button.setEnabled(
            (self._year, self._month) != (today.year, today.month)
        )
        self._show_cards(summary, today)
        self._show_breakdown(summary)

    def _show_cards(self, summary: MonthSummary, today: date) -> None:
        money = self._ctx.money
        count = sum(1 for _ in summary.breakdown)
        self.total_card.value.setText(money(summary.total_cents))
        self.total_card.detail.setText(
            f"across {count} categor{'y' if count == 1 else 'ies'}" if count else ""
        )

        change = summary.change_cents
        previous_name = month_label(*shift_month(summary.year, summary.month, -1))
        if change == 0:
            color, arrow = MUTED, ""
        elif change > 0:
            color, arrow = DANGER, "▲ "
        else:
            color, arrow = SUCCESS, "▼ "
        sign = "+" if change > 0 else "-" if change < 0 else ""
        self.change_card.value.setText(f"{arrow}{sign}{money(abs(change))}")
        self.change_card.value.setStyleSheet(f"color: {color};")
        if summary.change_percent is None:
            detail = f"Nothing spent in {escape(previous_name)}"
        else:
            detail = (
                f'<span style="color:{color};">{summary.change_percent:+.1f}%</span>'
                f" vs {money(summary.previous_total_cents)} in {escape(previous_name)}"
            )
        self.change_card.detail.setText(detail)

        self.average_card.value.setText(money(summary.average_daily_cents))
        is_current = (summary.year, summary.month) == (today.year, today.month)
        self.average_card.detail.setText(
            f"over the first {today.day} day{'' if today.day == 1 else 's'}"
            if is_current
            else "over the whole month"
        )

        if summary.top_categories:
            lines = [
                f'<span style="color:{top.color};">●</span>&nbsp; '
                f"<b>{escape(top.name)}</b> &nbsp;{money(top.total_cents)}"
                for top in summary.top_categories
            ]
            text = "<br>".join(lines)
            self.top_card.detail.setText(
                f'<div style="line-height:150%; color:#1F2328;">{text}</div>'
            )
        else:
            self.top_card.detail.setText("No spending yet")

    def _show_breakdown(self, summary: MonthSummary) -> None:
        has_rows = bool(summary.breakdown)
        self.breakdown.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.empty_label.setText(
            f"No expenses in {month_label(summary.year, summary.month)}."
        )
        self.breakdown.setRowCount(len(summary.breakdown))
        for row, entry in enumerate(summary.breakdown):
            name = QTableWidgetItem(color_icon(entry.color), entry.name)
            amount = QTableWidgetItem(self._ctx.money(entry.total_cents))
            amount.setTextAlignment(_RIGHT)
            percent = QTableWidgetItem(f"{entry.percent:.1f}%")
            percent.setTextAlignment(_RIGHT)
            for column, item in enumerate((name, amount, percent)):
                self.breakdown.setItem(row, column, item)

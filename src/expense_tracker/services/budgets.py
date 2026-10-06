"""Monthly budgets: limits, progress and alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from expense_tracker.db.repositories import (
    BudgetRepository,
    CategoryRepository,
    ExpenseRepository,
)
from expense_tracker.models import Expense
from expense_tracker.utils.dates import month_bounds

OVERALL_NAME = "Overall"
OVERALL_COLOR = "#2F6FED"

OK = "ok"  # under 75% of the limit
WARNING = "warning"  # 75% to 100%
OVER = "over"  # more than 100%

NEAR_LIMIT_PERCENT = 90


class BudgetError(ValueError):
    """Raised when a budget is not valid. The message is user-facing."""


@dataclass
class BudgetStatus:
    """How one budget is doing in a given month."""

    category_id: int | None  # None for the overall budget
    name: str
    color: str
    limit_cents: int
    spent_cents: int

    @property
    def remaining_cents(self) -> int:
        """Money left this month; negative once the limit is exceeded."""
        return self.limit_cents - self.spent_cents

    @property
    def percent(self) -> float:
        return self.spent_cents / self.limit_cents * 100

    @property
    def level(self) -> str:
        if self.spent_cents > self.limit_cents:
            return OVER
        if self.spent_cents * 100 >= 75 * self.limit_cents:
            return WARNING
        return OK


@dataclass
class BudgetAlert:
    """A budget that an expense has just pushed near or over its limit."""

    status: BudgetStatus
    is_over: bool

    def message(self, money: Callable[[int], str]) -> str:
        status = self.status
        subject = (
            "Your overall budget" if status.category_id is None else status.name
        )
        if self.is_over:
            return (
                f"{subject} is over its {money(status.limit_cents)} budget by "
                f"{money(-status.remaining_cents)}."
            )
        return (
            f"{subject} has used {int(status.percent)}% of its "
            f"{money(status.limit_cents)} budget; {money(status.remaining_cents)} left."
        )


class BudgetService:
    def __init__(
        self,
        budgets: BudgetRepository,
        categories: CategoryRepository,
        expenses: ExpenseRepository,
    ) -> None:
        self._budgets = budgets
        self._categories = categories
        self._expenses = expenses

    def limit_for(self, category_id: int | None) -> int | None:
        budget = self._budgets.get(category_id)
        return budget.monthly_limit_cents if budget else None

    def set_limit(self, category_id: int | None, monthly_limit_cents: int) -> None:
        """Set the monthly limit for a category, or the overall one for None."""
        if monthly_limit_cents <= 0:
            raise BudgetError("The limit must be greater than zero.")
        self._budgets.set(category_id, monthly_limit_cents)

    def remove(self, category_id: int | None) -> None:
        self._budgets.delete(category_id)

    def statuses(self, year: int, month: int) -> list[BudgetStatus]:
        """Return every budget's progress for a month: overall first, then by name."""
        start, end = month_bounds(year, month)
        spent_by_category = dict(self._expenses.totals_by_category(start, end))
        categories = {category.id: category for category in self._categories.list()}

        overall: list[BudgetStatus] = []
        per_category: list[BudgetStatus] = []
        for budget in self._budgets.list():
            if budget.category_id is None:
                overall.append(
                    BudgetStatus(
                        None,
                        OVERALL_NAME,
                        OVERALL_COLOR,
                        budget.monthly_limit_cents,
                        sum(spent_by_category.values()),
                    )
                )
                continue
            category = categories.get(budget.category_id)
            if category is None:
                continue
            per_category.append(
                BudgetStatus(
                    category.id,
                    category.name,
                    category.color,
                    budget.monthly_limit_cents,
                    spent_by_category.get(category.id, 0),
                )
            )
        per_category.sort(key=lambda status: status.name.casefold())
        return overall + per_category

    def alerts_for(self, expense: Expense) -> list[BudgetAlert]:
        """Return alerts for budgets that this just-saved expense pushed past 90%
        or over the limit. A budget that was already past the mark stays quiet."""
        alerts = []
        for status in self.statuses(expense.date.year, expense.date.month):
            if status.category_id not in (None, expense.category_id):
                continue
            limit, after = status.limit_cents, status.spent_cents
            before = after - expense.amount_cents
            if before <= limit < after:
                alerts.append(BudgetAlert(status, is_over=True))
            elif (
                before * 100 < NEAR_LIMIT_PERCENT * limit <= after * 100
                and after <= limit
            ):
                alerts.append(BudgetAlert(status, is_over=False))
        return alerts

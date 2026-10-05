"""Monthly dashboard figures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from expense_tracker.db.repositories import CategoryRepository, ExpenseRepository
from expense_tracker.utils.dates import days_in_month, month_bounds, shift_month


@dataclass
class CategoryTotal:
    category_id: int
    name: str
    color: str
    total_cents: int
    percent: float


@dataclass
class MonthSummary:
    year: int
    month: int
    total_cents: int = 0
    previous_total_cents: int = 0
    # None when last month had no spending, so a percentage is meaningless.
    change_percent: float | None = None
    average_daily_cents: int = 0
    breakdown: list[CategoryTotal] = field(default_factory=list)

    @property
    def change_cents(self) -> int:
        return self.total_cents - self.previous_total_cents

    @property
    def top_categories(self) -> list[CategoryTotal]:
        return self.breakdown[:3]


def _divide_rounded(numerator: int, denominator: int) -> int:
    """Integer division rounding half up, for non-negative values."""
    return (2 * numerator + denominator) // (2 * denominator)


def month_summary(
    expenses: ExpenseRepository,
    categories: CategoryRepository,
    year: int,
    month: int,
    today: date,
) -> MonthSummary:
    """Summarise one month's spending.

    The daily average for the current month divides by the days elapsed so far;
    other months divide by their full length.
    """
    start, end = month_bounds(year, month)
    previous_start, previous_end = month_bounds(*shift_month(year, month, -1))

    summary = MonthSummary(year=year, month=month)
    summary.total_cents = expenses.total_between(start, end)
    summary.previous_total_cents = expenses.total_between(previous_start, previous_end)
    if summary.previous_total_cents:
        summary.change_percent = (
            summary.change_cents / summary.previous_total_cents * 100
        )

    is_current_month = (year, month) == (today.year, today.month)
    days = today.day if is_current_month else days_in_month(year, month)
    summary.average_daily_cents = _divide_rounded(summary.total_cents, days)

    by_id = {category.id: category for category in categories.list()}
    for category_id, total in expenses.totals_by_category(start, end):
        category = by_id[category_id]
        summary.breakdown.append(
            CategoryTotal(
                category_id=category_id,
                name=category.name,
                color=category.color,
                total_cents=total,
                percent=total / summary.total_cents * 100,
            )
        )
    return summary

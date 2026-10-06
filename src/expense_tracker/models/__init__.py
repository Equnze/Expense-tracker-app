"""Plain dataclasses for the app's records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

PAYMENT_METHODS = ["Cash", "Debit Card", "Credit Card", "Bank Transfer", "Other"]

MONTHLY = "monthly"
WEEKLY = "weekly"
YEARLY = "yearly"
FREQUENCIES = [MONTHLY, WEEKLY, YEARLY]


@dataclass
class Category:
    id: int
    name: str
    color: str
    is_archived: bool = False


@dataclass
class Expense:
    amount_cents: int
    date: date
    category_id: int
    description: str = ""
    payment_method: str = ""
    tags: str = ""
    recurring_id: int | None = None
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ExpenseFilter:
    """Criteria for listing expenses. Unset fields do not restrict the result."""

    start_date: date | None = None
    end_date: date | None = None
    category_ids: set[int] = field(default_factory=set)
    payment_method: str | None = None
    search: str = ""


@dataclass
class Budget:
    """A monthly spending limit. ``category_id`` is None for the overall budget."""

    category_id: int | None
    monthly_limit_cents: int
    id: int | None = None


@dataclass
class RecurringExpense:
    """A rule that generates an expense on a schedule.

    Monthly rules fall on ``day_of_month`` (the last day in shorter months);
    weekly and yearly rules repeat from ``start_date``.
    """

    amount_cents: int
    category_id: int
    frequency: str
    start_date: date
    description: str = ""
    payment_method: str = ""
    day_of_month: int | None = None
    end_date: date | None = None
    last_generated_date: date | None = None
    is_active: bool = True
    id: int | None = None

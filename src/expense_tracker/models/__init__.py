"""Plain dataclasses for the app's records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

PAYMENT_METHODS = ["Cash", "Debit Card", "Credit Card", "Bank Transfer", "Other"]


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

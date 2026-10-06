"""Recurring expenses: schedules and generating the expenses that are due."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date, timedelta
from typing import Iterator

from expense_tracker.db.connection import transaction
from expense_tracker.db.repositories import ExpenseRepository, RecurringRepository
from expense_tracker.models import (
    FREQUENCIES,
    MONTHLY,
    WEEKLY,
    Expense,
    RecurringExpense,
)
from expense_tracker.utils.dates import days_in_month, shift_month


class RecurringError(ValueError):
    """Raised when a recurring rule is not valid. The message is user-facing."""


def _clamped(year: int, month: int, day: int) -> date:
    """Return the given day of a month, or the month's last day if it is shorter."""
    return date(year, month, min(day, days_in_month(year, month)))


def occurrences(rule: RecurringExpense) -> Iterator[date]:
    """Yield every date the rule falls on, from its start date onward, forever.

    Monthly rules fall on ``day_of_month``, moved to the last day in shorter
    months (the 31st becomes 30 April, 28 or 29 February). Weekly rules repeat
    every 7 days from the start date. Yearly rules repeat on the start date's
    anniversary (29 February becomes 28 February outside leap years).
    """
    start = rule.start_date
    if rule.frequency == WEEKLY:
        current = start
        while True:
            yield current
            current += timedelta(days=7)
    elif rule.frequency == MONTHLY:
        day = rule.day_of_month or start.day
        year, month = start.year, start.month
        while True:
            current = _clamped(year, month, day)
            if current >= start:
                yield current
            year, month = shift_month(year, month, 1)
    else:
        year = start.year
        while year <= date.max.year:
            yield _clamped(year, start.month, start.day)
            year += 1


def _period(rule: RecurringExpense, day: date) -> tuple:
    """Identify the month, year or day a date belongs to for the rule's frequency."""
    if rule.frequency == MONTHLY:
        return day.year, day.month
    if rule.frequency == WEEKLY:
        return (day.toordinal(),)
    return (day.year,)


def _pending(rule: RecurringExpense) -> Iterator[date]:
    """Yield the occurrences that have not been generated yet, up to the end date.

    A monthly rule generates at most once per calendar month (yearly: once per
    year), so moving its day later in an already-paid month cannot charge twice.
    """
    done = (
        _period(rule, rule.last_generated_date) if rule.last_generated_date else None
    )
    for day in occurrences(rule):
        if rule.end_date and day > rule.end_date:
            return
        if done is not None and _period(rule, day) <= done:
            continue
        yield day


def due_dates(rule: RecurringExpense, through: date) -> list[date]:
    """Return the not-yet-generated occurrences up to and including ``through``."""
    result = []
    for day in _pending(rule):
        if day > through:
            break
        result.append(day)
    return result


def next_due(rule: RecurringExpense) -> date | None:
    """Return the next date the rule will generate an expense, or None if ended."""
    return next(_pending(rule), None)


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def describe_schedule(rule: RecurringExpense) -> str:
    """Describe a rule's schedule in words, e.g. ``Monthly on the 5th``."""
    start = rule.start_date
    if rule.frequency == WEEKLY:
        return f"Weekly on {calendar.day_name[start.weekday()]}s"
    if rule.frequency == MONTHLY:
        day = rule.day_of_month or start.day
        text = f"Monthly on the {_ordinal(day)}"
        return text + " (or month end)" if day > 28 else text
    return f"Yearly on {start.day} {calendar.month_abbr[start.month]}"


class RecurringService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        recurring: RecurringRepository,
        expenses: ExpenseRepository,
    ) -> None:
        self._conn = conn
        self._recurring = recurring
        self._expenses = expenses

    @staticmethod
    def _validate(rule: RecurringExpense) -> None:
        if rule.amount_cents <= 0:
            raise RecurringError("Amount must be greater than zero.")
        if rule.frequency not in FREQUENCIES:
            raise RecurringError("Choose how often it repeats.")
        if rule.frequency == MONTHLY:
            if rule.day_of_month is None:
                rule.day_of_month = rule.start_date.day
            if not 1 <= rule.day_of_month <= 31:
                raise RecurringError("The day of the month must be between 1 and 31.")
        else:
            rule.day_of_month = None
        if rule.end_date and rule.end_date < rule.start_date:
            raise RecurringError("The end date can't be before the start date.")
        rule.description = rule.description.strip()

    def list(self) -> list[RecurringExpense]:
        return self._recurring.list()

    def add(self, rule: RecurringExpense) -> RecurringExpense:
        """Save a new rule. Call :meth:`generate_due` afterwards to add any
        expenses that are already due."""
        self._validate(rule)
        return self._recurring.add(rule)

    def update(self, rule: RecurringExpense) -> None:
        self._validate(rule)
        self._recurring.update(rule)

    def delete(self, rule_id: int) -> None:
        """Delete a rule. Expenses it already generated are kept."""
        self._recurring.delete(rule_id)

    def set_active(self, rule_id: int, active: bool, today: date) -> None:
        """Pause or resume a rule. Resuming does not back-fill the paused period:
        the rule carries on from today."""
        rule = self._recurring.get(rule_id)
        if rule is None:
            return
        if active and not rule.is_active:
            # Treat everything that came due while paused as already handled.
            missed = due_dates(rule, today - timedelta(days=1))
            if missed:
                rule.last_generated_date = missed[-1]
        rule.is_active = active
        self._recurring.update(rule)

    def generate_due(self, today: date) -> list[Expense]:
        """Create an expense for every occurrence of every active rule that has
        come due since it last generated, including missed ones. Returns them."""
        generated: list[Expense] = []
        with transaction(self._conn):
            for rule in self._recurring.list():
                if not rule.is_active:
                    continue
                dates = due_dates(rule, today)
                for day in dates:
                    generated.append(
                        self._expenses.add(
                            Expense(
                                amount_cents=rule.amount_cents,
                                date=day,
                                category_id=rule.category_id,
                                description=rule.description,
                                payment_method=rule.payment_method,
                                recurring_id=rule.id,
                            )
                        )
                    )
                if dates:
                    rule.last_generated_date = dates[-1]
                    self._recurring.update(rule)
        return generated

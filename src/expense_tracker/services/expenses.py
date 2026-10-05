"""Expense operations: add, edit, delete with undo, and remembered defaults."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Iterable

from expense_tracker.db.repositories import ExpenseRepository, SettingsRepository
from expense_tracker.models import Expense

LAST_CATEGORY_KEY = "last_category_id"
LAST_PAYMENT_METHOD_KEY = "last_payment_method"


class UndoError(Exception):
    """Raised when a delete cannot be undone. The message is user-facing."""


class ExpenseService:
    def __init__(
        self, expenses: ExpenseRepository, settings: SettingsRepository
    ) -> None:
        self._expenses = expenses
        self._settings = settings
        # Each entry is one delete action; undo is available until the app closes.
        self._deleted_batches: list[list[Expense]] = []

    def add(
        self,
        amount_cents: int,
        day: date,
        category_id: int,
        description: str = "",
        payment_method: str = "",
    ) -> Expense:
        expense = self._expenses.add(
            Expense(
                amount_cents=amount_cents,
                date=day,
                category_id=category_id,
                description=description.strip(),
                payment_method=payment_method,
            )
        )
        self._settings.set(LAST_CATEGORY_KEY, str(category_id))
        self._settings.set(LAST_PAYMENT_METHOD_KEY, payment_method)
        return expense

    def update(self, expense: Expense) -> None:
        expense.description = expense.description.strip()
        self._expenses.update(expense)

    def delete(self, expense_ids: Iterable[int]) -> int:
        """Delete expenses as one undoable action. Returns how many were deleted."""
        deleted = self._expenses.delete_many(expense_ids)
        if deleted:
            self._deleted_batches.append(deleted)
        return len(deleted)

    @property
    def can_undo_delete(self) -> bool:
        return bool(self._deleted_batches)

    def undo_delete(self) -> int:
        """Restore the most recently deleted expenses. Returns how many came back."""
        if not self._deleted_batches:
            return 0
        batch = self._deleted_batches.pop()
        try:
            self._expenses.restore(batch)
        except sqlite3.IntegrityError as exc:
            raise UndoError(
                "Couldn't undo: a category those expenses used no longer exists."
            ) from exc
        return len(batch)

    def last_category_id(self) -> int | None:
        value = self._settings.get(LAST_CATEGORY_KEY)
        return int(value) if value and value.isdigit() else None

    def last_payment_method(self) -> str | None:
        return self._settings.get(LAST_PAYMENT_METHOD_KEY)

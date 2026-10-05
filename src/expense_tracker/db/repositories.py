"""Repositories: all SQL lives here."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Iterable

from expense_tracker.db.connection import transaction
from expense_tracker.models import Category, Expense, ExpenseFilter
from expense_tracker.utils.dates import now_iso


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None or row["value"] is None else row["value"]

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class CategoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Category:
        return Category(
            id=row["id"],
            name=row["name"],
            color=row["color"] or "#90A4AE",
            is_archived=bool(row["is_archived"]),
        )

    def list(self, include_archived: bool = True) -> list[Category]:
        sql = "SELECT * FROM categories"
        if not include_archived:
            sql += " WHERE is_archived = 0"
        sql += " ORDER BY is_archived, name COLLATE NOCASE"
        return [self._from_row(row) for row in self._conn.execute(sql)]

    def get(self, category_id: int) -> Category | None:
        row = self._conn.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def find_by_name(self, name: str) -> Category | None:
        row = self._conn.execute(
            "SELECT * FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return self._from_row(row) if row else None

    def add(self, name: str, color: str) -> Category:
        cursor = self._conn.execute(
            "INSERT INTO categories (name, color) VALUES (?, ?)", (name, color)
        )
        return Category(id=cursor.lastrowid, name=name, color=color)

    def update(self, category_id: int, name: str, color: str) -> None:
        self._conn.execute(
            "UPDATE categories SET name = ?, color = ? WHERE id = ?",
            (name, color, category_id),
        )

    def set_archived(self, category_id: int, archived: bool) -> None:
        self._conn.execute(
            "UPDATE categories SET is_archived = ? WHERE id = ?",
            (int(archived), category_id),
        )

    def delete(self, category_id: int) -> None:
        self._conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def expense_count(self, category_id: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE category_id = ?", (category_id,)
        ).fetchone()[0]


class ExpenseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Expense:
        return Expense(
            id=row["id"],
            amount_cents=row["amount_cents"],
            date=date.fromisoformat(row["date"]),
            category_id=row["category_id"],
            description=row["description"] or "",
            payment_method=row["payment_method"] or "",
            tags=row["tags"] or "",
            recurring_id=row["recurring_id"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def add(self, expense: Expense) -> Expense:
        """Insert an expense and return it with its id and timestamps set."""
        now = now_iso()
        expense.created_at = expense.created_at or now
        expense.updated_at = now
        cursor = self._conn.execute(
            "INSERT INTO expenses (amount_cents, date, category_id, description, "
            "payment_method, tags, recurring_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                expense.amount_cents,
                expense.date.isoformat(),
                expense.category_id,
                expense.description,
                expense.payment_method,
                expense.tags,
                expense.recurring_id,
                expense.created_at,
                expense.updated_at,
            ),
        )
        expense.id = cursor.lastrowid
        return expense

    def update(self, expense: Expense) -> None:
        expense.updated_at = now_iso()
        self._conn.execute(
            "UPDATE expenses SET amount_cents = ?, date = ?, category_id = ?, "
            "description = ?, payment_method = ?, tags = ?, updated_at = ? WHERE id = ?",
            (
                expense.amount_cents,
                expense.date.isoformat(),
                expense.category_id,
                expense.description,
                expense.payment_method,
                expense.tags,
                expense.updated_at,
                expense.id,
            ),
        )

    def get(self, expense_id: int) -> Expense | None:
        row = self._conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def list(self, filters: ExpenseFilter | None = None) -> list[Expense]:
        """Return matching expenses, newest first."""
        filters = filters or ExpenseFilter()
        clauses: list[str] = []
        params: list[object] = []
        if filters.start_date:
            clauses.append("date >= ?")
            params.append(filters.start_date.isoformat())
        if filters.end_date:
            clauses.append("date <= ?")
            params.append(filters.end_date.isoformat())
        if filters.category_ids:
            ids = sorted(filters.category_ids)
            clauses.append(f"category_id IN ({','.join('?' * len(ids))})")
            params.extend(ids)
        if filters.payment_method:
            clauses.append("payment_method = ?")
            params.append(filters.payment_method)
        for term in filters.search.split():
            pattern = f"%{_escape_like(term)}%"
            clauses.append(
                "(IFNULL(description, '') LIKE ? ESCAPE '\\' "
                "OR IFNULL(tags, '') LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern])

        sql = "SELECT * FROM expenses"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date DESC, id DESC"
        return [self._from_row(row) for row in self._conn.execute(sql, params)]

    def delete_many(self, expense_ids: Iterable[int]) -> list[Expense]:
        """Delete the given expenses and return them so the delete can be undone."""
        deleted: list[Expense] = []
        with transaction(self._conn):
            for expense_id in expense_ids:
                expense = self.get(expense_id)
                if expense is None:
                    continue
                self._conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
                deleted.append(expense)
        return deleted

    def restore(self, expenses: Iterable[Expense]) -> None:
        """Re-insert previously deleted expenses with their original ids."""
        with transaction(self._conn):
            for expense in expenses:
                self._conn.execute(
                    "INSERT INTO expenses (id, amount_cents, date, category_id, "
                    "description, payment_method, tags, recurring_id, created_at, "
                    "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        expense.id,
                        expense.amount_cents,
                        expense.date.isoformat(),
                        expense.category_id,
                        expense.description,
                        expense.payment_method,
                        expense.tags,
                        expense.recurring_id,
                        expense.created_at,
                        expense.updated_at,
                    ),
                )

    def reassign_category(self, from_id: int, to_id: int) -> int:
        cursor = self._conn.execute(
            "UPDATE expenses SET category_id = ?, updated_at = ? WHERE category_id = ?",
            (to_id, now_iso(), from_id),
        )
        return cursor.rowcount

    def total_between(self, start: date, end: date) -> int:
        return self._conn.execute(
            "SELECT IFNULL(SUM(amount_cents), 0) FROM expenses "
            "WHERE date >= ? AND date <= ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()[0]

    def totals_by_category(self, start: date, end: date) -> list[tuple[int, int]]:
        """Return (category_id, total_cents) pairs, largest total first."""
        rows = self._conn.execute(
            "SELECT category_id, SUM(amount_cents) AS total FROM expenses "
            "WHERE date >= ? AND date <= ? GROUP BY category_id "
            "ORDER BY total DESC, category_id",
            (start.isoformat(), end.isoformat()),
        )
        return [(row["category_id"], row["total"]) for row in rows]

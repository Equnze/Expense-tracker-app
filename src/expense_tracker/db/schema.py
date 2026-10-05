"""Database schema and migrations.

To change the schema, append a new function to ``MIGRATIONS``. Never edit a
migration that has already shipped: existing databases have already run it.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

DEFAULT_CATEGORIES = [
    ("Food & Groceries", "#4CAF50"),
    ("Dining Out", "#FF7043"),
    ("Rent/Mortgage", "#5C6BC0"),
    ("Utilities", "#FFB300"),
    ("Transport", "#29B6F6"),
    ("Health", "#EC407A"),
    ("Shopping", "#AB47BC"),
    ("Entertainment", "#26A69A"),
    ("Subscriptions", "#7E57C2"),
    ("Travel", "#42A5F5"),
    ("Education", "#8D6E63"),
    ("Gifts", "#D4E157"),
    ("Other", "#90A4AE"),
]

DEFAULT_SETTINGS = {"currency_symbol": "$"}


def _migration_1(conn: sqlite3.Connection) -> None:
    """Initial schema with default categories and settings."""
    statements = [
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            color TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE recurring_expenses (
            id INTEGER PRIMARY KEY,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category_id INTEGER NOT NULL REFERENCES categories(id),
            description TEXT,
            payment_method TEXT,
            frequency TEXT NOT NULL,
            day_of_month INTEGER,
            start_date TEXT NOT NULL,
            end_date TEXT,
            last_generated_date TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            date TEXT NOT NULL,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            description TEXT,
            payment_method TEXT,
            tags TEXT,
            recurring_id INTEGER REFERENCES recurring_expenses(id) ON DELETE SET NULL,
            created_at TEXT,
            updated_at TEXT
        )
        """,
        "CREATE INDEX idx_expenses_date ON expenses(date)",
        "CREATE INDEX idx_expenses_category ON expenses(category_id)",
        """
        CREATE TABLE income (
            id INTEGER PRIMARY KEY,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            date TEXT NOT NULL,
            source TEXT,
            description TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            monthly_limit_cents INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """,
    ]
    for statement in statements:
        conn.execute(statement)
    conn.executemany(
        "INSERT INTO categories (name, color) VALUES (?, ?)", DEFAULT_CATEGORIES
    )
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)", DEFAULT_SETTINGS.items()
    )


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_migration_1]


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        return 0
    return row[0]


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any migrations the database has not seen yet, one transaction each."""
    current = schema_version(conn)
    if current > len(MIGRATIONS):
        raise RuntimeError(
            "This database was created by a newer version of Expense Tracker."
        )
    for version in range(current + 1, len(MIGRATIONS) + 1):
        conn.execute("BEGIN")
        try:
            MIGRATIONS[version - 1](conn)
            conn.execute("UPDATE schema_version SET version = ?", (version,))
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

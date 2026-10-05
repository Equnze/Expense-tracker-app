"""Shared application state passed to every tab and dialog."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QObject, Signal

from expense_tracker.db.repositories import (
    CategoryRepository,
    ExpenseRepository,
    SettingsRepository,
)
from expense_tracker.services.categories import CategoryService
from expense_tracker.services.expenses import ExpenseService
from expense_tracker.utils.money import format_cents

CURRENCY_KEY = "currency_symbol"


class AppContext(QObject):
    """Holds the repositories and services, and announces changes to the UI."""

    data_changed = Signal()
    categories_changed = Signal()
    settings_changed = Signal()
    status_message = Signal(str)

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__()
        self.conn = conn
        self.settings = SettingsRepository(conn)
        self.categories = CategoryRepository(conn)
        self.expenses = ExpenseRepository(conn)
        self.expense_service = ExpenseService(self.expenses, self.settings)
        self.category_service = CategoryService(conn, self.categories, self.expenses)

    @property
    def currency(self) -> str:
        return self.settings.get(CURRENCY_KEY, "$") or ""

    def money(self, cents: int) -> str:
        return format_cents(cents, self.currency)

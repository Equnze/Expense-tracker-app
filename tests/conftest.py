from __future__ import annotations

from datetime import date

import pytest

from expense_tracker.db.connection import open_database
from expense_tracker.db.repositories import (
    CategoryRepository,
    ExpenseRepository,
    SettingsRepository,
)
from expense_tracker.models import Expense
from expense_tracker.utils import paths


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Make sure no test can touch the real %APPDATA% database."""
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "appdata"))


@pytest.fixture
def conn(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def categories(conn):
    return CategoryRepository(conn)


@pytest.fixture
def expenses(conn):
    return ExpenseRepository(conn)


@pytest.fixture
def settings(conn):
    return SettingsRepository(conn)


@pytest.fixture
def make_expense(expenses, categories):
    """Factory that inserts an expense, looking the category up by name."""

    def _make(
        amount_cents=1000,
        day=date(2026, 10, 5),
        category="Other",
        description="",
        payment_method="Cash",
        tags="",
    ):
        category_id = categories.find_by_name(category).id
        return expenses.add(
            Expense(
                amount_cents=amount_cents,
                date=day,
                category_id=category_id,
                description=description,
                payment_method=payment_method,
                tags=tags,
            )
        )

    return _make

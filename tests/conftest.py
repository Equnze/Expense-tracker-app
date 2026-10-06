from __future__ import annotations

import os
from datetime import date

# UI tests run without a visible window.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

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


# --- UI fixtures ------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(qapp, conn):
    from expense_tracker.ui.context import AppContext

    return AppContext(conn)


@pytest.fixture
def window(ctx):
    from expense_tracker.ui.main_window import MainWindow

    main_window = MainWindow(ctx)
    main_window.show()
    yield main_window
    main_window.close()


@pytest.fixture
def statuses(ctx):
    messages = []
    ctx.status_message.connect(messages.append)
    return messages


@pytest.fixture
def confirm(monkeypatch):
    """Answer any QMessageBox by clicking its default button."""
    monkeypatch.setattr(QMessageBox, "exec", lambda box: box.defaultButton().click())

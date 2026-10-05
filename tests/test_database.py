import sqlite3
from datetime import date

import pytest

from expense_tracker.db import schema
from expense_tracker.db.connection import connect, open_database, transaction
from expense_tracker.models import Expense, ExpenseFilter


def test_first_launch_creates_tables_and_default_categories(conn, categories):
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "categories",
        "expenses",
        "income",
        "budgets",
        "recurring_expenses",
        "settings",
        "schema_version",
    } <= tables
    names = {category.name for category in categories.list()}
    assert names == {name for name, _ in schema.DEFAULT_CATEGORIES}
    assert len(names) == 13
    assert schema.schema_version(conn) == len(schema.MIGRATIONS)


def test_reopening_keeps_data_and_does_not_reseed(tmp_path):
    path = tmp_path / "again.db"
    first = open_database(path)
    first.execute("DELETE FROM categories WHERE name = 'Gifts'")
    first.close()

    second = open_database(path)
    count = second.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    second.close()
    assert count == 12


def test_new_migration_upgrades_existing_database(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    open_database(path).close()

    def add_notes_column(conn):
        conn.execute("ALTER TABLE expenses ADD COLUMN notes TEXT")

    monkeypatch.setattr(schema, "MIGRATIONS", [*schema.MIGRATIONS, add_notes_column])
    upgraded = open_database(path)
    columns = {row["name"] for row in upgraded.execute("PRAGMA table_info(expenses)")}
    assert "notes" in columns
    assert schema.schema_version(upgraded) == len(schema.MIGRATIONS)
    assert upgraded.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 13
    upgraded.close()


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "broken.db"
    open_database(path).close()

    def broken(conn):
        conn.execute("CREATE TABLE half_done (id INTEGER)")
        raise RuntimeError("boom")

    monkeypatch.setattr(schema, "MIGRATIONS", [*schema.MIGRATIONS, broken])
    with pytest.raises(RuntimeError):
        open_database(path)

    conn = connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "half_done" not in tables
    assert schema.schema_version(conn) == len(schema.MIGRATIONS) - 1
    conn.close()


def test_database_from_newer_version_is_refused(tmp_path):
    path = tmp_path / "newer.db"
    conn = open_database(path)
    conn.execute("UPDATE schema_version SET version = 999")
    conn.close()
    with pytest.raises(RuntimeError, match="newer version"):
        open_database(path)


def test_transaction_rolls_back_on_error(conn, settings):
    with pytest.raises(ValueError):
        with transaction(conn):
            settings.set("theme", "dark")
            raise ValueError
    assert settings.get("theme") is None


def test_settings_round_trip(settings):
    assert settings.get("currency_symbol") == "$"
    assert settings.get("missing", "fallback") == "fallback"
    settings.set("currency_symbol", "€")
    settings.set("currency_symbol", "£")
    assert settings.get("currency_symbol") == "£"


def test_expense_add_get_update(expenses, make_expense, categories):
    created = make_expense(1299, date(2026, 10, 5), "Dining Out", "Lunch", "Cash")
    assert created.id is not None and created.created_at

    loaded = expenses.get(created.id)
    assert loaded == created

    loaded.amount_cents = 1500
    loaded.description = "Late lunch"
    loaded.category_id = categories.find_by_name("Travel").id
    expenses.update(loaded)
    assert expenses.get(created.id).amount_cents == 1500
    assert expenses.get(created.id).description == "Late lunch"


def test_amount_must_be_positive(expenses, categories):
    other = categories.find_by_name("Other").id
    with pytest.raises(sqlite3.IntegrityError):
        expenses.add(Expense(amount_cents=0, date=date(2026, 1, 1), category_id=other))


def test_expense_requires_existing_category(expenses):
    with pytest.raises(sqlite3.IntegrityError):
        expenses.add(Expense(amount_cents=100, date=date(2026, 1, 1), category_id=9999))


def test_list_is_newest_first(expenses, make_expense):
    old = make_expense(day=date(2026, 9, 1))
    first_today = make_expense(day=date(2026, 10, 5))
    second_today = make_expense(day=date(2026, 10, 5))
    assert [e.id for e in expenses.list()] == [second_today.id, first_today.id, old.id]


def test_list_filters(expenses, make_expense, categories):
    groceries = make_expense(
        5000, date(2026, 10, 2), "Food & Groceries", "Weekly shop", "Debit Card"
    )
    coffee = make_expense(450, date(2026, 10, 3), "Dining Out", "Coffee", "Cash")
    flight = make_expense(
        30000, date(2026, 9, 20), "Travel", "Flight", "Credit Card", tags="vacation"
    )

    def ids(**criteria):
        return {e.id for e in expenses.list(ExpenseFilter(**criteria))}

    assert ids(start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)) == {
        groceries.id,
        coffee.id,
    }
    assert ids(end_date=date(2026, 9, 30)) == {flight.id}
    assert ids(start_date=date(2026, 10, 3), end_date=date(2026, 10, 3)) == {coffee.id}

    dining = categories.find_by_name("Dining Out").id
    travel = categories.find_by_name("Travel").id
    assert ids(category_ids={dining}) == {coffee.id}
    assert ids(category_ids={dining, travel}) == {coffee.id, flight.id}
    assert ids(payment_method="Cash") == {coffee.id}
    assert ids(category_ids={dining}, payment_method="Credit Card") == set()


def test_search_matches_description_and_tags(expenses, make_expense):
    shop = make_expense(description="Weekly shop at Aldi")
    flight = make_expense(description="Flight to Lagos", tags="vacation,reimbursable")
    discount = make_expense(description="50% off shoes")

    def search(text):
        return {e.id for e in expenses.list(ExpenseFilter(search=text))}

    assert search("aldi") == {shop.id}
    assert search("WEEKLY") == {shop.id}
    assert search("vacation") == {flight.id}
    assert search("flight reimb") == {flight.id}
    assert search("weekly lagos") == set()
    assert search("") == {shop.id, flight.id, discount.id}
    # LIKE wildcards typed by the user are matched literally.
    assert search("%") == {discount.id}
    assert search("_") == set()


def test_delete_many_and_restore(expenses, make_expense):
    keep = make_expense(description="keep")
    first = make_expense(description="first", tags="a")
    second = make_expense(description="second")

    deleted = expenses.delete_many([first.id, second.id, 424242])
    assert [e.id for e in deleted] == [first.id, second.id]
    assert [e.id for e in expenses.list()] == [keep.id]

    expenses.restore(deleted)
    assert expenses.get(first.id) == first
    assert expenses.get(second.id) == second


def test_totals(expenses, make_expense, categories):
    make_expense(1000, date(2026, 10, 1), "Travel")
    make_expense(2500, date(2026, 10, 31), "Travel")
    make_expense(700, date(2026, 10, 15), "Gifts")
    make_expense(9999, date(2026, 11, 1), "Gifts")

    start, end = date(2026, 10, 1), date(2026, 10, 31)
    assert expenses.total_between(start, end) == 4200
    assert expenses.total_between(date(2025, 1, 1), date(2025, 1, 31)) == 0
    assert expenses.totals_by_category(start, end) == [
        (categories.find_by_name("Travel").id, 3500),
        (categories.find_by_name("Gifts").id, 700),
    ]


def test_category_names_are_unique_ignoring_case(categories):
    with pytest.raises(sqlite3.IntegrityError):
        categories.add("travel", "#000000")


def test_category_with_expenses_cannot_be_deleted_at_database_level(
    categories, make_expense
):
    make_expense(category="Travel")
    with pytest.raises(sqlite3.IntegrityError):
        categories.delete(categories.find_by_name("Travel").id)


def test_category_list_can_hide_archived(categories):
    travel = categories.find_by_name("Travel")
    categories.set_archived(travel.id, True)
    assert travel.id not in {c.id for c in categories.list(include_archived=False)}
    archived = [c for c in categories.list() if c.is_archived]
    assert [c.id for c in archived] == [travel.id]

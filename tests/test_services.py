from datetime import date

import pytest

from expense_tracker.services.categories import (
    CategoryError,
    CategoryInUseError,
    CategoryService,
)
from expense_tracker.services.expenses import ExpenseService, UndoError
from expense_tracker.services.summary import month_summary


@pytest.fixture
def expense_service(expenses, settings):
    return ExpenseService(expenses, settings)


@pytest.fixture
def category_service(conn, categories, expenses):
    return CategoryService(conn, categories, expenses)


# --- expenses -------------------------------------------------------------


def test_add_remembers_last_category_and_payment_method(expense_service, categories):
    assert expense_service.last_category_id() is None
    assert expense_service.last_payment_method() is None

    travel = categories.find_by_name("Travel").id
    expense = expense_service.add(
        1299, date(2026, 10, 5), travel, "  Train  ", "Credit Card"
    )
    assert expense.description == "Train"
    assert expense_service.last_category_id() == travel
    assert expense_service.last_payment_method() == "Credit Card"


def test_delete_then_undo_restores_everything(expense_service, expenses, make_expense):
    first = make_expense(description="first")
    second = make_expense(description="second")
    assert not expense_service.can_undo_delete

    assert expense_service.delete([first.id, second.id]) == 2
    assert expenses.list() == []
    assert expense_service.can_undo_delete

    assert expense_service.undo_delete() == 2
    assert {e.id for e in expenses.list()} == {first.id, second.id}
    assert expenses.get(first.id) == first
    assert not expense_service.can_undo_delete
    assert expense_service.undo_delete() == 0


def test_undo_restores_most_recent_delete_first(
    expense_service, expenses, make_expense
):
    first = make_expense()
    second = make_expense()
    expense_service.delete([first.id])
    expense_service.delete([second.id])

    expense_service.undo_delete()
    assert [e.id for e in expenses.list()] == [second.id]
    expense_service.undo_delete()
    assert {e.id for e in expenses.list()} == {first.id, second.id}


def test_deleting_nothing_is_not_undoable(expense_service):
    assert expense_service.delete([12345]) == 0
    assert not expense_service.can_undo_delete


def test_undo_fails_cleanly_when_category_is_gone(
    expense_service, category_service, categories, make_expense
):
    expense = make_expense(category="Gifts")
    expense_service.delete([expense.id])
    category_service.delete(categories.find_by_name("Gifts").id)
    with pytest.raises(UndoError):
        expense_service.undo_delete()


# --- categories -----------------------------------------------------------


def test_add_category_cleans_name_and_assigns_color(category_service, categories):
    created = category_service.add("  Pet   care ")
    assert created.name == "Pet care"
    assert created.color.startswith("#") and len(created.color) == 7
    assert categories.find_by_name("pet care").id == created.id


@pytest.mark.parametrize(
    "name, color, message",
    [
        ("", "#123456", "Enter a category name"),
        ("   ", "#123456", "Enter a category name"),
        ("x" * 41, "#123456", "at most 40"),
        ("travel", "#123456", "already exists"),
        ("Pets", "red", "valid color"),
    ],
)
def test_add_category_validation(category_service, name, color, message):
    with pytest.raises(CategoryError, match=message):
        category_service.add(name, color)


def test_update_category(category_service, categories):
    travel = categories.find_by_name("Travel")
    # Changing only the capitalisation or color of a category is allowed.
    category_service.update(travel.id, "TRAVEL", "#112233")
    updated = categories.get(travel.id)
    assert (updated.name, updated.color) == ("TRAVEL", "#112233")

    with pytest.raises(CategoryError, match="already exists"):
        category_service.update(travel.id, "Gifts", "#112233")


def test_delete_unused_category(category_service, categories):
    gifts = categories.find_by_name("Gifts")
    category_service.delete(gifts.id)
    assert categories.get(gifts.id) is None


def test_delete_category_with_expenses_is_refused(
    category_service, categories, make_expense
):
    make_expense(category="Travel")
    make_expense(category="Travel")
    travel = categories.find_by_name("Travel")
    with pytest.raises(CategoryInUseError) as error:
        category_service.delete(travel.id)
    assert error.value.expense_count == 2
    assert "2 expenses" in str(error.value)
    assert categories.get(travel.id) is not None


def test_archive_keeps_history(category_service, categories, expenses, make_expense):
    expense = make_expense(category="Travel")
    travel = categories.find_by_name("Travel")
    category_service.set_archived(travel.id, True)
    assert travel.id not in {c.id for c in categories.list(include_archived=False)}
    assert expenses.get(expense.id).category_id == travel.id

    category_service.set_archived(travel.id, False)
    assert travel.id in {c.id for c in categories.list(include_archived=False)}


def test_reassign_and_delete(category_service, categories, expenses, make_expense):
    moved = make_expense(category="Travel")
    untouched = make_expense(category="Gifts")
    travel = categories.find_by_name("Travel")
    other = categories.find_by_name("Other")

    assert category_service.reassign_and_delete(travel.id, other.id) == 1
    assert categories.get(travel.id) is None
    assert expenses.get(moved.id).category_id == other.id
    assert expenses.get(untouched.id).category_id != other.id


def test_reassign_to_invalid_target_changes_nothing(
    category_service, categories, expenses, make_expense
):
    expense = make_expense(category="Travel")
    travel = categories.find_by_name("Travel")
    with pytest.raises(CategoryError):
        category_service.reassign_and_delete(travel.id, travel.id)
    with pytest.raises(CategoryError):
        category_service.reassign_and_delete(travel.id, 9999)
    assert expenses.get(expense.id).category_id == travel.id


# --- dashboard summary ----------------------------------------------------


def test_summary_of_empty_month(expenses, categories):
    summary = month_summary(expenses, categories, 2026, 10, date(2026, 10, 5))
    assert summary.total_cents == 0
    assert summary.change_cents == 0
    assert summary.change_percent is None
    assert summary.average_daily_cents == 0
    assert summary.breakdown == []
    assert summary.top_categories == []


def test_summary_totals_and_comparison(expenses, categories, make_expense):
    make_expense(20000, date(2026, 9, 10), "Travel")
    make_expense(6000, date(2026, 10, 1), "Travel")
    make_expense(3000, date(2026, 10, 2), "Gifts")
    make_expense(2000, date(2026, 10, 3), "Health")
    make_expense(1000, date(2026, 10, 4), "Other")
    make_expense(3000, date(2026, 10, 4), "Travel")

    summary = month_summary(expenses, categories, 2026, 10, date(2026, 10, 10))
    assert summary.total_cents == 15000
    assert summary.previous_total_cents == 20000
    assert summary.change_cents == -5000
    assert summary.change_percent == pytest.approx(-25.0)
    # Current month: averaged over the 10 days elapsed so far.
    assert summary.average_daily_cents == 1500

    assert [(c.name, c.total_cents) for c in summary.breakdown] == [
        ("Travel", 9000),
        ("Gifts", 3000),
        ("Health", 2000),
        ("Other", 1000),
    ]
    assert [c.name for c in summary.top_categories] == ["Travel", "Gifts", "Health"]
    assert summary.breakdown[0].percent == pytest.approx(60.0)
    assert sum(c.percent for c in summary.breakdown) == pytest.approx(100.0)


def test_summary_of_past_month_averages_over_whole_month(
    expenses, categories, make_expense
):
    make_expense(3000, date(2026, 9, 10), "Travel")
    summary = month_summary(expenses, categories, 2026, 9, date(2026, 10, 10))
    assert summary.average_daily_cents == 100  # 30 days in September
    assert summary.change_percent is None  # nothing spent in August


def test_summary_average_rounds_half_up(expenses, categories, make_expense):
    make_expense(5, date(2026, 10, 1))
    summary = month_summary(expenses, categories, 2026, 10, date(2026, 10, 2))
    assert summary.average_daily_cents == 3  # 2.5 cents rounds up


def test_summary_in_january_compares_with_december(expenses, categories, make_expense):
    make_expense(1000, date(2025, 12, 31))
    make_expense(1500, date(2026, 1, 1))
    summary = month_summary(expenses, categories, 2026, 1, date(2026, 1, 1))
    assert summary.previous_total_cents == 1000
    assert summary.change_percent == pytest.approx(50.0)

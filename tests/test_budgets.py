from datetime import date

import pytest
from PySide6.QtWidgets import QMessageBox

from expense_tracker.db.repositories import BudgetRepository
from expense_tracker.services.budgets import (
    OK,
    OVER,
    WARNING,
    BudgetError,
    BudgetService,
    BudgetStatus,
)
from expense_tracker.services.categories import CategoryService
from expense_tracker.ui.budgets_tab import BudgetDialog
from expense_tracker.utils.money import format_cents


@pytest.fixture
def budgets(conn, categories, expenses):
    return BudgetService(BudgetRepository(conn), categories, expenses)


def cid(categories, name):
    return categories.find_by_name(name).id


# --- service ----------------------------------------------------------------


@pytest.mark.parametrize(
    "spent, level",
    [
        (0, OK),
        (7499, OK),
        (7500, WARNING),  # exactly 75%
        (9999, WARNING),
        (10000, WARNING),  # exactly on the limit is not over
        (10001, OVER),
        (25000, OVER),
    ],
)
def test_level_thresholds(spent, level):
    status = BudgetStatus(1, "Food", "#000000", 10000, spent)
    assert status.level == level
    assert status.remaining_cents == 10000 - spent


def test_set_limit_replaces_and_validates(budgets, categories):
    travel = cid(categories, "Travel")
    assert budgets.limit_for(travel) is None
    budgets.set_limit(travel, 5000)
    budgets.set_limit(travel, 8000)
    budgets.set_limit(None, 100000)
    budgets.set_limit(None, 120000)
    assert budgets.limit_for(travel) == 8000
    assert budgets.limit_for(None) == 120000
    assert len(budgets.statuses(2026, 10)) == 2

    for bad in (0, -5):
        with pytest.raises(BudgetError):
            budgets.set_limit(travel, bad)

    budgets.remove(None)
    assert budgets.limit_for(None) is None
    assert budgets.limit_for(travel) == 8000


def test_statuses_count_only_that_month_and_category(budgets, categories, make_expense):
    budgets.set_limit(cid(categories, "Travel"), 10000)
    budgets.set_limit(cid(categories, "Gifts"), 2000)
    budgets.set_limit(None, 50000)
    make_expense(4000, date(2026, 10, 1), "Travel")
    make_expense(3500, date(2026, 10, 31), "Travel")
    make_expense(900, date(2026, 10, 15), "Health")  # counts toward overall only
    make_expense(9999, date(2026, 9, 30), "Travel")  # previous month
    make_expense(9999, date(2026, 11, 1), "Gifts")  # next month

    overall, gifts, travel = budgets.statuses(2026, 10)
    assert (overall.name, overall.category_id, overall.spent_cents) == (
        "Overall",
        None,
        8400,
    )
    assert (gifts.name, gifts.spent_cents, gifts.remaining_cents) == ("Gifts", 0, 2000)
    assert (travel.name, travel.spent_cents, travel.level) == ("Travel", 7500, WARNING)
    assert travel.percent == pytest.approx(75.0)


def test_budget_is_removed_with_its_category(budgets, conn, categories, expenses):
    gifts = cid(categories, "Gifts")
    budgets.set_limit(gifts, 2000)
    CategoryService(conn, categories, expenses).delete(gifts)
    assert budgets.statuses(2026, 10) == []


def test_alert_when_expense_crosses_ninety_percent(budgets, categories, make_expense):
    budgets.set_limit(cid(categories, "Travel"), 10000)
    quiet = make_expense(8900, date(2026, 10, 1), "Travel")
    assert budgets.alerts_for(quiet) == []

    crossing = make_expense(100, date(2026, 10, 2), "Travel")  # exactly 90%
    [alert] = budgets.alerts_for(crossing)
    assert not alert.is_over
    message = alert.message(format_cents)
    assert "Travel" in message and "90%" in message and "$10.00 left" in message

    already_past = make_expense(500, date(2026, 10, 3), "Travel")  # 95%, no repeat
    assert budgets.alerts_for(already_past) == []

    exact = make_expense(500, date(2026, 10, 4), "Travel")  # exactly 100%
    assert budgets.alerts_for(exact) == []

    over = make_expense(1, date(2026, 10, 5), "Travel")
    [alert] = budgets.alerts_for(over)
    assert alert.is_over
    assert "over its $100.00 budget by $0.01" in alert.message(format_cents)

    further_over = make_expense(5000, date(2026, 10, 6), "Travel")
    assert budgets.alerts_for(further_over) == []


def test_one_big_expense_gives_a_single_over_alert(budgets, categories, make_expense):
    budgets.set_limit(cid(categories, "Travel"), 10000)
    big = make_expense(20000, date(2026, 10, 1), "Travel")
    [alert] = budgets.alerts_for(big)
    assert alert.is_over


def test_alerts_cover_overall_budget_but_not_other_categories(
    budgets, categories, make_expense
):
    budgets.set_limit(None, 10000)
    budgets.set_limit(cid(categories, "Gifts"), 100)
    expense = make_expense(9500, date(2026, 10, 1), "Travel")
    [alert] = budgets.alerts_for(expense)
    assert alert.status.category_id is None
    assert alert.message(format_cents).startswith("Your overall budget has used 95%")


def test_alert_uses_the_month_of_the_expense(budgets, categories, make_expense):
    budgets.set_limit(cid(categories, "Travel"), 10000)
    make_expense(9900, date(2026, 10, 1), "Travel")
    september = make_expense(500, date(2026, 9, 1), "Travel")
    assert budgets.alerts_for(september) == []


# --- UI ---------------------------------------------------------------------


def test_budgets_tab_lists_progress(window, ctx, make_expense):
    tab = window.budgets_tab
    assert tab.rows == [] and not tab.empty_label.isHidden()

    today = date.today()
    travel = ctx.categories.find_by_name("Travel").id
    ctx.budget_service.set_limit(travel, 10000)
    ctx.budget_service.set_limit(None, 20000)
    make_expense(12000, today, "Travel")
    ctx.data_changed.emit()

    assert tab.empty_label.isHidden()
    overall, row = tab.rows
    assert overall.name.text() == "Overall"
    assert overall.bar.value() == 60 and overall.bar.property("level") == OK
    assert overall.remaining.text() == "$80.00 left"
    assert row.name.text() == "Travel"
    assert row.percent.text() == "120%"
    assert row.bar.value() == 100 and row.bar.property("level") == OVER
    assert row.spent.text() == "$120.00 of $100.00"
    assert row.remaining.text() == "$20.00 over"


def test_budget_dialog_saves_and_validates(ctx):
    travel = ctx.categories.find_by_name("Travel").id
    ctx.budget_service.set_limit(travel, 5000)

    dialog = BudgetDialog(ctx, travel)
    assert dialog.target.currentText() == "Travel"
    assert dialog.amount.text() == "50.00"

    dialog.amount.setText("zero")
    dialog.accept()
    assert dialog.error.text() != "" and dialog.result() == 0

    dialog.amount.setText("75.50")
    dialog.accept()
    assert dialog.result() == 1
    assert ctx.budget_service.limit_for(travel) == 7550

    overall = BudgetDialog(ctx)
    assert overall.target.currentData() is None and overall.amount.text() == ""
    overall.amount.setText("1,000")
    overall.accept()
    assert ctx.budget_service.limit_for(None) == 100000


def test_remove_budget_from_tab(window, ctx, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    ctx.budget_service.set_limit(None, 20000)
    window.budgets_tab.refresh()
    window.budgets_tab.rows[0].remove_button.click()
    assert ctx.budget_service.limit_for(None) is None
    assert window.budgets_tab.rows == []


def test_adding_expense_past_limit_shows_non_blocking_toast(window, ctx):
    form = window.expenses_tab.form
    form.category.setCurrentText("Travel")
    travel = ctx.categories.find_by_name("Travel").id
    ctx.budget_service.set_limit(travel, 10000)
    toast = window.toast
    assert toast.isHidden()

    form.amount.setText("50")
    form.submit()
    assert toast.isHidden()

    form.amount.setText("45")
    form.submit()
    assert not toast.isHidden()
    assert toast.title.text() == "Budget alert"
    assert "95%" in toast.body.text()
    assert toast.property("level") == "near"
    # Nothing modal is open: the form is already cleared for the next expense.
    assert form.amount.text() == "" and form.isEnabled()

    form.amount.setText("10")
    form.submit()
    assert "over its $100.00 budget by $5.00" in toast.body.text()
    assert toast.property("level") == "over"
    assert toast.body.text().count("\n") == 1  # both alerts are stacked

    toast.hide()
    form.amount.setText("1")
    form.submit()
    assert toast.isHidden()


def test_last_tab_is_remembered_by_name(ctx, conn):
    from expense_tracker.ui.context import AppContext
    from expense_tracker.ui.main_window import MainWindow

    first = MainWindow(ctx)
    first.tabs.setCurrentWidget(first.budgets_tab)
    first.close()
    second = MainWindow(AppContext(conn))
    assert second.tabs.currentWidget() is second.budgets_tab
    second.close()

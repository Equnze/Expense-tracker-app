from datetime import date, timedelta

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QMessageBox

from expense_tracker.models import MONTHLY, WEEKLY, RecurringExpense
from expense_tracker.ui.expense_table import DESCRIPTION as EXPENSE_DESCRIPTION
from expense_tracker.ui.recurring_tab import (
    AMOUNT,
    DESCRIPTION,
    NEXT_DUE,
    SCHEDULE,
    STATUS,
    RecurringDialog,
    generated_message,
)
from expense_tracker.utils.dates import format_display


def rule_for(ctx, category="Other", **fields):
    fields.setdefault("amount_cents", 1500)
    fields.setdefault("frequency", MONTHLY)
    fields.setdefault("start_date", date.today())
    fields.setdefault("description", "Streaming")
    return RecurringExpense(category_id=ctx.categories.find_by_name(category).id, **fields)


def qdate(day):
    return QDate(day.year, day.month, day.day)


# --- dialog -------------------------------------------------------------------


def test_new_rule_dialog_defaults_and_saves(ctx):
    today = date.today()
    dialog = RecurringDialog(ctx)
    assert dialog.frequency.currentData() == MONTHLY
    assert dialog.day.value() == today.day
    assert dialog.start.date() == qdate(today)
    assert not dialog.has_end.isChecked() and not dialog.end.isEnabled()
    assert "Saving adds 1 expense now" in dialog.hint.text()

    dialog.accept()  # no amount yet
    assert dialog.error.text() != "" and dialog.result() == 0

    dialog.amount.setText("15.99")
    dialog.description.setText("  Streaming ")
    dialog.category.setCurrentText("Subscriptions")
    dialog.payment.setCurrentText("Credit Card")
    dialog.accept()
    assert dialog.result() == 1

    [saved] = ctx.recurring_service.list()
    assert saved.id == dialog.rule.id
    assert (saved.amount_cents, saved.description) == (1599, "Streaming")
    assert (saved.frequency, saved.day_of_month, saved.start_date) == (
        MONTHLY,
        today.day,
        today,
    )
    assert saved.payment_method == "Credit Card" and saved.end_date is None
    assert ctx.categories.get(saved.category_id).name == "Subscriptions"


def test_dialog_day_follows_start_date_and_hides_for_weekly(ctx):
    dialog = RecurringDialog(ctx)
    dialog.show()
    future = date.today() + timedelta(days=40)
    dialog.start.setDate(qdate(future))
    assert dialog.day.value() == future.day
    assert f"Next: {format_display(future)}" in dialog.hint.text()

    dialog.frequency.setCurrentIndex(dialog.frequency.findData(WEEKLY))
    assert dialog.day.isHidden() and dialog.day_label.isHidden()
    assert dialog.hint.text().startswith("Weekly on ")
    dialog.amount.setText("5")
    dialog.accept()
    [saved] = ctx.recurring_service.list()
    assert saved.frequency == WEEKLY and saved.day_of_month is None
    dialog.close()


def test_dialog_rejects_end_before_start_inline(ctx):
    dialog = RecurringDialog(ctx)
    dialog.amount.setText("5")
    dialog.has_end.setChecked(True)
    assert dialog.end.isEnabled()
    dialog.end.setDate(qdate(date.today() - timedelta(days=3)))
    dialog.accept()
    assert "before the start date" in dialog.error.text()
    assert dialog.result() == 0 and ctx.recurring_service.list() == []


def test_edit_dialog_keeps_history(ctx):
    rule = ctx.recurring_service.add(rule_for(ctx, day_of_month=date.today().day))
    ctx.recurring_service.generate_due(date.today())
    stored = ctx.recurring_service.list()[0]
    assert stored.last_generated_date == date.today()

    dialog = RecurringDialog(ctx, stored)
    assert dialog.windowTitle() == "Edit recurring expense"
    assert dialog.amount.text() == "15.00"
    assert "Next:" in dialog.hint.text()  # this month is already done
    dialog.amount.setText("20")
    dialog.accept()

    updated = ctx.recurring_service.list()[0]
    assert updated.id == rule.id and updated.amount_cents == 2000
    assert updated.last_generated_date == date.today()
    assert ctx.recurring_service.generate_due(date.today()) == []


# --- tab ----------------------------------------------------------------------


def test_tab_lists_rules(window, ctx):
    tab = window.recurring_tab
    assert tab.table.isHidden() and not tab.empty_label.isHidden()
    assert not tab.edit_button.isEnabled()

    today = date.today()
    ctx.recurring_service.add(
        rule_for(ctx, "Rent/Mortgage", amount_cents=125000, description="Rent",
                 start_date=today + timedelta(days=40), day_of_month=1)
    )
    ctx.recurring_service.add(
        rule_for(ctx, description="Old plan", start_date=date(2020, 1, 1),
                 day_of_month=1, end_date=date(2020, 3, 1),
                 last_generated_date=date(2020, 3, 1))
    )
    tab.refresh()

    assert not tab.table.isHidden() and tab.empty_label.isHidden()
    assert tab.table.rowCount() == 2
    rows = {
        tab.table.item(r, DESCRIPTION).text(): [
            tab.table.item(r, c).text() for c in (AMOUNT, SCHEDULE, NEXT_DUE, STATUS)
        ]
        for r in range(2)
    }
    assert rows["Rent"][0] == "$1,250.00"
    assert rows["Rent"][1] == "Monthly on the 1st"
    assert rows["Rent"][3] == "Active" and rows["Rent"][2] != "—"
    assert rows["Old plan"][2:] == ["—", "Ended"]


def test_pause_resume_and_delete_from_tab(window, ctx, statuses, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    tab = window.recurring_tab
    rule = ctx.recurring_service.add(
        rule_for(ctx, start_date=date.today() + timedelta(days=10))
    )
    tab.refresh()
    tab.select_rule(rule.id)
    assert tab.edit_button.isEnabled() and tab.pause_button.text() == "Pause"

    tab.pause_button.click()
    assert not ctx.recurring_service.list()[0].is_active
    assert tab.table.item(0, STATUS).text() == "Paused"
    assert tab.table.item(0, NEXT_DUE).text() == "—"
    assert tab.pause_button.text() == "Resume"  # the row stays selected
    assert statuses[-1] == "Paused"

    tab.pause_button.click()
    assert ctx.recurring_service.list()[0].is_active
    assert statuses[-1] == "Resumed"

    tab.delete_button.click()
    assert ctx.recurring_service.list() == []
    assert tab.table.isHidden()
    assert statuses[-1] == "Recurring expense deleted"


def test_saving_a_due_rule_adds_its_expense_straight_away(window, ctx, statuses):
    tab = window.recurring_tab
    dialog = RecurringDialog(ctx, None, tab)
    dialog.amount.setText("9.99")
    dialog.description.setText("Music")
    dialog.exec = lambda: (dialog.accept(), dialog.result())[1]
    tab._run_dialog(dialog)

    [expense] = ctx.expenses.list()
    assert (expense.description, expense.amount_cents) == ("Music", 999)
    assert expense.date == date.today() and expense.recurring_id is not None
    assert statuses[-1] == "Recurring expense saved — added 1 expense"
    # Every tab picked up the new expense.
    assert "1 expense " in window.expenses_tab.footer.text()
    assert window.dashboard_tab.total_card.value.text() == "$9.99"
    model = window.expenses_tab.table.model()
    tooltip = model.index(0, EXPENSE_DESCRIPTION).data(Qt.ItemDataRole.ToolTipRole)
    assert "recurring" in tooltip


# --- launch -------------------------------------------------------------------


def test_launch_generates_due_expenses_and_shows_a_notice(window, ctx):
    today = date.today()
    start = today - timedelta(days=70)
    ctx.recurring_service.add(
        rule_for(ctx, "Rent/Mortgage", amount_cents=125000, description="Rent",
                 start_date=start, day_of_month=start.day)
    )
    ctx.recurring_service.add(
        rule_for(ctx, description="Not yet", start_date=today + timedelta(days=5))
    )
    assert window.toast.isHidden()

    added = window.generate_recurring()
    assert added >= 2  # the months missed since the start date
    assert len(ctx.expenses.list()) == added
    assert not window.toast.isHidden()
    assert window.toast.title.text() == f"Added {added} recurring expenses"
    assert "Rent  $1,250.00" in window.toast.body.text()
    assert window.toast.property("level") == "info"

    # Opening the app again the same day adds nothing and shows nothing.
    window.toast.hide()
    assert window.generate_recurring() == 0
    assert window.toast.isHidden()
    assert len(ctx.expenses.list()) == added


def test_generated_message_truncates_long_lists(ctx, make_expense):
    expenses = [
        make_expense(1000 + i, date(2026, 10, i + 1), description=f"Bill {i}")
        for i in range(6)
    ]
    lines = generated_message(expenses, ctx).split("\n")
    assert lines[0] == "Bill 0  $10.00  (01 Oct)"
    assert len(lines) == 5 and lines[-1] == "…and 2 more"
    assert generated_message(expenses[:1], ctx) == "Bill 0  $10.00  (01 Oct)"

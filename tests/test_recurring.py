from datetime import date
from itertools import islice

import pytest

from expense_tracker.db.repositories import RecurringRepository
from expense_tracker.models import MONTHLY, WEEKLY, YEARLY, RecurringExpense
from expense_tracker.services.categories import CategoryInUseError, CategoryService
from expense_tracker.services.expenses import ExpenseService
from expense_tracker.services.recurring import (
    RecurringError,
    RecurringService,
    describe_schedule,
    due_dates,
    next_due,
    occurrences,
)


@pytest.fixture
def service(conn, expenses):
    return RecurringService(conn, RecurringRepository(conn), expenses)


@pytest.fixture
def make_rule(categories):
    def _make(frequency=MONTHLY, start=date(2026, 1, 15), category="Other", **fields):
        fields.setdefault("amount_cents", 1000)
        fields.setdefault("description", "Rule")
        return RecurringExpense(
            category_id=categories.find_by_name(category).id,
            frequency=frequency,
            start_date=start,
            **fields,
        )

    return _make


def first(rule, count):
    return list(islice(occurrences(rule), count))


# --- schedules ------------------------------------------------------------


def test_monthly_on_a_normal_day(make_rule):
    rule = make_rule(MONTHLY, date(2026, 1, 15), day_of_month=15)
    assert first(rule, 3) == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]


def test_monthly_on_the_31st_moves_to_month_end(make_rule):
    rule = make_rule(MONTHLY, date(2026, 1, 31), day_of_month=31)
    assert first(rule, 6) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
    ]


def test_monthly_on_the_30th_and_29th_in_february(make_rule):
    assert first(make_rule(MONTHLY, date(2026, 1, 30), day_of_month=30), 2)[1] == date(
        2026, 2, 28
    )
    leap = make_rule(MONTHLY, date(2024, 1, 29), day_of_month=29)
    assert first(leap, 2)[1] == date(2024, 2, 29)
    assert first(make_rule(MONTHLY, date(2024, 1, 31), day_of_month=31), 2)[1] == date(
        2024, 2, 29
    )


def test_monthly_skips_the_start_month_when_the_day_has_passed(make_rule):
    rule = make_rule(MONTHLY, date(2026, 1, 20), day_of_month=5)
    assert first(rule, 2) == [date(2026, 2, 5), date(2026, 3, 5)]


def test_monthly_crosses_the_year_end(make_rule):
    rule = make_rule(MONTHLY, date(2026, 11, 30), day_of_month=30)
    assert first(rule, 4) == [
        date(2026, 11, 30),
        date(2026, 12, 30),
        date(2027, 1, 30),
        date(2027, 2, 28),
    ]


def test_weekly_repeats_every_seven_days(make_rule):
    rule = make_rule(WEEKLY, date(2026, 12, 21))
    assert first(rule, 3) == [date(2026, 12, 21), date(2026, 12, 28), date(2027, 1, 4)]


def test_yearly_repeats_on_the_anniversary(make_rule):
    assert first(make_rule(YEARLY, date(2026, 3, 10)), 2) == [
        date(2026, 3, 10),
        date(2027, 3, 10),
    ]
    leap_day = make_rule(YEARLY, date(2024, 2, 29))
    assert first(leap_day, 5) == [
        date(2024, 2, 29),
        date(2025, 2, 28),
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]


def test_due_dates_respect_last_generated_and_end_date(make_rule):
    rule = make_rule(MONTHLY, date(2026, 1, 15), day_of_month=15)
    assert due_dates(rule, date(2026, 1, 14)) == []
    assert due_dates(rule, date(2026, 1, 15)) == [date(2026, 1, 15)]
    assert len(due_dates(rule, date(2026, 4, 14))) == 3

    rule.last_generated_date = date(2026, 2, 15)
    assert due_dates(rule, date(2026, 4, 15)) == [date(2026, 3, 15), date(2026, 4, 15)]

    rule.end_date = date(2026, 3, 31)
    assert due_dates(rule, date(2026, 12, 31)) == [date(2026, 3, 15)]
    rule.end_date = date(2026, 3, 15)  # the end date itself is included
    assert due_dates(rule, date(2026, 12, 31)) == [date(2026, 3, 15)]


def test_next_due(make_rule):
    rule = make_rule(MONTHLY, date(2026, 1, 31), day_of_month=31)
    assert next_due(rule) == date(2026, 1, 31)
    rule.last_generated_date = date(2026, 1, 31)
    assert next_due(rule) == date(2026, 2, 28)
    rule.end_date = date(2026, 2, 27)
    assert next_due(rule) is None


def test_describe_schedule(make_rule):
    assert describe_schedule(make_rule(MONTHLY, day_of_month=1)) == "Monthly on the 1st"
    assert describe_schedule(make_rule(MONTHLY, day_of_month=22)) == "Monthly on the 22nd"
    assert describe_schedule(make_rule(MONTHLY, day_of_month=13)) == "Monthly on the 13th"
    assert (
        describe_schedule(make_rule(MONTHLY, day_of_month=31))
        == "Monthly on the 31st (or month end)"
    )
    assert describe_schedule(make_rule(WEEKLY, date(2026, 10, 5))) == "Weekly on Mondays"
    assert describe_schedule(make_rule(YEARLY, date(2026, 10, 5))) == "Yearly on 5 Oct"


# --- generation -----------------------------------------------------------


def test_generate_creates_linked_expenses_once(service, make_rule, expenses):
    rule = service.add(
        make_rule(
            MONTHLY,
            date(2026, 10, 1),
            "Rent/Mortgage",
            day_of_month=1,
            amount_cents=125000,
            description="Rent",
            payment_method="Bank Transfer",
        )
    )
    assert service.generate_due(date(2026, 9, 30)) == []

    [expense] = service.generate_due(date(2026, 10, 5))
    assert expense.recurring_id == rule.id
    assert (expense.date, expense.amount_cents) == (date(2026, 10, 1), 125000)
    assert (expense.description, expense.payment_method) == ("Rent", "Bank Transfer")
    assert expense.category_id == rule.category_id

    # Launching again the same day, or later the same month, adds nothing more.
    assert service.generate_due(date(2026, 10, 5)) == []
    assert service.generate_due(date(2026, 10, 31)) == []
    assert len(expenses.list()) == 1
    assert service.list()[0].last_generated_date == date(2026, 10, 1)


def test_generate_catches_up_on_missed_months(service, make_rule, expenses):
    service.add(make_rule(MONTHLY, date(2026, 1, 31), day_of_month=31))
    service.generate_due(date(2026, 1, 31))

    # The app is not opened again until early June.
    generated = service.generate_due(date(2026, 6, 2))
    assert [e.date for e in generated] == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]
    assert len(expenses.list()) == 5
    assert service.generate_due(date(2026, 6, 29)) == []
    assert [e.date for e in service.generate_due(date(2026, 6, 30))] == [date(2026, 6, 30)]


def test_generate_handles_several_rules_and_frequencies(service, make_rule):
    service.add(make_rule(WEEKLY, date(2026, 10, 1), description="Gym"))
    service.add(make_rule(YEARLY, date(2025, 10, 3), description="Insurance"))
    service.add(make_rule(MONTHLY, date(2026, 10, 20), day_of_month=20, description="Later"))

    generated = service.generate_due(date(2026, 10, 16))
    by_name = {}
    for expense in generated:
        by_name.setdefault(expense.description, []).append(expense.date)
    assert by_name == {
        "Gym": [date(2026, 10, 1), date(2026, 10, 8), date(2026, 10, 15)],
        "Insurance": [date(2025, 10, 3), date(2026, 10, 3)],
    }


def test_generation_stops_at_the_end_date(service, make_rule):
    service.add(
        make_rule(MONTHLY, date(2026, 1, 10), day_of_month=10, end_date=date(2026, 3, 10))
    )
    assert len(service.generate_due(date(2026, 12, 31))) == 3
    assert next_due(service.list()[0]) is None


def test_paused_rule_generates_nothing_and_resume_does_not_backfill(service, make_rule):
    rule = service.add(make_rule(MONTHLY, date(2026, 1, 10), day_of_month=10))
    service.generate_due(date(2026, 1, 10))
    service.set_active(rule.id, False, date(2026, 1, 11))
    assert service.generate_due(date(2026, 5, 1)) == []

    service.set_active(rule.id, True, date(2026, 5, 1))
    assert service.generate_due(date(2026, 5, 9)) == []
    assert [e.date for e in service.generate_due(date(2026, 5, 10))] == [date(2026, 5, 10)]


def test_resuming_on_the_due_day_still_generates_today(service, make_rule):
    rule = service.add(make_rule(MONTHLY, date(2026, 1, 10), day_of_month=10))
    service.set_active(rule.id, False, date(2026, 1, 1))
    service.set_active(rule.id, True, date(2026, 3, 10))
    assert [e.date for e in service.generate_due(date(2026, 3, 10))] == [date(2026, 3, 10)]


def test_generated_expense_is_editable_and_deleting_it_does_not_regenerate(
    service, make_rule, expenses, settings
):
    service.add(make_rule(MONTHLY, date(2026, 10, 1), day_of_month=1))
    [expense] = service.generate_due(date(2026, 10, 5))

    expense.amount_cents = 4321
    expense.description = "Edited"
    expenses.update(expense)
    assert expenses.get(expense.id).amount_cents == 4321
    assert expenses.get(expense.id).recurring_id == expense.recurring_id

    ExpenseService(expenses, settings).delete([expense.id])
    assert service.generate_due(date(2026, 10, 6)) == []
    assert expenses.list() == []


def test_deleting_a_rule_keeps_its_expenses(service, make_rule, expenses, settings):
    rule = service.add(make_rule(MONTHLY, date(2026, 10, 1), day_of_month=1))
    [expense] = service.generate_due(date(2026, 10, 5))
    expense_service = ExpenseService(expenses, settings)
    expense_service.delete([expense.id])

    service.delete(rule.id)
    assert service.list() == []
    # Undoing the delete still works; the expense just loses its link.
    assert expense_service.undo_delete() == 1
    assert expenses.get(expense.id).recurring_id is None

    kept = service.add(make_rule(MONTHLY, date(2026, 10, 1), day_of_month=1))
    [second] = service.generate_due(date(2026, 10, 5))
    service.delete(kept.id)
    assert expenses.get(second.id).recurring_id is None


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"amount_cents": 0}, "greater than zero"),
        ({"frequency": "daily"}, "how often"),
        ({"day_of_month": 32}, "between 1 and 31"),
        ({"day_of_month": 0}, "between 1 and 31"),
        ({"end_date": date(2026, 1, 14)}, "before the start date"),
    ],
)
def test_validation(service, make_rule, fields, message):
    with pytest.raises(RecurringError, match=message):
        service.add(make_rule(**fields))


def test_day_of_month_defaults_and_is_cleared_for_other_frequencies(service, make_rule):
    monthly = service.add(make_rule(MONTHLY, date(2026, 1, 15)))
    assert monthly.day_of_month == 15
    weekly = service.add(make_rule(WEEKLY, date(2026, 1, 15), day_of_month=9))
    assert weekly.day_of_month is None


def test_update_changes_future_expenses_only(service, make_rule, expenses):
    rule = service.add(make_rule(MONTHLY, date(2026, 1, 10), day_of_month=10))
    service.generate_due(date(2026, 1, 10))
    stored = service.list()[0]
    stored.amount_cents = 2500
    stored.day_of_month = 20
    service.update(stored)

    [later] = service.generate_due(date(2026, 2, 25))
    assert (later.date, later.amount_cents) == (date(2026, 2, 20), 2500)
    amounts = sorted(e.amount_cents for e in expenses.list())
    assert amounts == [1000, 2500]
    assert rule.id == stored.id


def test_category_used_by_a_rule_cannot_be_deleted_but_can_be_reassigned(
    conn, service, make_rule, categories, expenses
):
    travel = categories.find_by_name("Travel")
    other = categories.find_by_name("Other")
    service.add(make_rule(category="Travel"))
    category_service = CategoryService(conn, categories, expenses)

    with pytest.raises(CategoryInUseError) as error:
        category_service.delete(travel.id)
    assert (error.value.expense_count, error.value.recurring_count) == (0, 1)
    assert "1 recurring expense " in str(error.value)

    category_service.reassign_and_delete(travel.id, other.id)
    assert categories.get(travel.id) is None
    assert service.list()[0].category_id == other.id

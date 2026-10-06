from datetime import date

from expense_tracker.services.summary import cumulative_daily, monthly_totals


def test_monthly_totals_cover_twelve_months_including_empty_ones(
    expenses, make_expense
):
    make_expense(1000, date(2025, 11, 30))
    make_expense(2000, date(2026, 1, 1))
    make_expense(500, date(2026, 10, 5))
    make_expense(700, date(2026, 10, 31))
    make_expense(9999, date(2025, 10, 31))  # just outside the window
    make_expense(9999, date(2026, 11, 1))  # just outside the window

    totals = monthly_totals(expenses, 2026, 10)
    assert len(totals) == 12
    assert totals[0] == (2025, 11, 1000)
    assert totals[1] == (2025, 12, 0)
    assert totals[2] == (2026, 1, 2000)
    assert totals[-1] == (2026, 10, 1200)
    assert sum(cents for _, _, cents in totals) == 4200


def test_cumulative_daily_is_a_running_total(expenses, make_expense):
    make_expense(1000, date(2026, 9, 1))
    make_expense(250, date(2026, 9, 1))
    make_expense(500, date(2026, 9, 3))
    make_expense(100, date(2026, 9, 30))

    series = cumulative_daily(expenses, 2026, 9)
    assert len(series) == 30
    assert series[:4] == [1250, 1250, 1750, 1750]
    assert series[-1] == 1850


def test_cumulative_daily_can_stop_at_today(expenses, make_expense):
    make_expense(1000, date(2026, 10, 2))
    make_expense(5000, date(2026, 10, 20))
    assert cumulative_daily(expenses, 2026, 10, through_day=5) == [0, 1000, 1000, 1000, 1000]
    assert len(cumulative_daily(expenses, 2026, 2, through_day=31)) == 28
    assert cumulative_daily(expenses, 2024, 2)[-1] == 0 and len(
        cumulative_daily(expenses, 2024, 2)
    ) == 29


def test_dashboard_charts_follow_the_data(window, make_expense, ctx):
    dashboard = window.dashboard_tab
    assert dashboard.donut.is_empty and dashboard.bars.is_empty and dashboard.lines.is_empty

    today = date.today()
    make_expense(7500, today, "Travel")
    make_expense(2500, today.replace(day=1), "Gifts")
    ctx.data_changed.emit()

    assert not dashboard.donut.is_empty
    slices = dashboard.donut.series.slices()
    assert [(s.label(), s.value()) for s in slices] == [("Travel", 75.0), ("Gifts", 25.0)]
    travel = ctx.categories.find_by_name("Travel")
    assert slices[0].color().name().lower() == travel.color.lower()

    bars = dashboard.bars.bar_set
    assert bars.count() == 12
    assert bars.at(11) == 100.0 and bars.at(10) == 0.0

    current = dashboard.lines.current_series
    assert current.count() == today.day
    assert current.at(today.day - 1).y() == 100.0
    assert current.at(0).y() == (100.0 if today.day == 1 else 25.0)

    # Next month: this month's spending becomes the "previous" line.
    dashboard.next_button.click()
    assert dashboard.donut.is_empty
    assert dashboard.bars.bar_set.at(10) == 100.0
    assert dashboard.lines.previous_series.at(today.day - 1).y() == 100.0


def test_chart_axis_survives_percent_in_currency_symbol(window, make_expense, ctx):
    make_expense(1000, date.today())
    ctx.settings.set("currency_symbol", "%")
    ctx.settings_changed.emit()
    assert not window.dashboard_tab.bars.is_empty

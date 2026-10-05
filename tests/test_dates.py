from datetime import date

from expense_tracker.utils import dates


def test_shift_month_crosses_year_boundaries():
    assert dates.shift_month(2026, 1, -1) == (2025, 12)
    assert dates.shift_month(2026, 12, 1) == (2027, 1)
    assert dates.shift_month(2026, 3, -14) == (2025, 1)
    assert dates.shift_month(2026, 6, 0) == (2026, 6)


def test_month_bounds_handles_leap_years():
    assert dates.month_bounds(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))
    assert dates.month_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert dates.month_bounds(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))


def test_preset_ranges():
    today = date(2026, 1, 15)
    assert dates.preset_range(dates.THIS_MONTH, today) == (
        date(2026, 1, 1),
        date(2026, 1, 31),
    )
    assert dates.preset_range(dates.LAST_MONTH, today) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )
    assert dates.preset_range(dates.LAST_3_MONTHS, today) == (
        date(2025, 11, 1),
        date(2026, 1, 31),
    )
    assert dates.preset_range(dates.THIS_YEAR, today) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    assert dates.preset_range(dates.ALL_TIME, today) == (None, None)


def test_labels():
    assert dates.month_label(2026, 10) == "October 2026"
    assert dates.format_display(date(2026, 10, 5)) == "05 Oct 2026"

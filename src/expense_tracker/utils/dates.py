"""Date helpers: month arithmetic and the filter date-range presets."""

from __future__ import annotations

import calendar
from datetime import date, datetime

THIS_MONTH = "This Month"
LAST_MONTH = "Last Month"
LAST_3_MONTHS = "Last 3 Months"
THIS_YEAR = "This Year"
ALL_TIME = "All Time"
CUSTOM = "Custom range"

DATE_PRESETS = [THIS_MONTH, LAST_MONTH, LAST_3_MONTHS, THIS_YEAR, ALL_TIME, CUSTOM]


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return the (year, month) that is ``delta`` months away."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the first and last day of a month."""
    return date(year, month, 1), date(year, month, days_in_month(year, month))


def preset_range(preset: str, today: date) -> tuple[date | None, date | None]:
    """Return the inclusive (start, end) for a preset. ``None`` means unbounded.

    "Last 3 Months" covers the current month and the two before it.
    """
    if preset == THIS_MONTH:
        return month_bounds(today.year, today.month)
    if preset == LAST_MONTH:
        return month_bounds(*shift_month(today.year, today.month, -1))
    if preset == LAST_3_MONTHS:
        start, _ = month_bounds(*shift_month(today.year, today.month, -2))
        _, end = month_bounds(today.year, today.month)
        return start, end
    if preset == THIS_YEAR:
        return date(today.year, 1, 1), date(today.year, 12, 31)
    return None, None


def month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def format_display(day: date) -> str:
    """Format a date for the UI, e.g. ``05 Oct 2026``."""
    return f"{day.day:02d} {calendar.month_abbr[day.month]} {day.year}"


def now_iso() -> str:
    """Current local timestamp for created_at / updated_at columns."""
    return datetime.now().isoformat(timespec="seconds")

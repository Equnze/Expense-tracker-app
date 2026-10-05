"""Money parsing and formatting.

All amounts are handled as integer cents; floats are never used.
"""

from __future__ import annotations

import re

MAX_CENTS = 99_999_999_999  # 999,999,999.99

_AMOUNT_RE = re.compile(r"^(\d*)(?:\.(\d*))?$")


class MoneyError(ValueError):
    """Raised when text cannot be read as a valid amount. The message is user-facing."""


def parse_cents(text: str, currency_symbol: str = "$") -> int:
    """Convert user-entered text such as ``"12.99"`` or ``"$1,234.5"`` to cents.

    The amount must be positive and have at most two decimal places.
    """
    cleaned = (text or "").strip()
    if currency_symbol:
        cleaned = cleaned.replace(currency_symbol, "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    if not cleaned:
        raise MoneyError("Enter an amount.")
    if cleaned.startswith("-"):
        raise MoneyError("Amount must be greater than zero.")

    match = _AMOUNT_RE.match(cleaned)
    if not match or not (match.group(1) or match.group(2)):
        raise MoneyError("Amount must be a number, like 12.50.")

    whole, fraction = match.group(1) or "0", match.group(2) or ""
    if len(fraction) > 2:
        raise MoneyError("Use at most 2 decimal places.")

    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents <= 0:
        raise MoneyError("Amount must be greater than zero.")
    if cents > MAX_CENTS:
        raise MoneyError("Amount is too large.")
    return cents


def format_cents(cents: int, currency_symbol: str = "$") -> str:
    """Format cents for display, e.g. ``1234567`` -> ``"$12,345.67"``."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{currency_symbol}{whole:,}.{fraction:02d}"


def format_plain(cents: int) -> str:
    """Format cents without symbol or separators, for editing, e.g. ``"1234.50"``."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{whole}.{fraction:02d}"

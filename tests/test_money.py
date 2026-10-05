import pytest

from expense_tracker.utils.money import (
    MAX_CENTS,
    MoneyError,
    format_cents,
    format_plain,
    parse_cents,
)


@pytest.mark.parametrize(
    "text, cents",
    [
        ("12.99", 1299),
        ("12", 1200),
        ("12.5", 1250),
        ("12.", 1200),
        (".5", 50),
        ("0.01", 1),
        ("  7.25  ", 725),
        ("$12.99", 1299),
        ("1,234.56", 123456),
        ("$ 1,000", 100000),
        ("007.10", 710),
    ],
)
def test_parse_valid_amounts(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.parametrize(
    "text",
    # Values that come out one cent short when multiplied as floats.
    ["19.99", "0.29", "1.15", "4.35", "8.20", "1001.10", "0.57", "33.33"],
)
def test_parse_has_no_float_rounding_errors(text):
    whole, fraction = text.split(".")
    assert parse_cents(text) == int(whole) * 100 + int(fraction)


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "Enter an amount"),
        ("   ", "Enter an amount"),
        ("$", "Enter an amount"),
        ("abc", "must be a number"),
        ("12.3.4", "must be a number"),
        ("1e3", "must be a number"),
        (".", "must be a number"),
        ("12.999", "at most 2 decimal"),
        ("0.001", "at most 2 decimal"),
        ("0", "greater than zero"),
        ("0.00", "greater than zero"),
        ("-5", "greater than zero"),
        ("1000000000", "too large"),
    ],
)
def test_parse_rejects_invalid_amounts(text, message):
    with pytest.raises(MoneyError, match=message):
        parse_cents(text)


def test_parse_accepts_largest_amount():
    assert parse_cents("999,999,999.99") == MAX_CENTS


def test_parse_with_other_currency_symbol():
    assert parse_cents("€12.50", currency_symbol="€") == 1250
    assert parse_cents("12.50", currency_symbol="") == 1250


@pytest.mark.parametrize(
    "cents, text",
    [
        (0, "$0.00"),
        (5, "$0.05"),
        (1299, "$12.99"),
        (100000, "$1,000.00"),
        (123456789, "$1,234,567.89"),
        (-1250, "-$12.50"),
    ],
)
def test_format_cents(cents, text):
    assert format_cents(cents) == text


def test_format_with_other_symbol():
    assert format_cents(1299, "£") == "£12.99"
    assert format_cents(1299, "") == "12.99"


def test_format_plain_round_trips_through_parse():
    for cents in (1, 99, 100, 1299, 123456789):
        assert parse_cents(format_plain(cents)) == cents
    assert format_plain(123456) == "1234.56"

"""Import expenses from a bank-statement CSV file."""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from expense_tracker.db.connection import transaction
from expense_tracker.db.repositories import ExpenseRepository, duplicate_key
from expense_tracker.models import Expense
from expense_tracker.utils.money import MAX_CENTS

# (label shown to the user, strptime format). Earlier entries win when a file
# fits several, so day-first comes before month-first.
DATE_FORMATS = [
    ("2026-10-31  (year-month-day)", "%Y-%m-%d"),
    ("31/10/2026  (day/month/year)", "%d/%m/%Y"),
    ("10/31/2026  (month/day/year)", "%m/%d/%Y"),
    ("31-10-2026  (day-month-year)", "%d-%m-%Y"),
    ("10-31-2026  (month-day-year)", "%m-%d-%Y"),
    ("31.10.2026  (day.month.year)", "%d.%m.%Y"),
    ("2026/10/31  (year/month/day)", "%Y/%m/%d"),
    ("31/10/26  (day/month/year)", "%d/%m/%y"),
    ("10/31/26  (month/day/year)", "%m/%d/%y"),
    ("31 Oct 2026", "%d %b %Y"),
    ("31-Oct-2026", "%d-%b-%Y"),
    ("Oct 31, 2026", "%b %d, %Y"),
]

NEGATIVE_IS_EXPENSE = "Negative amounts are expenses (skip positive ones)"
POSITIVE_IS_EXPENSE = "Positive amounts are expenses (skip negative ones)"
ALL_ARE_EXPENSES = "Every row is an expense"
AMOUNT_MODES = [NEGATIVE_IS_EXPENSE, POSITIVE_IS_EXPENSE, ALL_ARE_EXPENSES]

READY = "ready"
SKIPPED = "skipped"
FAILED = "failed"

MAX_DESCRIPTION_LENGTH = 200


class CsvImportError(Exception):
    """Raised when a file cannot be used at all. The message is user-facing."""


@dataclass
class CsvTable:
    headers: list[str]
    rows: list[list[str]]
    # Line number in the file of each row, for error messages.
    line_numbers: list[int]


@dataclass
class ColumnMapping:
    date_column: int
    amount_column: int
    description_column: int | None
    date_format: str
    amount_mode: str = NEGATIVE_IS_EXPENSE


@dataclass
class ImportRow:
    line_number: int
    status: str
    note: str = ""
    date: date | None = None
    amount_cents: int | None = None
    description: str = ""
    category_id: int | None = None
    is_duplicate: bool = False
    selected: bool = True


@dataclass
class ImportSummary:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    failed_lines: list[int] = field(default_factory=list)


# --- reading ------------------------------------------------------------------


def read_csv(path: Path | str, has_header: bool = True) -> CsvTable:
    """Read a CSV file, working out its encoding and delimiter."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise CsvImportError("That file couldn't be opened.") from exc
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    if "\x00" in text:
        raise CsvImportError("That doesn't look like a CSV file.")

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    rows: list[list[str]] = []
    line_numbers: list[int] = []
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    try:
        for record in reader:
            if any(cell.strip() for cell in record):
                rows.append([cell.strip() for cell in record])
                line_numbers.append(reader.line_num)
    except csv.Error as exc:
        raise CsvImportError("That file isn't valid CSV.") from exc
    if not rows:
        raise CsvImportError("That file is empty.")

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    if has_header:
        headers = [name or f"Column {i}" for i, name in enumerate(rows[0], start=1)]
        rows, line_numbers = rows[1:], line_numbers[1:]
    else:
        headers = [f"Column {i}" for i in range(1, width + 1)]
    if not rows:
        raise CsvImportError("That file has column names but no rows.")
    return CsvTable(headers, rows, line_numbers)


# --- parsing single values ----------------------------------------------------


def parse_date(text: str, date_format: str) -> date:
    """Parse a date, ignoring any time of day after it. Raises ValueError."""
    text = text.strip()
    candidates = [text, text.split("T")[0]]
    if " " not in date_format:
        candidates.append(text.split(" ")[0])
    for candidate in candidates:
        try:
            return datetime.strptime(candidate, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"not a date: {text!r}")


def guess_date_format(samples: list[str]) -> str:
    """Return the format that reads the most of the sample values."""
    samples = [sample for sample in samples if sample.strip()]

    def score(date_format: str) -> int:
        count = 0
        for sample in samples:
            try:
                parse_date(sample, date_format)
                count += 1
            except ValueError:
                pass
        return count

    # max() keeps the first of equal scores, so the list order breaks ties.
    return max((fmt for _, fmt in DATE_FORMATS), key=score)


_THOUSANDS_COMMAS_RE = re.compile(r"^\d{1,3}(,\d{3})+$")


def parse_signed_cents(text: str) -> int:
    """Parse a bank-statement amount to cents, keeping its sign.

    Understands currency symbols, thousands separators, a decimal comma,
    a leading or trailing minus and accounting-style ``(12.34)`` negatives.
    Extra decimal places are rounded half up. Raises ValueError.
    """
    cleaned = text.strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = re.sub(r"[^\d.,+-]", "", cleaned)
    if "-" in cleaned:
        negative = True
    cleaned = cleaned.replace("-", "").replace("+", "")
    if not any(character.isdigit() for character in cleaned):
        raise ValueError(f"not an amount: {text!r}")

    if "," in cleaned and "." in cleaned:
        # Whichever comes last is the decimal separator.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if _THOUSANDS_COMMAS_RE.match(cleaned) or cleaned.count(",") > 1:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {text!r}") from exc
    cents = int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return -cents if negative else cents


def guess_amount_mode(samples: list[str]) -> str:
    """Pick the sign convention that treats most of the sample rows as expenses."""
    negatives = positives = 0
    for sample in samples:
        try:
            cents = parse_signed_cents(sample)
        except ValueError:
            continue
        if cents < 0:
            negatives += 1
        elif cents > 0:
            positives += 1
    if negatives and negatives >= positives:
        return NEGATIVE_IS_EXPENSE
    return POSITIVE_IS_EXPENSE


_COLUMN_HINTS = {
    "date": ("date", "posted", "time"),
    "amount": ("amount", "debit", "value", "withdrawal", "paid out", "money out"),
    "description": (
        "description",
        "details",
        "detail",
        "memo",
        "narrative",
        "payee",
        "merchant",
        "reference",
        "name",
    ),
}


def guess_column(headers: list[str], kind: str) -> int | None:
    """Return the index of the column whose name looks like a date/amount/description."""
    lowered = [header.casefold() for header in headers]
    for hint in _COLUMN_HINTS[kind]:
        for index, header in enumerate(lowered):
            if hint in header:
                return index
    return None


# --- parsing rows -------------------------------------------------------------


def parse_rows(table: CsvTable, mapping: ColumnMapping) -> list[ImportRow]:
    """Turn every CSV row into an ImportRow that is ready, skipped or failed."""
    result = []
    for cells, line_number in zip(table.rows, table.line_numbers):
        description = ""
        if mapping.description_column is not None:
            description = " ".join(cells[mapping.description_column].split())
            description = description[:MAX_DESCRIPTION_LENGTH]
        row = ImportRow(line_number, READY, description=description)
        result.append(row)

        amount_text = cells[mapping.amount_column]
        if not amount_text:
            row.status, row.note = SKIPPED, "No amount"
            continue
        try:
            signed = parse_signed_cents(amount_text)
        except ValueError:
            row.status, row.note = FAILED, f"Couldn't read the amount “{amount_text}”"
            continue
        try:
            row.date = parse_date(cells[mapping.date_column], mapping.date_format)
        except ValueError:
            row.status = FAILED
            row.note = f"Couldn't read the date “{cells[mapping.date_column]}”"
            continue

        if signed == 0:
            row.status, row.note = SKIPPED, "Amount is zero"
        elif mapping.amount_mode == NEGATIVE_IS_EXPENSE and signed > 0:
            row.status, row.note = SKIPPED, "Not an expense (money in)"
        elif mapping.amount_mode == POSITIVE_IS_EXPENSE and signed < 0:
            row.status, row.note = SKIPPED, "Not an expense (money in)"
        elif abs(signed) > MAX_CENTS:
            row.status, row.note = FAILED, "Amount is too large"
        else:
            row.amount_cents = abs(signed)
    return result


def flag_duplicates(rows: list[ImportRow], existing_keys: set[tuple]) -> int:
    """Mark ready rows that match an existing expense (same date, amount and
    description) and untick them. Returns how many were flagged."""
    count = 0
    for row in rows:
        if row.status != READY:
            continue
        row.is_duplicate = (
            duplicate_key(row.date, row.amount_cents, row.description) in existing_keys
        )
        row.selected = not row.is_duplicate
        count += row.is_duplicate
    return count


def import_rows(
    conn: sqlite3.Connection,
    expenses: ExpenseRepository,
    rows: list[ImportRow],
    default_category_id: int,
    payment_method: str = "",
) -> ImportSummary:
    """Save every ready, ticked row as an expense, all or nothing."""
    summary = ImportSummary()
    with transaction(conn):
        for row in rows:
            if row.status == FAILED:
                summary.failed += 1
                summary.failed_lines.append(row.line_number)
            elif row.status == SKIPPED or not row.selected:
                summary.skipped += 1
            else:
                expenses.add(
                    Expense(
                        amount_cents=row.amount_cents,
                        date=row.date,
                        category_id=row.category_id or default_category_id,
                        description=row.description,
                        payment_method=payment_method,
                    )
                )
                summary.imported += 1
    return summary

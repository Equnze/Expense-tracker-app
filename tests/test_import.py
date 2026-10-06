from datetime import date

import pytest

from expense_tracker.services import importer
from expense_tracker.services.importer import (
    ALL_ARE_EXPENSES,
    FAILED,
    NEGATIVE_IS_EXPENSE,
    POSITIVE_IS_EXPENSE,
    READY,
    SKIPPED,
    ColumnMapping,
    CsvImportError,
    flag_duplicates,
    guess_amount_mode,
    guess_column,
    guess_date_format,
    import_rows,
    parse_date,
    parse_rows,
    parse_signed_cents,
    read_csv,
)

STATEMENT = """Date,Description,Amount,Balance
05/10/2026,TESCO STORES 1234,-45.20,1000.00
06/10/2026,"COFFEE, CORNER",-3.50,996.50
07/10/2026,SALARY ACME LTD,2500.00,3496.50
not a date,BROKEN ROW,-1.00,0
08/10/2026,BAD AMOUNT,abc,0
09/10/2026,NO AMOUNT,,0

10/10/2026,  Spaced   out  ,"-1,234.56",0
"""


def write(tmp_path, text, name="statement.csv", encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


@pytest.fixture
def table(tmp_path):
    return read_csv(write(tmp_path, STATEMENT))


@pytest.fixture
def mapping():
    return ColumnMapping(0, 2, 1, "%d/%m/%Y", NEGATIVE_IS_EXPENSE)


# --- reading ------------------------------------------------------------------


def test_read_csv_with_header(table):
    assert table.headers == ["Date", "Description", "Amount", "Balance"]
    assert len(table.rows) == 7  # the blank line is dropped
    assert table.rows[1] == ["06/10/2026", "COFFEE, CORNER", "-3.50", "996.50"]
    # Line numbers refer to the file, so they skip the header and the blank line.
    assert table.line_numbers == [2, 3, 4, 5, 6, 7, 9]


def test_read_csv_without_header(tmp_path):
    table = read_csv(write(tmp_path, "2026-10-01,Bus,2.50\n2026-10-02,Tea\n"), False)
    assert table.headers == ["Column 1", "Column 2", "Column 3"]
    assert table.rows == [["2026-10-01", "Bus", "2.50"], ["2026-10-02", "Tea", ""]]
    assert table.line_numbers == [1, 2]


@pytest.mark.parametrize("delimiter", [";", "\t", "|"])
def test_read_csv_detects_delimiter(tmp_path, delimiter):
    text = "Date;Details;Amount\n01.10.2026;Bus;-2,50\n02.10.2026;Tea;-1,20\n"
    table = read_csv(write(tmp_path, text.replace(";", delimiter)))
    assert table.headers == ["Date", "Details", "Amount"]
    assert table.rows[0] == ["01.10.2026", "Bus", "-2,50"]


def test_read_csv_handles_bom_and_legacy_encoding(tmp_path):
    with_bom = read_csv(write(tmp_path, "Date,Memo\n2026-10-01,Café\n", "a.csv", "utf-8-sig"))
    assert with_bom.headers == ["Date", "Memo"] and with_bom.rows[0][1] == "Café"
    legacy = read_csv(write(tmp_path, "Date,Memo\n2026-10-01,Café £5\n", "b.csv", "cp1252"))
    assert legacy.rows[0][1] == "Café £5"


@pytest.mark.parametrize(
    "text, message",
    [("", "empty"), ("\n\n  \n", "empty"), ("Date,Amount\n", "no rows")],
)
def test_read_csv_rejects_unusable_files(tmp_path, text, message):
    with pytest.raises(CsvImportError, match=message):
        read_csv(write(tmp_path, text))


def test_read_csv_rejects_missing_and_binary_files(tmp_path):
    with pytest.raises(CsvImportError, match="couldn't be opened"):
        read_csv(tmp_path / "nope.csv")
    binary = tmp_path / "x.csv"
    binary.write_bytes(b"PK\x03\x04\x00\x00\x00binary")
    with pytest.raises(CsvImportError, match="doesn't look like"):
        read_csv(binary)


# --- single values ------------------------------------------------------------


@pytest.mark.parametrize(
    "text, fmt, expected",
    [
        ("2026-10-31", "%Y-%m-%d", date(2026, 10, 31)),
        ("31/10/2026", "%d/%m/%Y", date(2026, 10, 31)),
        ("10/31/2026", "%m/%d/%Y", date(2026, 10, 31)),
        ("5/1/26", "%d/%m/%y", date(2026, 1, 5)),
        ("31 Oct 2026", "%d %b %Y", date(2026, 10, 31)),
        ("Oct 31, 2026", "%b %d, %Y", date(2026, 10, 31)),
        ("2026-10-31 14:05:00", "%Y-%m-%d", date(2026, 10, 31)),
        ("2026-10-31T14:05:00", "%Y-%m-%d", date(2026, 10, 31)),
        (" 31.10.2026 ", "%d.%m.%Y", date(2026, 10, 31)),
    ],
)
def test_parse_date(text, fmt, expected):
    assert parse_date(text, fmt) == expected


@pytest.mark.parametrize("text", ["", "31/31/2026", "2026-02-30", "tomorrow"])
def test_parse_date_rejects_bad_values(text):
    with pytest.raises(ValueError):
        parse_date(text, "%d/%m/%Y")


def test_guess_date_format():
    assert guess_date_format(["2026-10-05", "2026-10-31"]) == "%Y-%m-%d"
    assert guess_date_format(["10/31/2026", "10/05/2026"]) == "%m/%d/%Y"
    assert guess_date_format(["31/10/2026", "05/10/2026"]) == "%d/%m/%Y"
    # Ambiguous values default to day-first; the wizard lets the user change it.
    assert guess_date_format(["05/10/2026", "06/10/2026"]) == "%d/%m/%Y"
    assert guess_date_format(["31 Oct 2026", ""]) == "%d %b %Y"


@pytest.mark.parametrize(
    "text, cents",
    [
        ("12.99", 1299),
        ("-12.99", -1299),
        ("12.99-", -1299),
        ("(12.99)", -1299),
        ("+12.99", 1299),
        ("$1,234.56", 123456),
        ("-£1,234.56", -123456),
        ("1.234,56", 123456),
        ("1 234,56 €", 123456),
        ("12,5", 1250),
        ("1,234", 123400),
        ("1,234,567", 123456700),
        ("45", 4500),
        (".5", 50),
        ("0.00", 0),
        ("19.99", 1999),
        ("2.675", 268),  # rounds half up, no float error
        ("1.005", 101),
        ("-0.125", -13),
    ],
)
def test_parse_signed_cents(text, cents):
    assert parse_signed_cents(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "-", "$", "n/a"])
def test_parse_signed_cents_rejects_non_amounts(text):
    with pytest.raises(ValueError):
        parse_signed_cents(text)


def test_guess_amount_mode():
    assert guess_amount_mode(["-1.00", "-2.00", "500.00"]) == NEGATIVE_IS_EXPENSE
    assert guess_amount_mode(["1.00", "2.00", "x"]) == POSITIVE_IS_EXPENSE
    assert guess_amount_mode([]) == POSITIVE_IS_EXPENSE


def test_guess_column():
    headers = ["Transaction Date", "Posted", "Details", "Debit Amount", "Balance"]
    assert guess_column(headers, "date") == 0
    assert guess_column(headers, "amount") == 3
    assert guess_column(headers, "description") == 2
    assert guess_column(["A", "B"], "date") is None


# --- rows -----------------------------------------------------------------


def test_parse_rows_maps_columns_and_classifies(table, mapping):
    rows = parse_rows(table, mapping)
    assert [row.status for row in rows] == [
        READY,
        READY,
        SKIPPED,  # salary: money in
        FAILED,  # bad date
        FAILED,  # bad amount
        SKIPPED,  # no amount
        READY,
    ]
    first = rows[0]
    assert (first.date, first.amount_cents, first.description, first.line_number) == (
        date(2026, 10, 5),
        4520,
        "TESCO STORES 1234",
        2,
    )
    assert rows[1].description == "COFFEE, CORNER"
    assert rows[2].note == "Not an expense (money in)"
    assert "date" in rows[3].note and "amount" in rows[4].note
    assert rows[5].note == "No amount"
    assert (rows[6].description, rows[6].amount_cents) == ("Spaced out", 123456)


def test_amount_modes(table, mapping):
    def ready_amounts(mode):
        mapping.amount_mode = mode
        return [r.amount_cents for r in parse_rows(table, mapping) if r.status == READY]

    assert ready_amounts(NEGATIVE_IS_EXPENSE) == [4520, 350, 123456]
    assert ready_amounts(POSITIVE_IS_EXPENSE) == [250000]
    assert ready_amounts(ALL_ARE_EXPENSES) == [4520, 350, 250000, 123456]


def test_wrong_date_format_fails_rows_instead_of_guessing(table, mapping):
    mapping.date_format = "%Y-%m-%d"
    rows = parse_rows(table, mapping)
    assert not any(row.status == READY for row in rows)


def test_rows_without_description_column(table, mapping):
    mapping.description_column = None
    assert parse_rows(table, mapping)[0].description == ""


def test_duplicates_are_flagged_and_unticked(table, mapping, expenses, make_expense):
    make_expense(4520, date(2026, 10, 5), description="tesco stores  1234")  # same
    make_expense(350, date(2026, 10, 7), description="COFFEE, CORNER")  # other day
    make_expense(999, date(2026, 10, 10), description="Spaced out")  # other amount

    rows = parse_rows(table, mapping)
    assert flag_duplicates(rows, expenses.duplicate_keys()) == 1
    ready = [row for row in rows if row.status == READY]
    assert [row.is_duplicate for row in ready] == [True, False, False]
    assert [row.selected for row in ready] == [False, True, True]


def test_import_saves_ready_rows_and_reports_counts(
    conn, table, mapping, expenses, categories, make_expense
):
    make_expense(4520, date(2026, 10, 5), description="TESCO STORES 1234")
    rows = parse_rows(table, mapping)
    flag_duplicates(rows, expenses.duplicate_keys())
    other = categories.find_by_name("Other").id
    dining = categories.find_by_name("Dining Out").id
    rows[1].category_id = dining  # per-row category change

    summary = import_rows(conn, expenses, rows, other, "Debit Card")
    assert (summary.imported, summary.skipped, summary.failed) == (2, 3, 2)
    assert summary.failed_lines == [5, 6]

    saved = {e.description: e for e in expenses.list()}
    assert len(saved) == 3
    assert saved["COFFEE, CORNER"].category_id == dining
    assert saved["COFFEE, CORNER"].payment_method == "Debit Card"
    assert saved["Spaced out"].category_id == other
    assert saved["Spaced out"].amount_cents == 123456
    assert saved["Spaced out"].date == date(2026, 10, 10)


def test_ticking_a_duplicate_imports_it_anyway(
    conn, table, mapping, expenses, categories, make_expense
):
    make_expense(4520, date(2026, 10, 5), description="TESCO STORES 1234")
    rows = parse_rows(table, mapping)
    flag_duplicates(rows, expenses.duplicate_keys())
    rows[0].selected = True
    summary = import_rows(conn, expenses, rows, categories.find_by_name("Other").id)
    assert summary.imported == 3
    assert len(expenses.list()) == 4


def test_importing_the_same_file_twice_adds_nothing(
    conn, table, mapping, expenses, categories
):
    other = categories.find_by_name("Other").id
    for expected in (3, 0):
        rows = parse_rows(table, mapping)
        flag_duplicates(rows, expenses.duplicate_keys())
        assert import_rows(conn, expenses, rows, other).imported == expected
    assert len(expenses.list()) == 3


def test_import_is_all_or_nothing(conn, table, mapping, expenses, monkeypatch):
    rows = parse_rows(table, mapping)
    with pytest.raises(Exception):
        import_rows(conn, expenses, rows, default_category_id=987654)  # no such category
    assert expenses.list() == []


def test_module_exposes_formats_for_the_wizard():
    assert len({fmt for _, fmt in importer.DATE_FORMATS}) == len(importer.DATE_FORMATS)
    assert importer.AMOUNT_MODES[0] == NEGATIVE_IS_EXPENSE

from datetime import date

import pytest
from PySide6.QtCore import Qt

from expense_tracker.services.importer import NEGATIVE_IS_EXPENSE
from expense_tracker.ui.import_wizard import (
    CATEGORY,
    NOTE,
    TICK,
    ImportWizard,
)

STATEMENT = """Transaction Date,Details,Amount
05/10/2026,TESCO STORES,-45.20
06/10/2026,COFFEE CORNER,-3.50
07/10/2026,SALARY,2500.00
oops,BROKEN,-1.00
13/10/2026,CINEMA,-12.00
"""


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "statement.csv"
    path.write_text(STATEMENT, encoding="utf-8")
    return path


@pytest.fixture
def wizard(ctx):
    wizard = ImportWizard(ctx)
    wizard.show()
    yield wizard
    wizard.close()


def test_file_page_previews_and_gates_next(wizard, csv_path, tmp_path):
    page = wizard.file_page
    assert not page.isComplete()

    page.load(tmp_path / "missing.csv")
    assert "couldn't be opened" in page.message.text()
    assert not page.isComplete()

    page.load(csv_path)
    assert page.isComplete()
    assert "5 rows found" in page.message.text()
    assert page.preview.rowCount() == 5
    assert page.preview.horizontalHeaderItem(1).text() == "Details"
    assert page.preview.item(0, 1).text() == "TESCO STORES"

    page.has_header.setChecked(False)
    assert page.preview.rowCount() == 6
    assert page.preview.horizontalHeaderItem(0).text() == "Column 1"


def test_full_import_flow(wizard, csv_path, ctx, make_expense):
    make_expense(350, date(2026, 10, 6), description="Coffee corner")  # duplicate
    dining = ctx.categories.find_by_name("Dining Out").id
    health = ctx.categories.find_by_name("Health").id

    wizard.file_page.load(csv_path)
    wizard.next()

    # Step 2: columns, date format and sign convention are guessed.
    mapping_page = wizard.mapping_page
    assert wizard.currentPage() is mapping_page
    assert mapping_page.date_column.currentText() == "Transaction Date"
    assert mapping_page.amount_column.currentText() == "Amount"
    assert mapping_page.description_column.currentText() == "Details"
    assert mapping_page.date_format.currentData() == "%d/%m/%Y"
    assert mapping_page.amount_mode.currentText() == NEGATIVE_IS_EXPENSE
    assert mapping_page.message.text() == (
        "3 ready to import, 1 will be skipped, 1 couldn't be read."
    )
    assert mapping_page.preview.item(0, 1).text() == "05 Oct 2026"
    assert mapping_page.preview.item(0, 3).text() == "$45.20"
    assert mapping_page.preview.item(3, 4).text().startswith("Couldn't read the date")
    assert mapping_page.isComplete()

    # A wrong date format leaves nothing to import, so Next is blocked.
    mapping_page.date_format.setCurrentIndex(mapping_page.date_format.findData("%Y-%m-%d"))
    assert not mapping_page.isComplete()
    assert "None of the rows" in mapping_page.message.text()
    mapping_page.date_format.setCurrentIndex(mapping_page.date_format.findData("%d/%m/%Y"))
    assert mapping_page.isComplete()
    wizard.next()

    # Step 3: duplicates are flagged and unticked; categories can be changed.
    review = wizard.review_page
    assert wizard.currentPage() is review
    assert review.table.rowCount() == 3
    assert review.default_category.currentText() == "Other"
    assert "1 look like expenses you already have" in review.message.text()
    ticks = [review.table.item(r, TICK).checkState() for r in range(3)]
    assert ticks == [Qt.CheckState.Checked, Qt.CheckState.Unchecked, Qt.CheckState.Checked]
    assert review.table.item(1, NOTE).text() == "Possible duplicate"
    assert review.table.item(0, CATEGORY).text() == "Other"

    review.default_category.setCurrentIndex(review.default_category.findData(dining))
    assert review.table.item(0, CATEGORY).text() == "Dining Out"

    # Change one row's category through the cell editor's delegate.
    index = review.table.model().index(2, CATEGORY)
    delegate = review.table.itemDelegateForColumn(CATEGORY)
    editor = delegate.createEditor(review.table.viewport(), None, index)
    editor.setCurrentIndex(editor.findData(health))
    delegate.setModelData(editor, review.table.model(), index)
    assert review.table.item(2, CATEGORY).text() == "Health"
    # Rows changed by hand keep their category when the default changes again.
    review.default_category.setCurrentText("Gifts")
    assert review.table.item(2, CATEGORY).text() == "Health"
    assert review.table.item(0, CATEGORY).text() == "Gifts"
    review.default_category.setCurrentIndex(review.default_category.findData(dining))
    review.payment.setCurrentText("Credit Card")
    wizard.next()

    # Step 4: summary, and the data is saved.
    result = wizard.result_page
    assert wizard.currentPage() is result
    assert result.imported.text() == "Imported 2 expenses."
    assert result.skipped.text().startswith("Skipped 2 rows")
    assert "line 5 of the file" in result.failed.text()
    summary = wizard.summary
    assert (summary.imported, summary.skipped, summary.failed) == (2, 2, 1)

    saved = {e.description: e for e in ctx.expenses.list()}
    assert set(saved) == {"Coffee corner", "TESCO STORES", "CINEMA"}
    assert saved["TESCO STORES"].category_id == dining
    assert saved["TESCO STORES"].amount_cents == 4520
    assert saved["TESCO STORES"].date == date(2026, 10, 5)
    assert saved["TESCO STORES"].payment_method == "Credit Card"
    assert saved["CINEMA"].category_id == health


def test_unticked_rows_are_not_imported_and_ticked_duplicates_are(
    wizard, csv_path, ctx, make_expense
):
    make_expense(350, date(2026, 10, 6), description="COFFEE CORNER")
    wizard.file_page.load(csv_path)
    wizard.next()
    wizard.next()
    review = wizard.review_page
    review.table.item(0, TICK).setCheckState(Qt.CheckState.Unchecked)
    review.table.item(1, TICK).setCheckState(Qt.CheckState.Checked)
    wizard.next()
    assert wizard.summary.imported == 2
    descriptions = sorted(e.description for e in ctx.expenses.list())
    assert descriptions == ["CINEMA", "COFFEE CORNER", "COFFEE CORNER"]


def test_same_column_for_date_and_amount_is_rejected(wizard, csv_path):
    wizard.file_page.load(csv_path)
    wizard.next()
    page = wizard.mapping_page
    page.amount_column.setCurrentIndex(page.date_column.currentIndex())
    assert not page.isComplete()
    assert "can't be the same column" in page.message.text()


def test_import_buttons_exist_on_expenses_and_settings_tabs(window):
    assert window.expenses_tab.import_button.text() == "Import CSV…"
    assert window.settings_tab.import_button.text() == "Import from CSV…"
    assert window.settings_tab.export_button.text() == "Export expenses…"

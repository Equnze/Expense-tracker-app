"""UI tests, run without a visible window using Qt's offscreen platform."""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from expense_tracker.models import ExpenseFilter
from expense_tracker.services.categories import CategoryInUseError
from expense_tracker.ui.category_dialogs import CategoryDialog, CategoryInUseDialog
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.expense_dialog import ExpenseDialog
from expense_tracker.ui.expense_table import AMOUNT, DATE
from expense_tracker.ui.main_window import MainWindow
from expense_tracker.utils.dates import ALL_TIME, CUSTOM, THIS_MONTH


def table_column(window, column):
    model = window.expenses_tab.table.model()
    return [model.index(row, column).data() for row in range(model.rowCount())]


def add(window, amount, description="", day=None):
    form = window.expenses_tab.form
    form.amount.setText(amount)
    form.description.setText(description)
    if day:
        form.date.setDate(QDate(day.year, day.month, day.day))
    QTest.keyClick(form.amount, Qt.Key.Key_Return)


# --- quick add ------------------------------------------------------------


def test_window_opens_with_three_tabs_and_amount_focused(window):
    tabs = window.tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Expenses",
        "Dashboard",
        "Settings",
    ]
    assert window.minimumWidth() == 1000 and window.minimumHeight() == 650
    form = window.expenses_tab.form
    assert form.date.date() == QDate.currentDate()
    assert form.category.count() == 13


def test_enter_adds_expense_and_resets_form(window, ctx, statuses):
    form = window.expenses_tab.form
    form.category.setCurrentText("Dining Out")
    form.payment.setCurrentText("Credit Card")
    add(window, "12.99", "Lunch")

    [expense] = ctx.expenses.list()
    assert expense.amount_cents == 1299
    assert expense.description == "Lunch"
    assert expense.date == date.today()
    assert expense.payment_method == "Credit Card"
    assert ctx.categories.get(expense.category_id).name == "Dining Out"

    assert form.amount.text() == "" and form.description.text() == ""
    assert form.category.currentText() == "Dining Out"
    assert form.error.text() == ""
    assert statuses[-1] == "Expense added"
    assert table_column(window, AMOUNT) == ["$12.99"]
    assert "1 expense " in window.expenses_tab.footer.text()
    assert "$12.99" in window.expenses_tab.footer.text()


def test_enter_in_any_field_saves(window, ctx):
    form = window.expenses_tab.form
    for widget in (form.date, form.category, form.description, form.payment):
        form.amount.setText("1")
        QTest.keyClick(widget, Qt.Key.Key_Return)
    assert len(ctx.expenses.list()) == 4


@pytest.mark.parametrize("text", ["", "abc", "0", "-3", "1.234"])
def test_invalid_amount_shows_inline_error_and_saves_nothing(window, ctx, text):
    add(window, text)
    form = window.expenses_tab.form
    assert form.error.text() != ""
    assert form.amount.property("invalid") is True
    assert ctx.expenses.list() == []

    form.amount.setText("5")
    assert form.error.text() == ""
    assert form.amount.property("invalid") is False


def test_form_defaults_to_last_used_category_and_method(ctx, conn):
    first = MainWindow(ctx)
    first.expenses_tab.form.category.setCurrentText("Travel")
    first.expenses_tab.form.payment.setCurrentText("Bank Transfer")
    add(first, "40")
    first.close()

    second = MainWindow(AppContext(conn))
    assert second.expenses_tab.form.category.currentText() == "Travel"
    assert second.expenses_tab.form.payment.currentText() == "Bank Transfer"
    second.close()


def test_expense_outside_filters_is_reported(window, statuses):
    add(window, "5", day=date(2001, 1, 1))
    assert statuses[-1] == "Expense added (hidden by the current filters)"
    assert table_column(window, AMOUNT) == []


def test_ctrl_n_focuses_amount_from_another_tab(window):
    window.tabs.setCurrentWidget(window.settings_tab)
    window.focus_new_expense()
    assert window.tabs.currentWidget() is window.expenses_tab


# --- table, filters -------------------------------------------------------


def test_table_sorts_newest_first_then_by_clicked_column(window, make_expense, ctx):
    today = date.today()
    make_expense(300, today.replace(day=1), description="first")
    make_expense(100, today.replace(day=2), description="second")
    make_expense(200, today.replace(day=2), description="third")
    ctx.data_changed.emit()
    assert table_column(window, AMOUNT) == ["$2.00", "$1.00", "$3.00"]

    table = window.expenses_tab.table
    table.sortByColumn(AMOUNT, Qt.SortOrder.AscendingOrder)
    assert table_column(window, AMOUNT) == ["$1.00", "$2.00", "$3.00"]
    table.sortByColumn(DATE, Qt.SortOrder.AscendingOrder)
    assert table_column(window, AMOUNT) == ["$3.00", "$1.00", "$2.00"]


def test_amount_sorts_numerically_and_formats_thousands(window, make_expense, ctx):
    today = date.today()
    make_expense(1000000, today)
    make_expense(99900, today)
    ctx.data_changed.emit()
    window.expenses_tab.table.sortByColumn(AMOUNT, Qt.SortOrder.DescendingOrder)
    assert table_column(window, AMOUNT) == ["$10,000.00", "$999.00"]
    assert "Total $10,999.00" in window.expenses_tab.footer.text()


def test_filters_narrow_the_table_and_clear_resets(window, make_expense, ctx):
    today = date.today()
    make_expense(100, today, "Travel", "Bus", "Cash")
    make_expense(200, today, "Gifts", "Flowers", "Credit Card", tags="birthday")
    make_expense(400, date(2001, 5, 5), "Gifts", "Old gift", "Cash")
    ctx.data_changed.emit()
    filters = window.expenses_tab.filters
    assert filters.preset.currentText() == THIS_MONTH
    assert sorted(table_column(window, AMOUNT)) == ["$1.00", "$2.00"]

    filters.search.setText("birth")
    assert table_column(window, AMOUNT) == ["$2.00"]
    filters.search.setText("")

    filters.payment.setCurrentText("Cash")
    assert table_column(window, AMOUNT) == ["$1.00"]

    filters.preset.setCurrentText(ALL_TIME)
    assert sorted(table_column(window, AMOUNT)) == ["$1.00", "$4.00"]

    gifts = ctx.categories.find_by_name("Gifts").id
    filters.categories._checks[gifts].setChecked(True)
    assert table_column(window, AMOUNT) == ["$4.00"]
    assert filters.categories.text() == "Gifts"
    assert "1 expense " in window.expenses_tab.footer.text()

    filters.clear_button.click()
    assert filters.preset.currentText() == THIS_MONTH
    assert filters.payment.currentIndex() == 0
    assert filters.categories.selected_ids() == set()
    assert sorted(table_column(window, AMOUNT)) == ["$1.00", "$2.00"]


def test_custom_range_shows_date_pickers(window, make_expense, ctx):
    make_expense(400, date(2001, 5, 5))
    ctx.data_changed.emit()
    filters = window.expenses_tab.filters
    assert filters.date_from.isHidden()

    filters.preset.setCurrentText(CUSTOM)
    assert not filters.date_from.isHidden() and not filters.date_to.isHidden()
    # A reversed range is treated as the same range.
    filters.date_from.setDate(QDate(2001, 12, 31))
    filters.date_to.setDate(QDate(2001, 1, 1))
    assert table_column(window, AMOUNT) == ["$4.00"]
    assert filters.current_filter() == ExpenseFilter(
        start_date=date(2001, 1, 1), end_date=date(2001, 12, 31)
    )


# --- edit, delete, undo ---------------------------------------------------


def test_edit_dialog_saves_changes_and_validates(ctx, make_expense):
    expense = make_expense(1299, date.today(), "Travel", "Bus")
    dialog = ExpenseDialog(ctx, ctx.expenses.get(expense.id))
    assert dialog.amount.text() == "12.99"
    assert dialog.category.currentText() == "Travel"

    dialog.amount.setText("nope")
    dialog.accept()
    assert dialog.error.text() != ""
    assert dialog.result() == 0

    dialog.amount.setText("20")
    dialog.category.setCurrentText("Gifts")
    dialog.description.setText("Taxi")
    dialog.accept()
    assert dialog.result() == 1
    assert dialog.expense.amount_cents == 2000
    assert dialog.expense.description == "Taxi"
    assert ctx.categories.get(dialog.expense.category_id).name == "Gifts"


def test_edit_dialog_keeps_archived_category_available(ctx, make_expense):
    expense = make_expense(category="Travel")
    ctx.categories.set_archived(expense.category_id, True)
    dialog = ExpenseDialog(ctx, ctx.expenses.get(expense.id))
    assert dialog.category.currentText() == "Travel (archived)"
    assert dialog.category.count() == 13


def test_enter_on_row_requests_edit(window, make_expense, ctx):
    expense = make_expense(day=date.today())
    ctx.data_changed.emit()
    requested = []
    table = window.expenses_tab.table
    table.edit_requested.disconnect()
    table.edit_requested.connect(requested.append)
    table.selectRow(0)
    QTest.keyClick(table, Qt.Key.Key_Return)
    assert requested == [expense.id]


def test_delete_key_removes_selected_rows_and_ctrl_z_restores(
    window, make_expense, ctx, statuses, confirm
):
    today = date.today()
    for cents in (100, 200, 300):
        make_expense(cents, today)
    ctx.data_changed.emit()
    tab = window.expenses_tab
    assert not tab.delete_button.isEnabled() and not tab.undo_button.isEnabled()

    tab.table.selectAll()
    assert tab.delete_button.isEnabled()
    QTest.keyClick(tab.table, Qt.Key.Key_Delete)
    assert ctx.expenses.list() == []
    assert table_column(window, AMOUNT) == []
    assert "Deleted 3 expenses" in statuses[-1]
    assert tab.undo_button.isEnabled()

    window._undo_delete()
    assert len(ctx.expenses.list()) == 3
    assert len(table_column(window, AMOUNT)) == 3
    assert statuses[-1] == "Restored 3 expenses"
    assert not tab.undo_button.isEnabled()


def test_delete_can_be_cancelled(window, make_expense, ctx, monkeypatch):
    make_expense(day=date.today())
    ctx.data_changed.emit()
    monkeypatch.setattr(QMessageBox, "exec", lambda box: box.reject())
    window.expenses_tab.table.selectAll()
    window.expenses_tab.delete_button.click()
    assert len(ctx.expenses.list()) == 1


# --- dashboard ------------------------------------------------------------


def test_dashboard_shows_month_figures_and_navigates(window, make_expense, ctx):
    today = date.today()
    dashboard = window.dashboard_tab
    assert dashboard.total_card.value.text() == "$0.00"
    assert not dashboard.empty_label.isHidden()

    make_expense(7500, today, "Travel")
    make_expense(2500, today, "Gifts")
    ctx.data_changed.emit()
    assert dashboard.total_card.value.text() == "$100.00"
    assert dashboard.breakdown.rowCount() == 2
    assert dashboard.breakdown.item(0, 0).text() == "Travel"
    assert dashboard.breakdown.item(0, 1).text() == "$75.00"
    assert dashboard.breakdown.item(0, 2).text() == "75.0%"
    assert "Travel" in dashboard.top_card.detail.text()
    assert "+$100.00" in dashboard.change_card.value.text()
    assert not dashboard.today_button.isEnabled()

    dashboard.next_button.click()
    assert dashboard.total_card.value.text() == "$0.00"
    assert "-$100.00" in dashboard.change_card.value.text()
    assert "-100.0%" in dashboard.change_card.detail.text()
    assert dashboard.today_button.isEnabled()

    dashboard.previous_button.click()
    dashboard.previous_button.click()
    assert dashboard.total_card.value.text() == "$0.00"
    dashboard.today_button.click()
    assert dashboard.total_card.value.text() == "$100.00"


# --- settings -------------------------------------------------------------


def test_currency_symbol_updates_everywhere(window, make_expense, ctx):
    make_expense(1299, date.today())
    ctx.data_changed.emit()
    settings_tab = window.settings_tab
    settings_tab.currency.setText("£")
    settings_tab.currency.editingFinished.emit()
    assert table_column(window, AMOUNT) == ["£12.99"]
    assert window.dashboard_tab.total_card.value.text() == "£12.99"

    settings_tab.currency.setText("  ")
    settings_tab.currency.editingFinished.emit()
    assert settings_tab.currency.text() == "£"


def test_category_dialog_shows_errors_inline(ctx):
    saved = []

    def save(name, color):
        saved.append(ctx.category_service.add(name, color))

    dialog = CategoryDialog("Add category", "", "#123456", save)
    dialog.name.setText("travel")
    dialog.accept()
    assert "already exists" in dialog.error.text()
    assert dialog.result() == 0 and saved == []

    dialog.name.setText("Pets")
    assert dialog.error.text() == ""
    dialog.accept()
    assert dialog.result() == 1
    assert saved[0].name == "Pets" and saved[0].color == "#123456"


def test_archiving_hides_category_from_add_form_only(window, ctx):
    settings_tab = window.settings_tab
    travel = ctx.categories.find_by_name("Travel")
    settings_tab._select(travel.id)
    assert settings_tab.archive_button.text() == "Archive"
    settings_tab.archive_button.click()

    form = window.expenses_tab.form
    assert form.category.findText("Travel") == -1
    assert form.category.count() == 12
    assert travel.id in window.expenses_tab.filters.categories._checks
    assert settings_tab.archive_button.text() == "Unarchive"

    settings_tab.archive_button.click()
    assert form.category.findText("Travel") >= 0


def test_deleting_unused_category(window, ctx, confirm, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    gifts = ctx.categories.find_by_name("Gifts")
    window.settings_tab._select(gifts.id)
    window.settings_tab.delete_button.click()
    assert ctx.categories.get(gifts.id) is None
    assert window.expenses_tab.form.category.findText("Gifts") == -1


def test_in_use_dialog_offers_archive_or_reassign(ctx, make_expense):
    make_expense(category="Travel")
    travel = ctx.categories.find_by_name("Travel")
    with pytest.raises(CategoryInUseError) as error:
        ctx.category_service.delete(travel.id)
    others = [c for c in ctx.categories.list() if c.id != travel.id]

    dialog = CategoryInUseDialog(error.value, others)
    assert dialog.archive_option.isChecked()
    assert dialog.reassign_target_id is None
    assert not dialog.target.isEnabled()

    dialog.reassign_option.setChecked(True)
    dialog.target.setCurrentText("Other")
    assert dialog.target.isEnabled()
    assert dialog.reassign_target_id == ctx.categories.find_by_name("Other").id


# --- persistence ----------------------------------------------------------


def test_window_size_and_tab_are_remembered(ctx, conn):
    first = MainWindow(ctx)
    first.show()
    first.resize(1000, 666)
    first.tabs.setCurrentWidget(first.dashboard_tab)
    first.close()

    second = MainWindow(AppContext(conn))
    assert second.tabs.currentWidget() is second.dashboard_tab
    # Only the height is checked: the offscreen test screen is narrower than
    # the window's minimum width, so Qt clamps the restored width.
    assert second.height() == 666
    second.close()

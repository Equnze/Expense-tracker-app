"""Wizard for importing a bank-statement CSV file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from expense_tracker.models import PAYMENT_METHODS
from expense_tracker.services import importer
from expense_tracker.services.importer import (
    FAILED,
    READY,
    SKIPPED,
    ColumnMapping,
    CsvImportError,
    CsvTable,
    ImportRow,
    ImportSummary,
)
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.style import DANGER, INPUT_HEIGHT, MUTED
from expense_tracker.ui.widgets import color_icon, fill_category_combo
from expense_tracker.utils.dates import format_display

IMPORT_DIR_KEY = "last_import_dir"
PREVIEW_ROWS = 10
NO_COLUMN = "(none)"

_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_ROW_ROLE = Qt.ItemDataRole.UserRole
# Review-table columns.
TICK, DATE, DESCRIPTION, AMOUNT, CATEGORY, NOTE = range(6)


def _make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(30)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    return table


def _item(text: str, alignment=None, color: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    if alignment is not None:
        item.setTextAlignment(alignment)
    if color:
        item.setForeground(QColor(color))
    return item


class FilePage(QWizardPage):
    """Step 1: choose the file and see its first rows."""

    def __init__(self, wizard: "ImportWizard") -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Choose a file")
        self.setSubTitle(
            "Pick the CSV file you downloaded from your bank. Nothing is imported yet."
        )

        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("No file chosen")
        self.path.setMinimumHeight(INPUT_HEIGHT)
        self.browse = QPushButton("Browse…")
        self.browse.setMinimumHeight(INPUT_HEIGHT)
        self.has_header = QCheckBox("The first row contains column names")
        self.has_header.setChecked(True)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.preview = _make_table([])

        chooser = QHBoxLayout()
        chooser.addWidget(self.path, 1)
        chooser.addWidget(self.browse)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(chooser)
        layout.addWidget(self.has_header)
        layout.addWidget(self.message)
        layout.addWidget(self.preview, 1)

        self.browse.clicked.connect(self._browse)
        self.has_header.toggled.connect(self._reload)

    def _browse(self) -> None:
        ctx = self._wizard.ctx
        folder = ctx.settings.get(IMPORT_DIR_KEY) or str(Path.home() / "Downloads")
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Choose a CSV file", folder, "CSV files (*.csv *.txt);;All files (*)"
        )
        if chosen:
            ctx.settings.set(IMPORT_DIR_KEY, str(Path(chosen).parent))
            self.load(Path(chosen))

    def _reload(self) -> None:
        if self.path.text():
            self.load(Path(self.path.text()))

    def load(self, path: Path) -> None:
        """Read the file and show a preview, or an inline message if it is unusable."""
        self.path.setText(str(path))
        try:
            table = importer.read_csv(path, self.has_header.isChecked())
        except CsvImportError as exc:
            self._wizard.table = None
            self.preview.setRowCount(0)
            self.preview.setColumnCount(0)
            self._show_message(str(exc), error=True)
        else:
            self._wizard.table = table
            self._show_preview(table)
            count = len(table.rows)
            shown = min(count, PREVIEW_ROWS)
            self._show_message(
                f"{count:,} row{'' if count == 1 else 's'} found. "
                f"Showing the first {shown}."
            )
        self.completeChanged.emit()

    def _show_message(self, text: str, error: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {DANGER if error else MUTED};")

    def _show_preview(self, table: CsvTable) -> None:
        self.preview.setColumnCount(len(table.headers))
        self.preview.setHorizontalHeaderLabels(table.headers)
        rows = table.rows[:PREVIEW_ROWS]
        self.preview.setRowCount(len(rows))
        for row, cells in enumerate(rows):
            for column, cell in enumerate(cells):
                self.preview.setItem(row, column, _item(cell))
        self.preview.resizeColumnsToContents()

    def isComplete(self) -> bool:
        return self._wizard.table is not None


class MappingPage(QWizardPage):
    """Step 2: say which columns hold the date, amount and description."""

    def __init__(self, wizard: "ImportWizard") -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self._loading = False
        self.setTitle("Match the columns")
        self.setSubTitle(
            "Tell the app which columns to use. Check the preview reads your "
            "dates and amounts correctly."
        )

        self.date_column = QComboBox()
        self.amount_column = QComboBox()
        self.description_column = QComboBox()
        self.date_format = QComboBox()
        for label, date_format in importer.DATE_FORMATS:
            self.date_format.addItem(label, date_format)
        self.amount_mode = QComboBox()
        self.amount_mode.addItems(importer.AMOUNT_MODES)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.preview = _make_table(["Line", "Date", "Description", "Amount", "Result"])
        self.preview.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.preview.horizontalHeaderItem(3).setTextAlignment(_RIGHT)

        left = QFormLayout()
        left.addRow("Date column", self.date_column)
        left.addRow("Date format", self.date_format)
        left.addRow("Description column", self.description_column)
        right = QFormLayout()
        right.addRow("Amount column", self.amount_column)
        right.addRow("Amounts", self.amount_mode)
        forms = QHBoxLayout()
        forms.setSpacing(24)
        forms.addLayout(left, 1)
        forms.addLayout(right, 1)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(forms)
        layout.addWidget(self.message)
        layout.addWidget(self.preview, 1)

        for combo in (
            self.date_column,
            self.amount_column,
            self.description_column,
            self.date_format,
            self.amount_mode,
        ):
            combo.setMinimumHeight(INPUT_HEIGHT)
            combo.currentIndexChanged.connect(self._update)

    def initializePage(self) -> None:
        """Fill the column lists and make a first guess at the mapping."""
        table = self._wizard.table
        self._loading = True
        for combo in (self.date_column, self.amount_column, self.description_column):
            combo.clear()
            if combo is self.description_column:
                combo.addItem(NO_COLUMN, None)
            for index, header in enumerate(table.headers):
                combo.addItem(header, index)

        date_index = importer.guess_column(table.headers, "date") or 0
        amount_index = importer.guess_column(table.headers, "amount")
        if amount_index is None:
            amount_index = min(len(table.headers) - 1, 1)
        description_index = importer.guess_column(table.headers, "description")
        self.date_column.setCurrentIndex(self.date_column.findData(date_index))
        self.amount_column.setCurrentIndex(self.amount_column.findData(amount_index))
        self.description_column.setCurrentIndex(
            max(self.description_column.findData(description_index), 0)
        )

        sample = table.rows[:50]
        guessed = importer.guess_date_format([row[date_index] for row in sample])
        self.date_format.setCurrentIndex(self.date_format.findData(guessed))
        self.amount_mode.setCurrentText(
            importer.guess_amount_mode([row[amount_index] for row in sample])
        )
        self._loading = False
        self._update()

    def mapping(self) -> ColumnMapping:
        return ColumnMapping(
            date_column=self.date_column.currentData(),
            amount_column=self.amount_column.currentData(),
            description_column=self.description_column.currentData(),
            date_format=self.date_format.currentData(),
            amount_mode=self.amount_mode.currentText(),
        )

    def _update(self) -> None:
        if self._loading or self._wizard.table is None:
            return
        mapping = self.mapping()
        rows = importer.parse_rows(self._wizard.table, mapping)
        self._wizard.rows = rows
        money = self._wizard.ctx.money

        counts = {status: 0 for status in (READY, SKIPPED, FAILED)}
        for row in rows:
            counts[row.status] += 1
        if mapping.date_column == mapping.amount_column:
            self._show_message("The date and the amount can't be the same column.", True)
            self._wizard.rows = []
        elif counts[READY] == 0:
            self._show_message(
                "None of the rows could be read as expenses with these settings. "
                "Try a different column, date format or amount setting.",
                True,
            )
        else:
            parts = [f"{counts[READY]:,} ready to import"]
            if counts[SKIPPED]:
                parts.append(f"{counts[SKIPPED]:,} will be skipped")
            if counts[FAILED]:
                parts.append(f"{counts[FAILED]:,} couldn't be read")
            self._show_message(", ".join(parts) + ".")

        shown = rows[:PREVIEW_ROWS]
        self.preview.setRowCount(len(shown))
        for index, row in enumerate(shown):
            color = None if row.status == READY else (
                DANGER if row.status == FAILED else MUTED
            )
            cells = [
                _item(str(row.line_number), color=MUTED),
                _item(format_display(row.date) if row.date else "—", color=color),
                _item(row.description, color=color),
                _item(
                    money(row.amount_cents) if row.amount_cents else "—", _RIGHT, color
                ),
                _item("Ready" if row.status == READY else row.note, color=color),
            ]
            for column, cell in enumerate(cells):
                self.preview.setItem(index, column, cell)
        self.preview.resizeColumnToContents(4)
        self.completeChanged.emit()

    def _show_message(self, text: str, error: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {DANGER if error else MUTED};")

    def isComplete(self) -> bool:
        return any(row.status == READY for row in self._wizard.rows)


class CategoryDelegate(QStyledItemDelegate):
    """Lets a Category cell in the review table be changed with a drop-down."""

    def __init__(self, page: "ReviewPage") -> None:
        super().__init__(page)
        self._page = page

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        fill_category_combo(combo, self._page.categories, None)
        combo.activated.connect(lambda: self._finish(combo))
        return combo

    def _finish(self, combo: QComboBox) -> None:
        self.commitData.emit(combo)
        self.closeEditor.emit(combo)

    def setEditorData(self, editor: QComboBox, index) -> None:
        row: ImportRow = index.data(_ROW_ROLE)
        category_id = row.category_id or self._page.default_category.currentData()
        editor.setCurrentIndex(max(editor.findData(category_id), 0))
        editor.showPopup()

    def setModelData(self, editor: QComboBox, model, index) -> None:
        row: ImportRow = index.data(_ROW_ROLE)
        row.category_id = editor.currentData()
        self._page.show_category(index.row())


class ReviewPage(QWizardPage):
    """Steps 3 and 4: choose categories and decide what to do with duplicates."""

    def __init__(self, wizard: "ImportWizard") -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.categories = []
        self.ready_rows: list[ImportRow] = []
        self.setTitle("Review and import")
        self.setSubTitle(
            "Untick anything you don't want. Click a category to change it for "
            "that row."
        )
        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "Import")

        self.default_category = QComboBox()
        self.default_category.setMinimumHeight(INPUT_HEIGHT)
        self.default_category.setMinimumWidth(200)
        self.payment = QComboBox()
        self.payment.setMinimumHeight(INPUT_HEIGHT)
        self.payment.addItems(PAYMENT_METHODS)
        self.payment.setCurrentText("Debit Card")
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(f"color: {MUTED};")

        self.table = _make_table(
            ["Import", "Date", "Description", "Amount", "Category", "Note"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.table.setItemDelegateForColumn(CATEGORY, CategoryDelegate(self))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(AMOUNT).setTextAlignment(_RIGHT)
        self.table.setColumnWidth(TICK, 64)
        self.table.setColumnWidth(DATE, 105)
        self.table.setColumnWidth(AMOUNT, 110)
        self.table.setColumnWidth(CATEGORY, 180)
        self.table.setColumnWidth(NOTE, 140)

        options = QHBoxLayout()
        options.setSpacing(10)
        options.addWidget(QLabel("Category for these expenses"))
        options.addWidget(self.default_category)
        options.addSpacing(16)
        options.addWidget(QLabel("Payment method"))
        options.addWidget(self.payment)
        options.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(options)
        layout.addWidget(self.message)
        layout.addWidget(self.table, 1)

        self.default_category.currentIndexChanged.connect(self._show_all_categories)
        self.table.itemChanged.connect(self._on_item_changed)

    def initializePage(self) -> None:
        ctx = self._wizard.ctx
        self.categories = ctx.categories.list(include_archived=False)
        other = next((c.id for c in self.categories if c.name == "Other"), None)
        fill_category_combo(self.default_category, self.categories, other)

        rows = self._wizard.rows
        duplicates = importer.flag_duplicates(rows, ctx.expenses.duplicate_keys())
        self.ready_rows = [row for row in rows if row.status == READY]
        for row in self.ready_rows:
            row.category_id = None

        self.table.blockSignals(True)
        self.table.setRowCount(len(self.ready_rows))
        for index, row in enumerate(self.ready_rows):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setCheckState(
                Qt.CheckState.Checked if row.selected else Qt.CheckState.Unchecked
            )
            category = QTableWidgetItem()
            category.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
            category.setData(_ROW_ROLE, row)
            cells = [
                tick,
                _item(format_display(row.date)),
                _item(row.description),
                _item(ctx.money(row.amount_cents), _RIGHT),
                category,
                _item("Possible duplicate" if row.is_duplicate else "", color=DANGER),
            ]
            for column, cell in enumerate(cells):
                self.table.setItem(index, column, cell)
            self.show_category(index)
        self.table.blockSignals(False)

        text = f"{len(self.ready_rows):,} expenses found."
        if duplicates:
            text += (
                f" {duplicates:,} look like expenses you already have (same date, "
                "amount and description) and are unticked."
            )
        self.message.setText(text)

    def show_category(self, index: int) -> None:
        """Refresh the Category cell of one row from its ImportRow."""
        row = self.ready_rows[index]
        category_id = row.category_id or self.default_category.currentData()
        category = next((c for c in self.categories if c.id == category_id), None)
        item = self.table.item(index, CATEGORY)
        self.table.blockSignals(True)
        item.setText(category.name if category else "")
        if category:
            item.setIcon(color_icon(category.color))
        self.table.blockSignals(False)

    def _show_all_categories(self) -> None:
        for index in range(len(self.ready_rows)):
            if self.table.item(index, CATEGORY) is not None:
                self.show_category(index)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == TICK:
            self.ready_rows[item.row()].selected = (
                item.checkState() == Qt.CheckState.Checked
            )

    def validatePage(self) -> bool:
        """Runs when Import is clicked: save the rows."""
        ctx = self._wizard.ctx
        if self.default_category.currentData() is None:
            self.message.setText("Add a category in Settings before importing.")
            self.message.setStyleSheet(f"color: {DANGER};")
            return False
        self._wizard.summary = importer.import_rows(
            ctx.conn,
            ctx.expenses,
            self._wizard.rows,
            self.default_category.currentData(),
            self.payment.currentText(),
        )
        ctx.data_changed.emit()
        return True


class ResultPage(QWizardPage):
    """Final step: how many rows were imported, skipped or failed."""

    def __init__(self, wizard: "ImportWizard") -> None:
        super().__init__(wizard)
        self._wizard = wizard
        self.setTitle("Import finished")
        self.imported = QLabel()
        self.imported.setObjectName("sectionTitle")
        self.skipped = QLabel()
        self.failed = QLabel()
        self.failed.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.imported)
        layout.addWidget(self.skipped)
        layout.addWidget(self.failed)
        layout.addStretch(1)

    def initializePage(self) -> None:
        summary: ImportSummary = self._wizard.summary
        self.imported.setText(
            f"Imported {summary.imported:,} expense{'' if summary.imported == 1 else 's'}."
        )
        self.skipped.setText(
            f"Skipped {summary.skipped:,} "
            f"row{'' if summary.skipped == 1 else 's'} "
            "(duplicates, rows you unticked, and rows that aren't expenses)."
        )
        text = f"Failed: {summary.failed:,} row{'' if summary.failed == 1 else 's'}"
        if summary.failed:
            lines = ", ".join(str(line) for line in summary.failed_lines[:15])
            more = "…" if summary.failed > 15 else ""
            text += (
                f" couldn't be read (line{'' if summary.failed == 1 else 's'} "
                f"{lines}{more} of the file). You can add them by hand."
            )
            self.failed.setStyleSheet(f"color: {DANGER};")
        else:
            text += "."
        self.failed.setText(text)


class ImportWizard(QWizard):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.table: CsvTable | None = None
        self.rows: list[ImportRow] = []
        self.summary = ImportSummary()

        self.setWindowTitle("Import from CSV")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)
        self.setOption(QWizard.WizardOption.NoCancelButtonOnLastPage, True)
        self.setMinimumSize(860, 600)

        self.file_page = FilePage(self)
        self.mapping_page = MappingPage(self)
        self.review_page = ReviewPage(self)
        self.result_page = ResultPage(self)
        for page in (
            self.file_page,
            self.mapping_page,
            self.review_page,
            self.result_page,
        ):
            self.addPage(page)

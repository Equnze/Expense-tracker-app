"""Settings tab: category management and general preferences."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expense_tracker.models import Category
from expense_tracker.services.categories import CategoryInUseError
from expense_tracker.ui.category_dialogs import CategoryDialog, CategoryInUseDialog
from expense_tracker.ui.context import CURRENCY_KEY, AppContext
from expense_tracker.ui.style import INPUT_HEIGHT, MUTED
from expense_tracker.ui.widgets import color_icon
from expense_tracker.utils import paths

_ID_ROLE = Qt.ItemDataRole.UserRole


class SettingsTab(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(14)
        layout.addWidget(self._build_categories_panel(), 3)
        layout.addWidget(self._build_general_panel(), 2)

        ctx.categories_changed.connect(self._reload_categories)
        self._reload_categories()

    # --- categories -------------------------------------------------------

    def _build_categories_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card")

        title = QLabel("Categories")
        title.setObjectName("sectionTitle")
        hint = QLabel(
            "Archived categories are hidden from the add form but keep their expenses."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)

        self.category_list = QListWidget()
        self.add_button = QPushButton("Add…")
        self.edit_button = QPushButton("Edit…")
        self.archive_button = QPushButton("Archive")
        self.delete_button = QPushButton("Delete…")

        buttons = QVBoxLayout()
        buttons.setSpacing(8)
        for button in (
            self.add_button,
            self.edit_button,
            self.archive_button,
            self.delete_button,
        ):
            button.setMinimumHeight(INPUT_HEIGHT)
            button.setMinimumWidth(110)
            buttons.addWidget(button)
        buttons.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.category_list, 1)
        body.addLayout(buttons)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(body, 1)

        self.add_button.clicked.connect(self._add_category)
        self.edit_button.clicked.connect(self._edit_category)
        self.archive_button.clicked.connect(self._toggle_archived)
        self.delete_button.clicked.connect(self._delete_category)
        self.category_list.itemDoubleClicked.connect(self._edit_category)
        self.category_list.currentItemChanged.connect(self._update_buttons)
        return panel

    def _reload_categories(self) -> None:
        selected_id = self._selected_id()
        self.category_list.blockSignals(True)
        self.category_list.clear()
        for category in self._ctx.categories.list():
            label = category.name + ("  (archived)" if category.is_archived else "")
            item = QListWidgetItem(color_icon(category.color), label)
            item.setData(_ID_ROLE, category.id)
            if category.is_archived:
                item.setForeground(QColor(MUTED))
            self.category_list.addItem(item)
            if category.id == selected_id:
                self.category_list.setCurrentItem(item)
        self.category_list.blockSignals(False)
        self._update_buttons()

    def _selected_id(self) -> int | None:
        item = self.category_list.currentItem()
        return item.data(_ID_ROLE) if item else None

    def _selected(self) -> Category | None:
        selected_id = self._selected_id()
        return self._ctx.categories.get(selected_id) if selected_id else None

    def _update_buttons(self) -> None:
        category = self._selected()
        for button in (self.edit_button, self.archive_button, self.delete_button):
            button.setEnabled(category is not None)
        self.archive_button.setText(
            "Unarchive" if category and category.is_archived else "Archive"
        )

    def _add_category(self) -> None:
        service = self._ctx.category_service
        created: list[Category] = []
        dialog = CategoryDialog(
            "Add category",
            "",
            service.next_color(),
            lambda name, color: created.append(service.add(name, color)),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._ctx.categories_changed.emit()
            self._select(created[0].id)
            self._ctx.status_message.emit(f"Added category “{created[0].name}”")

    def _edit_category(self) -> None:
        category = self._selected()
        if category is None:
            return
        dialog = CategoryDialog(
            "Edit category",
            category.name,
            category.color,
            lambda name, color: self._ctx.category_service.update(
                category.id, name, color
            ),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._ctx.categories_changed.emit()
            self._ctx.status_message.emit("Category updated")

    def _toggle_archived(self) -> None:
        category = self._selected()
        if category is None:
            return
        self._ctx.category_service.set_archived(category.id, not category.is_archived)
        self._ctx.categories_changed.emit()
        action = "Unarchived" if category.is_archived else "Archived"
        self._ctx.status_message.emit(f"{action} “{category.name}”")

    def _delete_category(self) -> None:
        category = self._selected()
        if category is None:
            return
        service = self._ctx.category_service
        if self._ctx.categories.expense_count(category.id) == 0:
            answer = QMessageBox.question(
                self,
                "Delete category",
                f"Delete the category “{category.name}”?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            service.delete(category.id)
        except CategoryInUseError as error:
            self._resolve_in_use(category, error)
            return
        self._ctx.categories_changed.emit()
        self._ctx.status_message.emit(f"Deleted category “{category.name}”")

    def _resolve_in_use(self, category: Category, error: CategoryInUseError) -> None:
        others = [
            other
            for other in self._ctx.categories.list()
            if other.id != category.id and not other.is_archived
        ]
        dialog = CategoryInUseDialog(error, others, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target_id = dialog.reassign_target_id
        if target_id is None:
            self._ctx.category_service.set_archived(category.id, True)
            message = f"Archived “{category.name}”"
        else:
            moved = self._ctx.category_service.reassign_and_delete(
                category.id, target_id
            )
            target = self._ctx.categories.get(target_id)
            message = (
                f"Moved {moved} expense{'' if moved == 1 else 's'} to "
                f"“{target.name}” and deleted “{category.name}”"
            )
        self._ctx.categories_changed.emit()
        self._ctx.data_changed.emit()
        self._ctx.status_message.emit(message)

    def _select(self, category_id: int) -> None:
        for row in range(self.category_list.count()):
            item = self.category_list.item(row)
            if item.data(_ID_ROLE) == category_id:
                self.category_list.setCurrentItem(item)
                return

    # --- general ----------------------------------------------------------

    def _build_general_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card")

        title = QLabel("General")
        title.setObjectName("sectionTitle")

        self.currency = QLineEdit(self._ctx.currency)
        self.currency.setMaxLength(4)
        self.currency.setFixedWidth(80)
        self.currency.setMinimumHeight(INPUT_HEIGHT)
        self.currency.setToolTip("Shown in front of every amount, e.g. $, £, € or ₦")
        self.currency.editingFinished.connect(self._save_currency)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.addRow("Currency symbol", self.currency)

        data_title = QLabel("Your data")
        data_title.setObjectName("sectionTitle")
        data_hint = QLabel(
            "Everything is saved automatically on this computer, in:\n"
            f"{paths.data_dir()}"
        )
        data_hint.setObjectName("hintLabel")
        data_hint.setWordWrap(True)
        data_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_button = QPushButton("Open data folder")
        open_button.setMinimumHeight(INPUT_HEIGHT)
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(paths.data_dir()))
            )
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addSpacing(14)
        layout.addWidget(data_title)
        layout.addWidget(data_hint)
        layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return panel

    def _save_currency(self) -> None:
        symbol = self.currency.text().strip()
        if not symbol:
            self.currency.setText(self._ctx.currency)
            return
        if symbol == self._ctx.currency:
            return
        self._ctx.settings.set(CURRENCY_KEY, symbol)
        self._ctx.settings_changed.emit()
        self._ctx.status_message.emit(f"Currency symbol set to {symbol}")

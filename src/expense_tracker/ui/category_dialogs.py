"""Dialogs used by category management in Settings."""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from expense_tracker.models import Category
from expense_tracker.services.categories import (
    MAX_NAME_LENGTH,
    CategoryError,
    CategoryInUseError,
)
from expense_tracker.ui.style import INPUT_HEIGHT
from expense_tracker.ui.widgets import color_icon, fill_category_combo, set_invalid


class CategoryDialog(QDialog):
    """Name and color editor. ``on_save`` does the work and may raise CategoryError,
    which is shown inline so the user can correct it without losing the dialog."""

    def __init__(
        self,
        title: str,
        name: str,
        color: str,
        on_save: Callable[[str, str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_save = on_save
        self._color = color
        self.setWindowTitle(title)
        self.setMinimumWidth(380)

        self.name = QLineEdit(name)
        self.name.setMaxLength(MAX_NAME_LENGTH)
        self.name.setMinimumHeight(INPUT_HEIGHT)
        self.color_button = QPushButton()
        self.color_button.setMinimumHeight(INPUT_HEIGHT)
        self.error = QLabel("")
        self.error.setObjectName("errorLabel")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        form.addRow("Name", self.name)
        form.addRow("Color", self.color_button)
        form.addRow("", self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.color_button.clicked.connect(self._pick_color)
        self.name.textChanged.connect(self._clear_error)
        self._show_color()
        self.name.selectAll()

    def _show_color(self) -> None:
        self.color_button.setIcon(color_icon(self._color))
        self.color_button.setText(f"  {self._color.upper()}   Change…")

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, "Category color")
        if chosen.isValid():
            self._color = chosen.name()
            self._show_color()

    def _clear_error(self) -> None:
        self.error.setText("")
        set_invalid(self.name, False)

    def accept(self) -> None:
        try:
            self._on_save(self.name.text(), self._color)
        except CategoryError as exc:
            self.error.setText(str(exc))
            set_invalid(self.name, True)
            self.name.setFocus()
            return
        super().accept()


class CategoryInUseDialog(QDialog):
    """Shown instead of deleting a category that has expenses: archive or reassign."""

    def __init__(
        self, error: CategoryInUseError, others: list[Category], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Category has expenses")
        self.setMinimumWidth(440)

        message = QLabel(f"{error}\nWhat would you like to do instead?")
        message.setWordWrap(True)
        self.archive_option = QRadioButton(
            "Archive it — hide it from the add form but keep its history"
        )
        self.archive_option.setChecked(True)
        if error.category.is_archived:
            self.archive_option.setText("Keep it archived")
        self.reassign_option = QRadioButton(
            "Move its expenses to another category, then delete it:"
        )
        self.target = QComboBox()
        self.target.setMinimumHeight(INPUT_HEIGHT)
        fill_category_combo(self.target, others, None)
        self.target.setEnabled(False)
        self.reassign_option.setEnabled(bool(others))
        self.reassign_option.toggled.connect(self.target.setEnabled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(message)
        layout.addWidget(self.archive_option)
        layout.addWidget(self.reassign_option)
        layout.addWidget(self.target)
        layout.addSpacing(6)
        layout.addWidget(buttons)

    @property
    def reassign_target_id(self) -> int | None:
        """The category to move expenses to, or None if archiving was chosen."""
        if self.reassign_option.isChecked():
            return self.target.currentData()
        return None

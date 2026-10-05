"""Category management rules."""

from __future__ import annotations

import re
import sqlite3

from expense_tracker.db.connection import transaction
from expense_tracker.db.repositories import CategoryRepository, ExpenseRepository
from expense_tracker.db.schema import DEFAULT_CATEGORIES
from expense_tracker.models import Category

MAX_NAME_LENGTH = 40
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class CategoryError(ValueError):
    """Raised when a category change is not allowed. The message is user-facing."""


class CategoryInUseError(CategoryError):
    """Raised when deleting a category that still has expenses."""

    def __init__(self, category: Category, expense_count: int) -> None:
        super().__init__(
            f"“{category.name}” has {expense_count} "
            f"expense{'s' if expense_count != 1 else ''} and can't be deleted."
        )
        self.category = category
        self.expense_count = expense_count


class CategoryService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        categories: CategoryRepository,
        expenses: ExpenseRepository,
    ) -> None:
        self._conn = conn
        self._categories = categories
        self._expenses = expenses

    def _validate(self, name: str, color: str, ignore_id: int | None = None) -> str:
        name = " ".join(name.split())
        if not name:
            raise CategoryError("Enter a category name.")
        if len(name) > MAX_NAME_LENGTH:
            raise CategoryError(f"Use at most {MAX_NAME_LENGTH} characters.")
        if not _HEX_COLOR_RE.match(color):
            raise CategoryError("Pick a valid color.")
        existing = self._categories.find_by_name(name)
        if existing and existing.id != ignore_id:
            raise CategoryError(f"A category named “{existing.name}” already exists.")
        return name

    def next_color(self) -> str:
        """Suggest a default-palette color that is used least by existing categories."""
        used = [category.color.upper() for category in self._categories.list()]
        palette = [color for _, color in DEFAULT_CATEGORIES]
        return min(palette, key=lambda color: used.count(color.upper()))

    def add(self, name: str, color: str | None = None) -> Category:
        color = color or self.next_color()
        name = self._validate(name, color)
        return self._categories.add(name, color)

    def update(self, category_id: int, name: str, color: str) -> None:
        name = self._validate(name, color, ignore_id=category_id)
        self._categories.update(category_id, name, color)

    def set_archived(self, category_id: int, archived: bool) -> None:
        self._categories.set_archived(category_id, archived)

    def delete(self, category_id: int) -> None:
        """Delete an unused category; raise CategoryInUseError if it has expenses."""
        category = self._categories.get(category_id)
        if category is None:
            return
        count = self._categories.expense_count(category_id)
        if count:
            raise CategoryInUseError(category, count)
        self._categories.delete(category_id)

    def reassign_and_delete(self, category_id: int, target_id: int) -> int:
        """Move a category's expenses to another one, then delete it."""
        if category_id == target_id:
            raise CategoryError("Choose a different category to move the expenses to.")
        if self._categories.get(target_id) is None:
            raise CategoryError("The category to move expenses to no longer exists.")
        with transaction(self._conn):
            moved = self._expenses.reassign_category(category_id, target_id)
            self._categories.delete(category_id)
        return moved

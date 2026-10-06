"""Main window: tabs, status bar, shortcuts and remembered window state."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QCloseEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget

from expense_tracker.ui.budgets_tab import BudgetsTab
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.dashboard_tab import DashboardTab
from expense_tracker.ui.expenses_tab import ExpensesTab
from expense_tracker.ui.recurring_tab import RecurringTab, generated_message
from expense_tracker.ui.settings_tab import SettingsTab
from expense_tracker.ui.toast import INFO, Toast

GEOMETRY_KEY = "window_geometry"
TAB_KEY = "last_tab"
STATUS_TIMEOUT_MS = 6000


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setWindowTitle("Expense Tracker")
        self.setMinimumSize(1000, 650)
        self.resize(1120, 720)

        self.expenses_tab = ExpensesTab(ctx)
        self.dashboard_tab = DashboardTab(ctx)
        self.budgets_tab = BudgetsTab(ctx)
        self.recurring_tab = RecurringTab(ctx)
        self.settings_tab = SettingsTab(ctx)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.expenses_tab, "Expenses")
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.budgets_tab, "Budgets")
        self.tabs.addTab(self.recurring_tab, "Recurring")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)

        self.statusBar().setSizeGripEnabled(False)
        ctx.status_message.connect(
            lambda text: self.statusBar().showMessage(text, STATUS_TIMEOUT_MS)
        )

        self.settings_tab.import_requested.connect(self.expenses_tab.import_csv)
        self.settings_tab.export_requested.connect(self.expenses_tab.export_filtered)

        self.toast = Toast(self)
        ctx.notification.connect(self.toast.show_message)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.focus_new_expense)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo_delete)

        self._restore_state()
        if self.tabs.currentWidget() is self.expenses_tab:
            self.expenses_tab.form.focus_amount()

    def generate_recurring(self) -> int:
        """Add recurring expenses that have come due since the last launch and
        show a short notice of what was added. Returns how many were added."""
        generated = self._ctx.recurring_service.generate_due(date.today())
        if generated:
            count = len(generated)
            self._ctx.data_changed.emit()
            self._ctx.notification.emit(
                f"Added {count} recurring expense{'' if count == 1 else 's'}",
                generated_message(generated, self._ctx),
                INFO,
            )
        return len(generated)

    def focus_new_expense(self) -> None:
        self.tabs.setCurrentWidget(self.expenses_tab)
        self.expenses_tab.form.focus_amount()

    def _undo_delete(self) -> None:
        self.tabs.setCurrentWidget(self.expenses_tab)
        self.expenses_tab.undo_delete()

    def _restore_state(self) -> None:
        geometry = self._ctx.settings.get(GEOMETRY_KEY)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        last_tab = self._ctx.settings.get(TAB_KEY, "")
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == last_tab:
                self.tabs.setCurrentIndex(index)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.toast.set_bottom_offset(self.statusBar().height())

    def closeEvent(self, event: QCloseEvent) -> None:
        geometry = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        self._ctx.settings.set(GEOMETRY_KEY, geometry)
        self._ctx.settings.set(TAB_KEY, self.tabs.tabText(self.tabs.currentIndex()))
        super().closeEvent(event)

"""Main window: tabs, status bar, shortcuts and remembered window state."""

from __future__ import annotations

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget

from expense_tracker.ui.context import AppContext
from expense_tracker.ui.dashboard_tab import DashboardTab
from expense_tracker.ui.expenses_tab import ExpensesTab
from expense_tracker.ui.settings_tab import SettingsTab

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
        self.settings_tab = SettingsTab(ctx)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.expenses_tab, "Expenses")
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)

        self.statusBar().setSizeGripEnabled(False)
        ctx.status_message.connect(
            lambda text: self.statusBar().showMessage(text, STATUS_TIMEOUT_MS)
        )

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.focus_new_expense)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo_delete)

        self._restore_state()
        if self.tabs.currentWidget() is self.expenses_tab:
            self.expenses_tab.form.focus_amount()

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
        tab = self._ctx.settings.get(TAB_KEY, "0")
        if tab.isdigit() and int(tab) < self.tabs.count():
            self.tabs.setCurrentIndex(int(tab))

    def closeEvent(self, event: QCloseEvent) -> None:
        geometry = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        self._ctx.settings.set(GEOMETRY_KEY, geometry)
        self._ctx.settings.set(TAB_KEY, str(self.tabs.currentIndex()))
        super().closeEvent(event)

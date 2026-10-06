"""Application start-up: logging, error handling and the main window."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from expense_tracker import APP_NAME
from expense_tracker.db.connection import open_database
from expense_tracker.ui.context import AppContext
from expense_tracker.ui.main_window import MainWindow
from expense_tracker.ui.style import apply_style
from expense_tracker.utils import paths

log = logging.getLogger(APP_NAME)


def _configure_logging() -> None:
    handler = RotatingFileHandler(
        paths.log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _show_error(summary: str) -> None:
    QMessageBox.critical(
        None,
        "Expense Tracker",
        f"{summary}\n\nThe details were saved to:\n{paths.log_path()}",
    )


def _install_exception_hook() -> None:
    """Log unexpected errors and tell the user, instead of closing silently."""
    showing = False

    def hook(exc_type, exc, traceback) -> None:
        nonlocal showing
        log.error("Unexpected error", exc_info=(exc_type, exc, traceback))
        if showing:
            return
        showing = True
        try:
            _show_error("Sorry, something went wrong. Your saved expenses are safe.")
        finally:
            showing = False

    sys.excepthook = hook


def _set_taskbar_identity() -> None:
    """Make Windows show the app's own icon in the taskbar when run from source."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    except (AttributeError, OSError):
        pass


def run() -> int:
    _configure_logging()
    _set_taskbar_identity()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("Expense Tracker")
    apply_style(app)
    icon = paths.asset_path("icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    _install_exception_hook()

    try:
        conn = open_database(paths.db_path())
    except Exception:
        log.exception("Could not open the database at %s", paths.db_path())
        _show_error("Expense Tracker couldn't open its database.")
        return 1

    log.info("Started; database at %s", paths.db_path())
    window = MainWindow(AppContext(conn))
    window.show()
    window.generate_recurring()
    exit_code = app.exec()
    conn.close()
    return exit_code

import sys

from expense_tracker import app
from expense_tracker.utils import paths


def test_data_lives_under_appdata_expense_tracker(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.DATA_DIR_ENV)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.data_dir() == tmp_path / "ExpenseTracker"
    assert paths.db_path() == tmp_path / "ExpenseTracker" / "expenses.db"
    assert paths.log_path() == tmp_path / "ExpenseTracker" / "logs" / "app.log"
    assert (tmp_path / "ExpenseTracker" / "logs").is_dir()


def test_bundled_icon_exists():
    assert paths.asset_path("icon.ico").is_file()


def test_unexpected_errors_are_logged_and_reported(monkeypatch, caplog):
    shown = []
    monkeypatch.setattr(app, "_show_error", shown.append)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    app._install_exception_hook()

    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    assert len(shown) == 1
    assert "Unexpected error" in caplog.text and "boom" in caplog.text

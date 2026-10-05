"""Locations of the app's data, log and bundled asset files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from expense_tracker import APP_NAME

# Set this to point the app at a different data folder (used for development
# and manual testing so the real database is left alone).
DATA_DIR_ENV = "EXPENSE_TRACKER_DATA_DIR"


def data_dir() -> Path:
    """Return the data folder (%APPDATA%\\ExpenseTracker), creating it if needed."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "expenses.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return log_dir() / "app.log"


def asset_path(name: str) -> Path:
    """Return the path of a bundled asset, both from source and inside the exe."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / name
    return Path(__file__).resolve().parents[3] / "assets" / name

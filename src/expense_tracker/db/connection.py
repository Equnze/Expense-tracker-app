"""SQLite connection handling."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from expense_tracker.db.schema import migrate


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection in autocommit mode; use :func:`transaction` to group writes."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_database(path: Path | str) -> sqlite3.Connection:
    """Open the database, creating or upgrading its tables as needed."""
    conn = connect(path)
    migrate(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run a block atomically. Nested use joins the outer transaction."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")

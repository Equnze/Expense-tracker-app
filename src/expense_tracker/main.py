"""Entry point: ``python src/expense_tracker/main.py`` or the packaged exe."""

import sys
from pathlib import Path

if not __package__:
    # Run as a script, so make the ``expense_tracker`` package importable.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from expense_tracker.app import run

if __name__ == "__main__":
    sys.exit(run())

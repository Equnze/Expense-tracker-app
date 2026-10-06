# Expense Tracker

A simple, offline personal expense tracker for Windows. It runs as a single
`ExpenseTracker.exe` — no internet connection, no account and no installer.
Everything you enter stays on your computer.

**Status:** Phases 1 and 2 of [the spec](expense-tracker-spec.md) are complete.
Income tracking, tags, backup/restore, themes and the PIN lock come in Phase 3.

## Using the app

| To do this | Do this |
|---|---|
| Add an expense | Type the amount, press `Tab` through the fields, press `Enter` |
| Jump to the Amount field | `Ctrl+N` |
| Edit an expense | Double-click it, or select it and press `Enter` |
| Delete expenses | Select one or more rows, then press `Delete` (or right-click) |
| Undo the last delete | `Ctrl+Z`, or the **Undo delete** button |
| Sort the list | Click a column header |
| Manage categories, change currency symbol | **Settings** tab |

Changes are saved the moment you make them; there is no Save button.
Undo is available until you close the app.

### Dashboard

Pick a month with the arrows to see its total, the change from the month
before, the daily average, the top categories, and three charts: spending by
category, the 12 months up to that month, and the running total through the
month against the previous one. Hover over a chart for exact figures.

### Budgets

On the **Budgets** tab, **Set budget…** sets a monthly limit for one category
or for all spending. Each budget shows a bar for the current month: green under
75% of the limit, amber from 75% to 100%, red when over. When an expense you
add takes a budget past 90%, or over its limit, a notice appears in the corner
of the window; it does not interrupt what you are doing.

### Recurring expenses

On the **Recurring** tab, add rent, subscriptions and other regular bills as
monthly, weekly or yearly items. Each time the app starts it adds any that have
come due, including ones missed while it was closed, and tells you what it
added. They are ordinary expenses once added, so you can edit or delete them.

- A monthly item set to the 29th, 30th or 31st falls on the last day of
  shorter months.
- **Pause** stops an item; **Resume** carries on from today without filling in
  the paused period.
- Deleting an item keeps the expenses it already added.

### Export

**Export…** on the Expenses tab saves the expenses currently shown in the list
(after filters and search) as an Excel workbook or a CSV file. The workbook has
a second sheet with totals per category.

### Import from a bank statement

**Import CSV…** on the Expenses tab opens a four-step wizard:

1. Choose the CSV file and check the preview.
2. Say which columns hold the date, amount and description. Check that the
   preview shows your dates correctly; if the day and month are swapped, change
   the date format.
3. Choose a category for the imported expenses and change it per row where
   needed. Rows that match an expense you already have (same date, amount and
   description) are flagged as possible duplicates and left unticked.
4. See how many rows were imported, skipped or could not be read.

Importing the same file twice adds nothing the second time.

## Where your data is stored

| What | Where |
|---|---|
| Database | `%APPDATA%\ExpenseTracker\expenses.db` |
| Error log | `%APPDATA%\ExpenseTracker\logs\app.log` |

Paste `%APPDATA%\ExpenseTracker` into the File Explorer address bar to open the
folder, or use **Settings → Open data folder**. To back up your data, copy
`expenses.db` somewhere safe while the app is closed. The exe itself holds no
data, so you can move, replace or delete it freely.

## Building the exe

Requires Windows 10/11 with [Python 3.11 or newer](https://www.python.org/downloads/).

Double-click `build.bat`, or run it from a terminal:

```
build.bat
```

It creates a virtual environment in `.venv`, installs the dependencies and
PyInstaller, and writes `dist\ExpenseTracker.exe`. The first build takes a few
minutes. The exe runs on any Windows 10/11 machine, with or without Python.

To put a shortcut on your desktop afterwards:

```
powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
```

### Windows SmartScreen warning

The exe is not code-signed, so the first time you run it Windows may show
"Windows protected your PC". Click **More info**, then **Run anyway**. This
only happens once per copy of the exe.

## Running from source

```
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python src\expense_tracker\main.py
```

To try things out without touching your real data, point the app at another
folder first:

```
set EXPENSE_TRACKER_DATA_DIR=C:\Temp\expense-tracker-test
.venv\Scripts\python src\expense_tracker\main.py
```

## Running the tests

```
.venv\Scripts\python -m pytest
```

The tests use temporary databases and never open the real one.

## Project layout

```
src/expense_tracker/
    main.py       entry point
    app.py        start-up, logging, error handling
    db/           connection, schema and migrations, repositories (all SQL)
    models/       dataclasses
    services/     business logic, free of any UI code
    ui/           main window, tabs, dialogs, widgets
    utils/        money, dates, paths
assets/           app icon
scripts/          icon generator, desktop shortcut helper
tests/
```

Money is stored and calculated as whole cents (`$12.99` is `1299`) and only
converted for display. Schema changes are made by appending a migration in
`db/schema.py`, which upgrades existing databases without losing data.

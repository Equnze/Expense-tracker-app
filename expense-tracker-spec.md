# Personal Expense Tracker — Project Spec

## 1. Overview

A simple, offline personal expense tracker for Windows. It runs as a standalone `.exe` that I can double-click to launch. No internet connection, no accounts, no installer required. All data stays on my machine.

**Primary goal:** adding an expense should take a few seconds, and I should be able to see where my money goes each month at a glance.

## 2. Tech Stack (required)

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| GUI | PySide6 (Qt for Python) |
| Charts | PySide6 `QtCharts` (avoid matplotlib to keep the exe smaller) |
| Database | SQLite via Python's built-in `sqlite3` |
| Excel export | `openpyxl` |
| Packaging | PyInstaller, single-file windowed `.exe` |
| Tests | `pytest` |

Keep third-party dependencies to the list above unless there's a strong reason.

## 3. Data Storage

- Database file location: `%APPDATA%\ExpenseTracker\expenses.db` (create the folder on first run). Do **not** store data next to the exe.
- Create tables automatically on first launch, seeded with default categories.
- Include a simple schema version table so future changes can migrate the database without losing data.
- **Store all money as integer cents** (e.g., `$12.99` → `1299`). Convert only for display.
- Currency symbol is a setting (default `$`).

### Schema

**categories**
- `id` INTEGER PK
- `name` TEXT UNIQUE NOT NULL
- `color` TEXT (hex, used in charts)
- `is_archived` INTEGER DEFAULT 0

Default categories: Food & Groceries, Dining Out, Rent/Mortgage, Utilities, Transport, Health, Shopping, Entertainment, Subscriptions, Travel, Education, Gifts, Other.

**expenses**
- `id` INTEGER PK
- `amount_cents` INTEGER NOT NULL (> 0)
- `date` TEXT NOT NULL (ISO `YYYY-MM-DD`)
- `category_id` INTEGER NOT NULL → categories.id
- `description` TEXT
- `payment_method` TEXT (Cash, Debit Card, Credit Card, Bank Transfer, Other)
- `tags` TEXT (comma-separated, optional)
- `recurring_id` INTEGER NULL → recurring_expenses.id
- `created_at`, `updated_at` TEXT

**income** (Phase 3)
- `id`, `amount_cents`, `date`, `source`, `description`, `created_at`, `updated_at`

**budgets**
- `id` INTEGER PK
- `category_id` INTEGER NULL (NULL = overall monthly budget)
- `monthly_limit_cents` INTEGER NOT NULL

**recurring_expenses**
- `id`, `amount_cents`, `category_id`, `description`, `payment_method`
- `frequency` TEXT (monthly, weekly, yearly)
- `day_of_month` INTEGER (for monthly)
- `start_date`, `end_date` (nullable)
- `last_generated_date`
- `is_active` INTEGER

**settings**
- key/value table (currency symbol, theme, last backup date, etc.)

## 4. Features

### Phase 1 — Core (MVP)

**4.1 Add expense**
- A quick-add form always visible at the top of the main window: Amount, Date, Category, Description, Payment method, and an Add button.
- Date defaults to today; category and payment method default to the last ones used.
- Keyboard-friendly: Tab moves between fields, Enter saves, focus returns to Amount after saving so I can enter several in a row.
- Global shortcut `Ctrl+N` focuses the Amount field.
- Validation: amount must be a positive number with at most 2 decimals; show inline errors, never crash.

**4.2 Edit and delete expenses**
- Double-click a row (or press Enter on it) to open an edit dialog.
- Delete via button, right-click menu, or `Delete` key, with a confirmation prompt.
- Support selecting multiple rows and deleting them together.
- `Ctrl+Z` undoes the most recent delete.

**4.3 Expense list**
- Table columns: Date, Category, Description, Payment Method, Amount.
- Sort by clicking any column header. Default: newest first.
- Amounts right-aligned and formatted with currency symbol and thousands separators.
- Footer shows the count and total of the currently filtered rows.

**4.4 Filtering and search**
- Date range presets: This Month (default), Last Month, Last 3 Months, This Year, All Time, Custom range.
- Category filter (multi-select).
- Payment method filter.
- Text search over description and tags, filtering as I type.
- "Clear filters" button.

**4.5 Category management**
- Settings dialog to add, rename, recolor, and archive categories.
- Archived categories are hidden from the add form but keep their historical expenses.
- Prevent deleting a category that has expenses; offer to archive or reassign instead.

**4.6 Dashboard / summary**
- A Dashboard tab showing, for a selected month (prev/next arrows):
  - Total spent this month
  - Comparison to last month (amount and % change, colored up/down)
  - Average daily spending
  - Top 3 categories
  - Category breakdown table: category, amount, % of total

**4.7 Persistence**
- Every change is saved immediately to SQLite. No "Save" button.
- App opens to the same tab and window size as last time.

### Phase 2 — Insights and data

**4.8 Charts** (on the Dashboard)
- Donut/pie chart: spending by category for the selected month (uses category colors).
- Bar chart: total spending per month for the last 12 months.
- Line chart: cumulative daily spending this month vs. last month.

**4.9 Budgets**
- Set a monthly limit per category and an optional overall monthly budget.
- Budgets tab shows a progress bar for each: spent / limit, remaining amount.
- Colors: green under 75%, amber 75–100%, red over 100%.
- After adding an expense that pushes a category past 90% or over its limit, show a non-blocking notification.

**4.10 Export**
- Export the currently filtered expenses to CSV or Excel (`.xlsx`).
- Excel export includes a second sheet with the category summary.

**4.11 Import from CSV**
- Import a bank statement CSV through a wizard:
  1. Pick file, show a preview of the first rows.
  2. Map columns to Date, Amount, Description (choose date format; handle negative amounts as expenses).
  3. Assign a default category, with the ability to change categories per row before importing.
  4. Flag likely duplicates (same date, amount, and description as an existing expense) and skip them by default.
- Show a summary of how many rows were imported, skipped, or failed.

**4.12 Recurring expenses**
- Manage recurring items (rent, subscriptions, etc.) in their own tab.
- On app launch, automatically generate any recurring expenses that are due since the last launch (including missed months), then show a short notice of what was added.
- Generated expenses are linked to their recurring rule and editable like any other expense.

### Phase 3 — Nice-to-haves

**4.13 Income tracking**
- Add/edit/delete income entries.
- Dashboard shows income, expenses, and net savings for the month, plus savings rate %.

**4.14 Tags**
- Free-form tags on expenses (e.g., "vacation", "reimbursable"), with autocomplete from existing tags.
- Filter by tag.

**4.15 Backup and restore**
- "Backup now" saves a timestamped copy of the database to a folder I choose.
- "Restore" replaces the current database from a backup file, after confirmation and after automatically backing up the current one first.
- Optional automatic backup on exit, keeping the last 10.

**4.16 Appearance**
- Light and dark theme, switchable in Settings, with "follow Windows setting" as the default.

**4.17 Optional PIN lock**
- Optional 4–6 digit PIN required at startup. Store only a salted hash (use `hashlib.pbkdf2_hmac`), never the PIN itself.
- This is a privacy convenience, not encryption; note that in the Settings UI.

## 5. UI Layout

Main window with tabs:

1. **Expenses** — quick-add form on top, filter bar below it, expense table filling the rest, totals footer.
2. **Dashboard** — month selector, summary cards, charts.
3. **Budgets** — progress bars per category, edit limits.
4. **Recurring** — list of recurring rules with add/edit/pause.
5. **Settings** — categories, currency, theme, backup/restore, PIN, import/export.

General UI rules:
- Clean, modern look; consistent spacing; readable default font size.
- Minimum window size 1000×650, resizable, remembers size/position.
- Status bar for brief confirmations ("Expense added", "Exported 42 rows").
- No blocking error dialogs for validation; use inline messages. Unexpected errors are logged to `%APPDATA%\ExpenseTracker\logs\app.log` and shown in a friendly dialog.

## 6. Project Structure

```
expense-tracker/
├── src/
│   └── expense_tracker/
│       ├── main.py            # entry point
│       ├── db/                # connection, schema, migrations, repositories
│       ├── models/            # dataclasses for Expense, Category, Budget, etc.
│       ├── services/          # business logic: budgets, recurring, import/export, backup
│       ├── ui/                # main window, tabs, dialogs, widgets
│       └── utils/             # money formatting, date helpers, paths
├── assets/
│   └── icon.ico
├── tests/
├── requirements.txt
├── build.bat
└── README.md
```

Keep business logic out of UI classes so it can be unit tested.

## 7. Packaging as a Windows .exe

- Provide `build.bat` that:
  1. Creates/uses a virtual environment.
  2. Installs `requirements.txt` and PyInstaller.
  3. Runs PyInstaller with `--onefile --windowed --name ExpenseTracker --icon assets/icon.ico`.
  4. Outputs `dist\ExpenseTracker.exe`.
- The exe must run on a Windows 10/11 machine **without Python installed**.
- No console window should appear.
- Generate a simple app icon (`icon.ico`) if none is provided.
- README explains: how to run from source, how to build the exe, where data is stored, and that Windows SmartScreen may warn on first run because the exe is unsigned ("More info → Run anyway").
- Optional: a script to create a desktop shortcut.

## 8. Testing

- `pytest` unit tests for: money parsing/formatting (cents conversion, rounding edge cases), database repositories, budget calculations, recurring expense generation (including missed months and month-end dates like the 31st), CSV import mapping and duplicate detection, and backup/restore.
- Tests use a temporary database, never the real one.
- After each phase, verify the app launches from source and that the built exe launches.

## 9. Out of Scope

- Cloud sync, multiple users, or online accounts
- Bank API connections
- Mobile version
- Multi-currency conversion
- Installer (MSI) — a single exe is enough

## 10. How to Work

- Build in phases (Phase 1 → 2 → 3). Finish and test each phase before starting the next.
- At the end of Phase 1, produce a working exe so I can start using it immediately.
- Ask me before adding new dependencies or changing the tech stack.
- Commit to git after each completed feature with a clear message.

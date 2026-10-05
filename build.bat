@echo off
rem Builds dist\ExpenseTracker.exe - a single file that runs without Python installed.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv || python -m venv .venv || goto :error
)
set "PY=.venv\Scripts\python.exe"

echo Installing dependencies...
"%PY%" -m pip install --quiet --upgrade pip || goto :error
"%PY%" -m pip install --quiet -r requirements.txt pyinstaller || goto :error

if not exist "assets\icon.ico" (
    "%PY%" scripts\make_icon.py || goto :error
)

echo Building the exe (this takes a few minutes)...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ExpenseTracker ^
    --icon assets\icon.ico ^
    --add-data "assets\icon.ico;assets" ^
    --paths src ^
    src\expense_tracker\main.py || goto :error

echo.
echo Done: dist\ExpenseTracker.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1

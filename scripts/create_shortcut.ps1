# Creates an "Expense Tracker" shortcut on your desktop pointing at the built exe.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

$exe = Join-Path $PSScriptRoot "..\dist\ExpenseTracker.exe"
if (-not (Test-Path $exe)) {
    Write-Error "dist\ExpenseTracker.exe not found. Run build.bat first."
    exit 1
}
$exe = (Resolve-Path $exe).Path

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut(
    (Join-Path $desktop "Expense Tracker.lnk"))
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = Split-Path $exe
$shortcut.Description = "Personal Expense Tracker"
$shortcut.Save()

Write-Output "Created shortcut on the desktop."

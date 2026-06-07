@echo off
title LOVE_PET - Sync (pull CURRENT branch)
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - Sync  (pull latest of current branch)
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [X] Git not found. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

REM ---------- Current branch ----------
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BR=%%b"
echo Branch: %BR%
echo.

REM ---------- Stop running pet (if any) ----------
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

REM ---------- Protect runtime save ----------
if exist save.json copy /y save.json save.json.bak >nul

REM ---------- SAFETY: never destroy uncommitted edits ----------
git update-index -q --refresh >nul 2>&1
git diff-index --quiet HEAD --
if errorlevel 1 (
  echo.
  echo [!] You have uncommitted changes on "%BR%".
  echo     Save them first:  publish.bat
  echo     Sync CANCELLED so nothing is lost.
  echo.
  if exist save.json.bak del save.json.bak >nul
  pause
  exit /b 1
)

REM ---------- Pull latest of current branch (fast-forward only) ----------
echo [..] Pulling latest "%BR%" from GitHub...
git fetch origin
git merge --ff-only origin/%BR%
if errorlevel 1 (
  echo.
  echo [!] Cannot fast-forward "%BR%" (diverged, or branch not on GitHub yet).
  echo     Use publish.bat to upload your commits. Nothing was changed.
  if exist save.json.bak copy /y save.json.bak save.json >nul
  if exist save.json.bak del save.json.bak >nul
  pause
  exit /b 1
)

REM ---------- Restore runtime save ----------
if exist save.json.bak (
  copy /y save.json.bak save.json >nul
  del save.json.bak >nul
)

echo.
echo [OK] "%BR%" is now up to date:
git log -1 --oneline
echo.
echo (Run run_debug.bat to test, or start_pet.vbs to launch.)
pause

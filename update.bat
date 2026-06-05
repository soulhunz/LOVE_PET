@echo off
title LOVE_PET - Update
cd /d "%~dp0"

echo ============================================
echo      LOVE_PET - Update (safe)
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [X] Git not found. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

REM ---------- Stop running pet ----------
echo [..] Stopping running pet...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

REM ---------- Protect runtime save ----------
if exist save.json copy /y save.json save.json.bak >nul

REM ---------- SAFETY: never destroy unpublished local code edits ----------
git update-index -q --refresh >nul 2>&1
git diff-index --quiet HEAD --
if errorlevel 1 (
  echo.
  echo [!] You have local code changes that are NOT on GitHub yet.
  echo     Update was CANCELLED so your work is NOT lost.
  echo     To upload your changes first, run:  publish.bat
  echo.
  if exist save.json.bak del save.json.bak >nul
  pause
  exit /b 1
)

REM ---------- Pull latest (fast-forward only = never discards commits) ----------
echo [..] Pulling latest code from GitHub...
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BR=%%b"
git fetch origin
git merge --ff-only origin/%BR%
if errorlevel 1 (
  echo.
  echo [!] Cannot fast-forward (local and GitHub have diverged).
  echo     Nothing was changed. Run publish.bat to upload local commits.
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

echo [OK] Updated. Latest version:
git log -1 --oneline
echo.
echo [..] Relaunching pet...
wscript "%~dp0start_pet.vbs"
echo.
echo [DONE] Update complete!
timeout /t 3 >nul

@echo off
title LOVE_PET - Update (get server / main)
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - Update  (pull server version = main)
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

REM ---------- SAFETY: never destroy uncommitted code edits ----------
git update-index -q --refresh >nul 2>&1
git diff-index --quiet HEAD --
if errorlevel 1 (
  echo.
  echo [!] You have uncommitted changes on this branch.
  echo     Update CANCELLED so nothing is lost.
  echo     Save your work first:  publish.bat   ^(or release.bat^)
  echo.
  if exist save.json.bak del save.json.bak >nul
  pause
  exit /b 1
)

REM ---------- Switch to server branch (main) and pull latest ----------
echo [..] Switching to server version (main)...
git fetch origin
git checkout main
if errorlevel 1 (
  echo [X] Could not switch to main branch.
  if exist save.json.bak copy /y save.json.bak save.json >nul & del save.json.bak >nul
  pause
  exit /b 1
)
git merge --ff-only origin/main
if errorlevel 1 (
  echo.
  echo [!] Cannot fast-forward main (it has diverged from GitHub).
  echo     Nothing was changed. Use release.bat / publish.bat to sync.
  if exist save.json.bak copy /y save.json.bak save.json >nul & del save.json.bak >nul
  pause
  exit /b 1
)

REM ---------- Restore runtime save ----------
if exist save.json.bak (
  copy /y save.json.bak save.json >nul
  del save.json.bak >nul
)

echo [OK] Now running SERVER version (main). Latest:
git log -1 --oneline
echo.
echo [..] Relaunching pet...
wscript "%~dp0start_pet.vbs"
echo.
echo [DONE] Update complete!
timeout /t 3 >nul

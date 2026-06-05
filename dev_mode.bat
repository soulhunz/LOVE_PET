@echo off
title LOVE_PET - Dev mode (switch to dev branch)
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - Dev mode  (switch to dev branch)
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [X] Git not found. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

REM ---------- Don't switch with unsaved work (would carry it over) ----------
git update-index -q --refresh >nul 2>&1
git diff-index --quiet HEAD --
if errorlevel 1 (
  echo.
  echo [!] You have uncommitted changes on the current branch.
  echo     Save them first:  publish.bat
  echo     Then run dev_mode.bat again.
  echo.
  pause
  exit /b 1
)

git fetch origin >nul 2>&1

REM ---------- Create dev from main if it doesn't exist yet ----------
git show-ref --verify --quiet refs/heads/dev
if errorlevel 1 (
  echo [..] Creating dev branch from main...
  git checkout main >nul 2>&1
  git checkout -b dev
) else (
  git checkout dev
)
if errorlevel 1 (
  echo [X] Could not switch to dev branch.
  pause
  exit /b 1
)

echo.
echo [OK] You are now on the DEV branch.
echo     Edit / test freely. When stable, run:  release.bat
echo     (release.bat moves your dev code into the server version = main)
echo.
pause

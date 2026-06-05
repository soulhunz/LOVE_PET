@echo off
title LOVE_PET - Publish to GitHub
cd /d "%~dp0"

echo ============================================
echo      LOVE_PET - Publish (upload to GitHub)
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [X] Git not found. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

echo [..] Staging local changes...
git add -A

git diff --cached --quiet
if not errorlevel 1 (
  echo [i] No new local changes to commit.
) else (
  git commit -m "Update via publish.bat"
  echo [OK] Local changes committed.
)

echo [..] Pushing to GitHub...
git push origin HEAD
if errorlevel 1 (
  echo.
  echo [X] Push failed - check your internet / GitHub login.
  echo     (First time may ask you to sign in to GitHub.)
  pause
  exit /b 1
)

echo.
echo [DONE] Published! Other PCs can now press Update to get this version.
pause

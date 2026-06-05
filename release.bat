@echo off
title LOVE_PET - Release (dev -> server/main)
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - Release  (promote dev -> server/main)
echo ============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [X] Git not found. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

REM ---------- Find current branch ----------
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "CUR=%%b"
if /i not "%CUR%"=="dev" (
  echo [!] You are on branch "%CUR%", not "dev".
  echo     release.bat is meant to promote the dev branch.
  echo     Run dev_mode.bat first, or continue anyway?
  choice /m "Continue releasing branch %CUR% into main"
  if errorlevel 2 ( echo Cancelled. & pause & exit /b 1 )
)

REM ---------- Commit any pending dev work ----------
echo [..] Saving current changes...
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Dev work before release"
  echo [OK] Committed.
) else (
  echo [i] Nothing new to commit.
)

REM ---------- Push dev as backup ----------
echo [..] Pushing dev to GitHub (backup)...
git push origin %CUR%
if errorlevel 1 (
  echo [X] Push failed - check internet / GitHub login. Release stopped.
  pause
  exit /b 1
)

REM ---------- Merge dev into main ----------
echo [..] Merging into server version (main)...
git checkout main
if errorlevel 1 ( echo [X] cannot switch to main & pause & exit /b 1 )
git merge --no-edit %CUR%
if errorlevel 1 (
  echo.
  echo [X] Merge conflict. Returning to %CUR%.
  echo     Resolve the conflict, then run release.bat again.
  git merge --abort
  git checkout %CUR%
  pause
  exit /b 1
)

REM ---------- Push the new server version ----------
echo [..] Publishing server version (main) to GitHub...
git push origin main
if errorlevel 1 (
  echo [X] Push of main failed - check internet / GitHub login.
  pause
  exit /b 1
)

REM ---------- Back to dev for more work ----------
git checkout %CUR% >nul 2>&1

echo.
echo [DONE] Released! Server version (main) is now updated on GitHub.
echo        Any PC can press Update to get it. You are back on "%CUR%".
pause

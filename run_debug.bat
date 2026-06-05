@echo off
title LOVE_PET - Debug mode
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - DEBUG MODE
echo   (If the pet does not show, read errors below)
echo ============================================
echo.
echo [i] Python used:
where python
echo.

REM Use python (with console) instead of pythonw to see all errors
python main.py

echo.
echo ============================================
echo  Program finished (exit code = %errorlevel%)
echo  If there is a red error above, copy it to me.
echo ============================================
pause

@echo off
title LOVE_PET - Disable auto-start
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - Disable auto-start
echo ============================================
echo.

echo [..] Removing from startup...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\LOVE_PET.lnk" 2>nul

echo [..] Stopping running pet...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

echo.
echo [OK] Auto-start disabled.
echo     (Program files and save data are kept - launch from the desktop icon)
echo.
pause

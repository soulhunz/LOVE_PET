@echo off
title LOVE_PET - Restart
cd /d "%~dp0"

echo [..] Stopping running pet...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

echo [..] Starting pet with the current local code...
wscript "%~dp0start_pet.vbs"

echo [OK] Restarted.
timeout /t 2 >nul

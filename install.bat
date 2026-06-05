@echo off
title LOVE_PET - Installer
cd /d "%~dp0"

echo ============================================
echo      LOVE_PET - Installer
echo ============================================
echo.

REM ---------- 1) Check Python ----------
where pythonw >nul 2>&1
if errorlevel 1 (
  echo [X] Python not found on this PC.
  echo     Please install Python 3 from https://www.python.org/downloads/
  echo     ** Tick "Add Python to PATH" during install **
  echo.
  pause
  exit /b 1
)
echo [OK] Python found
python --version
echo.

set "VBS=%~dp0start_pet.vbs"
set "PROJ=%~dp0"

REM ---------- 2) Auto-start on boot ----------
echo [..] Setting up auto-start on boot...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut('%STARTUP%\LOVE_PET.lnk'); $l.TargetPath='%VBS%'; $l.WorkingDirectory='%PROJ%'; $l.Save()"
echo [OK] Added to startup

REM ---------- 3) Desktop shortcut ----------
echo [..] Creating desktop shortcut...
powershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; $d=$s.SpecialFolders('Desktop'); $l=$s.CreateShortcut($d+'\LOVE_PET.lnk'); $l.TargetPath='%VBS%'; $l.WorkingDirectory='%PROJ%'; $l.Save()"
echo [OK] Desktop shortcut created
echo.

REM ---------- 4) Launch now ----------
echo [..] Launching LOVE_PET...
wscript "%VBS%"
echo.
echo ============================================
echo  [DONE] Installation complete!
echo   - The pet starts automatically on every boot
echo   - To update code   : double-click  update.bat
echo   - To disable auto  : double-click  uninstall.bat
echo   - If nothing shows : double-click  run_debug.bat
echo ============================================
echo.
pause

@echo off
REM ============================================
REM   LOVE_PET - Data Manager (skills / monsters / characters)
REM   เครื่องมือจัดการข้อมูลหลังบ้าน แยกจากตัวเกม
REM ============================================
cd /d "%~dp0"

REM 1) pythonw (no console) if available
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "manager.py"
    exit /b
)

REM 2) py launcher (windowed)
where py >nul 2>&1
if %errorlevel%==0 (
    start "" pyw "manager.py"
    exit /b
)

REM 3) fallback: plain python (shows console)
where python >nul 2>&1
if %errorlevel%==0 (
    python "manager.py"
    exit /b
)

echo [X] Python not found - install from https://www.python.org/downloads/
pause

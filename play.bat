@echo off
REM ============================================
REM   LOVE_PET - run the game (no console window)
REM   ดับเบิลคลิกเพื่อเล่นได้เลย
REM ============================================
cd /d "%~dp0"

REM 0) ใช้ Python ที่ติดตั้งจริง (เลี่ยง stub ของ Microsoft Store ใน WindowsApps)
if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Python\bin\pythonw.exe" "main.py"
    exit /b
)

REM 1) pythonw ใน PATH = รันแบบไม่มีหน้าต่างดำ (เหมาะกับเดสก์ท็อปเพ็ต)
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "main.py"
    exit /b
)

REM 2) py launcher (windowed)
where py >nul 2>&1
if %errorlevel%==0 (
    start "" pyw "main.py"
    exit /b
)

REM 3) สำรอง: python ธรรมดา (จะมีหน้าต่าง console)
where python >nul 2>&1
if %errorlevel%==0 (
    start "" python "main.py"
    exit /b
)

echo [X] ไม่พบ Python — ติดตั้งจาก https://www.python.org/downloads/
echo     (ตอนติดตั้งติ๊ก "Add Python to PATH" ด้วย)
pause

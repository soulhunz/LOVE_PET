@echo off
title LOVE_PET - Build .exe (for sharing, no Python needed)
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - สร้างไฟล์ .exe เพื่อแจกให้คนอื่น
echo   (คนรับไม่ต้องลง Python — ดับเบิลคลิกเล่นได้เลย)
echo ============================================
echo.

REM ---------- หา Python ที่ติดตั้งจริง ----------
set "PY="
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not defined PY ( where py   >nul 2>&1 && set "PY=py" )
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [X] ไม่พบ Python — ติดตั้งจาก https://www.python.org/downloads/
  pause & exit /b 1
)
echo [i] ใช้ Python: %PY%
"%PY%" --version
echo.

REM ---------- ติดตั้ง PyInstaller ถ้ายังไม่มี ----------
"%PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo [..] กำลังติดตั้ง PyInstaller...
  "%PY%" -m pip install --upgrade pyinstaller
  if errorlevel 1 ( echo [X] ติดตั้ง PyInstaller ไม่สำเร็จ & pause & exit /b 1 )
)

REM ---------- ล้างของเก่า ----------
echo [..] ล้าง build/dist เก่า...
if exist "dist\LOVE_PET" rmdir /s /q "dist\LOVE_PET"
if exist "build\LOVE_PET" rmdir /s /q "build\LOVE_PET"

REM ---------- แพ็กเป็น .exe (โฟลเดอร์เดียว, ไม่มีหน้าต่าง console) ----------
echo [..] กำลังสร้าง .exe (อาจใช้เวลาสักครู่)...
set "ICON="
if exist "icon.ico" set "ICON=--icon icon.ico"
"%PY%" -m PyInstaller --noconfirm --onedir --windowed --name LOVE_PET %ICON% main.py
if errorlevel 1 ( echo [X] สร้าง .exe ไม่สำเร็จ ดู error ด้านบน & pause & exit /b 1 )

REM ---------- คัดลอกรูป/ตัวละครไปไว้ข้าง .exe (ให้แก้ไข/เพิ่มได้ + เซฟลงตรงนี้) ----------
echo [..] คัดลอก assets / characters ไปไว้ข้าง .exe...
xcopy /e /i /y "assets"     "dist\LOVE_PET\assets"     >nul
xcopy /e /i /y "characters" "dist\LOVE_PET\characters" >nul
REM รวมตัวละคร/มอนสเตอร์ที่เคยอัปโหลดไว้ใน %APPDATA% เข้าไปด้วย (ถ้ามี)
if exist "%APPDATA%\MyDesktopPet\characters" xcopy /e /i /y "%APPDATA%\MyDesktopPet\characters" "dist\LOVE_PET\characters" >nul
if exist "%APPDATA%\MyDesktopPet\monsters"   xcopy /e /i /y "%APPDATA%\MyDesktopPet\monsters"   "dist\LOVE_PET\monsters"   >nul
if exist "README_วิธีใช้.txt" copy /y "README_วิธีใช้.txt" "dist\LOVE_PET\" >nul

echo.
echo ============================================
echo  [DONE] เสร็จแล้ว!
echo.
echo  โฟลเดอร์ที่ได้:  dist\LOVE_PET\
echo  ข้างในมี LOVE_PET.exe (ให้เพื่อนดับเบิลคลิกเล่นได้เลย)
echo.
echo  วิธีแจก: ซิปโฟลเดอร์ "dist\LOVE_PET" ทั้งโฟลเดอร์ ส่งให้เพื่อน
echo           เพื่อนแตกซิป แล้วดับเบิลคลิก LOVE_PET.exe
echo ============================================
echo.
pause

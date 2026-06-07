@echo off
title LOVE_PET - Reset save (start over)
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   LOVE_PET - รีเซ็ตเกม (เริ่มใหม่หมด)
echo ============================================
echo.
echo จะลบไฟล์เซฟทั้งหมด แล้วเริ่มนับ 1 ใหม่ (ได้ไข่ฟรี 1 ใบ)
echo *ตัวละครที่อัปโหลดไว้ไม่ถูกลบ*
echo.
choice /c YN /m "ยืนยันรีเซ็ต (Y=ใช่ / N=ยกเลิก)"
if errorlevel 2 (
  echo ยกเลิกแล้ว
  pause
  exit /b
)

echo.
REM 1) ปิดเกมที่เปิดอยู่ (ไม่งั้นมันจะเซฟทับกลับมา)
taskkill /im pythonw.exe /f >nul 2>&1
taskkill /im python.exe /f >nul 2>&1

REM 2) ลบเซฟใน %APPDATA% (ที่เก็บจริง)
del /q "%APPDATA%\MyDesktopPet\save.json" >nul 2>&1
del /q "%APPDATA%\MyDesktopPet\save.json.tmp" >nul 2>&1

REM 3) ลบเซฟเก่าในโฟลเดอร์โปรแกรม (กันถูกคัดลอกกลับมา)
del /q "%~dp0save.json" >nul 2>&1
del /q "%~dp0save.json.tmp" >nul 2>&1

echo.
echo [OK] รีเซ็ตเรียบร้อย! เปิด play.bat เพื่อเริ่มเกมใหม่
echo.
pause

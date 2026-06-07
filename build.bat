@echo off
REM ===== สร้างไฟล์ .exe สำหรับแจกจ่าย/ขาย (ใช้ PyInstaller) =====
REM รันไฟล์นี้: ดับเบิลคลิก หรือพิมพ์ build.bat ใน cmd
REM ผลลัพธ์: dist\MyDesktopPet.exe  (ไฟล์เดียว ไม่ต้องมี Python)

echo [1/2] ติดตั้ง/อัปเดต PyInstaller ...
py -m pip install --upgrade pyinstaller

echo [2/2] กำลังสร้าง .exe ...
py -m PyInstaller --noconfirm --onefile --windowed --name MyDesktopPet ^
  --add-data "assets;assets" ^
  --add-data "characters;characters" ^
  main.py

echo.
echo เสร็จแล้ว! ไฟล์อยู่ที่  dist\MyDesktopPet.exe
echo (ถ้ามีไฟล์ icon ของตัวเอง เพิ่ม  --icon app.ico  ในคำสั่งด้านบนได้)
pause

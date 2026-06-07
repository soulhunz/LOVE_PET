# -*- coding: utf-8 -*-
"""MyDesktopPet — ตัวละครอนิเมชันบนหน้าจอ

ฟีเจอร์:
  1) เดินไปมาบนหน้าจอเอง
  2) คลิกซ้ายเพื่อโต้ตอบ (ลูบหัว) / ลากเพื่อย้ายตำแหน่ง
  3) คลิกขวาเปิดเมนู: เปลี่ยนตัวละคร / ดูสถานะ  (ตั้งค่าอยู่ที่ปุ่ม ⚙ บนแถบ)

วิธีรัน:  python main.py        (กด Esc เพื่อออก)

ยังไม่ต้องมีไฟล์ภาพก็รันได้ — โปรแกรมจะวาดตัวละครสำรองให้
ถ้าต้องการใช้ภาพของตัวเอง ดูวิธีใน assets/README.txt
"""
import os
import sys
import traceback

# ทำให้ path สัมพัทธ์ (assets/ characters/ save.json) ชี้ไปที่ "โฟลเดอร์โปรแกรม" เสมอ
# ทั้งตอนรันสคริปต์ปกติ และตอนเป็นไฟล์ .exe (PyInstaller) ที่ดับเบิลคลิกจากที่ไหนก็ได้
_APP_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
try:
    os.chdir(_APP_DIR)
except OSError:
    pass


def main():
    from game import World
    World().run()


def _report_crash(exc):
    """เขียน error ลงไฟล์ + เด้งกล่องข้อความ (เห็น error แม้เปิดด้วย pythonw ที่ไม่มี console)"""
    here = os.path.dirname(os.path.abspath(__file__))
    log = os.path.join(here, "error.log")
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"Python: {sys.version}\n")
            f.write(f"Executable: {sys.executable}\n\n")
            f.write(detail)
    except Exception:
        pass
    # พยายามเด้งกล่องข้อความให้ผู้ใช้เห็น (เพราะ pythonw ไม่มีหน้าต่าง console)
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(
            "LOVE_PET เปิดไม่ได้",
            "เกิดข้อผิดพลาดตอนเปิดโปรแกรม:\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"รายละเอียดถูกบันทึกไว้ที่:\n{log}",
        )
        r.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:          # noqa: BLE001 — อยากดักทุกอย่างเพื่อรายงาน
        _report_crash(e)
        raise

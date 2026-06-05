# -*- coding: utf-8 -*-
"""จัดการที่อยู่ไฟล์ให้ทำงานได้ทั้งตอนรันสคริปต์และตอนแพ็กเป็น .exe (PyInstaller)

- resource_path(name): ไฟล์ที่ "มากับโปรแกรม" (อ่านอย่างเดียว) เช่น assets/, ตัวอย่างตัวละคร
- data_path(name):     ไฟล์ "ข้อมูลผู้ใช้" (เขียนได้) เก็บที่ %APPDATA%/MyDesktopPet
  เช่น save.json, settings.json, โฟลเดอร์ตัวละครที่ผู้ใช้เพิ่มเอง
"""
import os
import sys

APP_NAME = "MyDesktopPet"


def _base_dir():
    """โฟลเดอร์ฐานของไฟล์ที่มากับโปรแกรม"""
    if getattr(sys, "frozen", False):          # ถูกแพ็กเป็น .exe ด้วย PyInstaller
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    """ที่อยู่ไฟล์ที่มากับโปรแกรม (อ่านอย่างเดียว)"""
    return os.path.join(_base_dir(), *parts)


def data_dir():
    """โฟลเดอร์ข้อมูลผู้ใช้ (เขียนได้) = %APPDATA%/MyDesktopPet (สร้างให้ถ้ายังไม่มี)"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def data_path(*parts):
    """ที่อยู่ไฟล์ข้อมูลผู้ใช้ (เขียนได้)"""
    return os.path.join(data_dir(), *parts)

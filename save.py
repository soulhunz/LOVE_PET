# -*- coding: utf-8 -*-
"""บันทึก/โหลดความคืบหน้า (เลเวล, XP, สเตตัส) ลงไฟล์ save.json"""
import json
import os

# อิงโฟลเดอร์โปรแกรม (main.py ตั้ง working dir ไว้แล้ว) — เขียนได้ทั้งตอนรันสคริปต์และเป็น .exe
SAVE_PATH = os.path.abspath("save.json")


def load():
    """อ่านข้อมูลจากไฟล์เซฟ; คืน dict ว่างถ้าไม่มี/อ่านไม่ได้"""
    try:
        with open(SAVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(data):
    """เขียนข้อมูลลงไฟล์เซฟ (เงียบ ๆ ถ้าเขียนไม่ได้ เพื่อไม่ให้โปรแกรมล่ม)"""
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

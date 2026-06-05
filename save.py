# -*- coding: utf-8 -*-
"""บันทึก/โหลดความคืบหน้า (เลเวล, XP, สเตตัส) ลงไฟล์ save.json
เก็บที่ %APPDATA%/MyDesktopPet เพื่อให้เขียนได้แม้ติดตั้งใน Program Files (.exe)"""
import json
import os

import paths

SAVE_PATH = paths.data_path("save.json")

# ย้ายเซฟเก่าที่เคยอยู่ข้างโปรแกรมมาที่ใหม่ (ครั้งแรกที่อัปเกรด)
_OLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")
if os.path.exists(_OLD) and not os.path.exists(SAVE_PATH):
    try:
        with open(_OLD, encoding="utf-8") as _f:
            _data = _f.read()
        with open(SAVE_PATH, "w", encoding="utf-8") as _f:
            _f.write(_data)
    except OSError:
        pass


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

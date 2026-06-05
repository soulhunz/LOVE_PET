# -*- coding: utf-8 -*-
"""โหลดไฟล์ภาพของผู้ใช้ และสร้างตัวละครสำรอง (วาดเองด้วยโค้ด) เมื่อไม่มีไฟล์

ทุกอย่างถูกแปลงเป็นรายการ tk.PhotoImage (เฟรมอนิเมชัน) เพื่อให้ระบบเรนเดอร์
ใช้งานได้เหมือนกันหมด ไม่ว่ามาจากไฟล์จริงหรือวาดสำรอง
"""
import glob
import os
import re
import tkinter as tk

import config

_BROWN = "#8a5a2b"
_GREEN = "#3fa34d"


def _flip_h(img):
    """คืนภาพที่กลับด้านซ้าย-ขวา (mirror) ของ PhotoImage ที่ให้มา"""
    w, h = img.width(), img.height()
    out = tk.PhotoImage(width=w, height=h)
    for x in range(w):
        out.tk.call(out, "copy", img, "-from", x, 0, x + 1, h,
                    "-to", w - 1 - x, 0, "-compositingrule", "set")
    return out


class Animation:
    """ลำดับเฟรมภาพ 1 ชุด (สร้างเฟรมกลับด้านให้เมื่อต้องใช้ครั้งแรก)"""

    def __init__(self, frames):
        self.frames = frames          # list[tk.PhotoImage]
        self.w = frames[0].width()
        self.h = frames[0].height()
        self._flipped = None          # list[tk.PhotoImage] หรือ None (ยังไม่สร้าง)

    def frame(self, i, flip=False):
        if flip:
            if self._flipped is None:
                self._flipped = [_flip_h(f) for f in self.frames]
            return self._flipped[i % len(self._flipped)]
        return self.frames[i % len(self.frames)]


# ---------------------------------------------------------------------------
# โหลดจากไฟล์ของผู้ใช้
# ---------------------------------------------------------------------------
def _pixel(img, x, y):
    """อ่านสี (r,g,b) ของพิกเซล รองรับทั้งแบบคืน tuple และ string"""
    v = img.get(x, y)
    if isinstance(v, (tuple, list)):
        return int(v[0]), int(v[1]), int(v[2])
    parts = str(v).split()
    return int(parts[0]), int(parts[1]), int(parts[2])


def _keyout_bg(img):
    """ทำพื้นหลังของ sprite ให้โปร่งใส (แทนด้วย TRANSPARENT_KEY = magenta)
    - ภาพมี alpha (PNG โปร่งใส): เปลี่ยน 'พิกเซลโปร่งใส' เป็นสีคีย์โดยตรง
      (กันบางเครื่องที่ไม่เรนเดอร์ alpha และตัดขอบรุ่งริ่ง)
    - ภาพพื้นทึบสีเดียว: เดาสีพื้นจากมุม แล้ว flood fill จากขอบ (ไม่กินสีกลางตัว)
    ปิดได้ด้วย config.AUTO_REMOVE_BG = False"""
    if not getattr(config, "AUTO_REMOVE_BG", True):
        return img
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return img
    # มี alpha ไหม (เช็คจากมุม) -> เลือกโหมด
    try:
        has_alpha = bool(img.transparency_get(0, 0))
    except Exception:
        has_alpha = False
    if has_alpha:
        return _flatten_alpha(img)
    return _flood_keyout(img, getattr(config, "BG_TOLERANCE", 40))


def _flatten_alpha(img):
    """แบน PNG ที่มี alpha: พิกเซลโปร่งใส -> สีคีย์, พิกเซลทึบ -> คงสีเดิม"""
    w, h = img.width(), img.height()
    key = config.TRANSPARENT_KEY
    tget, pixel = img.transparency_get, _pixel
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            if tget(x, y):
                row.append(key)
            else:
                r, g, b = pixel(img, x, y)
                row.append(f"#{r:02x}{g:02x}{b:02x}")
        rows.append("{" + " ".join(row) + "}")
    out = tk.PhotoImage(width=w, height=h)
    out.put(" ".join(rows))
    return out


def _flood_keyout(img, tol):
    """ภาพพื้นทึบ: เดาสีพื้นจากมุมซ้ายบน ลบเฉพาะบริเวณที่ต่อเนื่องจากขอบภาพ (flood fill)"""
    w, h = img.width(), img.height()
    px = [[_pixel(img, x, y) for x in range(w)] for y in range(h)]
    br, bg_, bb = px[0][0]

    def is_bg(c):
        return abs(c[0] - br) + abs(c[1] - bg_) + abs(c[2] - bb) <= tol

    clear = [[False] * w for _ in range(h)]
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if is_bg(px[y][x]):
                clear[y][x] = True; stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if is_bg(px[y][x]):
                clear[y][x] = True; stack.append((x, y))
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not clear[ny][nx] and is_bg(px[ny][nx]):
                clear[ny][nx] = True; stack.append((nx, ny))

    key = config.TRANSPARENT_KEY
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            if clear[y][x]:
                row.append(key)
            else:
                r, g, b = px[y][x]
                row.append(f"#{r:02x}{g:02x}{b:02x}")
        rows.append("{" + " ".join(row) + "}")
    out = tk.PhotoImage(width=w, height=h)
    out.put(" ".join(rows))
    return out


def _load_gif_frames(path):
    """โหลดทุกเฟรมจากไฟล์ GIF (รองรับ GIF เคลื่อนไหว)"""
    frames = []
    i = 0
    while True:
        try:
            frames.append(tk.PhotoImage(file=path, format=f"gif -index {i}"))
        except tk.TclError:
            break
        i += 1
    return frames


def _frame_count_from_name(path):
    """อ่านจำนวนเฟรมจากชื่อไฟล์ เช่น pet_idle_strip4.png / pet_idle_4frames.png -> 4
    คืน None ถ้าไม่ได้ระบุ"""
    base = os.path.splitext(os.path.basename(path))[0].lower()
    m = (re.search(r"strip(\d+)", base) or
         re.search(r"(\d+)frames?", base) or
         re.search(r"frames?(\d+)", base))
    if m:
        n = int(m.group(1))
        if n >= 1:
            return n
    return None


def _slice_sheet(sheet, count=None):
    """ตัด sprite sheet (เฟรมเรียงแนวนอน) เป็นหลายเฟรม
    count: จำนวนเฟรมที่ระบุไว้ (จากชื่อไฟล์) — เฟรมไม่จำเป็นต้องจัตุรัส
    ถ้า count=None จะเดาเฉพาะกรณีเฟรมจัตุรัส (กว้าง = สูง) เท่านั้น"""
    w, h = sheet.width(), sheet.height()
    if count is None:
        if w <= h or w % h != 0:
            return [sheet]            # ภาพนิ่งเฟรมเดียว
        count = w // h
    if count <= 1:
        return [sheet]
    fw = w // count                   # ความกว้างต่อเฟรม (สูง = เต็มภาพ)
    frames = []
    for i in range(count):
        fr = tk.PhotoImage(width=fw, height=h)
        fr.tk.call(fr, "copy", sheet, "-from", i * fw, 0, i * fw + fw, h)
        frames.append(fr)
    return frames


# โฟลเดอร์ที่ใช้ค้นไฟล์ภาพ เรียงตามลำดับความสำคัญ (ตั้งค่าได้ตอนรันด้วย set_character_dir)
# ค่าเริ่มต้น = เฉพาะ ASSETS_DIR; ถ้าเลือกตัวละคร จะค้นโฟลเดอร์ตัวละครก่อน แล้วค่อย assets
_search_dirs = None


def set_character_dir(path):
    """กำหนดโฟลเดอร์ตัวละครที่กำลังใช้ (ค้นก่อน assets/); path=None = ใช้ assets/ อย่างเดียว"""
    global _search_dirs
    _search_dirs = [path, config.ASSETS_DIR] if path else [config.ASSETS_DIR]


def _dirs():
    return _search_dirs if _search_dirs else [config.ASSETS_DIR]


def character_path(name):
    """เส้นทางโฟลเดอร์ของตัวละครชื่อ name"""
    return os.path.join(config.CHARACTERS_DIR, name)


def list_characters():
    """คืนรายชื่อโฟลเดอร์ตัวละครใน characters/ (เรียงตามชื่อ); ไม่มีก็คืนลิสต์ว่าง"""
    root = config.CHARACTERS_DIR
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def _resolve_path(name):
    """หาไฟล์จริงของ candidate ในโฟลเดอร์ที่ค้น (ตัวละครก่อน แล้ว assets):
    ลองชื่อตรง ๆ ก่อน ถ้าไม่เจอ ลองชื่อที่มี marker เช่น 'pet_idle.png' -> 'pet_idle_strip4.png'"""
    base, ext = os.path.splitext(name)
    for d in _dirs():
        direct = os.path.join(d, name)
        if os.path.exists(direct):
            return direct
        matches = sorted(glob.glob(os.path.join(d, base + "_*" + ext)))
        if matches:
            return matches[0]
    return None


def load_sprite(candidates):
    """ลองโหลดไฟล์ตามรายชื่อใน candidates; คืน Animation หรือ None ถ้าไม่เจอ
    .gif หลายเฟรม = อนิเมชัน
    .png = ภาพนิ่ง, sprite sheet เฟรมจัตุรัส, หรือระบุจำนวนเฟรมในชื่อไฟล์ (_strip4)"""
    for name in candidates:
        path = _resolve_path(name)
        if not path:
            continue
        try:
            if path.lower().endswith(".gif"):
                frames = [_keyout_bg(f) for f in _load_gif_frames(path)]
            else:
                # ลบพื้นหลังที่ 'แผ่นรวม' ก่อน แล้วค่อยตัดเป็นเฟรม (ทำครั้งเดียว เร็วกว่า)
                sheet = _keyout_bg(tk.PhotoImage(file=path))
                frames = _slice_sheet(sheet, _frame_count_from_name(path))
        except tk.TclError:
            continue
        if frames:
            return Animation(frames)
    return None


# ---------------------------------------------------------------------------
# ตัวละครสำรอง (วาดเป็น pixel ด้วยโค้ด)
# ---------------------------------------------------------------------------
def _shade(hex_color, factor):
    """ทำสีอ่อน/เข้ม: factor>1 อ่อนลง, <1 เข้มขึ้น"""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _fill(img, color, x0, y0, x1, y1, size):
    """ระบายสี่เหลี่ยมบน PhotoImage แบบกันค่าเกินขอบภาพ"""
    x0 = max(0, min(size, int(x0)))
    y0 = max(0, min(size, int(y0)))
    x1 = max(0, min(size, int(x1)))
    y1 = max(0, min(size, int(y1)))
    if x1 > x0 and y1 > y0:
        img.put(color, to=(x0, y0, x1, y1))


def _draw_eyes(img, cx, cy, rx, ry, size, state, brows):
    ew = max(3, int(size * 0.13))
    eh = max(3, int(size * 0.16))
    off = int(rx * 0.45)
    ey = int(cy - ry * 0.15)
    for sign in (-1, 1):
        ex = int(cx + sign * off - ew / 2)
        if state == "blink":
            _fill(img, "#222222", ex, ey + eh // 2, ex + ew, ey + eh // 2 + max(2, eh // 5), size)
        else:
            _fill(img, "white", ex, ey, ex + ew, ey + eh, size)
            pw, ph = max(2, ew // 2), max(2, eh // 2)
            px, py = ex + (ew - pw) // 2, ey + (eh - ph) // 2 + 1
            _fill(img, "#222222", px, py, px + pw, py + ph, size)
        if brows:  # คิ้วโกรธ (มอนสเตอร์)
            _fill(img, "#3a0000", ex - 1, ey - max(2, eh // 3),
                  ex + ew + 1, ey - max(2, eh // 3) + max(2, eh // 5), size)


def _make_blob_frames(size, body_hex, *, eyes=True, brows=False, stem=False, count=4):
    key = config.TRANSPARENT_KEY
    edge = _shade(body_hex, 0.72)
    belly = _shade(body_hex, 1.18)
    squashes = [0.0, 0.06, 0.0, -0.05]
    eye_states = ["open", "open", "blink", "open"]
    cx = size / 2.0

    frames = []
    for f in range(count):
        sq = squashes[f % len(squashes)]
        rx = size * 0.42 * (1 + sq)
        ry = size * 0.42 * (1 - sq)
        cy = size * 0.52

        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                nx = (x - cx) / rx
                ny = (y - cy) / ry
                d = nx * nx + ny * ny
                if d <= 1.0:
                    if d > 0.78:
                        row.append(edge)
                    elif ny > 0.15 and abs(nx) < 0.6:
                        row.append(belly)
                    else:
                        row.append(body_hex)
                else:
                    row.append(key)
            rows.append("{" + " ".join(row) + "}")

        img = tk.PhotoImage(width=size, height=size)
        img.put(" ".join(rows))

        if stem:  # ก้าน + ใบ (สำหรับอาหาร)
            sw = max(2, size // 14)
            _fill(img, _BROWN, cx - sw / 2, cy - ry - size * 0.16, cx + sw / 2, cy - ry + 2, size)
            _fill(img, _GREEN, cx + sw / 2, cy - ry - size * 0.13,
                  cx + sw / 2 + size * 0.16, cy - ry - size * 0.03, size)
        if eyes:
            _draw_eyes(img, cx, cy, rx, ry, size, eye_states[f % len(eye_states)], brows)

        frames.append(img)
    return frames


def build_fallback(kind, size, color=None):
    """สร้าง Animation สำรองตามชนิด: 'pet' / 'monster' / 'food'
    color: สีตัว (ใช้กับ pet เพื่อให้แต่ละร่างแปลงร่างต่างสีกัน)"""
    if kind == "monster":
        return Animation(_make_blob_frames(size, "#e0556b", eyes=True, brows=True))
    if kind == "food":
        return Animation(_make_blob_frames(size, "#e23b3b", eyes=False, stem=True, count=2))
    return Animation(_make_blob_frames(size, color or "#5ec8f0", eyes=True))

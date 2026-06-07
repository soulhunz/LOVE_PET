# -*- coding: utf-8 -*-
"""โลกของ Desktop Pet: หน้าต่างโปร่งใสเต็มจอ + ลูปเกม + อินพุต + การต่อสู้"""
import base64
import ctypes
from ctypes import wintypes
import datetime
import os
import random
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox

import config
import assets
import paths
import save
import sound
from entities import Pet, Monster, Food


def _sign(n):
    return (n > 0) - (n < 0)


def _clamp(v, lo=0.0, hi=100.0):
    """บีบค่าให้อยู่ในช่วง [lo, hi] (กันค่าสเตตัสเพี้ยน/ไฟล์เซฟเสีย)"""
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return lo


def _enable_dpi_awareness():
    """บอก Windows ว่าเราคุมพิกัดเอง(per-monitor) เพื่อให้พิกัดข้ามจอที่สเกลต่างกันถูกต้อง
    ต้องเรียกก่อนสร้างหน้าต่าง Tk"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _screen_metrics(root):
    """คืน (vx0, vy0, virtual_w, virtual_h, primary_w, primary_h)
    โดย virtual_* ครอบคลุมจอทั้งหมดที่ต่ออยู่ (จอ 2/3 ด้วย)"""
    try:
        g = ctypes.windll.user32.GetSystemMetrics
        vx0, vy0 = g(76), g(77)        # SM_X/YVIRTUALSCREEN (มุมซ้ายบนของกรอบรวมทุกจอ)
        vw, vh = g(78), g(79)          # SM_CX/CYVIRTUALSCREEN (ขนาดกรอบรวม)
        pw, ph = g(0), g(1)            # SM_CX/CYSCREEN (ขนาดจอหลัก)
        if vw > 0 and vh > 0:
            return vx0, vy0, vw, vh, pw, ph
    except Exception:
        pass
    # สำรอง (ไม่ใช่ Windows): ใช้จอเดียว
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    return 0, 0, w, h, w, h


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),     # พื้นที่ใช้งานจริง = จอลบแถบ taskbar
                ("dwFlags", wintypes.DWORD)]


def _enumerate_monitors():
    """คืนสี่เหลี่ยมของแต่ละจอ [(mon_rect, work_rect), ...] ในพิกัดหน้าจอ
    โดย mon_rect = ขอบจอจริง, work_rect = พื้นที่ไม่รวม taskbar"""
    rects = []
    try:
        proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, wintypes.HDC,
                                  ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def _cb(hmon, hdc, lprc, lparam):
            r = lprc.contents
            mon = (r.left, r.top, r.right, r.bottom)
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                w = mi.rcWork
                work = (w.left, w.top, w.right, w.bottom)
            else:
                work = mon
            rects.append((mon, work))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(0, 0, proc(_cb), 0)
    except Exception:
        pass
    return rects


class World:
    def __init__(self):
        _enable_dpi_awareness()
        self.root = tk.Tk()
        # ครอบทุกจอ: sw/sh = ขนาดกรอบรวม, vx0/vy0 = มุมซ้ายบนของกรอบรวม
        (self.vx0, self.vy0, self.sw, self.sh,
         self.primary_w, self.primary_h) = _screen_metrics(self.root)
        # สี่เหลี่ยมของแต่ละจอ แปลงเป็นพิกัด canvas (canvas เริ่มที่มุมกรอบรวมทุกจอ)
        mons = _enumerate_monitors()
        if mons:
            self.monitors = [(l - self.vx0, t - self.vy0, r - self.vx0, b - self.vy0)
                             for ((l, t, r, b), _work) in mons]
            # ขอบล่างของพื้นที่ใช้งาน (เหนือ taskbar) ของแต่ละจอ ในพิกัด canvas
            self.work_bottoms = [(l - self.vx0, r - self.vx0, wb - self.vy0)
                                 for (_m, (l, t, r, wb)) in mons]
        else:
            self.monitors = [(0, 0, self.sw, self.sh)]
            self.work_bottoms = [(0, self.sw, self.sh)]

        # หน้าต่างไร้ขอบ โปร่งใส อยู่บนสุด ครอบทุกจอ
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.sw}x{self.sh}+{self.vx0}+{self.vy0}")
        self.root.config(bg=config.TRANSPARENT_KEY)
        self.root.wm_attributes("-transparentcolor", config.TRANSPARENT_KEY)
        self.root.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(self.root, width=self.sw, height=self.sh,
                                bg=config.TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # โหลดภาพ (ต้องทำหลังสร้าง root แล้ว)
        # อนิเมชันร่วม (มอนสเตอร์/อาหาร) โหลดจาก assets/ — ของเพ็ทโหลดต่อตัวใน _build_pet
        assets.set_character_dir(None)
        self.monster_sets = self._load_monster_sets()   # มอนหลายแบบ (สุ่มตอนเกิด)
        fa = assets.load_sprite(config.FOOD_SPRITES) or assets.build_fallback("food", config.FOOD_SIZE)
        self.food_anims = {"idle": fa}

        # สร้างน้องทั้งหมดจากเซฟ (รองรับหลายตัว + ย้ายข้อมูลเซฟเก่ามาเป็นตัวแรก)
        self.pets = []
        self.active = 0
        self.monster = None
        self._load_progress()
        # นับถอยหลัง (วินาที) จนกว่ามอนสเตอร์ตัวถัดไปจะสุ่มเกิดเอง
        self.monster_spawn_in = random.randint(config.MONSTER_SPAWN_MIN_SEC,
                                               config.MONSTER_SPAWN_MAX_SEC)
        self.effects = []          # [{"item":id, "ttl":int, "dy":float}]
        self.bubble_items = []
        self.bubble_ttl = 0
        self.show_hud = True            # แสดงเมนูด้านขวาล่าง (เปิด/ปิดได้ที่ปุ่ม ☰)
        self.hud_slide = 0.0            # ความคืบหน้าอนิเมชันยุบ/กาง 0=ยุบ 1=กางเต็ม
        self._hud_drag_active = False   # กำลังลากเมนูอยู่ไหม
        self._menu_pet = None            # น้องที่กำลังเปิดเมนูดูแลอยู่ (ถูกพักไว้)
        # self.combat_enabled ถูกตั้งใน _load_progress() (เรียกไปแล้วด้านบน)
        self.tick_count = 0
        self._sec_ticks = max(1, round(1000 / config.TICK_MS))  # จำนวน tick ต่อ 1 วินาที

        # อินพุต
        self._down = False
        self._dragged = False
        self._press_xy = (0, 0)
        # (การผูกคลิกที่ตัวน้องทำใน _build_pet ต่อตัว — รองรับหลายตัว)
        # ปุ่มเมนูด้านขวา (วาดใหม่ทุกเฟรม จึงผูกกับ tag)
        hud_btns = ("btn_combat", "btn_achv", "btn_pets", "btn_bag", "btn_adventure",
                    "btn_settings", "btn_hud_edge",
                    "btn_checkin", "btn_shop", "btn_quest")
        for _tag in hud_btns:
            self.canvas.tag_bind(_tag, "<Enter>",
                                 lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind(_tag, "<Leave>",
                                 lambda e: self.canvas.config(cursor=""))
        self.canvas.tag_bind("btn_combat", "<Button-1>", self._toggle_combat)
        self.canvas.tag_bind("btn_settings", "<Button-1>", self._on_settings_click)
        self.canvas.tag_bind("btn_hud_edge", "<ButtonPress-1>", self._hud_edge_press)
        self.canvas.tag_bind("btn_checkin", "<Button-1>",
                             lambda e: self._menu_click(self._show_checkin_window))
        self.canvas.tag_bind("btn_shop", "<Button-1>",
                             lambda e: self._menu_click(self._show_shop_window))
        self.canvas.tag_bind("btn_bag", "<Button-1>",
                             lambda e: self._menu_click(self._show_bag_window))
        self.canvas.tag_bind("btn_quest", "<Button-1>",
                             lambda e: self._menu_click(self._show_quest_window))
        self.canvas.tag_bind("btn_achv", "<Button-1>",
                             lambda e: self._menu_click(self._show_achievements_window))
        self.canvas.tag_bind("btn_pets", "<Button-1>",
                             lambda e: self._menu_click(self._show_pets_window))
        self.canvas.tag_bind("btn_adventure", "<Button-1>",
                             lambda e: self._menu_click(self._show_adventure_window))
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.quit())

        self._build_menu()

        # ซ่อนเพ็ทเมื่อมีโปรแกรมอื่นเปิดเต็มจอ (เกม/วิดีโอ fullscreen)
        self.root.update_idletasks()
        self._own_hwnds = self._collect_own_hwnds()
        self.hidden_for_fullscreen = False

        # การแจ้งเตือนหิว
        self._was_hungry = False
        self._last_hunger_notify = -1e9

    # --------------------------------------------------- หลายตัว (active pet)
    @property
    def pet(self):
        """น้องที่ 'กำลังดูแล' (active) — None ถ้ายังไม่มีน้อง (เกมใหม่ก่อนฟักไข่)"""
        if not self.pets:
            return None
        return self.pets[min(self.active, len(self.pets) - 1)]

    @property
    def character(self):
        return self.pet.character

    def _is_night(self):
        """กลางคืนไหม (ตามเวลาจริงของเครื่อง)"""
        h = datetime.datetime.now().hour
        s, e = config.NIGHT_START_HOUR, config.NIGHT_END_HOUR
        return (h >= s or h < e) if s > e else (s <= h < e)

    # ------------------------------------------------------------------ setup
    def _load_anims(self, spritemap, kind, size, color=None):
        anims = {}
        for state, candidates in spritemap.items():
            a = assets.load_sprite(candidates)
            if a:
                anims[state] = a
        if "idle" not in anims:
            anims["idle"] = assets.build_fallback(kind, size, color)
        return anims

    def _load_monster_sets(self):
        """โหลดชุดสไปรต์มอนสเตอร์ทุกแบบ: ตัวเริ่มต้น (assets/) + ทุกโฟลเดอร์ใน monsters/
        แต่ละชุดมี walk/hurt (+idle สำรอง) — ตอนเกิดจะสุ่มเลือกชุดหนึ่ง"""
        folder_cand = {
            "walk": ["walk.gif", "walk.png", "monster_walk.gif", "monster_walk.png",
                     "monster.gif", "monster.png"],
            "hurt": ["hurt.gif", "hurt.png", "monster_hurt.gif", "monster_hurt.png"],
        }
        sets = []
        assets.set_character_dir(None)               # ตัวเริ่มต้นจาก assets/
        sets.append(self._load_anims(config.MONSTER_SPRITES, "monster", config.MONSTER_SIZE))
        for name in assets.list_monsters():          # มอนที่ผู้ใช้เพิ่ม (โฟลเดอร์ละตัว)
            assets.set_character_dir(assets.monster_path(name))
            sets.append(self._load_anims(folder_cand, "monster", config.MONSTER_SIZE))
        assets.set_character_dir(None)
        return sets

    def _load_pet_anims(self):
        """โหลดชุดสไปรต์ของน้อง 1 ชุด (ไม่มีระบบแปลงร่างแล้ว)
        ใช้ไฟล์ pet_<state>.gif/png ในโฟลเดอร์ตัวละคร; ขาดไฟล์ → ตัวสำรอง"""
        return self._load_anims(config.PET_SPRITES, "pet", config.PET_SIZE)

    def _read_saved_character(self):
        """อ่านชื่อตัวละครที่บันทึกไว้ — คืน None ถ้าไม่มี/โฟลเดอร์หายไป (ใช้ assets/ ปกติ)"""
        name = save.load().get("character")
        return name if name and name in assets.list_characters() else None

    def set_character(self, name):
        """เปลี่ยน 'ตัวละคร/อาร์ต' ของน้องที่กำลังดูแล (เก็บสเตตัสเดิมไว้)"""
        pd = self._pet_to_data(self.pet)
        pd["character"] = name
        new = self._build_pet(name, pd)
        old = self.pets[self.active]
        old.destroy()
        if old.food is not None:
            old.food.destroy()
        self.pets[self.active] = new
        self._save_progress()
        self.show_bubble(f"เปลี่ยนร่าง: {name or 'ค่าเริ่มต้น'} ✨")

    def _cycle_character(self):
        """วนไปตัวละครถัดไป (ค่าเริ่มต้น → แต่ละโฟลเดอร์ → วนกลับ)"""
        options = [None] + assets.list_characters()
        try:
            i = options.index(self.pet.character)
        except ValueError:
            i = 0
        self.set_character(options[(i + 1) % len(options)])

    @staticmethod
    def _starter_character():
        """ตัวละครเริ่มต้นตอนเกมใหม่ = ตัวที่อัปโหลดไว้ตัวแรก (ถ้าไม่มีเลย = None ใช้ assets)"""
        chars = assets.list_characters()
        return chars[0] if chars else None

    def _build_pet(self, character, pd):
        """สร้าง Pet 1 ตัว: โหลดอาร์ต/ความชอบของตัวละคร แล้วใส่สเตตัสจาก pd (dict)"""
        pd = pd or {}
        assets.set_character_dir(assets.character_path(character) if character else None)
        anims = self._load_pet_anims()
        meta = assets.load_character_meta(character)
        valid = {f["id"] for f in config.FOOD_TYPES}
        x = float(pd.get("x", self.sw * (0.3 + 0.12 * len(self.pets))))
        pet = Pet(self.canvas, anims, x, 0)
        pet.character = character
        # ความชอบอาหาร: ใช้ค่าที่ส่งมา (สืบทอดจากพ่อแม่/ไข่) ถ้ามี ไม่งั้นเอาจาก pet.json
        likes_src = pd["likes"] if isinstance(pd.get("likes"), list) else meta.get("likes", [])
        dislikes_src = (pd["dislikes"] if isinstance(pd.get("dislikes"), list)
                        else meta.get("dislikes", []))
        pet.likes = [v for v in likes_src if v in valid]
        if not pet.likes:                    # ยังไม่ได้ตั้งความชอบ → ใช้ค่าเริ่มต้น (ผลไม้)
            pet.likes = [v for v in config.DEFAULT_FOOD_LIKES if v in valid]
        pet.dislikes = [v for v in dislikes_src if v in valid and v not in pet.likes]
        pet.name = str(pd.get("name", "")) or (character or "เพ็ท")
        # หน่วงเฟรมรายสถานะ (จาก pet.json ของตัวละคร) — clamp ให้อยู่ในช่วงที่ตั้งได้
        am = meta.get("anim_ms") if isinstance(meta.get("anim_ms"), dict) else {}
        pet.anim_ms = {k: max(config.ANIM_MS_MIN, min(config.ANIM_MS_MAX, int(v)))
                       for k, v in am.items() if k in config.PET_SPRITES}
        pet.level = max(1, int(pd.get("level", 1)))
        pet.xp = max(0, int(pd.get("xp", 0)))
        pet.fullness = _clamp(pd.get("fullness", 80))
        pet.happy = _clamp(pd.get("happy", 80))
        pet.energy = _clamp(pd.get("energy", 80))
        pet.cleanliness = _clamp(pd.get("cleanliness", 80))
        pet.affection = _clamp(pd.get("affection", 0))
        pet.sick = bool(pd.get("sick", False))
        # ฝึกฝน (จำนวนครั้งต่อสาย) + นิสัยประจำตัว (สุ่มถ้ายังไม่มี)
        tr = pd.get("train") if isinstance(pd.get("train"), dict) else {}
        pet.train = {k: max(0, int(tr.get(k, 0))) for k in ("atk", "hp", "speed")}
        # บิลด์/แต้มสกิล/รีบอร์น
        pet.rebirths = max(0, min(int(pd.get("rebirths", 0)), config.REBIRTH_MAX))
        pet.level = min(pet.level, config.MAX_LEVEL)
        pet.sp = max(0, int(pd.get("sp", 0)))
        bd = pd.get("build") if isinstance(pd.get("build"), dict) else {}
        pet.build = {k: max(0, min(int(bd.get(k, 0)), config.BUILD_MAX))
                     for k in ("crit", "dodge", "lifesteal", "skill")}
        valid_traits = {t["id"] for t in config.TRAITS}
        pet.trait = (pd["trait"] if pd.get("trait") in valid_traits
                     else random.choice(config.TRAITS)["id"])
        self._apply_trait(pet)
        # เพศ (สุ่มถ้ายังไม่มี) + สกิลติดตัว (สุ่ม 1 อย่างถ้ายังไม่มี)
        pet.gender = (pd["gender"] if pd.get("gender") in {"m", "f"}
                      else random.choice(config.GENDERS)["id"])
        valid_skills = {s["id"] for s in config.SKILLS}
        pet.skill = (pd["skill"] if pd.get("skill") in valid_skills
                     else random.choice(config.SKILLS)["id"])
        valid_rar = {r["id"] for r in config.RARITIES}
        pet.rarity = pd["rarity"] if pd.get("rarity") in valid_rar else "common"
        try:
            pet.away_until = float(pd.get("away_until", 0) or 0)
        except (TypeError, ValueError):
            pet.away_until = 0.0
        pet.away_mins = max(0, int(pd.get("away_mins", 0)))
        valid_tricks = {t["id"] for t in config.TRICKS}
        pet.tricks_taught = [t for t in pd.get("tricks_taught", []) if t in valid_tricks]
        pet.birth_date = str(pd.get("birth_date", "")) or self._today()
        hp = pd.get("hp")
        hp = float(hp) if hp not in (None, "") else pet.max_hp()
        pet.hp = min(hp, pet.max_hp())
        if pet.hp <= 0:
            pet.hp = pet.max_hp()
        self._drop_to_ground(pet)
        pet.sync_position()
        self.canvas.tag_bind(pet.item, "<ButtonPress-1>",
                             lambda e, p=pet: self.on_press(e, p))
        if pet.away_until > time.time():     # โหลดมาตอนยังผจญภัยอยู่ → ซ่อนไว้
            self.canvas.itemconfigure(pet.item, state="hidden")
        return pet

    def _pet_to_data(self, pet):
        """แปลงสเตตัสน้อง 1 ตัวเป็น dict สำหรับบันทึก"""
        return {
            "character": pet.character, "name": pet.name,
            "level": pet.level, "xp": pet.xp, "hp": round(pet.hp, 1),
            "fullness": round(pet.fullness, 1), "happy": round(pet.happy, 1),
            "energy": round(pet.energy, 1), "cleanliness": round(pet.cleanliness, 1),
            "affection": round(pet.affection, 1),
            "sick": pet.sick,
            "tricks_taught": pet.tricks_taught,
            "likes": list(pet.likes), "dislikes": list(pet.dislikes),
            "trait": pet.trait, "train": dict(pet.train),
            "gender": pet.gender, "skill": pet.skill, "rarity": pet.rarity,
            "sp": pet.sp, "build": dict(pet.build), "rebirths": pet.rebirths,
            "away_until": round(pet.away_until, 1), "away_mins": pet.away_mins,
            "birth_date": pet.birth_date, "x": round(pet.x, 1),
        }

    def _work_bottom_at(self, x):
        """ขอบบนของ taskbar (ขอบล่างพื้นที่ใช้งาน) ของจอที่ตำแหน่ง x ตกอยู่"""
        cands = [wb for (l, r, wb) in self.work_bottoms if l <= x < r]
        if cands:
            return max(cands)
        return max((wb for (_l, _r, wb) in self.work_bottoms), default=self.sh)

    def _ground_y(self, x):
        """พื้นที่เพ็ทยืน = ขอบบนของ taskbar (ลบ GROUND_OFFSET ถ้าอยากให้ลอยสูงขึ้น)"""
        return self._work_bottom_at(x) - config.GROUND_OFFSET

    def _drop_to_ground(self, ent):
        ent.y = self._ground_y(ent.x) - ent.current_anim().h / 2

    def _build_menu(self):
        # คลิกที่ตัวเพ็ทไม่มีเมนูแล้ว (ทุกเมนูย้ายไปคอลัมน์ปุ่มด้านขวา)
        # คงไว้เพื่อเริ่มต้นตัวแปรหน้าต่างป๊อปอัป (ธีมเข้ม) — สร้างใหม่ทุกครั้งที่เปิด
        self._settings_win = None
        self._char_win = None
        self._feature_window = None    # หน้าต่างฟีเจอร์ (เกม/ตู้เสื้อผ้า/ทริค/ความสำเร็จ)

    def _show_character_popup(self):
        """หน้าต่างเลือกตัวละคร (ธีมเข้ม มี hover + ✓ ตัวที่ใช้อยู่) อยู่กลางจอหลัก"""
        self._close_all_menus()
        options = [(None, "ค่าเริ่มต้น (assets)")]
        options += [(n, n) for n in assets.list_characters()]
        BG, FG, HOVER, SEL = "#1e1e1e", "#ffffff", "#34506b", "#1f6f4a"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")                       # ขอบ 2px
        frame = tk.Frame(win, bg=BG)
        frame.pack(padx=2, pady=2)
        tk.Label(frame, text="🎭  เลือกตัวละคร", bg="#15151a", fg="#f1c40f",
                 font=("Segoe UI", 13, "bold"), pady=11).pack(fill="x")
        for value, label in options:
            cur = (value == self.character)
            base = SEL if cur else BG
            mark = "✓" if cur else "  "
            row = tk.Label(frame, text=f"   {mark}   🐾   {label}", anchor="w",
                           bg=base, fg=FG, font=("Segoe UI", 12),
                           padx=20, pady=10, cursor="hand2")
            row.pack(fill="x")
            row.bind("<Enter>", lambda e, r=row: r.configure(bg=HOVER))
            row.bind("<Leave>", lambda e, r=row, b=base: r.configure(bg=b))
            row.bind("<Button-1>", lambda e, v=value: self._char_choose(v))
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = int(self.primary_w / 2 - w / 2)
        y = int(self.primary_h / 2 - h / 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
        self._char_win = win
        win.bind("<FocusOut>", lambda e: self._close_char_popup())
        win.bind("<Escape>", lambda e: self._close_char_popup())
        win.focus_force()

    def _close_char_popup(self):
        w = getattr(self, "_char_win", None)
        self._char_win = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _char_choose(self, value):
        self._close_char_popup()
        self.set_character(value)
        self._draw_hud()

    # ----------------------------------------------------------------- inputs
    def on_press(self, e, pet=None):
        # ตอนต่อสู้ (มีมอนบนจอ) ห้ามกด/ลากน้อง — ยกเว้นน้องที่เสียชีวิต (กดเพื่อชุบได้)
        if self.monster is not None and pet is not None and pet.behavior != "dead":
            self._down = False
            return
        # จับน้องตัวที่กดไว้ + ตั้งให้เป็น "ตัวที่กำลังดูแล" (active) ทันที
        self._down = True
        self._dragged = False
        self._press_xy = (e.x, e.y)
        if pet is not None and pet in self.pets:
            self._drag_pet = pet
            self.active = self.pets.index(pet)
        else:
            self._drag_pet = self.pet

    def on_drag(self, e):
        if self._hud_drag_active:            # กำลังลากเมนู
            self._hud_do_drag(e)
            return
        if not self._down:
            return
        pet = getattr(self, "_drag_pet", None) or self.pet
        if abs(e.x - self._press_xy[0]) + abs(e.y - self._press_xy[1]) > 6:
            if not self._dragged:                # เริ่มลาก → ซ่อนเคอร์เซอร์ ไม่ให้บังตัวน้อง
                try:
                    self.canvas.config(cursor="none")
                except Exception:
                    pass
            self._dragged = True
            pet.behavior = "drag"
            pet.x = max(20, min(self.sw - 20, e.x))
            pet.y = max(20, min(self.sh - 20, e.y))
            pet.set_state("taken")               # ท่าตอนถูกอุ้ม/ลาก
            pet.sync_position()

    def on_release(self, e):
        if self._hud_drag_active:            # ปล่อยจากการลาก/กดเมนู
            self._hud_end_drag(e)
            return
        if not self._down:
            return
        self._down = False
        pet = getattr(self, "_drag_pet", None) or self.pet
        if self._dragged:
            try:
                self.canvas.config(cursor="")    # ปล่อยแล้ว → คืนเคอร์เซอร์
            except Exception:
                pass
            self._drop_to_ground(pet)        # ปล่อยแล้วร่วงลงพื้น
            pet.behavior = "wander"
            pet.vx = 0
        else:
            self._show_pet_menu(pet)         # แตะ (ไม่ลาก) = เปิดเมนูดูแลเหนือหัวน้องตัวนั้น

    # ----------------------------------------------------- ลากเมนูไปวางที่อื่น
    def _hud_edge_press(self, e):
        """กดที่ปุ่ม ☰ — เริ่มจับการลาก (ถ้าขยับ = ย้ายเมนู, ถ้าไม่ขยับ = เปิด/ปิด)"""
        self._hud_drag_active = True
        self._hud_moved = False
        self._hud_press_root = (e.x_root, e.y_root)
        self._hud_press_offset = (self.hud_offset_x, self.hud_offset_y)
        return "break"

    def _hud_do_drag(self, e):
        dx = e.x_root - self._hud_press_root[0]
        dy = e.y_root - self._hud_press_root[1]
        if abs(dx) + abs(dy) > 5:
            self._hud_moved = True
        self.hud_offset_x = self._hud_press_offset[0] + dx
        self.hud_offset_y = self._hud_press_offset[1] + dy
        self._draw_hud()                     # _draw_hud จะ clamp ให้อยู่ในจอเอง

    def _hud_end_drag(self, e):
        self._hud_drag_active = False
        if self._hud_moved:
            self._save_progress()            # จำตำแหน่งใหม่
            self._draw_hud()
        else:
            sound.play("click")              # กดเฉย ๆ = เปิดเมนูหลักกลางจอ
            self._show_main_menu()

    # ---------------------------------------------------------------- actions
    def pet_react(self):
        pet = self.pet
        if pet.behavior == "dead":
            return
        if pet.behavior == "sleep":           # ลูบหัวแล้วตื่น
            self._wake(pet)
        pet.happy = min(100, pet.happy + 8)
        pet.affection = min(100, pet.affection + config.AFFECTION_PER_PET)
        self._start_action(pet, "pet", 30)            # เล่นอนิเมชันลูบหัว
        self._flash_bar(pet, "happy")
        self.show_bubble(random.choice(["❤", "♪", "สบายดี!", "ฮุ่ย~"]))
        sound.play("pet")
        self.add_xp(config.XP_PER_PET)

    # ---- นอน (ฟื้นพลังงาน) / อาบน้ำ (ฟื้นความสะอาด) -----------------------
    def sleep_toggle(self):
        """สลับนอน/ตื่น ของน้องที่กำลังดูแล (ปุ่ม 😴)"""
        pet = self.pet
        if pet.behavior == "dead":
            return
        if pet.behavior == "sleep":
            self._wake(pet)
            return
        if self.monster is not None:
            self.show_bubble("มีศัตรูอยู่ นอนไม่ได้! ⚔")
            return
        self._start_sleep(pet)

    def _start_sleep(self, pet, auto=False):
        """ให้น้องตัวที่ระบุเข้าสู่สถานะหลับ (auto=True คืองีบเองตอนหมดแรง)"""
        if pet.food is not None:                  # ยกเลิกอาหารที่ค้างอยู่
            pet.food.destroy()
            pet.food = None
        pet.behavior = "sleep"
        pet.vx = 0.0
        pet.set_state("sleep")
        self.show_bubble("หมดแรง... งีบก่อน 😴" if auto else "Zzz... 😴", pet)

    def _wake(self, pet=None):
        pet = pet or self.pet
        if pet.behavior == "sleep":
            pet.behavior = "wander"
            pet.vx = 0.0
            self.show_bubble("ตื่นแล้ว! ☀", pet)

    def bathe(self):
        """อาบน้ำ: เติมความสะอาดเต็ม + เพิ่มสุขเล็กน้อย (ปุ่ม 🛁)"""
        if self.pet.behavior == "dead":
            return
        if self.pet.cleanliness >= 99:
            self.show_bubble("สะอาดเอี่ยมอยู่แล้ว! ✨")
            return
        if self.pet.behavior == "sleep":
            self._wake()
        self.pet.cleanliness = 100
        self.pet.happy = min(100, self.pet.happy + 6)
        self.pet.affection = min(100, self.pet.affection + 0.2)
        self._start_action(self.pet, "bathe", 40)     # เล่นอนิเมชันอาบน้ำ
        self._flash_bar(self.pet, "cleanliness")
        self.show_bubble("สะอาดสดชื่น! 🛁")
        self.spawn_effect(self.pet.x, self.pet.top_y(), "🫧")
        sound.play("pet")

    def _pet_mood(self, pet=None):
        """คืน (อิโมจิ, ข้อความ) บอกอารมณ์/อาการของน้องจากสเตตัสปัจจุบัน"""
        p = pet or self.pet
        if p.behavior == "dead":
            return ("💀", "เสียชีวิต")
        if p.sick:
            return ("🤒", "ไม่สบาย")
        if p.behavior == "sleep":
            return ("😴", "หลับอยู่")
        if p.fullness < config.HUNGRY_THRESHOLD:
            return ("🍖", "หิว")
        if p.energy < config.SLEEPY_THRESHOLD:
            return ("🥱", "ง่วง")
        if p.cleanliness < config.DIRTY_THRESHOLD:
            return ("🛁", "อยากอาบน้ำ")
        if p.happy < 30:
            return ("😢", "เหงา")
        if p.happy > 75 and p.fullness > 60:
            return ("😄", "อารมณ์ดี")
        return ("🙂", "สบายดี")

    def feed(self, food_id=None):
        """ให้อาหารน้องที่กำลังดูแล (active) — เล่นอนิเมชัน eat จากไฟล์อยู่กับที่"""
        pet = self.pet
        if self.monster is not None:
            self.show_bubble("กำลังสู้อยู่ เดี๋ยวค่อยกิน! ⚔")
            return False
        if pet.behavior in ("dead", "eating") or self._is_away(pet):
            return False
        if pet.behavior == "sleep":
            self._wake(pet)
        pet.food_type = food_id             # ชนิดอาหารที่กำลังให้ (ใช้ตอนกินเสร็จ)
        pet.behavior = "eating"             # กินอยู่กับที่ ไม่มีก้อนอาหารวาดขึ้น
        pet.eat_timer = 40
        pet.set_state("eat")
        return True

    def _pick_food_for(self, pet):
        """เลือกอาหารในกระเป๋าให้น้องตัวนี้: ของชอบก่อน > ของเฉย ๆ > ที่มี"""
        foods = [it["id"] for it in config.SHOP_ITEMS
                 if it["use"] == "feed" and self.inventory.get(it["id"], 0) > 0]
        if not foods:
            return None
        liked = [f for f in foods if f in pet.likes]
        if liked:
            return liked[0]
        ok = [f for f in foods if f not in pet.dislikes]
        return (ok or foods)[0]

    def _auto_feed(self):
        """น้องที่หิว + มีอาหารในกระเป๋า → กินเองอัตโนมัติ (แม้ไม่กดป้อน)"""
        for pet in self.pets:
            if pet.behavior not in ("wander", "stay") or self._is_away(pet):
                continue
            if pet.fullness >= config.HUNGRY_THRESHOLD:
                continue
            fid = self._pick_food_for(pet)
            if not fid:
                continue
            self.inventory[fid] -= 1
            if self.inventory[fid] <= 0:
                del self.inventory[fid]
            pet.food_type = fid
            pet.behavior = "eating"
            pet.eat_timer = 40
            pet.set_state("eat")

    def _tick_spawn_monster(self):
        """นับถอยหลังเพื่อให้มอนสเตอร์สุ่มเกิดเอง (เรียกทุก ~1 วินาที)"""
        if not getattr(self, "combat_enabled", True):
            return                              # โหมดเลี้ยงอย่างเดียว: ไม่เกิดมอน
        if self.monster is not None:
            return
        # เกิดได้ถ้ามีน้องอย่างน้อย 1 ตัวพร้อมสู้ (ไม่สลบ/ไม่ถูกลาก/ไม่ผจญภัย)
        if not any(p.behavior not in ("dead", "drag") and not self._is_away(p)
                   for p in self.pets):
            return
        self.monster_spawn_in -= 1
        if self.monster_spawn_in <= 0:
            self._spawn_monster()
            self.monster_spawn_in = random.randint(config.MONSTER_SPAWN_MIN_SEC,
                                                   config.MONSTER_SPAWN_MAX_SEC)

    def _scaled_anims(self, anims, factor):
        """คืนชุดอนิเมชันที่ขยายขนาด factor เท่า (จำนวนเต็ม) — ใช้ทำบอสตัวใหญ่"""
        factor = max(1, int(factor))
        if factor == 1:
            return anims
        out = {}
        for state, anim in anims.items():
            out[state] = assets.Animation([f.zoom(factor) for f in anim.frames])
        return out

    def _spawn_monster(self):
        """สร้างมอนตัวถัดไปของเวฟ — HP/ATK สเกลตามเลเวลเพ็ท + เวฟ; ตัวที่ WAVE_LENGTH = บอส"""
        is_boss = self.wave_step >= config.WAVE_LENGTH
        # สุ่มเลือกมอนสเตอร์ 1 แบบจากชุดที่มี (บอสตัวใหญ่กว่า)
        base = random.choice(self.monster_sets) if self.monster_sets else \
            self._load_anims(config.MONSTER_SPRITES, "monster", config.MONSTER_SIZE)
        base_w = (base.get("walk") or base.get("idle")).w
        if is_boss:
            anims = self._scaled_anims(base, config.BOSS_SIZE_MULT)
            width = base_w * config.BOSS_SIZE_MULT
        else:
            anims = base
            width = base_w

        from_left = random.random() < 0.5
        x = -width if from_left else self.sw + width
        m = Monster(self.canvas, anims, x, 0)
        m.is_boss = is_boss

        # สเตตัสฐาน: ตามเลเวลเพ็ท แล้วคูณโบนัสเวฟ (เก่งขึ้นทุกเวฟ)
        lvl = self.pet.level
        round_mult = 1 + (self.wave_round - 1) * config.WAVE_STRENGTH_BONUS
        base_hp = (config.MONSTER_MAX_HP + (lvl - 1) * config.MONSTER_HP_PER_LEVEL) * round_mult
        base_atk = (config.MONSTER_ATTACK + (lvl - 1) * config.MONSTER_ATTACK_PER_LEVEL) * round_mult
        if is_boss:
            base_hp *= config.BOSS_HP_MULT
            base_atk *= config.BOSS_ATK_MULT
            m.max_hp = max(1, int(round(base_hp)))     # บอสไม่สุ่มแปรผัน (คงที่)
            m.atk = max(1, int(round(base_atk)))
        else:
            v = config.MONSTER_STAT_VARIANCE
            m.max_hp = max(1, int(round(base_hp * random.uniform(1 - v, 1 + v))))
            m.atk = max(1, int(round(base_atk * random.uniform(1 - v, 1 + v))))
        m.hp = m.max_hp

        self.monster = m
        self._drop_to_ground(m)
        m.sync_position()
        # น้องทุกตัวที่พร้อม (ไม่สลบ/ไม่ถูกลาก/ไม่ผจญภัย) วิ่งเข้าไปรุมสู้
        weaken = 0.0
        for p in self.pets:
            if p.behavior in ("dead", "drag") or self._is_away(p):
                continue
            if p.food is not None:
                p.food.destroy()
                p.food = None
            p.eat_timer = None
            p.behavior = "fight"
            weaken = max(weaken, self._skill_val(p, "weaken"))   # 💢 ทอนกำลัง
        if weaken:
            m.atk = max(1, int(m.atk * (1.0 - weaken)))
        if is_boss:
            self.show_bubble(f"👑 บอสเวฟ {self.wave_round} มาแล้ว!")
            sound.play("boss")
        else:
            self.show_bubble(f"⚔ มอนสเตอร์ ({self.wave_step}/{config.WAVE_LENGTH})")

    def toggle_stand(self):
        """สลับโหมด 'ยืนเฉย ๆ' (ไม่เดิน แต่หันซ้าย-ขวา) กับเดินเล่นปกติ"""
        if self.pet.behavior == "dead":
            return
        if self.pet.behavior == "stay":
            self.pet.behavior = "wander"
            self.pet.vx = 0.0
            self.show_bubble("เดินเล่นต่อ~ 🐾")
        else:
            self.pet.behavior = "stay"
            self.pet.vx = 0.0
            self.pet.set_state("idle")
            self.pet.stay_timer = random.randint(40, 90)
            self.show_bubble("ยืนเฉย ๆ 🧍")

    def toggle_hud(self):
        self.show_hud = not self.show_hud   # อนิเมชันสไลด์จัดการซ่อน/แสดงใน _draw_hud

    def _on_hud_edge_click(self, e):
        """กดปุ่ม handle ขอบขวา = เปิด/ปิดเมนูขวา (สไลด์เข้า/ออก)"""
        self.show_hud = not self.show_hud
        self._draw_hud()
        return "break"

    def _draw_edge_handle(self, rect, alert=False):
        """ปุ่มเมนูหลัก ☰ มุมขวาล่าง — กดเปิดเมนูกลางจอ, ลากเพื่อย้ายตำแหน่ง"""
        hx0, hy0, hx1, hy1 = rect
        self.canvas.create_rectangle(hx0, hy0, hx1, hy1, fill="#2c3e50",
                                     outline="#5a7fa5", width=2,
                                     tags=("hudedge", "btn_hud_edge"))
        self.canvas.create_text((hx0 + hx1) / 2, (hy0 + hy1) / 2, text="☰",
                                fill="#ffffff", font=("Segoe UI", 18, "bold"),
                                tags=("hudedge", "btn_hud_edge"))
        if alert:                                   # จุดแดงเตือนว่ามีอะไรรอทำ
            r = 6
            self.canvas.create_oval(hx1 - r - 3, hy0 + 3, hx1 - 3, hy0 + 3 + r,
                                    fill="#e74c3c", outline="#ffffff", width=1,
                                    tags=("hudedge", "btn_hud_edge"))

    def add_xp(self, amount, pet=None):
        """เพิ่ม XP ให้น้องตัวที่ระบุ (ค่าเริ่มต้น = ตัวที่กำลังดูแล) + เลื่อนเลเวล/แต้มสกิล"""
        p = pet or self.pet
        if p.level >= config.MAX_LEVEL:          # เลเวลตันแล้ว — เก็บ XP ไว้เต็มหลอด (รอรีบอร์น)
            p.xp = p.xp_to_next()
            return
        p.xp += amount
        leveled = 0
        while p.xp >= p.xp_to_next() and p.level < config.MAX_LEVEL:
            p.xp -= p.xp_to_next()
            p.level += 1
            leveled += 1
            p.sp += config.SP_PER_LEVEL          # ได้แต้มสกิลไปลงเอง
            if p.level % config.SP_MILESTONE_EVERY == 0:
                p.sp += config.SP_MILESTONE_BONUS    # โบนัสก้อนทุก 5 เลเวล
        if p.level >= config.MAX_LEVEL:
            p.xp = 0
        if leveled:
            p.hp = p.max_hp()
            cap = "  (ตัน — รีบอร์นได้!)" if p.level >= config.MAX_LEVEL else ""
            self.show_bubble(f"⬆ LEVEL UP! Lv.{p.level}{cap}", p)
            self.spawn_effect(p.x, p.top_y(), "✨")
            sound.play("levelup")
        self._save_progress()

    def _spend_sp(self, pet, line_id):
        """ลงแต้มสกิล 1 แต้มในสายที่ระบุ (crit/dodge/lifesteal/skill)"""
        if line_id not in pet.build:
            return
        if pet.sp <= 0:
            self.show_bubble("ไม่มีแต้มสกิล! เลเวลอัพก่อน ⬆", pet)
            return
        if pet.build[line_id] >= config.BUILD_MAX:
            self.show_bubble("สายนี้เต็มแล้ว!", pet)
            return
        pet.sp -= 1
        pet.build[line_id] += 1
        if line_id == "hp":
            pet.hp = pet.max_hp()
        sound.play("levelup")
        self._save_progress()

    def _can_rebirth(self, pet):
        return pet.level >= config.MAX_LEVEL and pet.rebirths < config.REBIRTH_MAX

    def _rebirth(self, pet):
        """ถึงเลเวลตัน → รีเซ็ตเป็น Lv.1 แลกโบนัส ATK/HP ถาวร (เก็บบิลด์/แต้มไว้)"""
        if not self._can_rebirth(pet):
            self.show_bubble("ยังรีบอร์นไม่ได้ — ต้องถึงเลเวลตันก่อน", pet)
            return
        pet.rebirths += 1
        pet.level = 1
        pet.xp = 0
        pet.hp = pet.max_hp()
        sound.play("levelup")
        bonus = int(config.REBIRTH_BONUS * 100)
        self.show_bubble(f"🌟 รีบอร์น! ดาว ×{pet.rebirths} (+{bonus * pet.rebirths}% พลัง)", pet)
        self.spawn_effect(pet.x, pet.top_y(), "🌟")
        self._save_progress()

    # -------------------------------------------------- เหรียญ / รางวัลรายวัน
    def add_coins(self, amount):
        self.coins = max(0, self.coins + int(amount))

    # -------------------------------------------- ความจุไข่/น้อง (ขยายได้ด้วยเงิน)
    def _egg_cap(self):
        return config.EGG_SLOTS_BASE + self.egg_slot_buys * config.EGG_SLOT_STEP

    def _egg_slot_cost(self):
        return int(config.EGG_SLOT_BASE_COST
                   * (config.EGG_SLOT_COST_GROWTH ** self.egg_slot_buys))

    def _buy_egg_slot(self):
        if self.egg_slot_buys >= config.EGG_SLOT_MAX_BUYS:
            self.show_bubble("ขยายช่องไข่สูงสุดแล้ว!")
            return
        cost = self._egg_slot_cost()
        if self.coins < cost:
            self.show_bubble(f"เหรียญไม่พอ! ต้องมี {cost} 🪙")
            sound.play("hurt")
            return
        self.coins -= cost
        self.egg_slot_buys += 1
        sound.play("eat")
        self.show_bubble(f"ขยายช่องไข่ +{config.EGG_SLOT_STEP} → {self._egg_cap()} ฟอง 🥚")
        self._save_progress()

    def _pet_cap(self):
        return min(config.PET_SLOTS_MAX, config.PET_SLOTS_BASE + self.pet_slot_buys)

    def _pet_slot_cost(self):
        return int(config.PET_SLOT_BASE_COST
                   * (config.PET_SLOT_COST_GROWTH ** self.pet_slot_buys))

    def _buy_pet_slot(self):
        if self._pet_cap() >= config.PET_SLOTS_MAX:
            self.show_bubble("ขยายช่องน้องบนจอสูงสุดแล้ว! (10 ตัว)")
            return
        cost = self._pet_slot_cost()
        if self.coins < cost:
            self.show_bubble(f"เหรียญไม่พอ! ต้องมี {cost} 🪙")
            sound.play("hurt")
            return
        self.coins -= cost
        self.pet_slot_buys += 1
        sound.play("eat")
        self.show_bubble(f"ขยายช่องน้องบนจอ → {self._pet_cap()} ตัว 🐾")
        self._save_progress()

    def _egg_icon(self):
        """PhotoImage รูปไข่ (โหลดครั้งเดียว แคชไว้) — None ถ้าไม่มีไฟล์ assets/egg.*"""
        if getattr(self, "_egg_img", "?") == "?":
            self._egg_img = None
            try:
                anim = assets.load_asset_sprite(config.EGG_SPRITE)
                if anim:
                    self._egg_img = anim.frame(0)
            except Exception:
                self._egg_img = None
        return self._egg_img

    @staticmethod
    def _rarity_of(obj):
        """rarity dict ของไข่ (dict) หรือเพ็ท (มี .rarity)"""
        rid = obj.get("rarity") if isinstance(obj, dict) else getattr(obj, "rarity", "common")
        return config.rarity_by_id(rid)

    @staticmethod
    def _roll_rarity():
        total = sum(r["weight"] for r in config.RARITIES)
        x = random.uniform(0, total)
        acc = 0
        for r in config.RARITIES:
            acc += r["weight"]
            if x <= acc:
                return r["id"]
        return config.RARITIES[0]["id"]

    @staticmethod
    def _weighted_character(rarity_filter=None):
        """สุ่มตัวละคร 1 ตัวจากที่อัปโหลด โดยถ่วงน้ำหนักตาม 'ระดับของตัวละคร'
        (ระดับสูง = น้ำหนักน้อย = สุ่มเจอยาก) — rarity_filter=set จำกัดเฉพาะระดับที่ระบุ
        คืนชื่อตัวละคร หรือ None (ใช้ assets เริ่มต้น) ถ้าไม่มีตัวที่เข้าเงื่อนไข"""
        pool, weights = [], []
        for c in assets.list_characters():
            rid = assets.character_rarity(c)
            if rarity_filter and rid not in rarity_filter:
                continue
            pool.append(c)
            weights.append(config.rarity_by_id(rid)["weight"])
        if not pool:
            return None
        return random.choices(pool, weights=weights, k=1)[0]

    @staticmethod
    def _trait_of(pet):
        return next((t for t in config.TRAITS if t["id"] == pet.trait), None)

    @staticmethod
    def _skill_of(pet):
        return config.skill_by_id(pet.skill)

    @staticmethod
    def _gender_of(pet):
        return next((g for g in config.GENDERS if g["id"] == pet.gender),
                    config.GENDERS[0])

    @staticmethod
    def _skill_val(pet, key, default=0):
        """อ่านค่าพารามิเตอร์ของสกิลติดตัว (เช่น atk_mult, poison) — default ถ้าไม่มี"""
        s = config.skill_by_id(pet.skill) or {}
        return s.get(key, default)

    @staticmethod
    def _self_val(pet, key, default=0):
        """ค่าสกิลที่ผลกับ 'ตัวเอง' เท่านั้น (target=self) — ของ target=all ไปรวมใน _team_buffs"""
        s = config.skill_by_id(pet.skill) or {}
        if s.get("target", "self") != "self":
            return default
        return s.get(key, default)

    @staticmethod
    def _team_buffs(fighters):
        """รวมบัฟที่ส่งผลทั้งทีม (สกิล target=all) จากน้องที่ร่วมสู้"""
        atk_mult, dmg_reduce, regen = 1.0, 0.0, 0
        for p in fighters:
            s = config.skill_by_id(p.skill) or {}
            if s.get("target") != "all":
                continue
            atk_mult *= s.get("atk_mult", 1.0)
            dmg_reduce = max(dmg_reduce, s.get("dmg_reduce", 0.0))
            regen += s.get("regen", 0)
        return {"atk_mult": atk_mult, "dmg_reduce": dmg_reduce, "regen": regen}

    def _apply_trait(self, pet):
        """ตั้งค่าผลของนิสัยประจำตัวลงบนน้อง (โจมตี/ลดสเตตัส/ความเร็ว/กิน)"""
        t = self._trait_of(pet) or {}
        pet.atk_mult = t.get("atk", 1.0)
        pet.decay_mult = t.get("decay", 1.0)
        pet.trait_speed = t.get("speed", 0.0)
        pet.feed_happy = t.get("feed_happy", 0)

    # ----------------------------------------------- ความสำเร็จ (Achievement)
    def _inc_lifetime(self, key, n=1):
        """เพิ่มตัวนับสะสมตลอดชีพ (feeds/kills/bosses/games) แล้วตรวจความสำเร็จ"""
        self.lifetime[key] = self.lifetime.get(key, 0) + n
        self._check_achievements()

    def _achievement_value(self, metric):
        if metric in ("feeds", "kills", "bosses", "games"):
            return self.lifetime.get(metric, 0)
        if metric == "level":
            return max((p.level for p in self.pets), default=0)
        if metric == "affection":
            return max((p.affection for p in self.pets), default=0)
        if metric == "streak":
            return self.login_streak
        return 0

    def _check_achievements(self):
        """ปลดล็อกความสำเร็จที่ถึงเป้า + ให้เหรียญรางวัลครั้งเดียวอัตโนมัติ"""
        for a in config.ACHIEVEMENTS:
            if a["id"] in self.achievements:
                continue
            if self._achievement_value(a["metric"]) >= a["goal"]:
                self.achievements.append(a["id"])
                self.add_coins(a["reward"])
                self.show_bubble(f"🏆 {a['name']}! +{a['reward']} 🪙")
                self.spawn_effect(self.pet.x, self.pet.top_y(), "🏆")

    @staticmethod
    def _today():
        return datetime.date.today().isoformat()

    # ------------------------------------------------------ เช็คอินรายวัน
    def _can_checkin(self):
        return self.last_login != self._today()

    def _checkin_reward(self, streak):
        return min(config.DAILY_REWARD_MAX,
                   config.DAILY_REWARD_BASE + (streak - 1) * config.DAILY_REWARD_PER_DAY)

    def _claim_checkin(self):
        """รับรางวัลเช็คอินของวันนี้ (คืน reward ที่ได้ หรือ 0 ถ้ารับไปแล้ว)"""
        if not self._can_checkin():
            return 0
        today = datetime.date.today()
        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        self.login_streak = self.login_streak + 1 if self.last_login == yesterday else 1
        self.last_login = today.isoformat()
        reward = self._checkin_reward(self.login_streak)
        self.add_coins(reward)
        self._save_progress()
        sound.play("levelup")
        self.spawn_effect(self.pet.x, self.pet.top_y(), "🎁")
        return reward

    # ---------------------------------------------------- เควสรายวัน
    def _reset_quests_if_new_day(self):
        if self.quest_date != self._today():
            self.quest_date = self._today()
            self.quest_progress = {q["id"]: 0 for q in config.DAILY_QUESTS}
            self.quest_claimed = []

    # -------------------------------------------------------------- อายุ/ช่วงวัย
    def _age_days(self, pet=None):
        """อายุน้องเป็นจำนวนวัน (นับจาก birth_date) — ค่าเริ่มต้น = ตัวที่กำลังดูแล"""
        pet = pet or self.pet
        try:
            b = datetime.date.fromisoformat(pet.birth_date)
            return max(0, (datetime.date.today() - b).days)
        except (ValueError, TypeError):
            return 0

    def _age_stage(self):
        """คืน dict ช่วงวัยสูงสุดที่ถึงตามอายุปัจจุบัน"""
        days = self._age_days()
        stage = config.AGE_STAGES[0]
        for s in config.AGE_STAGES:
            if days >= s["day"]:
                stage = s
        return stage

    def _check_birthday(self):
        """ฉลอง + ให้โบนัสเมื่อขึ้นวันใหม่ (น้องอายุเพิ่มอีกวัน) — วันละครั้ง"""
        if not self.pets:
            return
        today = self._today()
        if getattr(self, "_last_birthday", "") == today:
            return
        first_ever = not self._last_birthday
        self._last_birthday = today
        if first_ever:
            return                                   # วันแรกที่เริ่มเลี้ยง ไม่ต้องฉลอง
        self.add_coins(config.AGE_BIRTHDAY_BONUS)
        self.show_bubble(f"🎂 น้องอายุ {self._age_days()} วันแล้ว! +{config.AGE_BIRTHDAY_BONUS} 🪙")
        self.spawn_effect(self.pet.x, self.pet.top_y(), "🎂")

    def _quest_advance(self, qid, n=1):
        """เพิ่มความคืบหน้าเควส (เรียกตอนให้อาหาร/ล้มมอน/ล้มบอส)"""
        self._reset_quests_if_new_day()
        if qid in self.quest_progress:
            self.quest_progress[qid] += n

    def _quest_done(self, q):
        return self.quest_progress.get(q["id"], 0) >= q["goal"]

    def _quest_claimable(self, q):
        return self._quest_done(q) and q["id"] not in self.quest_claimed

    def _any_quest_claimable(self):
        self._reset_quests_if_new_day()
        return any(self._quest_claimable(q) for q in config.DAILY_QUESTS)

    def _claim_quest(self, q):
        if self._quest_claimable(q):
            self.quest_claimed.append(q["id"])
            self.add_coins(q["reward"])
            self._save_progress()
            sound.play("levelup")
            return True
        return False

    def show_status(self):
        p = self.pet
        # ปิด topmost ชั่วคราวเพื่อให้กล่องข้อความแสดงทับเพ็ทได้
        self.root.wm_attributes("-topmost", False)
        messagebox.showinfo(
            "สถานะของเพ็ท",
            f"เวฟ: {self.wave_round}  (มอนตัวที่ {self.wave_step}/{config.WAVE_LENGTH})\n"
            f"เลเวล: {p.level}\n"
            f"XP: {p.xp} / {p.xp_to_next()}\n"
            f"HP: {int(p.hp)} / {p.max_hp()}\n"
            f"พลังโจมตี: {p.attack()}\n"
            f"ความอิ่ม: {int(p.fullness)} / 100\n"
            f"ความสุข: {int(p.happy)} / 100\n"
            f"พลังงาน: {int(p.energy)} / 100\n"
            f"ความสะอาด: {int(p.cleanliness)} / 100\n"
            f"สายสัมพันธ์: {int(p.affection)} / 100\n"
            f"ช่วงวัย: {self._age_stage()['name']} (อายุ {self._age_days()} วัน)\n"
            f"อาการ: {'ป่วย 🤒' if p.sick else 'ปกติ'}",
        )
        self.root.wm_attributes("-topmost", True)

    def _apply_offline_decay(self, last_save):
        """หักสเตตัสตามเวลาที่โปรแกรมปิดไป (offline progression) มีเพดานกันลงโทษหนัก
        เก็บจำนวนวินาทีที่หายไปไว้ใน self._offline_secs เพื่อทักทายตอนเปิด"""
        self._offline_secs = 0.0
        try:
            last = float(last_save or 0)
        except (TypeError, ValueError):
            return
        if last <= 0:
            return
        secs = time.time() - last
        secs = max(0.0, min(secs, config.OFFLINE_MAX_HOURS * 3600))
        if secs < 60:
            return
        for p in self.pets:                              # หักสเตตัสทุกตัว
            p.fullness = _clamp(p.fullness - config.FULLNESS_DECAY * secs)
            p.happy = _clamp(p.happy - config.HAPPY_DECAY * secs)
            p.energy = _clamp(p.energy - config.ENERGY_DECAY * secs)
            p.cleanliness = _clamp(p.cleanliness - config.CLEANLINESS_DECAY * secs)
        self._offline_secs = secs

    def _load_progress(self):
        data = save.load()
        self._is_new_game = not data          # เซฟว่าง = เริ่มเกมใหม่ครั้งแรก (แจกไข่ฟรี)
        self._last_birthday = str(data.get("last_birthday", ""))
        # ช่องไข่/ช่องน้องที่ซื้อขยายไว้ (ต้องโหลดก่อนสร้างน้อง/ไข่ เพราะใช้คำนวณความจุ)
        self.egg_slot_buys = max(0, min(int(data.get("egg_slot_buys", 0)),
                                        config.EGG_SLOT_MAX_BUYS))
        self.pet_slot_buys = max(0, int(data.get("pet_slot_buys", 0)))
        # สร้างน้องจากลิสต์ (เซฟใหม่) หรือย้ายข้อมูลเซฟเก่า (ตัวเดียว) มาเป็นตัวแรก
        pets_data = data.get("pets")
        if not pets_data and not self._is_new_game:
            # เซฟเก่ารูปแบบตัวเดียว → ย้ายมาเป็นน้องตัวแรก (เกมใหม่จะไม่เข้าเงื่อนไขนี้ = เริ่ม 0 ตัว)
            legacy_char = data.get("character")
            if legacy_char not in assets.list_characters():
                legacy_char = None
            pets_data = [{
                "character": legacy_char,
                "level": data.get("level", 1), "xp": data.get("xp", 0),
                "hp": data.get("hp"), "fullness": data.get("fullness", 80),
                "happy": data.get("happy", 80), "energy": data.get("energy", 80),
                "cleanliness": data.get("cleanliness", 80),
                "affection": data.get("affection", 0), "sick": data.get("sick", False),
                "tricks_taught": data.get("tricks_taught", []),
                "birth_date": data.get("birth_date", ""),
            }]
        self.pets = []
        for pd in (pets_data or [])[:config.PET_SLOTS_MAX]:
            self.pets.append(self._build_pet(pd.get("character"), pd))
        # เกมใหม่ = เริ่ม 0 ตัว (ต้องฟักไข่เอาน้องตัวแรก) — ไม่สร้างน้องเริ่มต้นให้แล้ว
        self.active = max(0, min(int(data.get("active", 0)), max(0, len(self.pets) - 1)))
        # เวลาเดินต่อตอนปิดโปรแกรม: หักสเตตัสตามเวลาที่หายไป (มีเพดาน)
        self._apply_offline_decay(data.get("last_save", 0))
        self.wave_round = max(1, int(data.get("wave_round", 1)))
        self.wave_step = min(config.WAVE_LENGTH, max(1, int(data.get("wave_step", 1))))
        # เกมใหม่เริ่มโดยปิดต่อสู้ (น้องจะได้ไม่ออโต้สู้ขึ้นเลเวลเอง) — กดเปิด ⚔ เองภายหลัง
        self.combat_enabled = bool(data.get("combat_enabled", not self._is_new_game))
        self.sound_on = bool(data.get("sound_on", True))
        sound.set_enabled(self.sound_on)
        # เศรษฐกิจ/รายวัน
        self.coins = max(0, int(data.get("coins", 0)))
        self.last_login = str(data.get("last_login", ""))
        self.login_streak = max(0, int(data.get("login_streak", 0)))
        # เควสรายวัน
        self.quest_date = str(data.get("quest_date", ""))
        prog = data.get("quest_progress", {})
        self.quest_progress = {q["id"]: int(prog.get(q["id"], 0)) for q in config.DAILY_QUESTS}
        self.quest_claimed = list(data.get("quest_claimed", []))
        self._reset_quests_if_new_day()
        # เกม/ของสะสม/ความสำเร็จ/ทริค
        lt = data.get("lifetime", {}) or {}
        self.lifetime = {k: int(lt.get(k, 0)) for k in ("feeds", "kills", "bosses", "games")}
        eggs = data.get("eggs", []) or []        # ไข่ในรัง (ฟักตามเวลาจริง)
        _egg_max = config.EGG_SLOTS_BASE + config.EGG_SLOT_MAX_BUYS * config.EGG_SLOT_STEP
        self.eggs = [e for e in eggs if isinstance(e, dict)][:_egg_max]
        stored = data.get("stored", []) or []    # น้องที่เก็บเข้ากล่อง (พักไว้ ไม่ลดสเตตัส)
        self.stored = [s for s in stored if isinstance(s, dict)][:config.MAX_STORED]
        inv = data.get("inventory", {}) or {}
        valid_items = {it["id"] for it in config.SHOP_ITEMS}
        self.inventory = {k: int(v) for k, v in inv.items()
                          if k in valid_items and int(v) > 0}
        self.achievements = list(data.get("achievements", []))
        self.game_date = str(data.get("game_date", ""))
        self.games_today = max(0, int(data.get("games_today", 0)))
        # ตำแหน่งเมนู (ลากย้ายได้)
        self.hud_offset_x = float(data.get("hud_offset_x", 0))
        self.hud_offset_y = float(data.get("hud_offset_y", 0))
        # 🎁 เริ่มเกมใหม่ → ไม่มีน้อง มีแค่ไข่ฟรี 1 ใบ "ระดับปกติเสมอ" (ฟักได้ทันที)
        if self._is_new_game and not self.eggs and not self.pets:
            # ไข่เริ่มต้น = สุ่มตัวละครระดับ "ปกติ" เท่านั้น (ระดับสูงต้องไปดรอปจากบอส)
            start_char = self._weighted_character(rarity_filter={"common"})
            self._make_egg(start_char, rarity="common")
            if self.eggs:
                self.eggs[0]["hatch_at"] = time.time()     # พร้อมฟักเลย
            self._save_progress()
            # เปิด popup "ได้ไข่" แบบบังคับ — ออกไม่ได้จนกว่าจะกดฟัก
            self.root.after(500, lambda: self._show_hatch_window(forced=True))

    def _save_progress(self):
        self._check_achievements()      # ปลดล็อก achievement ที่ถึงเป้าจาก level/affection/streak
        save.save({
            "version": config.SAVE_VERSION,
            "last_save": time.time(),
            "pets": [self._pet_to_data(p) for p in self.pets],
            "active": self.active,
            "last_birthday": getattr(self, "_last_birthday", ""),
            "wave_round": self.wave_round,
            "wave_step": self.wave_step,
            "combat_enabled": self.combat_enabled,
            "sound_on": self.sound_on,
            "coins": self.coins,
            "last_login": self.last_login,
            "login_streak": self.login_streak,
            "quest_date": self.quest_date,
            "quest_progress": self.quest_progress,
            "quest_claimed": self.quest_claimed,
            "lifetime": self.lifetime,
            "eggs": self.eggs,
            "stored": self.stored,
            "egg_slot_buys": self.egg_slot_buys,
            "pet_slot_buys": self.pet_slot_buys,
            "inventory": self.inventory,
            "achievements": self.achievements,
            "game_date": self.game_date,
            "games_today": self.games_today,
            "hud_offset_x": round(self.hud_offset_x, 1),
            "hud_offset_y": round(self.hud_offset_y, 1),
        })

    # ------------------------------------------------------------------ loops
    def run(self):
        self._tick()
        self._anim()
        # ทักทายถ้าเพิ่งกลับมาหลังปิดโปรแกรมไปนาน (offline progression)
        if getattr(self, "_offline_secs", 0) >= 300:
            mins = int(self._offline_secs // 60)
            away = f"{mins // 60} ชม." if mins >= 60 else f"{mins} นาที"
            self.root.after(700, lambda: self.show_bubble(f"กลับมาแล้ว! หายไป {away} 🐾"))
        self.root.mainloop()

    @staticmethod
    def _entity_frame_ms(ent):
        """หน่วงเฟรม (ms) ของสถานะปัจจุบันของ ent — รายสถานะถ้าตั้งไว้ ไม่งั้นค่าเริ่มต้น"""
        ms = getattr(ent, "anim_ms", {}).get(ent.state) if hasattr(ent, "anim_ms") else None
        return ms if ms else config.ANIM_MS

    def _anim(self):
        step = config.ANIM_STEP_MS
        for ent in self._entities():
            # ท่าโจมตีตอนสู้: combat คุมเฟรมเอง (ซิงก์กับจังหวะโจมตี) — _anim ไม่ต้องเลื่อน
            if getattr(ent, "behavior", None) == "fight" and ent.state == "attack":
                continue
            ms = self._entity_frame_ms(ent)
            ent._anim_accum = getattr(ent, "_anim_accum", 0) + step
            if ent._anim_accum < ms:           # ยังไม่ถึงเวลาเปลี่ยนเฟรม
                continue
            ent._anim_accum = 0
            if getattr(ent, "behavior", None) == "dead":
                # น้องตาย: เล่นจนถึง "เฟรมสุดท้าย" (สภาพตาย) แล้วค้างไว้ ไม่วนลูป
                last = len(ent.current_anim().frames) - 1
                if ent.frame_i < last:
                    ent.advance_frame()
                elif ent.frame_i != last:
                    ent.frame_i = last
                    ent._render()
            else:
                ent.advance_frame()
        self.root.after(step, self._anim)

    def _tick(self):
        self.tick_count += 1
        # ทุก ~0.5 วิ: ซ่อน/แสดงเพ็ทตามว่ามีโปรแกรมอื่นเปิดเต็มจออยู่หรือไม่
        if self.tick_count % max(1, int(500 / config.TICK_MS)) == 0:
            self._update_fullscreen_visibility()
        if self.tick_count % max(1, int(1000 / config.TICK_MS)) == 0:
            for p in self.pets:
                if not self._is_away(p) and p.behavior != "dead":  # ผจญภัย/ตาย = ไม่ลดสเตตัส
                    self._decay_stats(p)
            self._auto_feed()                  # หิวแล้วมีอาหารในกระเป๋า → กินเอง
            self._check_hunger()
            self._check_birthday()
            self._social_play()
            self._notify_eggs_ready()          # ไข่ครบเวลา = เด้งเตือนให้ไปกดฟักเอง
            self._check_adventures()
            self._tick_spawn_monster()
        if self.tick_count % max(1, int(1000 / config.TICK_MS) * 20) == 0:
            self._save_progress()   # เซฟอัตโนมัติทุก ~20 วินาที

        if self.monster is not None:
            self._update_combat()              # น้องทุกตัวรุมสู้ใน _update_combat
        for p in self.pets:
            if self._is_away(p):               # ออกผจญภัยอยู่ → ซ่อน ไม่อัปเดต
                continue
            if p.behavior == "fight":
                continue                       # จัดการใน _update_combat แล้ว
            if p.behavior == "dead":
                self._update_dead(p)
            elif p.behavior == "act":
                self._update_action(p)
            elif p.behavior == "eating":
                self._update_eating(p)
            elif p.behavior == "sleep":
                self._update_sleep(p)
            elif p.behavior == "stay":
                self._update_stay(p)
            elif p.behavior == "drag":
                pass  # ตำแหน่งถูกคุมโดยเมาส์
            else:
                self._update_wander(p)
            p.sync_position()

        self._draw_auras()
        self._draw_mood_face()
        self._draw_stat_bars()
        self._update_effects()
        self._update_bubble()
        self._draw_hud()
        self._draw_monster_hud()
        self._draw_combat_extras()
        self.root.after(config.TICK_MS, self._tick)

    # --------------------------------------------------------------- behaviors
    def _decay_stats(self, pet):
        """ลดสเตตัสตามเวลา (เรียกทุก ~1 วินาที ต่อน้อง 1 ตัว): อิ่ม/สุข/พลังงาน/สะอาด/น้ำ
        พร้อมจัดการระบบป่วยและสายสัมพันธ์ (affection)"""
        p = pet
        # affection สูงช่วยให้สเตตัสลดช้าลง (รางวัลของการเลี้ยงดี) + นิสัยประจำตัว
        relief = (1.0 - config.AFFECTION_DECAY_RELIEF * (p.affection / 100.0)) * p.decay_mult
        happy_mult = config.SICK_HAPPY_DECAY_MULT if p.sick else 1.0
        energy_mult = config.NIGHT_ENERGY_MULT if self._is_night() else 1.0

        p.fullness = max(0, p.fullness - config.FULLNESS_DECAY * relief)
        p.happy = max(0, p.happy - config.HAPPY_DECAY * relief * happy_mult)
        p.cleanliness = max(0, p.cleanliness - config.CLEANLINESS_DECAY * relief)
        if p.behavior != "sleep":                        # ตอนหลับพลังงานฟื้น (ใน _update_sleep)
            p.energy = max(0, p.energy - config.ENERGY_DECAY * relief * energy_mult)

        if p.fullness <= 0:                              # หิวจัดเลือดลด
            p.hp -= 1
        if p.sick:                                       # ป่วยก็เสียเลือดช้า ๆ
            p.hp -= config.SICK_HP_DRAIN
        if p.hp <= 0:                                    # เลือดหมด = เสียชีวิต
            self._kill_pet(p)
            return

        # ป่วยเมื่อถูกละเลย (สกปรกมาก/หิวจัด) — เว้นตอนป่วยอยู่แล้ว/สลบ
        neglected = (p.cleanliness < config.DIRTY_THRESHOLD or p.fullness <= 5)
        if not p.sick and p.behavior != "dead" and neglected:
            if random.random() < config.SICK_CHANCE:
                p.sick = True
                self.show_bubble("ไม่สบาย... 🤒", p)
                self.spawn_effect(p.x, p.top_y(), "🤒")
        # หายป่วยเองถ้าดูแลดี (อิ่ม+สะอาดสูง)
        elif p.sick and p.fullness > 60 and p.cleanliness > 60:
            if random.random() < config.SICK_RECOVER_CHANCE:
                p.sick = False
                self.show_bubble("หายป่วยแล้ว! 💪", p)

        # สายสัมพันธ์: โตเมื่อดูแลครบ, ลดเมื่อป่วย/หิวจัด
        well = (p.fullness > 50 and p.happy > 50 and p.cleanliness > 50
                and p.energy > 30 and not p.sick)
        if well:
            p.affection = min(100, p.affection + config.AFFECTION_GAIN)
        elif p.sick or p.fullness <= 0:
            p.affection = max(0, p.affection - config.AFFECTION_LOSS)

        # หมดแรงสุด ๆ (หรือกลางคืน+ง่วง) → งีบเอง (ถ้าไม่ติดสู้/ลาก/สลบ/กินอยู่)
        if (p.energy <= 0 and p.behavior in ("wander", "stay")
                and self.monster is None and p.food is None):
            self._start_sleep(p, auto=True)

    def _social_play(self):
        """น้องที่อยู่ใกล้กัน = เล่นด้วยกัน → สุข/สายสัมพันธ์เพิ่มทั้งคู่"""
        if len(self.pets) < 2:
            return
        for i, a in enumerate(self.pets):
            if a.behavior in ("dead", "drag") or self._is_away(a):
                continue
            for b in self.pets[i + 1:]:
                if b.behavior in ("dead", "drag") or self._is_away(b):
                    continue
                if abs(a.x - b.x) <= config.SOCIAL_RANGE:
                    for q in (a, b):
                        q.happy = min(100, q.happy + config.SOCIAL_HAPPY)
                        q.affection = min(100, q.affection + config.SOCIAL_AFFECTION)
                    if self.tick_count % 90 == 0:
                        self.spawn_effect((a.x + b.x) / 2, min(a.top_y(), b.top_y()), "❤")

    def _combat_target(self):
        """น้องที่มอนสเตอร์จะเล่นงาน = ตัวที่ยังไม่สลบ/ไม่ผจญภัย ใกล้มอนที่สุด"""
        alive = [p for p in self.pets if p.behavior != "dead" and not self._is_away(p)]
        if not alive:
            return None
        return min(alive, key=lambda p: abs(p.x - self.monster.x))

    def _speed(self, pet):
        # หิวจัด/ง่วง/ป่วย เดินช้าลง + โบนัสรองเท้า/นิสัย/ฝึกฝน
        s = (config.WALK_SPEED + pet.trait_speed
             + pet.train["speed"] * config.TRAIN_SPEED_STEP)
        if pet.fullness < 20:
            s *= 0.5
        if pet.energy < config.SLEEPY_THRESHOLD:
            s *= 0.6
        if pet.sick:
            s *= 0.6
        return s

    def _walk_toward(self, pet, target_x, speed):
        d = target_x - pet.x
        reached = abs(d) <= speed
        if reached:
            pet.x = target_x
        else:
            pet.x += _sign(d) * speed
            pet.set_state("walk")
            pet.face(d)
        self._drop_to_ground(pet)
        return reached

    def _update_wander(self, pet):
        pet.wtimer -= 1
        if pet.wtimer <= 0:
            if random.random() < 0.3:
                pet.vx = 0.0
                pet.wtimer = random.randint(20, 50)
            else:
                pet.vx = random.choice([-1, 1]) * self._speed(pet)
                pet.wtimer = random.randint(40, 120)

        pet.x += pet.vx
        half = pet.current_anim().w / 2
        if pet.x < half:
            pet.x = half
            pet.vx = abs(pet.vx)
        elif pet.x > self.sw - half:
            pet.x = self.sw - half
            pet.vx = -abs(pet.vx)
        self._drop_to_ground(pet)
        pet.set_state("walk" if pet.vx != 0 else "idle")
        pet.face(pet.vx)

    def _update_stay(self, pet):
        """ยืนอยู่กับที่ ไม่เดินไปไหน แต่หันซ้าย-ขวาเป็นระยะ ๆ"""
        pet.set_state("idle")
        self._drop_to_ground(pet)
        pet.stay_timer -= 1
        if pet.stay_timer <= 0:
            pet.face(-pet.facing)                      # หันกลับด้าน
            pet.stay_timer = random.randint(40, 110)

    def _start_action(self, pet, state, frames):
        """เล่นอนิเมชันสั้น ๆ (อาบน้ำ/ลูบหัว) แล้วกลับไปเดินเล่นเอง"""
        if pet.behavior in ("dead", "fight", "drag", "sleep", "eating"):
            return
        pet.behavior = "act"
        pet.act_state = state
        pet.act_timer = frames
        pet.vx = 0.0
        pet.set_state(state)

    def _update_action(self, pet):
        """กำลังเล่นอนิเมชันแอ็กชันชั่วคราว (อาบน้ำ 🛁 / ลูบหัว ✋)"""
        pet.set_state(pet.act_state)
        self._drop_to_ground(pet)
        pet.act_timer -= 1
        if pet.act_timer <= 0:
            pet.behavior = "wander"

    def _update_sleep(self, pet):
        """หลับอยู่กับที่: ฟื้นพลังงานเรื่อย ๆ มีฟอง 💤 เป็นระยะ ตื่นเองเมื่อเต็ม"""
        pet.set_state("sleep")                         # ท่านอน (ไม่มี → ใช้สำรอง idle)
        self._drop_to_ground(pet)
        pet.energy = min(100, pet.energy + config.ENERGY_RESTORE)
        self._flash_bar(pet, "energy", ttl=8)          # โชว์หลอดพลังงานต่อเนื่องระหว่างหลับ
        if self.tick_count % 30 == 0:                  # ~ทุก 1 วินาที
            self.spawn_effect(pet.x, pet.top_y(), "💤")
        if pet.energy >= 100 and not self._is_night():  # กลางคืนหลับยาว
            self._wake(pet)

    def _update_eating(self, pet):
        """กินอยู่กับที่ — เล่นอนิเมชัน eat จากไฟล์ (ไม่มีก้อนอาหารวาดขึ้น)"""
        pet.set_state("eat")
        self._drop_to_ground(pet)
        if pet.eat_timer is None:
            pet.eat_timer = 40
        pet.eat_timer -= 1
        if pet.eat_timer <= 0:
            ftype = pet.food_type
            gain = config.FOOD_FULLNESS
            happy = 12
            aff = config.AFFECTION_PER_FEED
            if ftype and ftype in pet.likes:                # ของโปรด
                happy += config.FOOD_LIKE_HAPPY_BONUS
                aff += config.FOOD_LIKE_AFFECTION_BONUS
                self.show_bubble("อร่อยที่สุด! 😍", pet)
            elif ftype and ftype in pet.dislikes:           # ของไม่ชอบ
                gain *= config.FOOD_DISLIKE_FULLNESS_MULT
                happy -= config.FOOD_DISLIKE_HAPPY
                self.show_bubble("ไม่ค่อยชอบเลย... 😖", pet)
            else:
                self.show_bubble("อร่อย! 🍽", pet)
            pet.fullness = min(100, pet.fullness + gain)
            pet.happy = min(100, max(0, pet.happy + happy + pet.feed_happy))
            pet.affection = min(100, pet.affection + aff)
            self._flash_bar(pet, "fullness")
            pet.food_type = None
            sound.play("eat")
            self.add_xp(config.XP_PER_FEED, pet)
            self.add_coins(config.COINS_PER_FEED)
            self._quest_advance("feed")
            self._inc_lifetime("feeds")
            pet.eat_timer = None
            pet.behavior = "wander"
            pet.vx = 0

    def _update_combat(self):
        """น้องทุกตัว (behavior='fight') รุมสู้มอนสเตอร์ตัวเดียว มอนตีตัวที่ใกล้สุด"""
        m = self.monster
        if m is None:
            return
        fighters = [p for p in self.pets if p.behavior == "fight"]
        if not fighters:                             # ไม่มีใครสู้แล้ว
            return

        team = self._team_buffs(fighters)            # บัฟทั้งทีม (สกิล target=all)
        sec = (self.tick_count % self._sec_ticks == 0)   # จังหวะ "ต่อวินาที" (โชว์ DoT/ฮีล)

        # ── สถานะต่อเนื่องของน้อง (โชว์เลขต่อวินาที): ไฟไหม้ 🔥 + ฮีล 💚 ──
        for p in fighters:
            if p.burn_ttl > 0:
                p.burn_ttl -= 1
                if sec:
                    p.hp -= config.BURN_DMG
                    self.spawn_status_text(p, f"-{config.BURN_DMG}",
                                           config.STATUS_COLORS["fire"])
            if sec:
                regen_pct = self._self_val(p, "regen", 0) + team["regen"]   # 💚 ฟื้นฟู/ทีม
                if regen_pct and p.hp < p.max_hp():
                    heal = max(1, int(p.max_hp() * regen_pct / 100.0))
                    p.hp = min(p.max_hp(), p.hp + heal)
                    self.spawn_status_text(p, f"+{heal}",
                                           config.STATUS_COLORS["heal"])

        # ── พิษติดมอน ☠ (ลดเลือด + โชว์เลขต่อวินาที) ──
        if m.poison_ttl > 0:
            m.poison_ttl -= 1
            if sec:
                m.hp -= m.poison_dmg
                self.spawn_status_text(m, f"-{m.poison_dmg}",
                                       config.STATUS_COLORS["poison"])
                if m.hp <= 0:
                    self._combat_win(m, fighters)
                    return

        # ── มอนสเตอร์: เล่นงานตัวที่ใกล้ที่สุด (ถ้าไม่โดนสตัน/แช่แข็ง) ──
        tgt = min(fighters, key=lambda p: abs(p.x - m.x))
        if m.stun_ttl > 0:                           # โดนท่าไม้ตาย/แช่แข็ง → นิ่ง
            m.stun_ttl -= 1
            m.set_state("hurt")
        else:
            m.attack_cd = max(0, m.attack_cd - 1)
            m.set_state("walk")
            m.face(tgt.x - m.x)
            if abs(tgt.x - m.x) > config.ATTACK_RANGE:
                m.x += _sign(tgt.x - m.x) * config.MONSTER_SPEED
            elif m.attack_cd == 0:
                if random.random() * 100 < tgt.dodge_chance():   # น้องหลบได้!
                    self.spawn_effect(tgt.x, tgt.top_y(), "หลบ✨")
                else:
                    # ลดดาเมจ: เกราะตัวเอง 🛡 หรือ ปราการทั้งทีม 🔵 (เอาค่ามากสุด)
                    reduce = max(self._self_val(tgt, "dmg_reduce", 0.0),
                                 team["dmg_reduce"])
                    dmg = max(1, int(m.atk * (1.0 - reduce)))
                    tgt.hp -= dmg
                    tgt.set_state("hurt")
                    tgt.happy = max(0, tgt.happy - 3)
                    rg = config.RAGE_ON_HURT * self._skill_val(tgt, "rage_mult", 1.0)
                    tgt.rage = min(config.RAGE_MAX, tgt.rage + rg)
                    self.spawn_effect(tgt.x, tgt.top_y(), f"-{dmg}")
                    sound.play("hurt")
                    if m.is_boss and tgt.burn_ttl <= 0 \
                            and random.random() < config.BURN_CHANCE_BOSS:
                        tgt.burn_ttl = config.BURN_SECONDS * self._sec_ticks  # บอสจุดไฟ!
                        self.spawn_status_text(tgt, "🔥", config.STATUS_COLORS["fire"])
                m.attack_cd = config.ATTACK_COOLDOWN
        self._drop_to_ground(m)
        m.sync_position()

        # ── น้องทุกตัววิ่งเข้าหา + โจมตี ──
        # ท่าโจมตีเล่นพอดีจังหวะ: 3 เฟรมเฉลี่ยตลอด cooldown, ดาเมจลงตอน "เฟรมกลาง" (ปล่อยหมัด)
        cool = config.ATTACK_COOLDOWN
        for p in fighters:
            p.attack_cd = max(0, p.attack_cd - 1)
            if abs(p.x - m.x) > config.ATTACK_RANGE:
                self._walk_toward(p, m.x, self._speed(p))
            else:
                p.face(m.x - p.x)
                if p.attack_cd <= 0:                  # เริ่มสวิงรอบใหม่
                    p.attack_cd = cool
                    p._atk_hit = False
                p.set_state("attack")
                a = p.current_anim()
                nf = max(1, len(a.frames))
                prog = 1.0 - max(0, p.attack_cd) / cool      # 0..1 ตลอดสวิง
                fi = min(nf - 1, int(prog * nf))
                if fi != p.frame_i:
                    p.frame_i = fi
                    p._render()
                hit_frame = nf // 2                  # 3 เฟรม → เฟรมที่ 2 (index 1) = ปล่อยหมัด
                if not getattr(p, "_atk_hit", False) and fi >= hit_frame:
                    self._pet_hit_monster(p, m, team["atk_mult"])
                    p._atk_hit = True
            p.sync_position()

        if m.hp <= 0:                                # ชนะ! (ทั้งทีมได้ XP)
            self._combat_win(m, fighters)
            return

        # ── เกจเดือดเต็ม → ปล่อยท่าไม้ตายเอง (ไม่ต้องกด) ──
        for p in fighters:
            if self.monster is not None and p.behavior == "fight" \
                    and p.rage >= config.RAGE_MAX:
                self._fire_ultimate(p)
        if self.monster is None:                     # ท่าไม้ตายปิดเกมไปแล้ว
            return

        # ── ใครเลือดหมด = เสียชีวิต (ต้องใช้ใบชุบ) ตัวอื่นสู้ต่อ ──
        for p in fighters:
            if p.hp <= 0:
                self._kill_pet(p)
        # ทั้งทีมตาย → มอนหนีไป + กลับเวฟ 1
        if not any(p.behavior == "fight" for p in self.pets):
            self.wave_round = 1
            self.wave_step = 1
            self.show_bubble("ทีมแพ้... 💀 ต้องชุบน้องด้วยใบชุบ 📜", self.pet)
            m.destroy()
            self.monster = None
            self._save_progress()

    def _pet_hit_monster(self, p, m, team_atk=1.0):
        """น้อง 1 ตัวฟันมอน 1 ครั้ง — รวมคริ + สกิลติดตัว (โจมตี/ดีบัฟ) + บัฟทีม + ดูดเลือด + เกจ"""
        atk_mult = self._self_val(p, "atk_mult", 1.0) * team_atk   # ⚔ ตัวเอง × 📣 ทีม
        dmg = int(p.attack() * atk_mult)
        crit_chance = p.crit_chance() + self._skill_val(p, "crit_add")  # 🎯 แม่นปืน
        crit = random.random() * 100 < crit_chance
        if crit:
            dmg = int(dmg * config.CRIT_MULT)
        m.hp -= dmg
        p.set_state("attack")
        rg = config.RAGE_ON_HIT * self._skill_val(p, "rage_mult", 1.0)   # 🔥 เดือดดาล
        p.rage = min(config.RAGE_MAX, p.rage + rg)
        self.spawn_effect(m.x, m.top_y(), f"💥-{dmg}" if crit else f"-{dmg}")
        # 🗡 ดาบคู่: มีโอกาสตีเพิ่มอีกครั้ง
        if random.random() < self._skill_val(p, "double"):
            d2 = int(p.attack() * atk_mult)
            m.hp -= d2
            self.spawn_effect(m.x + 12, m.top_y() - 8, f"-{d2}")
        # ── ดีบัฟติดมอน ──
        poison = self._skill_val(p, "poison")          # ☠ พิษ (ดาเมจต่อวินาที)
        if poison:
            m.poison_ttl = config.POISON_SECONDS * self._sec_ticks
            m.poison_dmg = max(m.poison_dmg, poison)
        if random.random() < self._skill_val(p, "freeze_chance"):   # ❄ เยือกแข็ง
            m.stun_ttl = max(m.stun_ttl, int(self._skill_val(p, "freeze", 0)))
            self.spawn_status_text(m, "❄", config.STATUS_COLORS["ice"])
        # ── ดูดเลือด (บิลด์ 🩸) ──
        ls = p.lifesteal_pct()
        if ls > 0 and p.hp < p.max_hp():
            total = dmg
            p.hp = min(p.max_hp(), p.hp + max(1, int(total * ls / 100.0)))
        sound.play("attack")

    def _kill_pet(self, pet):
        """น้องเสียชีวิต — ต้องใช้ใบชุบเท่านั้นถึงฟื้น (ไม่ฟื้นเอง)"""
        pet.hp = 0
        pet.behavior = "dead"
        pet.vx = 0
        pet.rage = 0
        pet.burn_ttl = 0
        pet.set_state("dead")
        pet.happy = max(0, pet.happy - 25)
        self.show_bubble("เสียชีวิต... 💀", pet)
        self.spawn_effect(pet.x, pet.top_y(), "💀")

    def _fire_ultimate(self, pet):
        """ปล่อยท่าไม้ตาย — ดาเมจหนักใส่มอน + สตันมอน (ใช้ได้เมื่อเกจเดือดเต็มและกำลังสู้)"""
        m = self.monster
        if m is None or pet.behavior != "fight" or pet.rage < config.RAGE_MAX:
            return
        pet.rage = 0
        dmg = pet.ult_damage()
        m.hp -= dmg
        m.stun_ttl = max(m.stun_ttl, config.ULT_STUN_TICKS)
        pet.set_state("attack")
        self.show_bubble("ท่าไม้ตาย! 💥⚡", pet)
        self.spawn_effect(m.x, m.top_y(), f"⚡-{dmg}")
        self.spawn_effect(m.x, m.top_y() - 18, "💫")
        sound.play("attack")
        if m.hp <= 0:
            self._combat_win(m, [p for p in self.pets if p.behavior == "fight"])

    def _combat_win(self, m, fighters):
        was_boss = m.is_boss
        self.spawn_effect(m.x, m.top_y(), "✨")
        sound.play("win")
        m.destroy()
        self.monster = None
        for p in fighters:                           # น้องทุกตัวที่สู้กลับมาเดิน + ดีใจ + ได้ XP
            p.behavior = "wander"
            p.vx = 0
            p.happy = min(100, p.happy + 20)
            p.burn_ttl = 0                            # ดับไฟหลังจบศึก (เกจเดือดเก็บไว้)
        lead = fighters[0]
        if was_boss:
            self.wave_round += 1
            self.wave_step = 1
            self.show_bubble(f"🏆 ผ่านบอส! ขึ้นเวฟ {self.wave_round}", lead)
            self.spawn_effect(lead.x, lead.top_y(), "🎉")
            for p in fighters:
                self.add_xp(config.XP_PER_WIN * config.BOSS_XP_MULT, p)
            self.add_coins(config.COINS_PER_BOSS)
            self._quest_advance("boss")
            self._inc_lifetime("bosses")
        else:
            self.wave_step += 1
            self.show_bubble(f"ชนะ! ({self.wave_step}/{config.WAVE_LENGTH}) 🎉", lead)
            for p in fighters:
                self.add_xp(config.XP_PER_WIN, p)
            self.add_coins(config.COINS_PER_WIN)
        self._quest_advance("kill")
        self._inc_lifetime("kills")
        drop = config.EGG_DROP_CHANCE_BOSS if was_boss else config.EGG_DROP_CHANCE_MONSTER
        if len(self.eggs) < self._egg_cap() and random.random() < drop:
            # บอส = ดรอปได้ทุกระดับ (ระดับสูงยิ่งยาก) / มอนปกติ = แค่ปกติ-หายาก
            char = (self._weighted_character() if was_boss
                    else self._weighted_character(rarity_filter={"common", "rare"}))
            self._make_egg(char)
            rar = assets.character_rarity(char) if char else "common"
            rname = config.rarity_by_id(rar)["name"]
            self.show_bubble(f"🥚 ได้ไข่ระดับ {rname}!", lead)
            self.spawn_effect(lead.x, lead.top_y(), "🥚")
        self._save_progress()

    def _update_dead(self, pet):
        """น้องที่เสียชีวิต — นอนอยู่กับที่ ไม่ฟื้นเอง (ต้องใช้ใบชุบ 📜 เท่านั้น)"""
        pet.set_state("dead")
        self._drop_to_ground(pet)

    # สี/ค่าสูงสุดของหลอดสถานะลอย (เมื่อกำลังทำกิจกรรมกับสเตตัสนั้น)
    _STAT_BAR = {
        "fullness":    ("🍖", "#f39c12"),
        "happy":       ("💗", "#e84393"),
        "energy":      ("⚡", "#9b59b6"),
        "cleanliness": ("🛁", "#1abc9c"),
    }

    def _flash_bar(self, pet, stat, ttl=90):
        """สั่งให้หลอดสเตตัส stat ลอยเหนือหัวน้องชั่วคราว (เห็นค่าทันทีว่าเต็มหรือยัง)"""
        pet.bar_stat = stat
        pet.bar_ttl = ttl

    def _draw_stat_bars(self):
        """วาดหลอดสเตตัสลอยเหนือหัวน้องที่กำลังทำกิจกรรม (นับถอยหลังแล้วหาย)"""
        self.canvas.delete("statbar")
        for pet in self.pets:
            if self._is_away(pet) or getattr(pet, "bar_ttl", 0) <= 0:
                continue
            pet.bar_ttl -= 1
            info = self._STAT_BAR.get(pet.bar_stat)
            if not info:
                continue
            emoji, color = info
            val = max(0.0, min(100.0, getattr(pet, pet.bar_stat, 0)))
            full = val >= 99
            bw, bh = 46, 7
            cx = pet.x
            y0 = pet.top_y() - 18
            x0 = cx - bw / 2
            self.canvas.create_rectangle(x0 - 1, y0 - 1, x0 + bw + 1, y0 + bh + 1,
                                         fill="#1e1e1e", outline="#000000", tags="statbar")
            self.canvas.create_rectangle(x0, y0, x0 + bw * (val / 100.0), y0 + bh,
                                         fill="#2ecc71" if full else color,
                                         outline="", tags="statbar")
            self.canvas.create_text(x0 - 6, y0 + bh / 2, anchor="e", text=emoji,
                                    font=("Segoe UI Emoji", 9), tags="statbar")
            if full:
                self.canvas.create_text(x0 + bw + 5, y0 + bh / 2, anchor="w", text="เต็ม",
                                        fill="#2ecc71", font=("Segoe UI", 8, "bold"),
                                        tags="statbar")

    def _draw_auras(self):
        """ออร่าวงรีที่เท้าน้องตามชนิดสกิลบัฟ: แดง=โจมตี ฟ้า=ป้องกัน เขียว=ฮีล
        แสดงเฉพาะ 'ตอนต่อสู้' (มีมอน + น้องกำลังสู้) เท่านั้น"""
        self.canvas.delete("aura")
        if self.monster is None:                 # ไม่ได้สู้ = ไม่โชว์บัฟ
            return
        for pet in self.pets:
            if pet.behavior != "fight" or self._is_away(pet):
                continue
            s = config.skill_by_id(pet.skill) or {}
            col = config.AURA_COLORS.get(s.get("aura"))
            if not col:
                continue
            a = pet.current_anim()
            cy = pet.y + a.h * 0.42                  # ระดับเท้า
            rx = max(15, a.w * 0.44)
            ry = max(5, a.w * 0.16)
            oid = self.canvas.create_oval(pet.x - rx, cy - ry, pet.x + rx, cy + ry,
                                          fill=col, outline=col, stipple="gray25",
                                          tags="aura")
            try:
                self.canvas.tag_lower(oid, pet.item)   # อยู่ใต้ตัวน้อง
            except Exception:
                pass

    def _pet_emotes(self, pet):
        """คืนรายการอิโมจิอารมณ์/อาการที่ต้องโชว์เหนือหัว (มีหลายอาการ = วนสลับ)"""
        p = pet
        if p.behavior == "dead":
            return ["💀"]
        out = []
        if p.burn_ttl > 0:
            out.append("🔥")              # ไฟไหม้ (จากบอส)
        if p.behavior == "sleep":
            out.append("😴")
        if p.sick:
            out.append("🤒")
        if p.fullness < config.HUNGRY_THRESHOLD:
            out.append("🍖")              # หิว
        if p.energy < config.SLEEPY_THRESHOLD and p.behavior != "sleep":
            out.append("🥱")              # ง่วง/หมดแรง
        if p.cleanliness < config.DIRTY_THRESHOLD:
            out.append("🛁")              # สกปรก
        if p.happy < 30:
            out.append("😢")              # เหงา
        return out                        # ไม่มีอาการ = ไม่โชว์ (คืนลิสต์ว่าง)

    def _draw_mood_face(self):
        """โชว์อารมณ์/อาการของน้องเป็นอิโมจิลอยเหนือหัว — ถ้ามีหลายอาการจะวนสลับเรื่อย ๆ"""
        self.canvas.delete("face")
        cycle = self.tick_count // 45        # เปลี่ยนอาการทุก ~1.5 วินาที
        for pet in self.pets:
            if pet.behavior == "drag" or self._is_away(pet):
                continue
            emotes = self._pet_emotes(pet)
            if not emotes:                   # ปกติดี ไม่มีอาการ → ไม่โชว์ emote
                continue
            emoji = emotes[cycle % len(emotes)]
            a = pet.current_anim()
            fs = max(13, int(a.h * 0.22))
            cx = pet.x + a.w * 0.36
            cy = pet.top_y() - fs * 0.2
            txt = self.canvas.create_text(cx, cy, text=emoji,
                                          font=("Segoe UI Emoji", fs), tags="face")
            # พื้นหลังสีขาวหลังอิโมจิ
            bb = self.canvas.bbox(txt)
            if bb:
                pad = 3
                bg = self.canvas.create_oval(bb[0] - pad, bb[1] - pad,
                                             bb[2] + pad, bb[3] + pad,
                                             fill="white", outline="#cccccc",
                                             tags="face")
                self.canvas.tag_lower(bg, txt)

    # --------------------------------------------------------- effects & ui
    # ทิศขอบดำรอบตัวอักษร (halo) ให้อ่านชัดบนทุกพื้นหลังเดสก์ท็อป
    _HALO = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

    def _floating_text(self, x, y, text, fill, size, ttl, dy, anchor="center"):
        """สร้างตัวอักษรลอยพร้อมขอบดำ (วาดสำเนาดำรอบ ๆ แล้วทับด้วยสีจริง) ให้คมชัด"""
        items = []
        font = ("Segoe UI Emoji", size, "bold")
        for ox, oy in self._HALO:                  # ขอบดำ
            items.append(self.canvas.create_text(x + ox, y + oy, text=text,
                                                 anchor=anchor, fill="#000000",
                                                 font=font))
        items.append(self.canvas.create_text(x, y, text=text, anchor=anchor,
                                             fill=fill, font=font))   # ตัวจริงทับบน
        self.effects.append({"items": items, "ttl": ttl, "dy": dy})

    def spawn_effect(self, x, y, text):
        """ตัวเลขดาเมจ/อิโมจิลอยกลางตัว (ขาวคมมีขอบดำ)"""
        self._floating_text(x, y - 6, text, "#ffffff", 17, 16, -1.4)

    def spawn_status_text(self, entity, text, color):
        """ตัวเลขสถานะเล็ก ๆ มีสี+ขอบดำ ลอยขึ้นที่ 'ด้านขวา' ของตัว (ฮีล/พิษ/ไฟ/น้ำแข็ง)"""
        a = entity.current_anim()
        x = entity.x + a.w * 0.5 + 6
        y = entity.y - a.h * 0.1
        self._floating_text(x, y, text, color, 12, 22, -0.9, anchor="w")

    def _update_effects(self):
        for fx in self.effects[:]:
            fx["ttl"] -= 1
            items = fx.get("items") or [fx.get("item")]
            for it in items:
                self.canvas.move(it, 0, fx["dy"])
            if fx["ttl"] <= 0:
                for it in items:
                    self.canvas.delete(it)
                self.effects.remove(fx)

    def show_bubble(self, text, pet=None):
        pet = pet or self.pet
        for it in self.bubble_items:
            self.canvas.delete(it)
        self.bubble_items = []
        if pet is None:                       # ยังไม่มีน้อง (เกมใหม่ก่อนฟัก) → เด้งกลางบนจอ
            x = (-self.vx0 + self.primary_w / 2)
            y = 80
        else:
            x = pet.x
            y = pet.top_y() - 34
        txt = self.canvas.create_text(x, y, text=text, font=("Segoe UI Emoji", 12, "bold"),
                                      fill="#222222")
        x0, y0, x1, y1 = self.canvas.bbox(txt)
        pad = 6
        rect = self.canvas.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad,
                                            fill="white", outline="#888888")
        self.canvas.tag_lower(rect, txt)
        self.bubble_items = [rect, txt]
        self.bubble_ttl = 55

    def _update_bubble(self):
        if not self.bubble_items:
            return
        self.bubble_ttl -= 1
        if self.bubble_ttl <= 0:
            for it in self.bubble_items:
                self.canvas.delete(it)
            self.bubble_items = []
            return
        # ให้บับเบิลลอยตามหัวเพ็ท (ถ้าไม่มีน้อง = อยู่กับที่)
        if self.pet is None:
            return
        rect, txt = self.bubble_items
        x = self.pet.x
        y = self.pet.top_y() - 34
        self.canvas.coords(txt, x, y)
        x0, y0, x1, y1 = self.canvas.bbox(txt)
        pad = 6
        self.canvas.coords(rect, x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def _close_all_menus(self):
        """ปิดเมนู/ป๊อปอัปทุกอันในคอลัมน์ขวา (ใช้ก่อนเปิดอันใหม่ — เปิดได้ทีละอัน)"""
        self._close_checkin_window()
        self._close_quest_window()
        self._close_shop_window()
        self._close_settings_popup()
        self._close_settings_window()
        self._close_char_popup()
        self._close_feature_window()

    def _toggle_combat(self, e):
        """⚔/🛡 สลับโหมดต่อสู้ ↔ เลี้ยงอย่างเดียว"""
        if not self.pets and not self.combat_enabled:    # ไม่มีน้อง = เปิดต่อสู้ไม่ได้
            self.show_bubble("ต้องมีน้องก่อนถึงต่อสู้ได้ — ฟักไข่ 🥚")
            return "break"
        self._close_all_menus()
        self.combat_enabled = not self.combat_enabled
        if not self.combat_enabled and self.monster is not None:
            self.monster.destroy()          # ปิดต่อสู้ = เอามอนสเตอร์ออกทันที
            self.monster = None
            if self.pet and self.pet.behavior != "dead":
                self.pet.behavior = "wander"
                self.pet.vx = 0
        self.show_bubble("⚔ พร้อมแล้ว!" if self.combat_enabled else "😴 พักผ่อน")
        self._save_progress()
        self._draw_hud()
        return "break"

    def _menu_click(self, action):
        """กดปุ่มเมนูซ้าย — สั่งงานแล้ววาดใหม่ทันที"""
        sound.play("click")
        action()
        self._draw_hud()
        return "break"

    def _on_settings_click(self, e):
        """กดปุ่ม ⚙ = เปิดป๊อปอัปตั้งค่ากลางจอ"""
        self._close_all_menus()
        self._show_settings_popup()
        return "break"

    def _close_settings_popup(self):
        w = getattr(self, "_settings_win", None)
        self._settings_win = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _settings_choose(self, cmd):
        self._close_settings_popup()
        cmd()

    # ------------------------------------------------------ เปิดเองตอนเปิดเครื่อง
    def _autorun_lnk(self):
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                            "Programs", "Startup", "MyDesktopPet.lnk")

    def _is_autorun_enabled(self):
        return os.path.exists(self._autorun_lnk())

    def _set_autorun(self, on):
        """สร้าง/ลบ ทางลัดใน Startup เพื่อเปิดโปรแกรมเองตอนเปิดเครื่อง"""
        lnk = self._autorun_lnk()
        if on:
            if getattr(sys, "frozen", False):     # เป็น .exe แล้ว
                target, args, workdir = sys.executable, "", os.path.dirname(sys.executable)
            else:                                 # ยังรันเป็นสคริปต์ -> ใช้ตัวเรียก .vbs
                vbs = paths.resource_path("start_pet.vbs")
                target, args, workdir = "wscript.exe", f'"{vbs}"', paths.resource_path()
            ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
                  "$s.TargetPath='%s';$s.Arguments='%s';$s.WorkingDirectory='%s';$s.Save()"
                  % (lnk, target, args.replace("'", "''"), workdir))
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                                 creationflags=0x08000000)
            except Exception:
                pass
        else:
            try:
                os.remove(lnk)
            except OSError:
                pass

    # ------------------------------------------------------------- หน้าตั้งค่า
    def _close_settings_window(self):
        w = getattr(self, "_settings_window", None)
        self._settings_window = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _show_settings_window(self):
        """หน้าต่างตั้งค่า: เสียง / ความเร็วอนิเมชัน / เปิดเองตอนเปิดเครื่อง"""
        self._close_all_menus()
        BG, FG, SUB = "#1e1e1e", "#ffffff", "#bbbbbb"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")
        self._settings_window = win
        self._bind_autoclose(win, self._close_settings_window)
        fr = tk.Frame(win, bg=BG, padx=18, pady=16)
        fr.pack(padx=2, pady=2)
        tk.Label(fr, text="⚙  ตั้งค่า", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 12))

        # 🔊 เสียง
        snd = tk.BooleanVar(value=self.sound_on)

        def on_snd():
            self.sound_on = snd.get()
            sound.set_enabled(self.sound_on)
            self._save_progress()
            if self.sound_on:
                sound.play("click")
        tk.Checkbutton(fr, text="  🔊  เปิดเสียง", variable=snd, command=on_snd,
                       bg=BG, fg=FG, selectcolor="#2c3e50", activebackground=BG,
                       activeforeground=FG, font=("Segoe UI", 12), anchor="w",
                       bd=0, highlightthickness=0, cursor="hand2").pack(fill="x", pady=3)

        # 🏃 ความเร็วอนิเมชัน (เฟรม/วินาที)
        tk.Label(fr, text="🏃  ความเร็วอนิเมชัน (เฟรม/วิ)", bg=BG, fg=SUB,
                 font=("Segoe UI", 11), anchor="w").pack(fill="x", pady=(10, 0))
        spd = tk.Scale(fr, from_=2, to=20, orient="horizontal", bg=BG, fg=FG,
                       troughcolor="#2c3e50", highlightthickness=0, bd=0,
                       length=220, font=("Segoe UI", 9))
        spd.set(max(2, min(20, round(1000 / max(1, config.ANIM_MS)))))

        def on_spd(v):
            config.ANIM_MS = int(1000 / max(2, int(float(v))))
        spd.config(command=on_spd)
        spd.pack(fill="x")

        # 🚀 เปิดเองตอนเปิดเครื่อง
        auto = tk.BooleanVar(value=self._is_autorun_enabled())

        def on_auto():
            self._set_autorun(auto.get())
            sound.play("click")
        tk.Checkbutton(fr, text="  🚀  เปิดเองตอนเปิดเครื่อง", variable=auto,
                       command=on_auto, bg=BG, fg=FG, selectcolor="#2c3e50",
                       activebackground=BG, activeforeground=FG, font=("Segoe UI", 12),
                       anchor="w", bd=0, highlightthickness=0,
                       cursor="hand2").pack(fill="x", pady=3)

        tk.Button(fr, text="ปิด", command=self._close_settings_window, bg="#2c3e50",
                  fg=FG, activebackground="#34495e", activeforeground=FG, bd=0,
                  font=("Segoe UI", 11, "bold"), cursor="hand2",
                  padx=20, pady=4).pack(pady=(14, 0))

        self._center_popup(win)

    def _cursor_monitor_rect(self):
        """คืนกรอบจอ (left, top, right, bottom) ของจอที่เคอร์เซอร์อยู่ตอนนี้
        คืนจอหลักถ้าหาไม่ได้ (เช่นไม่ใช่ Windows)"""
        try:
            user32 = ctypes.windll.user32
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            hmon = user32.MonitorFromPoint(pt, 2)        # MONITOR_DEFAULTTONEAREST
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi)):
                r = mi.rcMonitor
                return (r.left, r.top, r.right, r.bottom)
        except Exception:
            pass
        return (0, 0, self.primary_w, self.primary_h)

    def _center_on_screen(self, win):
        """เด้งหน้าต่างกลาง 'จอที่เมาส์อยู่' — จัดซ้ำหลังวาดจริงกันเฟรมแรกเพี้ยน"""
        def place():
            if not win.winfo_exists():
                return
            win.update_idletasks()
            w, h = win.winfo_reqwidth(), win.winfo_reqheight()
            left, top, right, bottom = self._cursor_monitor_rect()
            x = left + max(0, (right - left - w) // 2)
            y = top + max(0, (bottom - top - h) // 2)
            win.geometry(f"+{int(x)}+{int(y)}")
        place()
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
        win.after(30, place)         # จัดกลางอีกครั้งหลังหน้าต่าง map เสร็จ (ขนาดนิ่งแล้ว)

    # ทุกหน้าต่างเด้งกลางจอ (ไม่อิงตำแหน่งปุ่ม/ตัวน้องอีก เพื่อความแน่นอน)
    def _center_popup(self, win):
        self._center_on_screen(win)

    def _place_feature_window(self, win):
        self._center_on_screen(win)

    def _place_window_beside(self, win, rect=None):
        self._center_on_screen(win)

    # ---------------------------------------------------------------- ร้านค้า
    def _show_shop_window(self):
        """ร้านค้า: ซื้อของใช้ (ยา/ใบชุบ/อาหาร) → เก็บเข้ากระเป๋า แล้วค่อยกดใช้"""
        self._close_all_menus()
        BG, FG, SUB = "#1e1e1e", "#ffffff", "#bbbbbb"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")
        self._shop_window = win
        self._bind_autoclose(win, self._close_shop_window)
        fr = tk.Frame(win, bg=BG, padx=18, pady=16)
        fr.pack(padx=2, pady=2)
        title = tk.Label(fr, bg=BG, fg="#f1c40f", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w")
        msg = tk.Label(fr, bg=BG, fg=SUB, font=("Segoe UI", 10))
        msg.pack(anchor="w", pady=(0, 10))

        def refresh():
            title.config(text=f"🛒  ร้านค้า    🪙 {self.coins}")

        def buy(item):
            def do():
                if self.coins < item["price"]:
                    msg.config(text="เหรียญไม่พอ! สู้/ให้อาหารเพื่อเก็บเหรียญ", fg="#e74c3c")
                    sound.play("hurt")
                    return
                self.coins -= item["price"]
                self.inventory[item["id"]] = self.inventory.get(item["id"], 0) + 1
                self._save_progress()
                sound.play("eat")
                msg.config(text=f"ซื้อ {item['name']} → เก็บเข้ากระเป๋า 🎒 ({self.inventory[item['id']]})",
                           fg="#2ecc71")
                refresh()
                self._draw_hud()
            return do

        for item in config.SHOP_ITEMS:
            have = self.inventory.get(item["id"], 0)
            text = f"{item['emoji']}  {item['name']} ({item['desc']})"
            tk.Button(fr, text=f"{text}   {item['price']} 🪙", anchor="w", justify="left",
                      command=buy(item), bg="#2c3e50", fg=FG,
                      activebackground="#34495e", activeforeground=FG, bd=0,
                      font=("Segoe UI", 12), padx=12, pady=8, cursor="hand2",
                      width=28).pack(fill="x", anchor="w", pady=3)

        tk.Button(fr, text="ปิด", command=self._close_shop_window, bg="#3a3a3a",
                  fg=FG, activebackground="#4a4a4a", activeforeground=FG, bd=0,
                  font=("Segoe UI", 11, "bold"), cursor="hand2",
                  padx=20, pady=4).pack(pady=(12, 0))
        refresh()
        self._center_popup(win)

    # ---------------------------------------------------------------- กระเป๋า
    def _apply_revive(self, p):
        """ผลของการชุบชีวิต (ใช้ได้ทั้งจากใบชุบและจ่ายเหรียญตรง)"""
        p.hp = p.max_hp()
        p.behavior = "wander"
        p.vx = 0
        p.sick = False
        p.rage = 0
        p.burn_ttl = 0
        # ฟื้นค่าพื้นฐานกันตายซ้ำทันที
        p.fullness = max(p.fullness, 50)
        p.happy = max(p.happy, 40)
        self.spawn_effect(p.x, p.top_y(), "✨")

    @staticmethod
    def _revive_cost():
        it = next((x for x in config.SHOP_ITEMS if x["id"] == "revive"), None)
        return it["price"] if it else 20

    def _revive_pay(self, pet):
        """ชุบชีวิตด้วยการจ่ายเหรียญตรง (ไม่ต้องมีใบชุบ)"""
        if pet.behavior != "dead":
            return
        cost = self._revive_cost()
        if self.coins < cost:
            self.show_bubble(f"เหรียญไม่พอชุบ! ต้องมี {cost} 🪙", pet)
            sound.play("hurt")
            return
        self.coins -= cost
        self._apply_revive(pet)
        sound.play("levelup")
        self.show_bubble("ชุบชีวิตสำเร็จ! ✨", pet)
        self._save_progress()

    def _use_item(self, item_id):
        """ใช้ของจากกระเป๋ากับน้องที่กำลังดูแล (active) แล้วลดจำนวนลง 1"""
        if self.inventory.get(item_id, 0) <= 0:
            return False
        item = next((x for x in config.SHOP_ITEMS if x["id"] == item_id), None)
        if item is None:
            return False
        p = self.pet
        use = item["use"]
        if use == "feed":
            if not self.feed(item_id):       # อาหาร: สั่งให้กิน (feed แจ้งเหตุผลถ้าทำไม่ได้)
                return False
        elif use == "revive":
            if p.behavior != "dead":
                self.show_bubble("ยังไม่เสียชีวิต ไม่ต้องชุบ!", p)
                return False
            self._apply_revive(p)
        elif use == "cure":
            if not p.sick:
                self.show_bubble("น้องไม่ได้ป่วยนี่!", p)
                return False
            p.sick = False
        elif use == "heal":
            if p.hp >= p.max_hp():
                self.show_bubble("เลือดเต็มแล้ว!", p)
                return False
            p.hp = p.max_hp()
        else:
            return False
        self.inventory[item_id] -= 1
        if self.inventory[item_id] <= 0:
            del self.inventory[item_id]
        if use != "feed":                    # อาหารมีบับเบิล/เสียงตอนกินเสร็จอยู่แล้ว
            self.show_bubble(f"ใช้ {item['emoji']} แล้ว", p)
            sound.play("eat")
        self._save_progress()
        return True

    def _show_bag_window(self):
        _nm = (self.pet.name or "เพ็ท") if self.pet else "เพ็ท"
        win, fr = self._feature_popup(f"🎒  กระเป๋า — {_nm}")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        tab = getattr(self, "_bag_tab", "items")

        def reopen():
            self._draw_hud()
            self._show_bag_window()

        # ===== แถบแท็บด้านบน (เผื่อเพิ่มเมนูในอนาคต) =====
        tabs = [("items", "🧰 ของใช้"), ("eggs", f"🥚 ไข่ ({len(self.eggs)})")]
        bar = tk.Frame(fr, bg=BG)
        bar.pack(fill="x", pady=(4, 8))
        for key, label in tabs:
            active = (tab == key)

            def switch(k=key):
                self._bag_tab = k
                self._show_bag_window()
            b = tk.Button(bar, text=label, command=switch, bd=0, cursor="hand2",
                          fg="#ffffff" if active else SUB,
                          bg="#3a4150" if active else "#2c313a",
                          activebackground="#3a4150", font=("Segoe UI", 11, "bold"),
                          padx=14, pady=5)
            b.pack(side="left", padx=(0, 4))

        body = tk.Frame(fr, bg=BG)
        body.pack(fill="x")

        if tab == "items":
            # กระเป๋า = ดูของที่มีเท่านั้น (กดใช้ไม่ได้ — ใช้ผ่านเมนูน้อง 🎒)
            tk.Label(body, text="ดูของที่มี (ใช้ของได้จากเมนูน้อง 🎒)", bg=BG, fg="#777777",
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
            owned = [it for it in config.SHOP_ITEMS if self.inventory.get(it["id"], 0) > 0]
            if not owned:
                tk.Label(body, text="ว่างเปล่า — ซื้อที่ร้านค้า 🛒", bg=BG, fg=SUB,
                         font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 4))
            for it in owned:
                n = self.inventory.get(it["id"], 0)
                row = tk.Frame(body, bg=BG)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=f"{it['emoji']}  {it['name']} ({it['desc']})",
                         bg=BG, fg=FG, font=("Segoe UI", 11), anchor="w",
                         width=22).pack(side="left")
                tk.Label(row, text=f"×{n}", bg=BG, fg="#f1c40f",
                         font=("Segoe UI", 11, "bold")).pack(side="right")
        else:  # eggs (ดูอย่างเดียว — ฟัก/ขายไปทำที่เมนู 🐣 ฟักไข่)
            tk.Label(body, text=f"🥚 ไข่ ({len(self.eggs)}/{self._egg_cap()})", bg=BG,
                     fg=SUB, font=("Segoe UI", 9)).pack(anchor="w")
            if not self.eggs:
                tk.Label(body, text="ยังไม่มีไข่ — ผสมพันธุ์ 💕 หรือล้มบอส 🥚", bg=BG,
                         fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 4))
            icon = self._egg_icon()
            for egg in self.eggs:
                left = int(float(egg.get("hatch_at", 0)) - time.time())
                rar = self._rarity_of(egg)
                status = "พร้อมฟัก! 🐣" if left <= 0 else f"อีก {left // 60}:{left % 60:02d}"
                row = tk.Frame(body, bg=BG)
                row.pack(fill="x", anchor="w", pady=2)
                if icon is not None:
                    tk.Label(row, image=icon, bg=BG).pack(side="left")
                else:
                    tk.Label(row, text="🥚", bg=BG, font=("Segoe UI Emoji", 16)
                             ).pack(side="left")
                tk.Label(row, text=f" {'★' * rar['stars']} {rar['name']}",
                         bg=BG, fg=rar["color"], font=("Segoe UI", 10, "bold")).pack(side="left")
                tk.Label(row, text=f"  {status}", bg=BG,
                         fg="#2ecc71" if left <= 0 else FG,
                         font=("Segoe UI", 9)).pack(side="left")
            if self.eggs:
                self._feature_btn(body, "🐣  ไปฟักไข่ / ขายไข่", self._show_hatch_window,
                                  color="#2c7a51", font=("Segoe UI", 11, "bold")
                                  ).pack(fill="x", pady=(6, 0))

        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._place_window_beside(win, getattr(self, "_bag_canvas", None))

    def _close_shop_window(self):
        w = getattr(self, "_shop_window", None)
        self._shop_window = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------- เช็คอินรายวัน
    def _close_checkin_window(self):
        w = getattr(self, "_checkin_window", None)
        self._checkin_window = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _show_checkin_window(self):
        self._close_all_menus()
        BG, FG, SUB = "#1e1e1e", "#ffffff", "#bbbbbb"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")
        self._checkin_window = win
        self._bind_autoclose(win, self._close_checkin_window)
        fr = tk.Frame(win, bg=BG, padx=20, pady=18)
        fr.pack(padx=2, pady=2)
        tk.Label(fr, text="📅  เช็คอินรายวัน", bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        info = tk.Label(fr, bg=BG, fg=SUB, font=("Segoe UI", 10))
        info.pack(anchor="w", pady=(2, 12))

        def refresh_info():
            info.config(text=f"🔥 ติดต่อกัน {self.login_streak} วัน      🪙 {self.coins}")
        refresh_info()
        status = tk.Label(fr, bg=BG, fg=FG, font=("Segoe UI", 11))
        status.pack(pady=(0, 8))

        today = datetime.date.today()
        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        pred_streak = self.login_streak + 1 if self.last_login == yesterday else 1
        pred_reward = self._checkin_reward(pred_streak)

        btn = tk.Button(fr, bd=0, font=("Segoe UI", 12, "bold"), cursor="hand2",
                        padx=20, pady=8, fg=FG)

        def claim():
            r = self._claim_checkin()
            if r:
                self.show_bubble(f"🎁 เช็คอินวันที่ {self.login_streak}! +{r} 🪙")
                status.config(text=f"รับ +{r} 🪙 แล้ว! 🎉", fg="#2ecc71")
                btn.config(text="รับแล้ววันนี้ ✓", state="disabled",
                           bg="#3a3a3a", activebackground="#3a3a3a")
                refresh_info()
                self._draw_hud()

        if self._can_checkin():
            status.config(text=f"รางวัลวันนี้: +{pred_reward} 🪙", fg="#f1c40f")
            btn.config(text=f"รับรางวัล  (+{pred_reward} 🪙)", command=claim,
                       bg="#2c7a51", activebackground="#349a66")
        else:
            status.config(text="รับรางวัลของวันนี้แล้ว — พรุ่งนี้มาใหม่นะ!", fg=SUB)
            btn.config(text="รับแล้ววันนี้ ✓", state="disabled",
                       bg="#3a3a3a", activebackground="#3a3a3a")
        btn.pack()
        tk.Label(fr, text="ล็อกอินติดกันทุกวัน รางวัลยิ่งเยอะ (พลาดวัน = เริ่มใหม่)",
                 bg=BG, fg="#888", font=("Segoe UI", 9)).pack(pady=(10, 0))
        tk.Button(fr, text="ปิด", command=self._close_checkin_window, bg="#2c3e50",
                  fg=FG, activebackground="#34495e", bd=0, font=("Segoe UI", 11, "bold"),
                  cursor="hand2", padx=20, pady=4).pack(pady=(12, 0))
        self._center_popup(win)

    # --------------------------------------------------------------- เควสรายวัน
    def _close_quest_window(self):
        w = getattr(self, "_quest_window", None)
        self._quest_window = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def _show_quest_window(self):
        self._close_all_menus()
        self._reset_quests_if_new_day()
        BG, FG, SUB = "#1e1e1e", "#ffffff", "#bbbbbb"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")
        self._quest_window = win
        self._bind_autoclose(win, self._close_quest_window)
        fr = tk.Frame(win, bg=BG, padx=20, pady=18)
        fr.pack(padx=2, pady=2)
        tk.Label(fr, text="📋  เควสรายวัน", bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(fr, text=f"🪙 {self.coins}      (รีเซ็ตทุกวัน)", bg=BG, fg=SUB,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 10))

        def reopen():
            self._draw_hud()
            self._close_quest_window()
            self._show_quest_window()

        for q in config.DAILY_QUESTS:
            prog = min(self.quest_progress.get(q["id"], 0), q["goal"])
            done = self._quest_done(q)
            claimed = q["id"] in self.quest_claimed
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=f"{q['icon']}  {q['label']}   {prog}/{q['goal']}",
                     bg=BG, fg=FG if done else "#dddddd", font=("Segoe UI", 11),
                     anchor="w", width=20).pack(side="left")
            if claimed:
                tk.Label(row, text="✓ รับแล้ว", bg=BG, fg="#2ecc71",
                         font=("Segoe UI", 10, "bold")).pack(side="right")
            elif done:
                tk.Button(row, text=f"รับ +{q['reward']} 🪙",
                          command=lambda qq=q: (self._claim_quest(qq), reopen()),
                          bg="#2c7a51", fg=FG, activebackground="#349a66", bd=0,
                          font=("Segoe UI", 10, "bold"), cursor="hand2",
                          padx=10, pady=3).pack(side="right")
            else:
                tk.Label(row, text=f"+{q['reward']} 🪙", bg=BG, fg=SUB,
                         font=("Segoe UI", 10)).pack(side="right")

        tk.Button(fr, text="ปิด", command=self._close_quest_window, bg="#2c3e50",
                  fg=FG, activebackground="#34495e", bd=0, font=("Segoe UI", 11, "bold"),
                  cursor="hand2", padx=20, pady=4).pack(pady=(14, 0))
        self._center_popup(win)

    # ============================================ เกม/ของสะสม/ทริค/ความสำเร็จ
    def _feature_popup(self, title):
        """สร้าง Toplevel ธีมเข้มมาตรฐาน (ปิดอันเก่าก่อน) คืน (win, frame หลัก)"""
        self._close_all_menus()
        self._close_feature_window()
        BG = "#1e1e1e"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")
        self._feature_window = win
        fr = tk.Frame(win, bg=BG, padx=18, pady=16)
        fr.pack(padx=2, pady=2)
        tk.Label(fr, text=title, bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self._bind_autoclose(win, self._close_feature_window)
        return win, fr

    def _close_feature_window(self):
        w = getattr(self, "_feature_window", None)
        self._feature_window = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
        self._resume_menu_pet()

    def _bind_autoclose(self, win, closer):
        """ปิดหน้าต่างเองเมื่อเสียโฟกัส (คลิกที่อื่น/พื้นที่ว่างบนจอ)"""
        def on_focus_out(_e):
            win.after(120, lambda: self._autoclose_check(win, closer))
        win.bind("<FocusOut>", on_focus_out)

    def _autoclose_check(self, win, closer):
        try:
            if not win.winfo_exists():
                return
            foc = win.focus_displayof()          # widget ที่มีโฟกัสในแอป (None = ไปแอปอื่น/เดสก์ท็อป)
        except Exception:
            foc = None
        if foc is None or foc.winfo_toplevel() is not win:
            try:
                closer()
            except Exception:
                pass

    def _resume_menu_pet(self):
        """ปลดล็อกให้น้องที่ถูกพักไว้ตอนเปิดเมนู กลับมาเดินเล่นได้ (ถ้ายังพักอยู่)"""
        pet = getattr(self, "_menu_pet", None)
        self._menu_pet = None
        if pet is not None and pet in self.pets and pet.behavior == "stay":
            pet.behavior = "wander"
            pet.vx = 0.0

    def _pause_active_for_menu(self):
        """พักน้องที่กำลังดูแลให้ยืนนิ่งระหว่างเปิดหน้าต่างเมนูของตัวมัน (อาหาร/ตู้เสื้อผ้า/ทริค)"""
        pet = self.pet
        self._menu_pet = pet
        if pet.behavior == "wander":
            pet.behavior = "stay"
            pet.vx = 0.0
            pet.set_state("idle")
            pet.stay_timer = random.randint(40, 90)
        return pet

    # สีธีมการ์ดเมนูน้อง
    _PM_BORDER = "#3a3f4b"
    _PM_BG = "#23272e"
    _PM_CARD = "#2d333d"
    _PM_HOVER = "#3a4150"
    _PM_FG = "#ffffff"
    _PM_SUB = "#aab2bf"

    def _pet_menu_cell(self, parent, emoji, label, cmd, enabled=True):
        """สร้างช่องปุ่มในกริดเมนูน้อง (มี hover); enabled=False = หรี่ลง (ยังไม่ต้องใช้)"""
        CARD, HOVER, FG, SUB = self._PM_CARD, self._PM_HOVER, self._PM_FG, self._PM_SUB
        card = CARD if enabled else "#262a30"
        fg = FG if enabled else "#5d6470"
        sub = SUB if enabled else "#5d6470"
        cell = tk.Frame(parent, bg=card, cursor="hand2")
        ic = tk.Label(cell, text=emoji, bg=card, fg=fg, font=("Segoe UI Emoji", 18))
        ic.pack(padx=14, pady=(8, 0))
        lb = tk.Label(cell, text=label, bg=card, fg=sub, font=("Segoe UI", 9))
        lb.pack(pady=(0, 7))
        widgets = (cell, ic, lb)
        if enabled:
            for wdg in widgets:
                wdg.bind("<Enter>", lambda e, w=widgets: [x.configure(bg=HOVER) for x in w])
                wdg.bind("<Leave>", lambda e, w=widgets: [x.configure(bg=card) for x in w])
        for wdg in widgets:
            wdg.bind("<Button-1>", lambda e, c=cmd: c())
        return cell

    def _show_pet_menu(self, pet):
        """แตะที่น้อง → เด้งการ์ดเมนูดูแลเหนือหัวตัวนั้น (น้องหยุดนิ่งจนกว่าจะปิดเมนู)"""
        if pet not in self.pets:
            return
        self.active = self.pets.index(pet)
        self._close_all_menus()
        self._close_feature_window()
        BORDER, BG, CARD = self._PM_BORDER, self._PM_BG, self._PM_CARD
        HOVER, FG, SUB = self._PM_HOVER, self._PM_FG, self._PM_SUB
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg=BORDER)
        self._feature_window = win
        self._menu_pet = pet
        self._bind_autoclose(win, self._close_feature_window)
        if pet.behavior == "wander":            # หยุดน้องไว้ระหว่างเปิดเมนู
            pet.behavior = "stay"
            pet.vx = 0.0
            pet.set_state("idle")
            pet.stay_timer = random.randint(40, 90)

        outer = tk.Frame(win, bg=BG)
        outer.pack(padx=2, pady=2)

        # ===== หัวการ์ด: ชื่อ + เลเวล + อารมณ์ + ปุ่มปิด =====
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", padx=12, pady=(9, 2))
        mood_e, mood_t = self._pet_mood(pet)
        g = self._gender_of(pet)
        tk.Label(head, text=f"{mood_e} {pet.name or 'เพ็ท'}", bg=BG, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(head, text=g["emoji"], bg=BG, fg=g["color"],
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=(4, 0))
        tk.Label(head, text=f"Lv.{pet.level}", bg=BG, fg=SUB,
                 font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))
        close = tk.Label(head, text="✕", bg=BG, fg=SUB, cursor="hand2",
                         font=("Segoe UI", 12, "bold"))
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self._close_feature_window())
        close.bind("<Enter>", lambda e: close.configure(fg="#ff6b6b"))
        close.bind("<Leave>", lambda e: close.configure(fg=SUB))

        # ===== น้องเสียชีวิต: ชุบด้วยใบชุบ / จ่ายเหรียญตรง / ไปร้านค้า =====
        if pet.behavior == "dead":
            tk.Label(outer, text="💀 น้องเสียชีวิต...", bg=BG, fg="#ff8a8a",
                     font=("Segoe UI", 11, "bold")).pack(padx=14, pady=(2, 2))
            n_rev = self.inventory.get("revive", 0)
            cost = self._revive_cost()
            box = tk.Frame(outer, bg=BG)
            box.pack(padx=14, pady=(2, 12), fill="x")
            # 1) ชุบด้วยใบชุบที่มีในกระเป๋า (ถ้ามี)
            if n_rev > 0:
                tk.Button(box, text=f"📜  ใช้ใบชุบ  (×{n_rev})",
                          command=lambda: (self._use_item("revive"),
                                           self._close_feature_window()),
                          bg="#2c7a51", fg=FG, activebackground="#349a66", bd=0,
                          font=("Segoe UI", 12, "bold"), cursor="hand2",
                          padx=14, pady=7).pack(fill="x", pady=(0, 4))
            # 2) จ่ายเหรียญชุบเลย (ไม่ต้องมีใบชุบ)
            can_pay = self.coins >= cost
            tk.Button(box, text=f"🪙  จ่ายชุบเลย  ({cost})",
                      command=lambda: (self._revive_pay(pet),
                                       self._close_feature_window()),
                      bg="#b8860b" if can_pay else "#444444", fg=FG,
                      activebackground="#d4a017", bd=0,
                      font=("Segoe UI", 12, "bold"), cursor="hand2",
                      padx=14, pady=7).pack(fill="x", pady=(0, 4))
            # 3) ไปซื้อใบชุบที่ร้านค้า
            tk.Button(box, text="🛒  ไปซื้อที่ร้านค้า",
                      command=lambda: (self._close_feature_window(),
                                       self._show_shop_window()),
                      bg="#2c3e50", fg=FG, activebackground="#34495e", bd=0,
                      font=("Segoe UI", 11, "bold"), cursor="hand2",
                      padx=14, pady=6).pack(fill="x")
            tk.Label(outer, text=f"มี {self.coins} 🪙", bg=BG, fg=SUB,
                     font=("Segoe UI", 9)).pack(pady=(0, 8))
            self._place_window_at_pet(win, pet)
            return

        # ===== แถบสเตตัสย่อ (ดูปราดเดียว) =====
        chips = tk.Frame(outer, bg=BG)
        chips.pack(fill="x", padx=12, pady=(0, 6))
        for emoji, val, warn in (("🍖", pet.fullness, config.HUNGRY_THRESHOLD),
                                 ("💗", pet.happy, 25),
                                 ("⚡", pet.energy, config.SLEEPY_THRESHOLD),
                                 ("🛁", pet.cleanliness, config.DIRTY_THRESHOLD)):
            col = "#ff6b6b" if val < warn else SUB
            tk.Label(chips, text=f"{emoji}{int(val)}", bg=BG, fg=col,
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))

        # ===== กริดกิจกรรม (หรี่ลงถ้าหลอดเต็มแล้ว = ยังไม่ต้องทำ) =====
        def act(fn):
            return lambda: (fn(), self._close_feature_window())

        actions = [
            ("✋", "ลูบ", act(self.pet_react), True),
            ("🛁", "อาบน้ำ", act(self.bathe), pet.cleanliness < 99),
            ("😴", "นอน", act(self.sleep_toggle), True),
            ("🎓", "ทริค", self._show_tricks_window, True),
            ("💪", "ฝึก", self._show_train_window, True),
            ("🌟", "บิลด์" + (f" ({pet.sp})" if pet.sp > 0 else ""),
             self._show_build_window, True),
            ("✊", "เป่ายิงฉุบ", self._show_rps_window, True),
            ("📈", "สแตท", self._show_stat_window, True),
            ("📊", "สถานะ", self._show_pet_status, True),
        ]
        grid = tk.Frame(outer, bg=BG)
        grid.pack(padx=10, pady=(0, 6))
        cols = 4
        for i, (emoji, label, cmd, enabled) in enumerate(actions):
            self._pet_menu_cell(grid, emoji, label, cmd, enabled).grid(
                row=i // cols, column=i % cols, padx=4, pady=4, sticky="nsew")

        # ===== 🎒 ของใช้: อาหารที่ชอบ (อย่างเดียว) + ยา/ใบชุบ ที่มีในกระเป๋า =====
        tk.Frame(outer, bg="#3a3f4b", height=1).pack(fill="x", padx=12, pady=(2, 4))
        tk.Label(outer, text="🎒 ของใช้", bg=BG, fg=SUB,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14)
        usefr = tk.Frame(outer, bg=BG)
        usefr.pack(padx=10, pady=(2, 10))
        cell_list = []
        # อาหารที่ชอบ (เฉพาะของโปรด) — มีแล้วกดให้กิน / ไม่มีขึ้น ×0 ให้ไปซื้อ
        for ft in (f for f in config.FOOD_TYPES if f["id"] in pet.likes):
            n = self.inventory.get(ft["id"], 0)
            if n > 0:
                cmd = (lambda i=ft: (self._use_item(i["id"]),
                                     self._close_feature_window()))
            else:
                cmd = (lambda nm=ft["name"]:
                       self.show_bubble(f"ยังไม่มี{nm} — ซื้อที่ร้าน 🛒", pet))
            cell_list.append((ft["emoji"], f"{ft['name']}×{n} ❤", cmd, n > 0))
        # ของใช้อื่นที่มี (ยา/ยาเพิ่มเลือด/ใบชุบ)
        for it in config.SHOP_ITEMS:
            if it["use"] == "feed" or self.inventory.get(it["id"], 0) <= 0:
                continue
            n = self.inventory.get(it["id"], 0)
            cell_list.append((it["emoji"], f"{it['name']}×{n}",
                              (lambda i=it: (self._use_item(i["id"]),
                                             self._close_feature_window())), True))
        if not cell_list:
            tk.Label(usefr, text="ว่าง — ซื้อของที่ร้าน 🛒", bg=BG, fg=SUB,
                     font=("Segoe UI", 9)).pack(anchor="w")
        for j, (emoji, label, cmd, enabled) in enumerate(cell_list):
            self._pet_menu_cell(usefr, emoji, label, cmd, enabled).grid(
                row=j // cols, column=j % cols, padx=4, pady=4, sticky="nsew")
        self._place_window_at_pet(win, pet)

    def _show_pet_status(self):
        """เปิดหน้าต่างสถานะลอยเหนือหัวน้องตัวที่แตะ (ชื่อ/อารมณ์/อายุ + บาร์ครบ)"""
        p = self.pet
        win, fr = self._feature_popup(f"📊  {p.name or 'เพ็ท'}")
        self._pause_active_for_menu()
        BG, SUB = "#1e1e1e", "#bbbbbb"
        mood_emoji, mood_text = self._pet_mood(p)
        stage = self._age_stage()
        daynight = "🌙 กลางคืน" if self._is_night() else "☀ กลางวัน"
        tk.Label(fr, text=f"{mood_emoji} {mood_text} · Lv.{p.level}", bg=BG, fg="#ffffff",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(2, 0))
        tk.Label(fr, text=f"{stage['emoji']} {stage['name']} · {self._age_days()} วัน · {daynight}",
                 bg=BG, fg=SUB, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))

        # นิสัยประจำตัว
        tr = self._trait_of(p)
        if tr:
            tk.Label(fr, text=f"{tr['emoji']} นิสัย: {tr['name']} ({tr['desc']})",
                     bg=BG, fg="#c9a0ff", font=("Segoe UI", 9)).pack(anchor="w")

        # อาหารที่ชอบ/ไม่ชอบ ของตัวนี้ (รู้ว่าควรซื้ออะไร)
        def _emojis(ids):
            return " ".join(g["emoji"] for g in config.FOOD_TYPES if g["id"] in ids)
        if p.likes:
            tk.Label(fr, text=f"❤ ชอบ: {_emojis(p.likes)}", bg=BG, fg="#ff8ab0",
                     font=("Segoe UI", 9)).pack(anchor="w")
        if p.dislikes:
            tk.Label(fr, text=f"✖ ไม่ชอบ: {_emojis(p.dislikes)}", bg=BG, fg="#9aa0a6",
                     font=("Segoe UI", 9)).pack(anchor="w")
        if not p.likes and not p.dislikes:
            tk.Label(fr, text="🍽 กินได้ทุกอย่าง", bg=BG, fg=SUB,
                     font=("Segoe UI", 9)).pack(anchor="w")
        tk.Frame(fr, bg=BG, height=4).pack()

        rows = [
            ("HP", p.alive_ratio(), "#e74c3c", f"{int(p.hp)}/{p.max_hp()}"),
            ("อิ่ม", p.fullness / 100.0, "#f39c12", f"{int(p.fullness)}"),
            ("สุข", p.happy / 100.0, "#e84393", f"{int(p.happy)}"),
            ("พลัง", p.energy / 100.0, "#9b59b6", f"{int(p.energy)}"),
            ("สะอาด", p.cleanliness / 100.0, "#1abc9c", f"{int(p.cleanliness)}"),
            ("รัก", p.affection / 100.0, "#ff5e8a", f"{int(p.affection)}"),
            ("XP", p.xp_ratio(), "#3498db", f"{p.xp}/{p.xp_to_next()}"),
        ]
        cw, rh, bh = 236, 24, 15
        c = tk.Canvas(fr, width=cw, height=len(rows) * rh, bg=BG, highlightthickness=0)
        c.pack()
        bx, bw = 58, cw - 58 - 6
        for i, (label, ratio, color, text) in enumerate(rows):
            y = i * rh + (rh - bh) / 2
            c.create_text(6, y + bh / 2, anchor="w", text=label, fill="#dddddd",
                          font=("Segoe UI", 10))
            c.create_rectangle(bx, y, bx + bw, y + bh, fill="#3a3a3a", outline="")
            c.create_rectangle(bx, y, bx + bw * max(0, min(1, ratio)), y + bh,
                               fill=color, outline="")
            c.create_text(bx + bw / 2, y + bh / 2, text=text, fill="#ffffff",
                          font=("Segoe UI", 9, "bold"))
        btns = tk.Frame(fr, bg=BG)
        btns.pack(pady=(10, 0))
        self._feature_btn(btns, "ปิด", self._close_feature_window,
                          color="#3a3a3a").pack(side="left", padx=3)
        # ปุ่มตั้งชื่อ — มุมขวาบน แถวเดียวกับชื่อ (title ของ _feature_popup)
        rn = self._feature_btn(fr, "✏️ ตั้งชื่อ", self._show_rename_window,
                               color="#2c3e50")
        rn.place(relx=1.0, x=-2, y=0, anchor="ne")
        self._place_window_at_pet(win, p)

    def _place_window_at_pet(self, win, pet=None):
        """เด้งกลางจอเสมอ (เดิมวางเหนือหัวน้อง แต่ข้ามจอ/DPI เพี้ยน เลยใช้กลางจอ)"""
        self._center_on_screen(win)

    @staticmethod
    def _feature_btn(parent, text, cmd, color="#2c3e50", **kw):
        kw.setdefault("font", ("Segoe UI", 10, "bold"))
        kw.setdefault("padx", 10)
        kw.setdefault("pady", 3)
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="#ffffff",
                         activebackground="#34495e", bd=0, cursor="hand2", **kw)

    # ---- มินิเกม: เป่ายิงฉุบ ----------------------------------------------
    def _roll_game_day(self):
        """รีเซ็ตตัวนับรางวัลเกมเมื่อขึ้นวันใหม่"""
        today = self._today()
        if self.game_date != today:
            self.game_date = today
            self.games_today = 0

    def _show_rps_window(self):
        self._roll_game_day()
        win, fr = self._feature_popup(f"✊  เป่ายิงฉุบ กับ {self.pet.name or 'เพ็ท'}")
        pet = self._pause_active_for_menu()     # เล่นกับน้องตัวที่ดูแล (หยุดนิ่ง)
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        cap = config.RPS_DAILY_REWARD_CAP
        moves = [("✊", "ค้อน"), ("✋", "กระดาษ"), ("✌", "กรรไกร")]

        info = tk.Label(fr, bg=BG, fg=SUB, font=("Segoe UI", 10))
        info.pack(anchor="w", pady=(2, 8))
        result = tk.Label(fr, bg=BG, fg=FG, font=("Segoe UI", 12),
                          text="เลือกออกอาวุธสู้กับน้อง!", justify="center")
        result.pack(pady=(0, 10))

        def refresh_info():
            info.config(text=f"🪙 {self.coins}     ชนะรับเหรียญวันนี้ "
                             f"{self.games_today}/{cap}")
        refresh_info()

        def play(i):
            pet_i = random.randrange(3)
            outcome = (i - pet_i) % 3          # 0=เสมอ 1=ผู้เล่นชนะ 2=แพ้
            self._inc_lifetime("games")
            self.pet.happy = min(100, self.pet.happy + config.RPS_PLAY_HAPPY)
            head = f"คุณ {moves[i][0]}   vs   น้อง {moves[pet_i][0]}\n"
            if outcome == 1:
                self.pet.happy = min(100, self.pet.happy + config.RPS_WIN_HAPPY)
                if self.games_today < cap:
                    self.add_coins(config.RPS_WIN_COINS)
                    self.games_today += 1
                    result.config(text=head + f"คุณชนะ! 🎉  +{config.RPS_WIN_COINS} 🪙",
                                  fg="#2ecc71")
                else:
                    result.config(text=head + "คุณชนะ! 🎉  (ครบโควตาเหรียญวันนี้)",
                                  fg="#2ecc71")
            elif outcome == 0:
                result.config(text=head + "เสมอ! 🤝", fg=FG)
            else:
                result.config(text=head + "น้องชนะ! 😆", fg="#e67e22")
            refresh_info()
            self._save_progress()
            self._draw_hud()

        row = tk.Frame(fr, bg=BG)
        row.pack()
        for i, (emo, name) in enumerate(moves):
            tk.Button(row, text=f"{emo}\n{name}", command=lambda i=i: play(i),
                      bg="#2c3e50", fg=FG, activebackground="#34495e", bd=0,
                      font=("Segoe UI Emoji", 15), width=5, cursor="hand2"
                      ).pack(side="left", padx=5)
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(14, 0))
        self._place_window_at_pet(win, pet)

    # ---- สอนทริค / แสดงท่า -----------------------------------------------
    def _teach_trick(self, t):
        pet = self.pet
        if t["id"] not in pet.tricks_taught and pet.affection >= t["req"]:
            pet.tricks_taught.append(t["id"])
            pet.happy = min(100, pet.happy + 5)
            self.show_bubble(f"{pet.name} เรียนรู้ '{t['name']}' แล้ว! 🎓", pet)
            self._save_progress()

    def _perform_trick(self, t):
        now = self.tick_count * config.TICK_MS / 1000.0
        if now - getattr(self, "_last_trick_at", -999) < config.TRICK_COOLDOWN_SEC:
            return
        self._last_trick_at = now
        self.pet.happy = min(100, self.pet.happy + config.TRICK_HAPPY)
        self.pet.affection = min(100, self.pet.affection + 0.1)
        self.show_bubble(t["say"])
        self.spawn_effect(self.pet.x, self.pet.top_y(), t["emoji"])
        sound.play("pet")

    def _show_tricks_window(self):
        pet = self.pet
        win, fr = self._feature_popup(f"🎓  ทริคของ {pet.name or 'เพ็ท'}")
        self._pause_active_for_menu()
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        tk.Label(fr, text=f"❤ {pet.name} · สายสัมพันธ์ {int(pet.affection)}/100"
                          "  (เลี้ยงดีเพื่อปลดล็อก)", bg=BG, fg=SUB,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 8))

        def reopen():
            self._show_tricks_window()

        for t in config.TRICKS:
            taught = t["id"] in pet.tricks_taught
            unlocked = pet.affection >= t["req"]
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{t['emoji']}  {t['name']}", bg=BG,
                     fg=FG if unlocked else "#777777", font=("Segoe UI", 11),
                     anchor="w", width=14).pack(side="left")
            if not unlocked:
                tk.Label(row, text=f"🔒 ต้องรัก {t['req']}", bg=BG, fg=SUB,
                         font=("Segoe UI", 10)).pack(side="right")
            elif not taught:
                self._feature_btn(row, "สอน",
                                  lambda tt=t: (self._teach_trick(tt), reopen()),
                                  color="#2c7a51").pack(side="right")
            else:
                self._feature_btn(row, "แสดง ▶",
                                  lambda tt=t: self._perform_trick(tt),
                                  color="#2c3e50").pack(side="right")
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(14, 0))
        self._place_window_at_pet(win, pet)

    # ---- ความสำเร็จ (Achievement) ----------------------------------------
    def _show_achievements_window(self):
        self._check_achievements()
        win, fr = self._feature_popup("🏆  ความสำเร็จ")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        done, total = len(self.achievements), len(config.ACHIEVEMENTS)
        tk.Label(fr, text=f"ปลดล็อกแล้ว {done}/{total}", bg=BG, fg=SUB,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 8))
        for a in config.ACHIEVEMENTS:
            got = a["id"] in self.achievements
            val = min(self._achievement_value(a["metric"]), a["goal"])
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{a['icon']}  {a['name']}", bg=BG,
                     fg="#2ecc71" if got else FG, font=("Segoe UI", 11),
                     anchor="w", width=18).pack(side="left")
            status = "✓ สำเร็จ" if got else f"{int(val)}/{a['goal']}"
            tk.Label(row, text=f"{status}   +{a['reward']}🪙", bg=BG,
                     fg="#2ecc71" if got else SUB,
                     font=("Segoe UI", 10)).pack(side="right")
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(14, 0))
        self._place_feature_window(win)

    # ---- หลังบ้าน: อัปโหลด/จัดการมอนสเตอร์ -------------------------------
    def _reload_monsters(self):
        self.monster_sets = self._load_monster_sets()

    def _show_monster_manager(self):
        from tkinter import filedialog
        win, fr = self._feature_popup("🐲  จัดการมอนสเตอร์")
        win.unbind("<FocusOut>")               # กันปิดเองตอนเปิด file dialog
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"

        def reopen():
            self._show_monster_manager()

        mons = assets.list_monsters()
        tk.Label(fr, text=f"มอนที่มี ({len(mons)})  + ตัวเริ่มต้น 1",
                 bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 4))
        for nm in mons:
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"🐲 {nm}", bg=BG, fg=FG, font=("Segoe UI", 11),
                     anchor="w", width=16).pack(side="left")
            self._feature_btn(row, "ลบ",
                              lambda n=nm: (assets.delete_monster(n),
                                            self._reload_monsters(), reopen()),
                              color="#7a2c2c").pack(side="right")

        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 6))
        tk.Label(fr, text="เพิ่มมอนใหม่ (อัปโหลดรูป)", bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        name_var = tk.StringVar()
        walk_var = tk.StringVar(value="(ยังไม่เลือก)")
        hurt_var = tk.StringVar(value="(ไม่บังคับ)")
        picked = {"walk": None, "hurt": None}
        msg = tk.Label(fr, bg=BG, fg=SUB, font=("Segoe UI", 9))

        nrow = tk.Frame(fr, bg=BG); nrow.pack(fill="x", pady=(4, 2))
        tk.Label(nrow, text="ชื่อ:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(nrow, textvariable=name_var, font=("Segoe UI", 11), width=16,
                 bg="#2d333d", fg=FG, insertbackground=FG, bd=0).pack(side="left", padx=6, ipady=3)

        def pick(slot, var):
            self.root.wm_attributes("-topmost", False)
            path = filedialog.askopenfilename(
                title="เลือกไฟล์ภาพมอนสเตอร์",
                filetypes=[("รูปภาพ", "*.png *.gif"), ("ทั้งหมด", "*.*")])
            self.root.wm_attributes("-topmost", True)
            if path:
                picked[slot] = path
                var.set(os.path.basename(path))

        for slot, label, var in (("walk", "🚶 รูปเดิน", walk_var),
                                 ("hurt", "💥 รูปโดนตี", hurt_var)):
            r = tk.Frame(fr, bg=BG); r.pack(fill="x", pady=2)
            self._feature_btn(r, label, lambda s=slot, v=var: pick(s, v),
                              color="#2c3e50").pack(side="left")
            tk.Label(r, textvariable=var, bg=BG, fg=SUB,
                     font=("Segoe UI", 9)).pack(side="left", padx=6)

        def save():
            if not name_var.get().strip() or not picked["walk"]:
                msg.config(text="ต้องใส่ชื่อ + เลือกรูปเดิน", fg="#e74c3c")
                return
            res = assets.add_monster(name_var.get(), picked)
            if not res:
                msg.config(text="บันทึกไม่สำเร็จ", fg="#e74c3c")
                return
            self._reload_monsters()
            self.show_bubble(f"เพิ่มมอน '{res}' แล้ว! 🐲")
            reopen()

        msg.pack(anchor="w", pady=(4, 0))
        self._feature_btn(fr, "💾 บันทึกมอนใหม่", save, color="#2c7a51",
                          font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(6, 0))
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(8, 0))
        self._place_feature_window(win)

    def _reload_character_pets(self, name):
        """โหลดสไปรต์ใหม่ให้น้องบนจอที่ใช้ตัวละครนี้ (หลังแก้ไขรูป) ให้เห็นผลทันที"""
        for p in self.pets:
            if p.character != name:
                continue
            assets.set_character_dir(assets.character_path(name))
            p.anims = self._load_pet_anims()
            p.frame_i = 0
            p._render()
            self._drop_to_ground(p)
            p.sync_position()

    def _show_character_manager(self, edit_name=None):
        """หลังบ้านตัวละคร — เพิ่ม/แก้ไข/ลบ (รูป Idle/Walk/Attack/Dead/Taken + เปลี่ยนชื่อ)"""
        from tkinter import filedialog
        win, fr = self._feature_popup("🐾  จัดการตัวละคร")
        win.unbind("<FocusOut>")               # กันปิดเองตอนเปิด file dialog
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        editing = edit_name in assets.list_characters()

        def reopen(name=None):
            self._show_character_manager(name)

        # ===== รายการตัวละคร (แก้ไข / ลบ) =====
        chars = assets.list_characters()
        tk.Label(fr, text=f"ตัวละครที่มี ({len(chars)})  + ค่าเริ่มต้น 1",
                 bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 4))
        for nm in chars:
            in_use = any(p.character == nm for p in self.pets)
            sel = (nm == edit_name)
            rr = config.rarity_by_id(assets.character_rarity(nm))
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{'✏️' if sel else '🐾'} {nm}", bg=BG,
                     fg="#f1c40f" if sel else FG, font=("Segoe UI", 11),
                     anchor="w", width=12).pack(side="left")
            tk.Label(row, text="★" * rr["stars"], bg=BG, fg=rr["color"],
                     font=("Segoe UI", 9)).pack(side="left")
            if not in_use:
                self._feature_btn(row, "ลบ",
                                  lambda n=nm: (assets.delete_character(n), reopen()),
                                  color="#7a2c2c").pack(side="right", padx=(4, 0))
            else:
                tk.Label(row, text="กำลังเลี้ยง", bg=BG, fg="#2ecc71",
                         font=("Segoe UI", 8)).pack(side="right", padx=(4, 0))
            self._feature_btn(row, "แก้ไข", lambda n=nm: reopen(n),
                              color="#2c3e50").pack(side="right")

        # ===== ฟอร์มเพิ่ม/แก้ไข =====
        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 6))
        title = (f"แก้ไขตัวละคร: {edit_name}" if editing
                 else "เพิ่มตัวละครใหม่ (อัปโหลดรูป)")
        tk.Label(fr, text=title, bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(fr, text="รูป 100×100/เฟรม · หลายเฟรมตั้งชื่อ _strip3 (Attack=3, อื่นๆ≤4)",
                 bg=BG, fg="#777777", font=("Segoe UI", 8)).pack(anchor="w")

        name_var = tk.StringVar(value=edit_name if editing else "")
        msg = tk.Label(fr, bg=BG, fg=SUB, font=("Segoe UI", 9))
        picked = {"idle": None, "walk": None, "attack": None, "hurt": None,
                  "eat": None, "dead": None, "taken": None,
                  "sleep": None, "bathe": None, "pet": None}

        nrow = tk.Frame(fr, bg=BG); nrow.pack(fill="x", pady=(4, 2))
        tk.Label(nrow, text="ชื่อ:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(nrow, textvariable=name_var, font=("Segoe UI", 11), width=16,
                 bg="#2d333d", fg=FG, insertbackground=FG, bd=0
                 ).pack(side="left", padx=6, ipady=3)

        # ===== เลือกระดับของตัวละคร (ใช้ถ่วงน้ำหนักการสุ่มไข่/ดรอปบอส) =====
        cur_rar = assets.character_rarity(edit_name) if editing else "common"
        rarity_var = tk.StringVar(value=cur_rar)
        rrow = tk.Frame(fr, bg=BG); rrow.pack(fill="x", pady=(2, 2))
        tk.Label(rrow, text="ระดับ:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        rar_btns = {}

        def set_rarity(rid):
            rarity_var.set(rid)
            for k, b in rar_btns.items():
                on = (k == rid)
                rr = config.rarity_by_id(k)
                b.configure(bg=rr["color"] if on else "#2c313a",
                            fg="#1e1e1e" if on else rr["color"])
        for r in config.RARITIES:
            b = tk.Button(rrow, text=f"{'★' * r['stars']}{r['name']}", bd=0, cursor="hand2",
                          font=("Segoe UI", 8, "bold"), padx=5, pady=2,
                          command=lambda rid=r["id"]: set_rarity(rid))
            b.pack(side="left", padx=2)
            rar_btns[r["id"]] = b
        set_rarity(cur_rar)

        # ===== อาหารที่กินได้ (ติ๊กเลือก) — เก็บเป็น likes ใน pet.json =====
        cur_likes = (assets.load_character_meta(edit_name).get("likes", [])
                     if editing else [f["id"] for f in config.FOOD_TYPES])
        food_vars = {}
        frow = tk.Frame(fr, bg=BG); frow.pack(fill="x", pady=(2, 2))
        tk.Label(frow, text="กินได้:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        for ft in config.FOOD_TYPES:
            v = tk.BooleanVar(value=(ft["id"] in cur_likes))
            food_vars[ft["id"]] = v
            tk.Checkbutton(frow, text=f"{ft['emoji']}{ft['name']}", variable=v,
                           bg=BG, fg=FG, selectcolor="#2c313a", activebackground=BG,
                           activeforeground=FG, font=("Segoe UI", 8), bd=0
                           ).pack(side="left")

        def pick(slot, var):
            self.root.wm_attributes("-topmost", False)
            path = filedialog.askopenfilename(
                title="เลือกไฟล์ภาพตัวละคร",
                filetypes=[("รูปภาพ", "*.png *.gif"), ("ทั้งหมด", "*.*")])
            self.root.wm_attributes("-topmost", True)
            if path:
                picked[slot] = path
                var.set("ใหม่: " + os.path.basename(path))

        slots = [("idle", "🧍 Idle"), ("walk", "🚶 Walk"), ("attack", "⚔ Attack (3 เฟรม)"),
                 ("hurt", "💥 Hurt (โดนตี)"), ("eat", "🍽 Eat (กิน)"),
                 ("sleep", "😴 Sleep (นอน)"), ("bathe", "🛁 Bathe (อาบน้ำ)"),
                 ("pet", "✋ Pet (ลูบหัว)"),
                 ("dead", "💀 Dead"), ("taken", "🤲 Taken")]
        cur_anim_ms = (assets.load_character_meta(edit_name).get("anim_ms", {})
                       if editing else {})
        ms_vars = {}
        tk.Label(fr, text="แต่ละท่า: เลือกรูป + ตั้งหน่วงเฟรม (ms ยิ่งน้อยยิ่งเร็ว)",
                 bg=BG, fg="#777777", font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))
        for slot, label in slots:
            cur = assets.character_slot_file(edit_name, slot) if editing else None
            if cur:
                default = f"มีอยู่: {cur}"
            elif slot == "idle":
                default = "(จำเป็น)"
            else:
                default = "(ไม่บังคับ)"
            var = tk.StringVar(value=default)
            r = tk.Frame(fr, bg=BG); r.pack(fill="x", pady=2)
            self._feature_btn(r, label, lambda s=slot, v=var: pick(s, v),
                              color="#2c3e50", width=8).pack(side="left")
            # ช่องตั้งหน่วงเฟรม (ms) ของท่านี้
            msv = tk.StringVar(value=str(int(cur_anim_ms.get(slot, config.ANIM_MS))))
            ms_vars[slot] = msv
            tk.Entry(r, textvariable=msv, width=4, justify="center",
                     bg="#2d333d", fg=FG, insertbackground=FG, bd=0,
                     font=("Segoe UI", 9)).pack(side="right", ipady=2)
            tk.Label(r, text="ms", bg=BG, fg=SUB,
                     font=("Segoe UI", 8)).pack(side="right", padx=(0, 2))
            tk.Label(r, textvariable=var, bg=BG, fg=SUB,
                     font=("Segoe UI", 8)).pack(side="left", padx=6)

        def collect_anim_ms():
            out = {}
            for slot, v in ms_vars.items():
                try:
                    n = int(float(v.get()))
                except (TypeError, ValueError):
                    continue
                n = max(config.ANIM_MS_MIN, min(config.ANIM_MS_MAX, n))
                if n != config.ANIM_MS:        # เก็บเฉพาะที่ต่างจากค่าเริ่มต้น
                    out[slot] = n
            return out

        def save():
            nm = name_var.get().strip()
            if not nm:
                msg.config(text="ต้องใส่ชื่อ", fg="#e74c3c")
                return
            if editing:
                # อัปเดตรูปที่เลือกใหม่ (ทับของเดิม) — idle เดิมมีอยู่แล้วไม่ต้องเลือก
                target = edit_name
                if nm != edit_name:                       # เปลี่ยนชื่อ → ย้ายโฟลเดอร์
                    rn = assets.rename_character(edit_name, nm)
                    if not rn:
                        msg.config(text="เปลี่ยนชื่อไม่ได้ (ซ้ำ/ผิดพลาด)", fg="#e74c3c")
                        return
                    target = rn
                    for p in self.pets:                   # อัปเดตชื่อตัวละครของน้องที่ใช้
                        if p.character == edit_name:
                            p.character = rn
                if any(picked.values()):                  # มีรูปใหม่ → คัดลอกทับ
                    picked.setdefault("idle", None)
                    # add_character ต้องการ idle — ถ้าไม่เลือกใหม่ ใช้ของเดิมที่มีอยู่
                    if not picked["idle"]:
                        picked["idle"] = os.path.join(
                            assets.character_path(target),
                            assets.character_slot_file(target, "idle") or "")
                    assets.add_character(target, picked)
                likes = [fid for fid, v in food_vars.items() if v.get()]
                assets.set_character_meta(target, {"rarity": rarity_var.get(),
                                                   "likes": likes,
                                                   "anim_ms": collect_anim_ms()})
                self._reload_character_pets(target)
                self._save_progress()
                self.show_bubble(f"แก้ไขตัวละคร '{target}' แล้ว! ✏️")
                reopen(target)
            else:
                if not picked["idle"]:
                    msg.config(text="ต้องเลือกรูป Idle", fg="#e74c3c")
                    return
                res = assets.add_character(nm, picked)
                if not res:
                    msg.config(text="บันทึกไม่สำเร็จ", fg="#e74c3c")
                    return
                likes = [fid for fid, v in food_vars.items() if v.get()]
                assets.set_character_meta(res, {"rarity": rarity_var.get(),
                                                "likes": likes,
                                                "anim_ms": collect_anim_ms()})
                rname = config.rarity_by_id(rarity_var.get())["name"]
                self.show_bubble(f"เพิ่มตัวละคร '{res}' ({rname}) แล้ว! 🐾")
                reopen()

        msg.pack(anchor="w", pady=(4, 0))
        btn_text = "💾 บันทึกการแก้ไข" if editing else "💾 บันทึกตัวละครใหม่"
        self._feature_btn(fr, btn_text, save, color="#2c7a51",
                          font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(6, 0))
        if editing:
            self._feature_btn(fr, "+ เพิ่มตัวใหม่แทน", lambda: reopen(None),
                              color="#2c3e50").pack(fill="x", pady=(4, 0))
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(8, 0))
        self._place_feature_window(win)

    # ---- เลี้ยงหลายตัว: เลือกดูแล / รับเลี้ยงเพิ่ม / ปล่อย -----------------
    def _set_active_pet(self, idx):
        self.active = max(0, min(idx, len(self.pets) - 1))
        self._save_progress()

    def _release_pet(self, idx):
        if len(self.pets) <= 1:
            return
        pet = self.pets.pop(idx)
        if pet.food is not None:
            pet.food.destroy()
        pet.destroy()
        if idx < self.active:
            self.active -= 1
        self.active = max(0, min(self.active, len(self.pets) - 1))
        self._save_progress()

    # ---- เก็บน้องเข้ากล่อง / เรียกออกมา (พักไว้ ไม่ลดสเตตัส) --------------
    def _store_pet(self, idx):
        """เก็บน้องตัวที่ idx เข้ากล่อง (พักไว้ ดึงกลับได้ภายหลัง)"""
        if not (0 <= idx < len(self.pets)):
            return
        if len(self.pets) <= 1:
            self.show_bubble("ต้องเหลือน้องบนจออย่างน้อย 1 ตัว!")
            return
        if len(self.stored) >= config.MAX_STORED:
            self.show_bubble("กล่องเก็บเต็มแล้ว!")
            return
        pet = self.pets[idx]
        if pet.behavior == "dead":
            self.show_bubble("ชุบก่อนถึงเก็บได้ 💀", pet)
            return
        if self._is_away(pet):
            self.show_bubble("กำลังผจญภัยอยู่ เก็บไม่ได้!", pet)
            return
        self.stored.append(self._pet_to_data(pet))
        self.pets.pop(idx)
        if pet.food is not None:
            pet.food.destroy()
        pet.destroy()
        if idx < self.active:
            self.active -= 1
        self.active = max(0, min(self.active, len(self.pets) - 1))
        sound.play("click")
        self.show_bubble("เก็บน้องเข้ากล่องแล้ว 📦")
        self._save_progress()

    def _retrieve_pet(self, sidx):
        """เรียกน้องในกล่องตัวที่ sidx ออกมาเลี้ยงต่อ"""
        if not (0 <= sidx < len(self.stored)):
            return
        if len(self.pets) >= self._pet_cap():
            self.show_bubble("บนจอเต็มแล้ว! เก็บตัวอื่นก่อน")
            sound.play("hurt")
            return
        pd = self.stored.pop(sidx)
        pet = self._build_pet(pd.get("character"), pd)
        self.pets.append(pet)
        self.active = len(self.pets) - 1
        sound.play("levelup")
        self.show_bubble("เรียกน้องออกมาแล้ว! 🎉", pet)
        self._save_progress()

    def _release_stored(self, sidx):
        """ปล่อยน้องในกล่อง (ลบถาวร)"""
        if 0 <= sidx < len(self.stored):
            self.stored.pop(sidx)
            self._save_progress()

    def _adopt_pet(self, character):
        if len(self.pets) >= self._pet_cap():
            self.show_bubble("เลี้ยงครบจำนวนแล้ว!")
            return
        if self.coins < config.ADOPT_COST:
            self.show_bubble("เหรียญไม่พอรับเลี้ยง! 🪙")
            sound.play("hurt")
            return
        self.coins -= config.ADOPT_COST
        pet = self._build_pet(character, {"birth_date": self._today()})
        self.pets.append(pet)
        self.active = len(self.pets) - 1
        sound.play("levelup")
        self.show_bubble("ยินดีต้อนรับสมาชิกใหม่! 🎉")
        self._save_progress()

    # ---------------------------------------------- ผสมพันธุ์ / ไข่ / ฟัก
    def _make_egg(self, character, likes=None, dislikes=None, trait=None,
                  skill=None, rarity=None):
        """เพิ่มไข่ลงรัง (ฟักตามเวลาจริง) — คืน False ถ้ารังเต็ม"""
        if len(self.eggs) >= self._egg_cap():
            return False
        meta = assets.load_character_meta(character)
        valid = {f["id"] for f in config.FOOD_TYPES}
        lk = likes if likes is not None else meta.get("likes", [])
        dk = dislikes if dislikes is not None else meta.get("dislikes", [])
        valid_traits = {t["id"] for t in config.TRAITS}
        valid_skills = {s["id"] for s in config.SKILLS}
        valid_rar = {r["id"] for r in config.RARITIES}
        # ระดับไข่ = ระดับของตัวละครนั้น (ถ้าไม่ส่ง rarity มา) — ตัวละคร None = ปกติ
        if rarity not in valid_rar:
            rarity = assets.character_rarity(character) if character else "common"
        self.eggs.append({
            "character": character,
            "likes": [v for v in lk if v in valid],
            "dislikes": [v for v in dk if v in valid],
            "trait": trait if trait in valid_traits else random.choice(config.TRAITS)["id"],
            "skill": skill if skill in valid_skills else random.choice(config.SKILLS)["id"],
            "rarity": rarity,
            "hatch_at": time.time() + config.HATCH_SECONDS,
        })
        return True

    def _egg_ready(self, egg):
        return time.time() >= float(egg.get("hatch_at", 0))

    def _notify_eggs_ready(self):
        """ไข่ครบเวลา → เด้งเตือนครั้งเดียวให้ผู้เล่นไปกดฟักเอง (ไม่ฟักอัตโนมัติ)"""
        ready = [e for e in self.eggs if self._egg_ready(e)
                 and not e.get("_notified")]
        if not ready:
            return
        for e in ready:
            e["_notified"] = True
        self.show_bubble(f"🥚 ไข่พร้อมฟักแล้ว {len(ready)} ฟอง! เปิด 🐣 ฟักไข่")

    def _hatch_egg(self, egg):
        """ฟักไข่ 1 ฟองด้วยมือผู้เล่น — สุ่มนิสัย+สกิลตอนฟัก; ถ้าจอเต็มให้เข้ากล่องเก็บ"""
        if egg not in self.eggs:
            return
        if not self._egg_ready(egg):
            self.show_bubble("ไข่ยังฟักไม่ได้ — รอให้ครบเวลา ⏳")
            sound.play("hurt")
            return
        to_box = len(self.pets) >= self._pet_cap()   # จอเต็ม → ฟักเข้ากล่องแทน
        if to_box and len(self.stored) >= config.MAX_STORED:
            self.show_bubble("เต็มทั้งจอและกล่องเก็บ! ปล่อยน้องก่อน")
            sound.play("hurt")
            return
        # สุ่มนิสัย + สกิลติดตัว ตอนฟัก (ไม่ส่ง trait/skill → _build_pet สุ่มให้)
        # ความหายากมาจากไข่ (rarity ของไข่ = ระดับของตัวละครที่ฟักออกมา)
        pd = {"character": egg.get("character"),
              "likes": egg.get("likes", []),
              "dislikes": egg.get("dislikes", []),
              "rarity": egg.get("rarity", "common"),
              "birth_date": self._today()}
        pet = self._build_pet(egg.get("character"), pd)
        self.eggs.remove(egg)
        sound.play("levelup")
        if to_box:                                   # จอเต็ม → เก็บเข้ากล่องเลย
            self.stored.append(self._pet_to_data(pet))
            pet.destroy()
            self.show_bubble("🥚→🐣 ฟักแล้วเก็บเข้ากล่อง 📦 (จอเต็ม)")
        else:
            self.pets.append(pet)
            self.active = len(self.pets) - 1
            self.show_bubble("🥚→🐣 ฟักสำเร็จ! ยินดีต้อนรับ", pet)
            self.spawn_effect(pet.x, pet.top_y(), "🐣")
        self._save_progress()

    def _sell_egg(self, egg):
        """ขายไข่เข้าตลาด → ได้เหรียญตามระดับความหายาก"""
        if egg not in self.eggs:
            return
        price = self._rarity_of(egg).get("sell", 0)
        self.eggs.remove(egg)
        self.add_coins(price)
        sound.play("eat")
        self.show_bubble(f"ขายไข่ได้ {price} 🪙")
        self._save_progress()

    def _show_hatch_window(self, forced=False):
        """เมนูฟักไข่ — รูปไข่ + ระดับความหายาก, ฟัก/ขายทีละฟอง, ขยายช่องไข่ได้
        forced=True (เริ่มเกมครั้งแรก) = ออกไม่ได้จนกว่าจะกดฟัก (ไม่มีปุ่มปิด/ขาย/ล็อกหน้าจอ)"""
        win, fr = self._feature_popup(f"🐣  ฟักไข่ ({len(self.eggs)}/{self._egg_cap()})")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        full = len(self.pets) >= self._pet_cap()
        icon = self._egg_icon()

        def reopen():
            self._draw_hud()
            self._show_hatch_window(forced)

        def do_hatch(e):
            self._hatch_egg(e)
            if forced and not self.pets:    # ยังไม่ได้น้อง (เช่นเต็ม) → คงหน้าบังคับไว้
                reopen()
            elif forced:                    # ได้น้องตัวแรกแล้ว → ปลดล็อกออกได้
                self._close_feature_window()
            else:
                reopen()

        if forced:
            tk.Label(fr, text="ยินดีต้อนรับ! 🎉 ได้รับไข่ฟรี 1 ใบ", bg=BG, fg="#f1c40f",
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(2, 0))
            note = "กด 🐣 ฟัก เพื่อรับน้องตัวแรก (ลุ้นตัวละคร/นิสัย/สกิล)"
        else:
            note = ("จอเต็ม — ฟักแล้วน้องจะเข้ากล่องเก็บ 📦" if full
                    else "กดฟักได้ทีละฟอง · นิสัย+สกิล+ระดับ สุ่มตอนฟัก ✨")
        tk.Label(fr, text=note, bg=BG, fg="#e67e22" if (full and not forced) else SUB,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))

        if not self.eggs:
            tk.Label(fr, text="ยังไม่มีไข่ — ผสมพันธุ์ 💕 หรือล้มบอส 🥚",
                     bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 6))
        for egg in list(self.eggs):
            rar = self._rarity_of(egg)
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=4)
            left = int(float(egg.get("hatch_at", 0)) - time.time())
            # รูปไข่ (หรืออิโมจิสำรอง)
            if icon is not None:
                tk.Label(row, image=icon, bg=BG).pack(side="left")
            else:
                tk.Label(row, text="🥚", bg=BG, font=("Segoe UI Emoji", 18)).pack(side="left")
            info = tk.Frame(row, bg=BG); info.pack(side="left", padx=(4, 0))
            tk.Label(info, text=f"{'★' * rar['stars']} {rar['name']}", bg=BG,
                     fg=rar["color"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text="❓ ลุ้นนิสัย+สกิล", bg=BG, fg=SUB,
                     font=("Segoe UI", 8)).pack(anchor="w")
            # ปุ่มขาย (เฉพาะโหมดปกติ) + ฟัก (เมื่อครบเวลา)
            if not forced:
                self._feature_btn(row, f"💰 ขาย {rar['sell']}",
                                  lambda e=egg: (self._sell_egg(e), reopen()),
                                  color="#7a6a2c").pack(side="right", padx=(4, 0))
            if left > 0:
                tk.Label(row, text=f"⏳ {left // 60}:{left % 60:02d}", bg=BG,
                         fg=SUB, font=("Segoe UI", 10)).pack(side="right")
            else:
                self._feature_btn(row, "🐣 ฟัก",
                                  lambda e=egg: do_hatch(e),
                                  color="#2c7a51",
                                  font=("Segoe UI", 11, "bold")).pack(side="right")

        if not forced:
            # ── ขยายช่องเก็บไข่ ──
            tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 6))
            if self.egg_slot_buys < config.EGG_SLOT_MAX_BUYS:
                cost = self._egg_slot_cost()
                self._feature_btn(
                    fr, f"➕ ขยายช่องไข่ +{config.EGG_SLOT_STEP}  ({cost} 🪙)",
                    lambda: (self._buy_egg_slot(), reopen()),
                    color="#2c3e50", font=("Segoe UI", 10, "bold")).pack(fill="x")
            else:
                tk.Label(fr, text="ช่องไข่ขยายสูงสุดแล้ว", bg=BG, fg=SUB,
                         font=("Segoe UI", 9)).pack(anchor="w")
            self._feature_btn(fr, "ปิด", self._close_feature_window,
                              font=("Segoe UI", 11, "bold"), padx=20, pady=4
                              ).pack(pady=(10, 0))
        else:
            # โหมดบังคับ: ไม่มีปุ่มปิด + ปิดเองเมื่อคลิกที่อื่นไม่ได้ + ล็อกอินพุตไว้ที่หน้านี้
            win.unbind("<FocusOut>")
            try:
                win.grab_set()
            except Exception:
                pass
        self._place_window_beside(win, getattr(self, "_pets_canvas", None))

    def _can_breed(self, pet):
        return (pet.behavior != "dead"
                and pet.affection >= config.BREED_MIN_AFFECTION
                and self._age_days(pet) >= config.BREED_MIN_AGE_DAYS)

    def _breed(self, a, b):
        """ผสมพันธุ์ 2 ตัว → ได้ไข่ (ลูกได้ร่าง+ความชอบผสมจากพ่อแม่)"""
        if a is b or a not in self.pets or b not in self.pets:
            return
        if len(self.eggs) >= self._egg_cap():
            self.show_bubble("รังไข่เต็มแล้ว!")
            return
        if not (self._can_breed(a) and self._can_breed(b)):
            self.show_bubble("น้องยังไม่พร้อม (ต้องโต + รักพอ)")
            sound.play("hurt")
            return
        if config.BREED_NEED_DIFFERENT_GENDER and a.gender == b.gender:
            self.show_bubble("ต้องจับคู่ ♂ + ♀ ถึงผสมพันธุ์ได้!")
            sound.play("hurt")
            return
        if self.coins < config.BREED_COST:
            self.show_bubble("เหรียญไม่พอผสมพันธุ์! 🪙")
            sound.play("hurt")
            return
        self.coins -= config.BREED_COST
        child_char = random.choice([a.character, b.character])
        likes = list(dict.fromkeys(list(a.likes) + list(b.likes)))[:3]
        dislikes = [d for d in dict.fromkeys(list(a.dislikes) + list(b.dislikes))
                    if d not in likes][:2]
        # นิสัยสืบทอดจากพ่อแม่ (มีโอกาสกลายพันธุ์)
        if random.random() < 0.15:
            child_trait = random.choice(config.TRAITS)["id"]
        else:
            child_trait = random.choice([a.trait, b.trait])
        # สกิลติดตัว: มีโอกาสสืบทอดของพ่อ/แม่ (ที่เหลือ = สุ่มใหม่/กลายพันธุ์)
        if random.random() < config.SKILL_INHERIT_CHANCE:
            child_skill = random.choice([a.skill, b.skill])
        else:
            child_skill = random.choice(config.SKILLS)["id"]
        self._make_egg(child_char, likes, dislikes, child_trait, child_skill)
        sound.play("levelup")
        self.show_bubble("💕 ได้ไข่มาแล้ว! รอฟัก 🥚")
        self._save_progress()

    # ---------------------------------------------- พาผจญภัย (idle)
    def _is_away(self, pet):
        return pet.away_until and time.time() < pet.away_until

    def _send_adventure(self, pet, opt):
        if self.monster is not None and pet is self._combat_target():
            self.show_bubble("กำลังสู้อยู่ ไปผจญภัยไม่ได้!", pet)
            return
        pet.away_until = time.time() + opt["mins"] * 60
        pet.away_mins = opt["mins"]
        if pet.food is not None:
            pet.food.destroy()
            pet.food = None
        self.show_bubble(f"{pet.name} ออกผจญภัย {opt['mins']} นาที! 🧭", pet)
        try:
            self.canvas.itemconfigure(pet.item, state="hidden")
        except Exception:
            pass
        sound.play("click")
        self._save_progress()

    def _check_adventures(self):
        for pet in self.pets:
            if pet.away_until and time.time() >= pet.away_until:
                self._return_adventure(pet)

    def _return_adventure(self, pet):
        mins = pet.away_mins or config.ADVENTURE_OPTIONS[0]["mins"]
        opt = next((o for o in config.ADVENTURE_OPTIONS if o["mins"] == mins),
                   config.ADVENTURE_OPTIONS[0])
        pet.away_until = 0.0
        pet.away_mins = 0
        pet.behavior = "wander"
        try:
            self.canvas.itemconfigure(pet.item, state="normal")
        except Exception:
            pass
        self._drop_to_ground(pet)
        pet.sync_position()
        coins = random.randint(*opt["coins"])
        self.add_coins(coins)
        msg = f"{pet.name} กลับมาแล้ว! +{coins}🪙"
        if random.random() < config.ADVENTURE_ITEM_CHANCE:
            it = random.choice(config.SHOP_ITEMS)
            self.inventory[it["id"]] = self.inventory.get(it["id"], 0) + 1
            msg += f" {it['emoji']}"
        if random.random() < config.ADVENTURE_EGG_CHANCE and len(self.eggs) < self._egg_cap():
            self._make_egg(self._weighted_character(rarity_filter={"common", "rare"}))
            msg += " 🥚"
        sound.play("win")
        self.show_bubble(msg, pet)
        self.spawn_effect(pet.x, pet.top_y(), "🎁")
        self._save_progress()

    # ---------------------------------------------- ฝึกฝน / ตั้งชื่อ
    def _train_cost(self, pet, stat):
        return config.TRAIN_BASE_COST + pet.train[stat] * config.TRAIN_COST_GROWTH

    def _train(self, pet, stat):
        if pet.train[stat] >= config.TRAIN_MAX:
            self.show_bubble("ฝึกสายนี้เต็มแล้ว!", pet)
            return
        cost = self._train_cost(pet, stat)
        if self.coins < cost:
            self.show_bubble("เหรียญไม่พอฝึก! 🪙", pet)
            sound.play("hurt")
            return
        self.coins -= cost
        pet.train[stat] += 1
        if stat == "hp":
            pet.hp = pet.max_hp()
        sound.play("levelup")
        self.show_bubble("ฝึกฝนสำเร็จ! 💪", pet)
        self._save_progress()

    def _rename_pet(self, pet, name):
        name = (name or "").strip()[:16]
        if name:
            pet.name = name
            self._save_progress()

    def _show_train_window(self):
        pet = self.pet
        win, fr = self._feature_popup(f"💪  ฝึกฝน — {pet.name or 'เพ็ท'}")
        self._pause_active_for_menu()
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        tk.Label(fr, text=f"🪙 {self.coins}   ⚔{pet.attack()} ❤{pet.max_hp()}",
                 bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 8))

        def reopen():
            self._draw_hud()
            self._show_train_window()

        rows = [("atk", "⚔ พลังโจมตี", config.TRAIN_ATK_STEP),
                ("hp", "❤ เลือดสูงสุด", config.TRAIN_HP_STEP),
                ("speed", "💨 ความเร็ว", config.TRAIN_SPEED_STEP)]
        for stat, label, step in rows:
            n = pet.train[stat]
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{label}  ({n}/{config.TRAIN_MAX})", bg=BG, fg=FG,
                     font=("Segoe UI", 11), anchor="w", width=16).pack(side="left")
            if n >= config.TRAIN_MAX:
                tk.Label(row, text="เต็ม ✓", bg=BG, fg="#2ecc71",
                         font=("Segoe UI", 10, "bold")).pack(side="right")
            else:
                cost = self._train_cost(pet, stat)
                self._feature_btn(row, f"+{step}  ({cost}🪙)",
                                  lambda s=stat: (self._train(pet, s), reopen()),
                                  color="#2c7a51").pack(side="right")
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._place_window_at_pet(win, pet)

    def _show_build_window(self):
        """หน้าต่างบิลด์ — ลงแต้มสกิล (จากเลเวลอัพ) ในสายต่อสู้ + รีบอร์นเมื่อเลเวลตัน"""
        pet = self.pet
        win, fr = self._feature_popup(f"🌟  บิลด์ — {pet.name or 'เพ็ท'}")
        self._pause_active_for_menu()
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        star = f"  🌟×{pet.rebirths}" if pet.rebirths else ""
        tk.Label(fr, text=f"Lv.{pet.level}/{config.MAX_LEVEL}{star}   "
                          f"แต้มสกิล: {pet.sp} ✨",
                 bg=BG, fg="#ffd23f", font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w", pady=(2, 2))
        tk.Label(fr, text=f"⚔{pet.attack()}  ❤{pet.max_hp()}  "
                          f"💥{pet.crit_chance():.0f}%  🛡{pet.dodge_chance():.0f}%  "
                          f"🩸{pet.lifesteal_pct():.0f}%",
                 bg=BG, fg=SUB, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        def reopen():
            self._draw_hud()
            self._show_build_window()

        for b in config.BUILD_LINES:
            n = pet.build[b["id"]]
            val = n * b["per"]
            shown = f"+{val:.0f}{b['unit']}" if b["unit"] == "%" else f"+{val:.2f}{b['unit']}"
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{b['emoji']} {b['name']}  ({n}/{config.BUILD_MAX})",
                     bg=BG, fg=FG, font=("Segoe UI", 11), anchor="w", width=18
                     ).pack(side="left")
            tk.Label(row, text=shown, bg=BG, fg="#7fd1a0",
                     font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
            if n >= config.BUILD_MAX:
                tk.Label(row, text="เต็ม ✓", bg=BG, fg="#2ecc71",
                         font=("Segoe UI", 10, "bold")).pack(side="right")
            else:
                self._feature_btn(
                    row, "＋1", lambda i=b["id"]: (self._spend_sp(pet, i), reopen()),
                    color="#2c7a51" if pet.sp > 0 else "#444444").pack(side="right")

        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 6))
        if self._can_rebirth(pet):
            nb = int(config.REBIRTH_BONUS * 100)
            self._feature_btn(
                fr, f"🌟 รีบอร์น  (+{nb}% พลังถาวร, รีเซ็ตเป็น Lv.1)",
                lambda: (self._rebirth(pet), reopen()),
                color="#7a3ea0", font=("Segoe UI", 10, "bold")).pack(pady=(0, 2))
        elif pet.rebirths >= config.REBIRTH_MAX:
            tk.Label(fr, text="🌟 รีบอร์นครบสูงสุดแล้ว!", bg=BG, fg="#c9a0ff",
                     font=("Segoe UI", 9)).pack()
        else:
            tk.Label(fr, text=f"ถึง Lv.{config.MAX_LEVEL} เพื่อรีบอร์น 🌟",
                     bg=BG, fg=SUB, font=("Segoe UI", 9)).pack()
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(10, 0))
        self._place_window_at_pet(win, pet)

    def _show_stat_window(self):
        """เมนูสแตท — ชีตข้อมูลตัวละคร: เพศ/สกิลติดตัว/ค่าต่อสู้/ฝึกฝน/บิลด์/รีบอร์น"""
        p = self.pet
        win, fr = self._feature_popup(f"📈  สแตท — {p.name or 'เพ็ท'}")
        self._pause_active_for_menu()
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        g = self._gender_of(p)
        star = f"  🌟×{p.rebirths}" if p.rebirths else ""
        tk.Label(fr, text=f"{g['emoji']} {p.name or 'เพ็ท'}  ·  Lv.{p.level}/"
                          f"{config.MAX_LEVEL}{star}",
                 bg=BG, fg=g["color"], font=("Segoe UI", 13, "bold")
                 ).pack(anchor="w", pady=(2, 0))
        # ── ระดับความหายาก ──
        rar = self._rarity_of(p)
        tk.Label(fr, text=f"{'★' * rar['stars']} ระดับ {rar['name']} "
                          f"(พลัง ×{rar['stat_mult']:.2f})",
                 bg=BG, fg=rar["color"], font=("Segoe UI", 10, "bold")).pack(anchor="w")

        # ── สกิลติดตัว ──
        sk = self._skill_of(p)
        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(6, 4))
        if sk:
            tlabel = config.SKILL_TYPE_LABEL.get(sk["type"], sk["type"])
            tcolor = {"attack": "#ff7676", "buff": "#7fd1a0",
                      "debuff": "#c9a0ff"}.get(sk["type"], FG)
            tk.Label(fr, text=f"สกิลติดตัว: {sk['emoji']} {sk['name']}  [{tlabel}]",
                     bg=BG, fg=tcolor, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(fr, text=f"   {sk['desc']}", bg=BG, fg=SUB,
                     font=("Segoe UI", 9)).pack(anchor="w")
        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(4, 6))

        # ── ค่าต่อสู้ (กริด 2 คอลัมน์) ──
        stats = [
            ("⚔ พลังโจมตี", f"{p.attack()}"),
            ("❤ เลือดสูงสุด", f"{p.max_hp()}"),
            ("💥 คริติคอล", f"{p.crit_chance():.0f}%"),
            ("🛡 หลบหลีก", f"{p.dodge_chance():.0f}%"),
            ("🩸 ดูดเลือด", f"{p.lifesteal_pct():.0f}%"),
            ("⚡ ท่าไม้ตาย", f"{p.ult_damage()}"),
        ]
        grid = tk.Frame(fr, bg=BG)
        grid.pack(fill="x")
        for i, (label, val) in enumerate(stats):
            cell = tk.Frame(grid, bg=BG)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16), pady=2)
            tk.Label(cell, text=label, bg=BG, fg=SUB,
                     font=("Segoe UI", 10), width=11, anchor="w").pack(side="left")
            tk.Label(cell, text=val, bg=BG, fg="#ffd23f",
                     font=("Segoe UI", 10, "bold")).pack(side="left")

        # ── ฝึกฝน + แต้มบิลด์ค้าง ──
        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(6, 4))
        tk.Label(fr, text=f"💪 ฝึกฝน — ⚔{p.train['atk']} ❤{p.train['hp']} "
                          f"💨{p.train['speed']} (สูงสุดสายละ {config.TRAIN_MAX})",
                 bg=BG, fg=SUB, font=("Segoe UI", 9)).pack(anchor="w")
        if p.sp > 0:
            tk.Label(fr, text=f"✨ มีแต้มสกิลรอลง {p.sp} แต้ม — ไปที่ 🌟 บิลด์",
                     bg=BG, fg="#ffd23f", font=("Segoe UI", 9, "bold")).pack(anchor="w")

        btns = tk.Frame(fr, bg=BG)
        btns.pack(pady=(10, 0))
        self._feature_btn(btns, "🌟 บิลด์", self._show_build_window,
                          color="#7a3ea0").pack(side="left", padx=(0, 6))
        self._feature_btn(btns, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=16, pady=4
                          ).pack(side="left")
        self._place_window_at_pet(win, p)

    def _show_adventure_window(self):
        """เมนูผจญภัย (คอลัมน์ขวา): ลิสต์ตัวที่ออกไป + ส่งตัวที่ว่างไปได้"""
        win, fr = self._feature_popup("🧭  ผจญภัย")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"

        def reopen():
            self._draw_hud()
            self._show_adventure_window()

        away = [p for p in self.pets if self._is_away(p)]
        ready = [p for p in self.pets if not self._is_away(p) and p.behavior != "dead"]

        tk.Label(fr, text=f"กำลังผจญภัย ({len(away)})", bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(2, 2))
        if not away:
            tk.Label(fr, text="— ไม่มีตัวไหนออกไป —", bg=BG, fg=SUB,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 2))
        for p in away:
            left = int(p.away_until - time.time())
            el = max(0, p.away_mins * 60 - left)
            name = p.name or "เพ็ท"
            tk.Label(fr,
                     text=f"🧭 {name} — ไป {el // 60} น. · เหลือ {left // 60}:{left % 60:02d}",
                     bg=BG, fg="#2ecc71", font=("Segoe UI", 11),
                     anchor="w").pack(anchor="w", pady=2)

        tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 4))
        tk.Label(fr, text="ส่งไป (ได้เหรียญ/ไอเทม/ไข่ ตอนกลับ)", bg=BG, fg="#f1c40f",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        if not ready:
            tk.Label(fr, text="— ทุกตัวไม่ว่าง —", bg=BG, fg=SUB,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        for p in ready:
            name = p.name or "เพ็ท"
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=name, bg=BG, fg=FG, font=("Segoe UI", 11),
                     anchor="w", width=10).pack(side="left")
            for opt in config.ADVENTURE_OPTIONS:
                self._feature_btn(row, f"{opt['mins']}น",
                                  lambda pp=p, o=opt: (self._send_adventure(pp, o), reopen()),
                                  color="#2c7a51", padx=6).pack(side="left", padx=2)
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._place_window_beside(win, getattr(self, "_adv_canvas", None))

    def _show_rename_window(self):
        pet = self.pet
        win, fr = self._feature_popup("✏️  ตั้งชื่อน้อง")
        self._pause_active_for_menu()
        BG, FG = "#1e1e1e", "#ffffff"
        var = tk.StringVar(value=pet.name)
        ent = tk.Entry(fr, textvariable=var, font=("Segoe UI", 13), width=16,
                       bg="#2d333d", fg=FG, insertbackground=FG, bd=0)
        ent.pack(pady=(4, 10), ipady=4)
        ent.focus_set()
        ent.selection_range(0, "end")

        def ok():
            self._rename_pet(pet, var.get())
            self._close_feature_window()
            self._draw_hud()
        ent.bind("<Return>", lambda e: ok())
        self._feature_btn(fr, "ตกลง", ok, color="#2c7a51",
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack()
        self._place_window_at_pet(win, pet)

    def _show_pets_window(self):
        win, fr = self._feature_popup(f"👪  น้อง ๆ ({len(self.pets)}/{self._pet_cap()})")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        tk.Label(fr, text=f"🪙 {self.coins}   (กดตัวน้องบนจอเพื่อเลือกดูแลก็ได้)",
                 bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 8))

        def reopen():
            self._draw_hud()
            self._show_pets_window()

        for i, p in enumerate(self.pets):
            active = (i == self.active)
            mood, _ = self._pet_mood(p)
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=3)
            name = p.name or (p.character or "เพ็ท")
            if self._is_away(p):                      # กำลังผจญภัย → โชว์เวลาเหลือ
                left = int(p.away_until - time.time())
                label = f"{'▶ ' if active else '   '}🧭 {name} (เหลือ {left // 60}:{left % 60:02d})"
            else:
                label = (f"{'▶ ' if active else '   '}{mood} {name} "
                         f"{self._gender_of(p)['emoji']}  Lv.{p.level}")
            tk.Label(row, text=label,
                     bg=BG, fg="#2ecc71" if active else FG, font=("Segoe UI", 11),
                     anchor="w", width=18).pack(side="left")
            if len(self.pets) > 1:
                self._feature_btn(row, "ปล่อย",
                                  lambda i=i: (self._release_pet(i), reopen()),
                                  color="#7a2c2c").pack(side="right", padx=(4, 0))
                # เก็บเข้ากล่อง (พักไว้) — เก็บได้เมื่อยังไม่ตาย/ไม่ผจญภัย
                if p.behavior != "dead" and not self._is_away(p):
                    self._feature_btn(row, "📦 เก็บ",
                                      lambda i=i: (self._store_pet(i), reopen()),
                                      color="#5a4a7a").pack(side="right", padx=(4, 0))
            if not active:
                self._feature_btn(row, "ดูแล",
                                  lambda i=i: (self._set_active_pet(i), reopen()),
                                  color="#2c7a51").pack(side="right")

        # ===== กล่องเก็บน้อง (เรียกออกมาได้) =====
        if self.stored:
            tk.Frame(fr, bg="#3a3f4b", height=1).pack(fill="x", pady=(8, 4))
            tk.Label(fr, text=f"📦 กล่องเก็บ ({len(self.stored)}/{config.MAX_STORED})",
                     bg=BG, fg=SUB, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            for si, pd in enumerate(self.stored):
                nm = pd.get("name") or pd.get("character") or "เพ็ท"
                gem = next((g["emoji"] for g in config.GENDERS
                            if g["id"] == pd.get("gender")), "")
                row = tk.Frame(fr, bg=BG)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=f"📦 {nm} {gem}  Lv.{pd.get('level', 1)}",
                         bg=BG, fg=FG, font=("Segoe UI", 11),
                         anchor="w", width=18).pack(side="left")
                self._feature_btn(row, "ปล่อย",
                                  lambda s=si: (self._release_stored(s), reopen()),
                                  color="#7a2c2c").pack(side="right", padx=(4, 0))
                full = len(self.pets) >= self._pet_cap()
                self._feature_btn(row, "เรียกออก",
                                  lambda s=si: (self._retrieve_pet(s), reopen()),
                                  color="#2c7a51" if not full else "#444444"
                                  ).pack(side="right")

        if len(self.pets) < self._pet_cap():
            self._feature_btn(fr, f"➕  รับเลี้ยงเพิ่ม ({config.ADOPT_COST} 🪙)",
                              self._show_adopt_window, color="#2c3e50",
                              font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(8, 0))
        # ขยายช่องน้องบนจอ (สูงสุด 10 ตัว)
        if self._pet_cap() < config.PET_SLOTS_MAX:
            cost = self._pet_slot_cost()
            self._feature_btn(
                fr, f"🖥  ขยายช่องน้องบนจอ +1  ({cost} 🪙)",
                lambda: (self._buy_pet_slot(), reopen()),
                color="#2c3e50", font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(4, 0))
        if len(self.pets) >= 2:
            self._feature_btn(fr, f"💕  ผสมพันธุ์ ({config.BREED_COST} 🪙)",
                              self._show_breed_window, color="#7a2c5a",
                              font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(4, 0))
        self._feature_btn(fr, f"🐣  ฟักไข่ ({len(self.eggs)})",
                          self._show_hatch_window, color="#7a6a2c",
                          font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(4, 0))
        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._place_window_beside(win, getattr(self, "_pets_canvas", None))

    def _show_adopt_window(self):
        win, fr = self._feature_popup("➕  รับเลี้ยงน้องใหม่")
        BG, SUB = "#1e1e1e", "#bbbbbb"
        tk.Label(fr, text=f"ค่ารับเลี้ยง {config.ADOPT_COST} 🪙   (มี {self.coins} 🪙)",
                 bg=BG, fg=SUB, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 8))
        for c in [None] + assets.list_characters():
            self._feature_btn(fr, f"🐾  {c or 'ค่าเริ่มต้น'}",
                              lambda c=c: (self._adopt_pet(c), self._show_pets_window()),
                              anchor="w", width=16).pack(fill="x", pady=2)
        self._feature_btn(fr, "ย้อนกลับ", self._show_pets_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._place_window_beside(win, getattr(self, "_pets_canvas", None))

    def _show_breed_window(self):
        win, fr = self._feature_popup("💕  ผสมพันธุ์")
        BG, SUB, FG = "#1e1e1e", "#bbbbbb", "#ffffff"
        a = getattr(self, "_breed_a", None)
        if a not in self.pets:
            a = None
            self._breed_a = None
        cond = (f"🪙 {config.BREED_COST}   เงื่อนไข: อายุ ≥ {config.BREED_MIN_AGE_DAYS} วัน"
                f" + รัก ≥ {config.BREED_MIN_AFFECTION}")
        tk.Label(fr, text=cond, bg=BG, fg=SUB, font=("Segoe UI", 9)
                 ).pack(anchor="w", pady=(2, 2))
        tk.Label(fr, text=(f"เลือกตัวที่ 2 (คู่กับ {a.name})" if a else "เลือกพ่อแม่ตัวที่ 1"),
                 bg=BG, fg="#f1c40f", font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", pady=(0, 6))

        def choose(p):
            if self._breed_a is None:
                self._breed_a = p
                self._show_breed_window()
            else:
                first = self._breed_a
                self._breed_a = None
                self._breed(first, p)
                self._show_pets_window()

        for p in self.pets:
            ok = self._can_breed(p) and p is not a
            if ok and a is not None and config.BREED_NEED_DIFFERENT_GENDER \
                    and p.gender == a.gender:
                ok = False                        # ต้องเป็นเพศตรงข้ามกับตัวที่ 1
            name = p.name or (p.character or "เพ็ท")
            tag = "✓ " if p is a else ""
            row = tk.Frame(fr, bg=BG)
            row.pack(fill="x", pady=2)
            gg = self._gender_of(p)
            tk.Label(row, text=f"{tag}{name} {gg['emoji']} ❤{int(p.affection)} "
                              f"· {self._age_days(p)}ว.",
                     bg=BG, fg=FG if (ok or p is a) else "#777777",
                     font=("Segoe UI", 11), anchor="w", width=18).pack(side="left")
            if p is a:
                tk.Label(row, text="ตัวที่ 1", bg=BG, fg="#2ecc71",
                         font=("Segoe UI", 9)).pack(side="right")
            elif ok:
                self._feature_btn(row, "เลือก", lambda pp=p: choose(pp),
                                  color="#2c7a51").pack(side="right")
            else:
                tk.Label(row, text="🔒", bg=BG, fg=SUB,
                         font=("Segoe UI", 10)).pack(side="right")
        self._feature_btn(fr, "ย้อนกลับ",
                          lambda: (setattr(self, "_breed_a", None),
                                   self._show_pets_window()),
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(10, 0))
        self._place_window_beside(win, getattr(self, "_pets_canvas", None))

    def _show_settings_popup(self):
        """ป๊อปอัปตั้งค่าแบบกำหนดเอง: ธีมเข้ม มี hover เด้งเหนือปุ่ม ⚙"""
        items = [
            ("⚙", "ตั้งค่า", self._show_settings_window, "#2c3e50"),
            ("🐾", "จัดการตัวละคร", self._show_character_manager, "#2c3e50"),
            ("🐲", "จัดการมอนสเตอร์", self._show_monster_manager, "#2c3e50"),
            ("🔄", "อัพเดทโปรแกรม", self.update_program, "#2c3e50"),
            ("ℹ", "เกี่ยวกับโปรแกรม", self.show_about, "#2c3e50"),
            ("sep", None, None, None),
            ("❌", "ออกจากระบบ", self.quit, "#c0392b"),
        ]
        BG, FG = "#1e1e1e", "#ffffff"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg="#5a5a5a")                 # ขอบ 2px
        frame = tk.Frame(win, bg=BG)
        frame.pack(padx=2, pady=2)
        for icon, text, cmd, hover in items:
            if icon == "sep":                       # เส้นแบ่งกลุ่มเมนู
                tk.Frame(frame, bg="#3a3a3a", height=1).pack(fill="x", padx=8, pady=4)
                continue
            row = tk.Label(frame, text=f"   {icon}    {text}", anchor="w",
                           bg=BG, fg=FG, font=("Segoe UI", 12),
                           padx=18, pady=9, cursor="hand2")
            row.pack(fill="x")
            row.bind("<Enter>", lambda e, r=row, c=hover: r.configure(bg=c))
            row.bind("<Leave>", lambda e, r=row: r.configure(bg=BG))
            row.bind("<Button-1>", lambda e, c=cmd: self._settings_choose(c))
        self._settings_win = win
        self._bind_autoclose(win, self._close_settings_popup)
        win.bind("<Escape>", lambda e: self._close_settings_popup())
        self._center_on_screen(win)

    def _draw_button(self, x0, y0, x1, y1, text, tag, enabled=True):
        """วาดปุ่มกดบน canvas (ถ้า enabled=False จะเป็นสีจางและกดไม่ได้)"""
        tags = ("hud", tag) if enabled else ("hud",)
        self.canvas.create_rectangle(x0, y0, x1, y1,
                                     fill="#2c3e50" if enabled else "#2a2a2a",
                                     outline="#5a5a5a", width=2, tags=tags)
        self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text,
                                 fill="#ffffff" if enabled else "#6a6a6a",
                                 font=("Segoe UI", 12, "bold"), tags=tags)

    def _draw_icon_button(self, x0, y0, x1, y1, icon, tag, enabled=True,
                          accent=False, accent_color="#2c7a51"):
        """วาดปุ่มไอคอนล้วน; accent=True = ไฮไลต์ (กำลังเปิดอยู่)"""
        tags = ("hud", tag) if enabled else ("hud",)
        fill = "#2a2a2a" if not enabled else (accent_color if accent else "#2c3e50")
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill,
                                     outline="#5a5a5a", width=2, tags=tags)
        self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=icon,
                                 fill="#ffffff" if enabled else "#6a6a6a",
                                 font=("Segoe UI Emoji", 12), tags=tags)

    def _draw_pill(self, xr, yc, text, color):
        """ป้ายข้อความเล็ก พื้นเข้ม วางชิดขวาที่ตำแหน่ง (xr, yc)"""
        t = self.canvas.create_text(xr - 10, yc, text=text, anchor="e",
                                    fill=color, font=("Segoe UI", 11, "bold"),
                                    tags="hud")
        bb = self.canvas.bbox(t)
        if bb:
            bx0, by0, bx1, by1 = bb
            r = self.canvas.create_rectangle(bx0 - 10, by0 - 5, bx1 + 6, by1 + 5,
                                             fill="#1e1e1e", outline="#5a5a5a",
                                             width=2, tags="hud")
            self.canvas.tag_lower(r, t)

    def _draw_hud(self):
        """ปุ่มเมนูเดียว ☰ มุมขวาล่าง (ลากย้ายได้) — กดแล้วเด้งเมนูหลักกลางจอ"""
        self.canvas.delete("hud")
        self.canvas.delete("hudedge")
        margin = 18
        # มุมขวาล่างของจอหลัก; ใช้ขอบบน taskbar เป็นฐานล่าง (ปุ่มจึงอยู่เหนือ taskbar)
        right = -self.vx0 + self.primary_w
        bottom = self._work_bottom_at(right - margin)
        bw = 46                                # ปุ่มเมนูใหญ่ขึ้น เห็นชัด
        x1 = max(bw + 4, min(self.sw - 2, (right - margin) + self.hud_offset_x))
        y1 = max(bw + 4, min(self.sh - 2, (bottom - margin) + self.hud_offset_y))
        self.hud_offset_x = x1 - (right - margin)   # เขียนกลับค่าที่ clamp แล้ว
        self.hud_offset_y = y1 - (bottom - margin)
        self._hud_x1, self._hud_y1 = x1, y1         # เก็บไว้วางป๊อปอัปข้างเมนู
        self._hud_handle_rect = (x1 - bw, y1 - bw, x1, y1)
        # มีอะไรรอทำ (เช็คอิน/เควส/ไข่พร้อมฟัก) → โชว์จุดแดงเตือนบนปุ่ม
        alert = (self._can_checkin() or self._any_quest_claimable()
                 or any(self._egg_ready(e) for e in self.eggs))
        self._draw_edge_handle(self._hud_handle_rect, alert)

    def _main_menu_cell(self, parent, emoji, label, cmd, accent=False,
                        sub="", accent_color="#2c7a51"):
        """ช่องปุ่มในกริดเมนูหลัก: ไอคอนใหญ่ + ป้ายชื่อ + จุดเตือน (มี hover)"""
        BASE, HOVER, FG, SUB = "#2d333d", "#3a4150", "#ffffff", "#aab2bf"
        cell = tk.Frame(parent, bg=BASE, cursor="hand2",
                        highlightbackground="#3a3f4b", highlightthickness=1)
        ic = tk.Label(cell, text=emoji, bg=BASE, fg=FG,
                      font=("Segoe UI Emoji", 22))
        ic.pack(pady=(10, 0))
        lb = tk.Label(cell, text=label, bg=BASE, fg=FG, font=("Segoe UI", 10, "bold"))
        lb.pack()
        sb = tk.Label(cell, text=sub or " ", bg=BASE,
                      fg=accent_color if accent else SUB, font=("Segoe UI", 8))
        sb.pack(pady=(0, 8))
        kids = [cell, ic, lb, sb]

        def enter(_e):
            for w in kids:
                w.configure(bg=HOVER)
        def leave(_e):
            for w in kids:
                w.configure(bg=BASE)
        def click(_e):
            cmd()
        for w in kids:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", click)
        if accent:                                   # จุดเตือนมุมขวาบน
            dot = tk.Label(cell, text="●", bg=BASE, fg="#e74c3c",
                           font=("Segoe UI", 9))
            dot.place(relx=1.0, x=-12, y=4, anchor="ne")
            dot.bind("<Button-1>", click)
        return cell

    def _show_main_menu(self):
        """เมนูหลัก — เด้งกลางจอ รวมทุกเมนูเกมเป็นกริดเดียว (แทนคอลัมน์ปุ่มด้านขวาเดิม)"""
        win, fr = self._feature_popup("☰  เมนู")
        BG, SUB = "#1e1e1e", "#bbbbbb"
        has_pet = bool(self.pets)
        # ไม่มีน้อง = ไม่โชว์เลเวล
        head = f"🪙 {self.coins}      🐾 {len(self.pets)}/{self._pet_cap()}"
        if has_pet:
            head += f"      Lv.{self.pet.level}"
        tk.Label(fr, text=head, bg=BG, fg=SUB,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 10))

        def toggle_combat():
            if not has_pet:                       # ไม่มีน้อง = กดต่อสู้ไม่ได้
                self.show_bubble("ต้องมีน้องก่อนถึงต่อสู้ได้ — ฟักไข่ 🥚")
                return
            self._toggle_combat(None)
            self._show_main_menu()

        any_away = any(self._is_away(p) for p in self.pets)
        eggs_ready = any(self._egg_ready(e) for e in self.eggs)
        items = [
            ("⚔" if self.combat_enabled else "🛡", "ต่อสู้", toggle_combat,
             has_pet and self.combat_enabled,
             ("เปิดอยู่" if self.combat_enabled else "ปิดอยู่") if has_pet else "ต้องมีน้อง",
             "#c0392b" if self.combat_enabled else "#7f8c8d"),
            ("👪", "น้อง ๆ", self._show_pets_window, len(self.pets) > 1,
             f"{len(self.pets)} ตัว", "#2c7a51"),
            ("🐣", "ฟักไข่", self._show_hatch_window, eggs_ready,
             f"{len(self.eggs)} ฟอง" + (" พร้อม!" if eggs_ready else ""), "#e67e22"),
            ("🧭", "ผจญภัย", self._show_adventure_window, any_away,
             "มีตัวออกไป" if any_away else "", "#2c7a51"),
            ("📋", "เควส", self._show_quest_window, self._any_quest_claimable(),
             "รับรางวัลได้!" if self._any_quest_claimable() else "", "#f1c40f"),
            ("📅", "เช็คอิน", self._show_checkin_window, self._can_checkin(),
             "เช็คอินได้!" if self._can_checkin() else "", "#b8860b"),
            ("🛒", "ร้านค้า", self._show_shop_window, False, "", "#2c7a51"),
            ("🎒", "กระเป๋า", self._show_bag_window, bool(self.inventory),
             "", "#7a6a2c"),
            ("🏆", "ความสำเร็จ", self._show_achievements_window, False, "", "#2c7a51"),
            ("⚙", "ตั้งค่า",
             lambda: (self._close_feature_window(), self._show_settings_popup()),
             False, "", "#2c7a51"),
        ]
        grid = tk.Frame(fr, bg=BG)
        grid.pack()
        cols = 4
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="mm")
        for i, (emoji, label, cmd, accent, sub, ac) in enumerate(items):
            self._main_menu_cell(grid, emoji, label, cmd, accent, sub, ac).grid(
                row=i // cols, column=i % cols, padx=5, pady=5, sticky="nsew")

        self._feature_btn(fr, "ปิด", self._close_feature_window,
                          font=("Segoe UI", 11, "bold"), padx=20, pady=4
                          ).pack(pady=(12, 0))
        self._center_on_screen(win)

    # ----------------------------------------------------------- hunger alert
    def _check_hunger(self):
        """ถ้าความอิ่มต่ำกว่าเกณฑ์ ให้แจ้งเตือน (เด้งทันทีตอนเริ่มหิว และเตือนซ้ำตามรอบ)"""
        if not self.pets:
            return
        hungry = (self.pet.fullness < config.HUNGRY_THRESHOLD
                  and self.pet.behavior != "dead")
        now = self.tick_count * config.TICK_MS / 1000.0   # วินาทีโดยประมาณ
        if hungry:
            renotify = config.HUNGRY_RENOTIFY_SEC
            due = renotify > 0 and (now - self._last_hunger_notify) >= renotify
            if not self._was_hungry or due:
                self._last_hunger_notify = now
                self._notify_hungry()
        self._was_hungry = hungry

    def _notify_hungry(self):
        self.notify("🍽 เพ็ทหิวแล้ว",
                    "พามาหาอะไรกินหน่อยนะ 🐾  (ปุ่ม 🐾 → 🍎 ให้อาหาร)")
        if not self.hidden_for_fullscreen:
            self.show_bubble("หิวแล้ว... 🍽")

    def notify(self, title, message):
        """แจ้งเตือนผ่าน Windows toast — เห็นได้แม้กำลังเปิดโปรแกรมอื่นเต็มจอ
        ใช้ PowerShell เรียก ToastNotificationManager (ไม่ต้องลงไลบรารีเพิ่ม)"""
        def esc(s):
            s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return s.replace("'", "''")   # หนีเครื่องหมาย ' สำหรับสตริงใน PowerShell
        xml = (f"<toast><visual><binding template=\"ToastGeneric\">"
               f"<text>{esc(title)}</text><text>{esc(message)}</text>"
               f"</binding></visual></toast>")
        # AUMID ของ PowerShell — ใช้แล้ว toast แสดงได้โดยไม่ต้องลงทะเบียนแอป
        aumid = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
            "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom,ContentType=WindowsRuntime]|Out-Null;"
            "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$x.LoadXml('{xml}');"
            "$t=New-Object Windows.UI.Notifications.ToastNotification $x;"
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{aumid}').Show($t);"
        )
        try:
            b64 = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64],
                creationflags=0x08000000,   # CREATE_NO_WINDOW (ไม่มีหน้าต่าง console เด้ง)
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # --------------------------------------------------- fullscreen detection
    def _collect_own_hwnds(self):
        """รวบรวม HWND ของหน้าต่างเราเอง ไว้ยกเว้นตอนตรวจ fullscreen"""
        hwnds = set()
        try:
            hwnds.add(int(self.root.winfo_id()))
        except Exception:
            pass
        try:
            hwnds.add(int(self.root.wm_frame(), 16))
        except Exception:
            pass
        return hwnds

    def _foreground_is_fullscreen(self):
        """True ถ้าหน้าต่างที่อยู่หน้าสุด (foreground) ครอบ 'เต็มจอ' พอดี
        เช่น เกม/วิดีโอ fullscreen — เอาไว้ซ่อนเพ็ทไม่ให้ไปบัง
        (หน้าต่างที่ขยายใหญ่สุด/maximize ปกติจะ 'ไม่' เต็มจอ เพราะยังเหลือ taskbar)"""
        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetShellWindow.restype = wintypes.HWND
            user32.MonitorFromWindow.restype = wintypes.HANDLE   # HMONITOR
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            if int(hwnd) in self._own_hwnds:
                return False
            if int(hwnd) == int(user32.GetShellWindow() or 0):
                return False
            # ข้ามเดสก์ท็อป (Progman / WorkerW)
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in ("Progman", "WorkerW"):
                return False
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
            hmon = user32.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return False
            m = mi.rcMonitor   # ขอบจอจริง (ไม่ใช่ rcWork ที่หัก taskbar)
            # ครอบเต็มจอจริง (เผื่อคลาด 1px)
            return (rect.left <= m.left + 1 and rect.top <= m.top + 1 and
                    rect.right >= m.right - 1 and rect.bottom >= m.bottom - 1)
        except Exception:
            return False

    def _update_fullscreen_visibility(self):
        fs = self._foreground_is_fullscreen()
        if fs and not self.hidden_for_fullscreen:
            self.hidden_for_fullscreen = True
            self.root.withdraw()                       # ซ่อนทั้งหน้าต่าง
        elif not fs and self.hidden_for_fullscreen:
            self.hidden_for_fullscreen = False
            self.root.deiconify()                      # แสดงกลับ
            self.root.wm_attributes("-topmost", True)  # ย้ำให้อยู่บนสุดเหมือนเดิม

    def _draw_monster_hud(self):
        """บาร์ HP + ตัวเลข HP/ATK ลอยเหนือหัวมอนสเตอร์ (ตามตำแหน่งมอน)"""
        self.canvas.delete("monhud")
        m = self.monster
        if m is None:
            return
        # บอส: บาร์กว้างกว่า สีทอง / มอนปกติ: บาร์แดง
        bar_w, bar_h = (96, 9) if m.is_boss else (60, 7)
        hp_color = "#f1c40f" if m.is_boss else "#e74c3c"
        cx = m.x
        y0 = m.top_y() - 16
        x0 = cx - bar_w / 2
        ratio = max(0.0, min(1.0, m.hp_ratio()))
        self.canvas.create_rectangle(x0, y0, x0 + bar_w, y0 + bar_h,
                                     fill="#3a3a3a", outline="#000000", tags="monhud")
        self.canvas.create_rectangle(x0, y0, x0 + bar_w * ratio, y0 + bar_h,
                                     fill=hp_color, outline="", tags="monhud")
        # ตัวเลข HP / ATK (มีพื้นหลังเข้มให้อ่านง่ายบนทุกฉากหลัง)
        label = (f"👑 บอส  HP {int(m.hp)}/{m.max_hp}  ATK {m.atk}" if m.is_boss
                 else f"HP {int(m.hp)}/{m.max_hp}   ATK {m.atk}")
        txt = self.canvas.create_text(cx, y0 - 9, text=label,
                                      fill="#ffffff", font=("Segoe UI", 9, "bold"),
                                      tags="monhud")
        bx0, by0, bx1, by1 = self.canvas.bbox(txt)
        pad = 3
        bg = self.canvas.create_rectangle(bx0 - pad, by0 - pad, bx1 + pad, by1 + pad,
                                          fill="#222222", outline="", tags="monhud")
        self.canvas.tag_lower(bg, txt)

    def _draw_combat_extras(self):
        """ขณะสู้: วาดเกจเดือด (rage) เหนือหัวน้องทุกตัว — เต็มแล้วปล่อยท่าไม้ตายเอง"""
        self.canvas.delete("rage")
        if self.monster is None:
            return
        for p in self.pets:
            if p.behavior != "fight" or self._is_away(p):
                continue
            full = p.rage >= config.RAGE_MAX
            bw, bh = 40, 5
            cx = p.x
            y0 = p.top_y() - 10
            x0 = cx - bw / 2
            self.canvas.create_rectangle(x0 - 1, y0 - 1, x0 + bw + 1, y0 + bh + 1,
                                         fill="#1e1e1e", outline="#000000", tags="rage")
            ratio = max(0.0, min(1.0, p.rage / config.RAGE_MAX))
            self.canvas.create_rectangle(x0, y0, x0 + bw * ratio, y0 + bh,
                                         fill="#ffd23f" if full else "#e67e22",
                                         outline="", tags="rage")
            if full:                                  # เต็ม = กำลังจะปล่อยท่าเอง
                self.canvas.create_text(x0 + bw + 8, y0 + bh / 2, text="⚡",
                                        font=("Segoe UI Emoji", 11), tags="rage")

    def _entities(self):
        ents = list(self.pets)
        for p in self.pets:
            if p.food is not None:
                ents.append(p.food)
        if self.monster is not None:
            ents.append(self.monster)
        return ents

    def show_about(self):
        """กล่องข้อมูล 'เกี่ยวกับโปรแกรม'"""
        self.root.wm_attributes("-topmost", False)
        try:
            messagebox.showinfo(
                "เกี่ยวกับโปรแกรม",
                "LOVE_PET  🐾\n"
                "เดสก์ท็อปเพ็ตน่ารัก ๆ บนหน้าจอ\n\n"
                "การใช้งาน\n"
                "  • กดที่ตัวน้อง : เลือกตัวที่ดูแล\n"
                "  • ลาก              : ย้ายตำแหน่ง\n"
                "  • ปุ่ม 🐾          : ให้อาหาร/ลูบ/นอน/อาบน้ำ\n"
                "  • ปุ่ม 👪          : เลี้ยงหลายตัว / รับเลี้ยงเพิ่ม\n"
                "  • ปุ่ม 🎮          : เกม / ตู้เสื้อผ้า / ทริค / ความสำเร็จ\n"
                "  • ปุ่ม ⚙           : ตั้งค่า (อัพเดท / ออก)\n\n"
                "อัพเดทโค้ดล่าสุดได้ที่  ⚙ → อัพเดทโปรแกรม",
            )
        finally:
            self.root.wm_attributes("-topmost", True)

    def update_program(self):
        """ดึงโค้ดล่าสุดจาก GitHub แล้วเปิดโปรแกรมใหม่ (เก็บเซฟเกมไว้)"""
        bat = os.path.join(os.path.dirname(os.path.abspath(__file__)), "update.bat")
        if not os.path.exists(bat):
            messagebox.showinfo("อัพเดท", "ไม่พบไฟล์ update.bat ในโฟลเดอร์โปรแกรม")
            return
        if not messagebox.askyesno(
                "อัพเดทโปรแกรม",
                "จะดึงโค้ดล่าสุดจาก GitHub แล้วเปิดโปรแกรมใหม่\n"
                "(เซฟเกมจะถูกเก็บไว้ให้)\n\nดำเนินการต่อหรือไม่?"):
            return
        self._save_progress()
        try:
            # เปิด update.bat ในหน้าต่างใหม่ที่แยกจากตัวโปรแกรม แล้วปิดตัวเอง
            subprocess.Popen(
                ["cmd", "/c", "start", "", bat],
                cwd=os.path.dirname(bat),
            )
        except Exception as e:
            messagebox.showerror("อัพเดท", f"เปิดตัวอัพเดทไม่ได้: {e}")
            return
        self.root.destroy()

    def quit(self):
        self._save_progress()
        self.root.destroy()

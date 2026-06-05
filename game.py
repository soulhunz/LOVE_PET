# -*- coding: utf-8 -*-
"""โลกของ Desktop Pet: หน้าต่างโปร่งใสเต็มจอ + ลูปเกม + อินพุต + การต่อสู้"""
import base64
import ctypes
from ctypes import wintypes
import os
import random
import subprocess
import tkinter as tk
from tkinter import messagebox

import config
import assets
import save
from entities import Pet, Monster, Food


def _sign(n):
    return (n > 0) - (n < 0)


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
        # เลือกตัวละครที่บันทึกไว้ (ค้นไฟล์เพ็ทจากโฟลเดอร์ตัวละครก่อน assets/)
        self.character = self._read_saved_character()
        assets.set_character_dir(assets.character_path(self.character) if self.character else None)
        self.pet_forms = self._load_pet_forms()      # ทุกร่างของเพ็ท (Evolution)
        self.monster_anims = self._load_anims(config.MONSTER_SPRITES, "monster", config.MONSTER_SIZE)
        fa = assets.load_sprite(config.FOOD_SPRITES) or assets.build_fallback("food", config.FOOD_SIZE)
        self.food_anims = {"idle": fa}

        # สร้างเพ็ท (เริ่มร่างแรกไว้ก่อน แล้วค่อยปรับตามเลเวลที่โหลดมา)
        self.cur_form = 0
        self.pet = Pet(self.canvas, self.pet_forms[0]["anims"], self.sw * 0.35, 0)
        self._load_progress()
        self._apply_pet_form(self._pet_form_for_level(self.pet.level))
        self._drop_to_ground(self.pet)
        self.pet.sync_position()

        self.monster = None
        self.food = None
        # นับถอยหลัง (วินาที) จนกว่ามอนสเตอร์ตัวถัดไปจะสุ่มเกิดเอง
        self.monster_spawn_in = random.randint(config.MONSTER_SPAWN_MIN_SEC,
                                               config.MONSTER_SPAWN_MAX_SEC)
        self.effects = []          # [{"item":id, "ttl":int, "dy":float}]
        self.bubble_items = []
        self.bubble_ttl = 0
        self.show_hud = True            # แสดงเมนูด้านขวาล่าง
        self.show_status_panel = False  # 📊 กดเพื่อโชว์แผงสถานะ (เริ่มต้น: ซ่อน)
        self.show_actions = False       # 🍎 กดเพื่อโชว์เมนูให้อาหาร/ลูบหัว
        # self.combat_enabled ถูกตั้งใน _load_progress() (เรียกไปแล้วด้านบน)
        self.tick_count = 0

        # อินพุต
        self._down = False
        self._dragged = False
        self._press_xy = (0, 0)
        self.canvas.tag_bind(self.pet.item, "<ButtonPress-1>", self.on_press)
        # ปุ่มเมนูด้านขวา (วาดใหม่ทุกเฟรม จึงผูกกับ tag)
        hud_btns = ("btn_status", "btn_actions", "btn_combat",
                    "btn_feed", "btn_pat", "btn_char", "btn_settings")
        for _tag in hud_btns:
            self.canvas.tag_bind(_tag, "<Enter>",
                                 lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind(_tag, "<Leave>",
                                 lambda e: self.canvas.config(cursor=""))
        self.canvas.tag_bind("btn_status", "<Button-1>", self._toggle_status_panel)
        self.canvas.tag_bind("btn_actions", "<Button-1>", self._toggle_actions)
        self.canvas.tag_bind("btn_combat", "<Button-1>", self._toggle_combat)
        self.canvas.tag_bind("btn_feed", "<Button-1>",
                             lambda e: self._menu_click(self.feed))
        self.canvas.tag_bind("btn_pat", "<Button-1>",
                             lambda e: self._menu_click(self.pet_react))
        self.canvas.tag_bind("btn_char", "<Button-1>",
                             lambda e: self._show_character_popup())
        self.canvas.tag_bind("btn_settings", "<Button-1>", self._on_settings_click)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Button-3>", self.on_menu)
        self.root.bind("<Escape>", lambda e: self.quit())

        self._build_menu()

        # ซ่อนเพ็ทเมื่อมีโปรแกรมอื่นเปิดเต็มจอ (เกม/วิดีโอ fullscreen)
        self.root.update_idletasks()
        self._own_hwnds = self._collect_own_hwnds()
        self.hidden_for_fullscreen = False

        # การแจ้งเตือนหิว
        self._was_hungry = False
        self._last_hunger_notify = -1e9

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

    def _load_pet_forms(self):
        """โหลดสไปรต์ของทุกร่างแปลงร่างตาม config.PET_EVOLUTIONS
        แต่ละร่างใช้ไฟล์ '{prefix}_{state}.gif/png' (state เดียวกับ PET_SPRITES)
        ถ้าร่างไหน 'ไม่มีไฟล์เลย' จะใช้ภาพของร่างก่อนหน้า (ตัวละครเดียวกัน) แทน
        เพื่อให้ตัวละครที่ใส่แค่ pet_idle เห็นภาพนั้นได้ทุกเลเวล (ไม่กลายเป็นตัวสำรอง)"""
        states = list(config.PET_SPRITES.keys())
        forms = []
        for ev in config.PET_EVOLUTIONS:
            prefix = ev["prefix"]
            anims = {}
            for s in states:
                a = assets.load_sprite([f"{prefix}_{s}.gif", f"{prefix}_{s}.png"])
                if a:
                    anims[s] = a
            if not anims:                       # ร่างนี้ไม่มีไฟล์เลย
                if forms:                       # ใช้ภาพร่างก่อนหน้า (ตัวละครเดียวกัน)
                    anims = forms[-1]["anims"]
                else:                           # ร่างแรกก็ไม่มี -> วาดตัวสำรอง
                    anims = {"idle": assets.build_fallback(
                        "pet", ev.get("size", config.PET_SIZE), ev.get("color"))}
            elif "idle" not in anims:           # มีบางสถานะแต่ขาด idle
                anims["idle"] = assets.build_fallback(
                    "pet", ev.get("size", config.PET_SIZE), ev.get("color"))
            forms.append({"level": ev["level"], "name": ev.get("name", prefix), "anims": anims})
        if not forms:   # สำรอง ถ้าไม่ได้ตั้ง PET_EVOLUTIONS ไว้
            anims = self._load_anims(config.PET_SPRITES, "pet", config.PET_SIZE)
            forms.append({"level": 1, "name": "pet", "anims": anims})
        return forms

    def _read_saved_character(self):
        """อ่านชื่อตัวละครที่บันทึกไว้ — คืน None ถ้าไม่มี/โฟลเดอร์หายไป (ใช้ assets/ ปกติ)"""
        name = save.load().get("character")
        return name if name and name in assets.list_characters() else None

    def set_character(self, name):
        """สลับตัวละคร: name = ชื่อโฟลเดอร์ใน characters/ หรือ None = ค่าเริ่มต้น (assets/)
        โหลดสไปรต์เพ็ทใหม่ทั้งหมดแล้วใช้ร่างตามเลเวลปัจจุบัน"""
        self.character = name
        assets.set_character_dir(assets.character_path(name) if name else None)
        self.pet_forms = self._load_pet_forms()
        self._apply_pet_form(self._pet_form_for_level(self.pet.level))
        self._save_progress()
        self.show_bubble(f"เปลี่ยนตัวละคร: {name or 'ค่าเริ่มต้น'} ✨")

    def _cycle_character(self):
        """วนไปตัวละครถัดไป (ค่าเริ่มต้น → แต่ละโฟลเดอร์ → วนกลับ) — ใช้กับปุ่ม 🐾"""
        options = [None] + assets.list_characters()
        try:
            i = options.index(self.character)
        except ValueError:
            i = 0
        self.set_character(options[(i + 1) % len(options)])

    def _pet_form_for_level(self, level):
        """ดัชนีร่างสูงสุดที่ปลดล็อกได้ ณ เลเวลนี้"""
        idx = 0
        for i, f in enumerate(self.pet_forms):
            if level >= f["level"]:
                idx = i
        return idx

    def _apply_pet_form(self, idx, announce=False):
        """สลับชุดสไปรต์ของเพ็ทเป็นร่างที่ idx (ขนาดอาจเปลี่ยน จึงจัดให้ยืนบนพื้นใหม่)"""
        idx = max(0, min(idx, len(self.pet_forms) - 1))
        self.cur_form = idx
        form = self.pet_forms[idx]
        self.pet.anims = form["anims"]
        self.pet.frame_i = 0
        self.pet._render()
        self._drop_to_ground(self.pet)
        self.pet.sync_position()
        if announce:
            self.show_bubble(f"✨ แปลงร่าง! → {form['name']}")
            self.spawn_effect(self.pet.x, self.pet.top_y(), "🌟")

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
        # เมนูคลิกขวา: เปลี่ยนตัวละคร (เปิดหน้าต่างเลือก) / ดูสถานะ
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="🎭  เปลี่ยนตัวละคร", command=self._show_character_popup)
        m.add_command(label="📊  ดูสถานะ / เลเวล", command=self.show_status)
        self.menu = m

        # ป๊อปอัปแบบกำหนดเอง (ธีมเข้ม) — สร้างใหม่ทุกครั้งที่เปิด
        self._settings_win = None
        self._char_win = None

    def _show_character_popup(self):
        """หน้าต่างเลือกตัวละคร (ธีมเข้ม มี hover + ✓ ตัวที่ใช้อยู่) อยู่กลางจอหลัก"""
        self._close_settings_popup()
        if getattr(self, "_char_win", None) is not None:
            self._close_char_popup()
            return
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
    def on_press(self, e):
        self._down = True
        self._dragged = False
        self._press_xy = (e.x, e.y)

    def on_drag(self, e):
        if not self._down:
            return
        if abs(e.x - self._press_xy[0]) + abs(e.y - self._press_xy[1]) > 6:
            self._dragged = True
            self.pet.behavior = "drag"
            self.pet.x = max(20, min(self.sw - 20, e.x))
            self.pet.y = max(20, min(self.sh - 20, e.y))
            self.pet.set_state("idle")
            self.pet.sync_position()

    def on_release(self, e):
        if not self._down:
            return
        self._down = False
        if self._dragged:
            self._drop_to_ground(self.pet)   # ปล่อยแล้วร่วงลงพื้น
            self.pet.behavior = "wander"
            self.pet.vx = 0
        else:
            self.pet_react()                 # คลิกเฉย ๆ = โต้ตอบ

    def on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    # ---------------------------------------------------------------- actions
    def pet_react(self):
        if self.pet.behavior == "ko":
            return
        self.pet.happy = min(100, self.pet.happy + 8)
        self.show_bubble(random.choice(["❤", "♪", "สบายดี!", "ฮุ่ย~"]))
        self.add_xp(config.XP_PER_PET)

    def feed(self):
        # กำลังสู้กับมอน/บอส → กินไม่ได้ (ต้องเคลียร์ศัตรูก่อน)
        if self.monster is not None:
            self.show_bubble("กำลังสู้อยู่ เดี๋ยวค่อยกิน! ⚔")
            return
        if self.pet.behavior == "ko" or self.food is not None:
            return
        # วางอาหารตรงตำแหน่งน้องแล้วกินทันที (ไม่ต้องเดินไปหา)
        self.food = Food(self.canvas, self.food_anims, self.pet.x, 0)
        self._drop_to_ground(self.food)
        self.food.sync_position()
        self.pet.behavior = "goto_food"
        self.pet.eat_timer = None

    def _tick_spawn_monster(self):
        """นับถอยหลังเพื่อให้มอนสเตอร์สุ่มเกิดเอง (เรียกทุก ~1 วินาที)"""
        if not getattr(self, "combat_enabled", True):
            return                              # โหมดเลี้ยงอย่างเดียว: ไม่เกิดมอน
        if self.monster is not None or self.pet.behavior in ("ko", "drag", "goto_food"):
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
        # ขนาด/อนิเมชัน (บอสตัวใหญ่กว่า)
        if is_boss:
            anims = self._scaled_anims(self.monster_anims, config.BOSS_SIZE_MULT)
            width = config.MONSTER_SIZE * config.BOSS_SIZE_MULT
        else:
            anims = self.monster_anims
            width = config.MONSTER_SIZE

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

        # ถ้ามีอาหารค้างอยู่ (กำลังกิน) ให้ยกเลิก เพราะต้องไปสู้ก่อน
        if self.food is not None:
            self.food.destroy()
            self.food = None
            self.pet.eat_timer = None

        self.monster = m
        self._drop_to_ground(m)
        m.sync_position()
        self.pet.behavior = "fight"
        if is_boss:
            self.show_bubble(f"👑 บอสเวฟ {self.wave_round} มาแล้ว!")
        else:
            self.show_bubble(f"⚔ มอนสเตอร์ ({self.wave_step}/{config.WAVE_LENGTH})")

    def toggle_stand(self):
        """สลับโหมด 'ยืนเฉย ๆ' (ไม่เดิน แต่หันซ้าย-ขวา) กับเดินเล่นปกติ"""
        if self.pet.behavior == "ko":
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
        self.show_hud = not self.show_hud
        if not self.show_hud:
            self.canvas.delete("hud")

    def add_xp(self, amount):
        """เพิ่ม XP และเลื่อนเลเวลถ้าครบ (เลเวลอัปจะฟื้นเลือดเต็ม)"""
        p = self.pet
        p.xp += amount
        leveled = False
        while p.xp >= p.xp_to_next():
            p.xp -= p.xp_to_next()
            p.level += 1
            leveled = True
        if leveled:
            p.hp = p.max_hp()
            self.show_bubble(f"⬆ LEVEL UP! Lv.{p.level}")
            self.spawn_effect(p.x, p.top_y(), "✨")
            new_form = self._pet_form_for_level(p.level)
            if new_form != self.cur_form:
                self._apply_pet_form(new_form, announce=True)
        self._save_progress()

    def show_status(self):
        p = self.pet
        # ปิด topmost ชั่วคราวเพื่อให้กล่องข้อความแสดงทับเพ็ทได้
        self.root.wm_attributes("-topmost", False)
        messagebox.showinfo(
            "สถานะของเพ็ท",
            f"ร่าง: {self.pet_forms[self.cur_form]['name']}\n"
            f"เวฟ: {self.wave_round}  (มอนตัวที่ {self.wave_step}/{config.WAVE_LENGTH})\n"
            f"เลเวล: {p.level}\n"
            f"XP: {p.xp} / {p.xp_to_next()}\n"
            f"HP: {int(p.hp)} / {p.max_hp()}\n"
            f"พลังโจมตี: {p.attack()}\n"
            f"ความอิ่ม: {int(p.fullness)} / 100\n"
            f"ความสุข: {int(p.happy)} / 100",
        )
        self.root.wm_attributes("-topmost", True)

    def _load_progress(self):
        data = save.load()
        self.pet.level = max(1, int(data.get("level", 1)))
        self.pet.xp = max(0, int(data.get("xp", 0)))
        self.pet.fullness = float(data.get("fullness", 80))
        self.pet.happy = float(data.get("happy", 80))
        hp = float(data.get("hp", self.pet.max_hp()))
        self.pet.hp = min(hp, self.pet.max_hp())
        if self.pet.hp <= 0:
            self.pet.hp = self.pet.max_hp()
        self.wave_round = max(1, int(data.get("wave_round", 1)))
        self.wave_step = min(config.WAVE_LENGTH, max(1, int(data.get("wave_step", 1))))
        self.combat_enabled = bool(data.get("combat_enabled", True))

    def _save_progress(self):
        p = self.pet
        save.save({
            "level": p.level,
            "xp": p.xp,
            "hp": round(p.hp, 1),
            "fullness": round(p.fullness, 1),
            "happy": round(p.happy, 1),
            "wave_round": self.wave_round,
            "wave_step": self.wave_step,
            "combat_enabled": self.combat_enabled,
            "character": self.character,
        })

    # ------------------------------------------------------------------ loops
    def run(self):
        self._tick()
        self._anim()
        self.root.mainloop()

    def _anim(self):
        for ent in self._entities():
            ent.advance_frame()
        self.root.after(config.ANIM_MS, self._anim)

    def _tick(self):
        self.tick_count += 1
        # ทุก ~0.5 วิ: ซ่อน/แสดงเพ็ทตามว่ามีโปรแกรมอื่นเปิดเต็มจออยู่หรือไม่
        if self.tick_count % max(1, int(500 / config.TICK_MS)) == 0:
            self._update_fullscreen_visibility()
        if self.tick_count % max(1, int(1000 / config.TICK_MS)) == 0:
            self._decay_stats()
            self._check_hunger()
            self._tick_spawn_monster()
        if self.tick_count % max(1, int(1000 / config.TICK_MS) * 20) == 0:
            self._save_progress()   # เซฟอัตโนมัติทุก ~20 วินาที

        if self.pet.behavior == "ko":
            self._update_ko()
        elif self.monster is not None:
            self._update_combat()
        elif self.pet.behavior == "goto_food" and self.food is not None:
            self._update_eating()
        elif self.pet.behavior == "stay":
            self._update_stay()
        elif self.pet.behavior == "drag":
            pass  # ตำแหน่งถูกคุมโดยเมาส์
        else:
            self._update_wander()

        self.pet.sync_position()
        self._update_effects()
        self._update_bubble()
        self._draw_hud()
        self._draw_monster_hud()
        self.root.after(config.TICK_MS, self._tick)

    # --------------------------------------------------------------- behaviors
    def _decay_stats(self):
        self.pet.fullness = max(0, self.pet.fullness - config.FULLNESS_DECAY)
        self.pet.happy = max(0, self.pet.happy - config.HAPPY_DECAY)
        if self.pet.fullness <= 0:                       # หิวมากเลือดจะค่อย ๆ ลด
            self.pet.hp = max(1, self.pet.hp - 1)

    def _speed(self):
        # หิวจัดเดินช้าลง
        return config.WALK_SPEED * (0.5 if self.pet.fullness < 20 else 1.0)

    def _walk_toward(self, target_x, speed):
        d = target_x - self.pet.x
        reached = abs(d) <= speed
        if reached:
            self.pet.x = target_x
        else:
            self.pet.x += _sign(d) * speed
            self.pet.set_state("walk")
            self.pet.face(d)
        self._drop_to_ground(self.pet)
        return reached

    def _update_wander(self):
        self.pet.wtimer -= 1
        if self.pet.wtimer <= 0:
            if random.random() < 0.3:
                self.pet.vx = 0.0
                self.pet.wtimer = random.randint(20, 50)
            else:
                self.pet.vx = random.choice([-1, 1]) * self._speed()
                self.pet.wtimer = random.randint(40, 120)

        self.pet.x += self.pet.vx
        half = self.pet.current_anim().w / 2
        if self.pet.x < half:
            self.pet.x = half
            self.pet.vx = abs(self.pet.vx)
        elif self.pet.x > self.sw - half:
            self.pet.x = self.sw - half
            self.pet.vx = -abs(self.pet.vx)
        self._drop_to_ground(self.pet)
        self.pet.set_state("walk" if self.pet.vx != 0 else "idle")
        self.pet.face(self.pet.vx)

    def _update_stay(self):
        """ยืนอยู่กับที่ ไม่เดินไปไหน แต่หันซ้าย-ขวาเป็นระยะ ๆ"""
        self.pet.set_state("idle")
        self._drop_to_ground(self.pet)
        self.pet.stay_timer -= 1
        if self.pet.stay_timer <= 0:
            self.pet.face(-self.pet.facing)            # หันกลับด้าน
            self.pet.stay_timer = random.randint(40, 110)

    def _update_eating(self):
        food = self.food
        if abs(food.x - self.pet.x) > 10:
            self._walk_toward(food.x, self._speed())
            return
        # ถึงอาหารแล้ว — กิน
        self.pet.set_state("eat")
        if self.pet.eat_timer is None:
            self.pet.eat_timer = 40
        self.pet.eat_timer -= 1
        if self.pet.eat_timer <= 0:
            self.pet.fullness = min(100, self.pet.fullness + 35)
            self.pet.happy = min(100, self.pet.happy + 12)
            self.show_bubble("อร่อย! 🍽")
            self.add_xp(config.XP_PER_FEED)
            food.destroy()
            self.food = None
            self.pet.eat_timer = None
            self.pet.behavior = "wander"
            self.pet.vx = 0

    def _update_combat(self):
        m = self.monster
        dist = abs(self.pet.x - m.x)

        # มอนสเตอร์เดินเข้าหาเพ็ทเสมอ
        if dist > config.ATTACK_RANGE:
            m.x += _sign(self.pet.x - m.x) * config.MONSTER_SPEED
            m.face(self.pet.x - m.x)
            self._drop_to_ground(m)
            m.set_state("walk")
            self._walk_toward(m.x, self._speed())   # เพ็ทเข้าหามอนสเตอร์
        else:
            self.pet.set_state("idle")
            self.pet.face(m.x - self.pet.x)         # หันเข้าหากันตอนต่อสู้
            m.face(self.pet.x - m.x)
            m.set_state("walk")
            self.pet.attack_cd = max(0, self.pet.attack_cd - 1)
            m.attack_cd = max(0, m.attack_cd - 1)

            if self.pet.attack_cd == 0:              # เพ็ทโจมตี
                dmg = self.pet.attack()
                m.hp -= dmg
                self.pet.set_state("attack")
                self.spawn_effect(m.x, m.top_y(), f"-{dmg}")
                self.pet.attack_cd = config.ATTACK_COOLDOWN
            if m.attack_cd == 0:                     # มอนสเตอร์โจมตี
                self.pet.hp -= m.atk
                self.pet.set_state("hurt")
                self.pet.happy = max(0, self.pet.happy - 3)
                self.spawn_effect(self.pet.x, self.pet.top_y(), f"-{m.atk}")
                m.attack_cd = config.ATTACK_COOLDOWN

        m.sync_position()

        if m.hp <= 0:                                # ชนะ
            was_boss = m.is_boss
            self.spawn_effect(m.x, m.top_y(), "✨")
            m.destroy()
            self.monster = None
            self.pet.happy = min(100, self.pet.happy + 20)
            self.pet.behavior = "wander"
            self.pet.vx = 0
            # คืบหน้าเวฟ: ล้มบอส = ขึ้นเวฟใหม่ (กลับไปนับ 1 แต่มอนเก่งขึ้น)
            if was_boss:
                self.wave_round += 1
                self.wave_step = 1
                self.show_bubble(f"🏆 ผ่านบอส! ขึ้นเวฟ {self.wave_round}")
                self.spawn_effect(self.pet.x, self.pet.top_y(), "🎉")
                self.add_xp(config.XP_PER_WIN * config.BOSS_XP_MULT)
            else:
                self.wave_step += 1
                self.show_bubble(f"ชนะ! ({self.wave_step}/{config.WAVE_LENGTH}) 🎉")
                self.add_xp(config.XP_PER_WIN)
            self._save_progress()
        elif self.pet.hp <= 0:                       # เพ็ทแพ้ (สลบ ไม่ตายถาวร)
            self.pet.set_state("hurt")
            self.pet.behavior = "ko"
            self.pet.ko_timer = 90
            self.pet.happy = max(0, self.pet.happy - 25)
            self.show_bubble("สลบ... 😵")
            m.destroy()
            self.monster = None

    def _update_ko(self):
        self.pet.ko_timer -= 1
        if self.pet.ko_timer <= 0:
            self.pet.hp = self.pet.max_hp() * 0.5
            self.pet.behavior = "wander"
            self.pet.vx = 0
            self.show_bubble("ฟื้นแล้ว!")

    # --------------------------------------------------------- effects & ui
    def spawn_effect(self, x, y, text):
        item = self.canvas.create_text(x, y - 6, text=text, font=("Segoe UI Emoji", 20))
        self.effects.append({"item": item, "ttl": 14, "dy": -1.4})

    def _update_effects(self):
        for fx in self.effects[:]:
            fx["ttl"] -= 1
            self.canvas.move(fx["item"], 0, fx["dy"])
            if fx["ttl"] <= 0:
                self.canvas.delete(fx["item"])
                self.effects.remove(fx)

    def show_bubble(self, text):
        for it in self.bubble_items:
            self.canvas.delete(it)
        self.bubble_items = []
        x = self.pet.x
        y = self.pet.top_y() - 34
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
        # ให้บับเบิลลอยตามหัวเพ็ท
        rect, txt = self.bubble_items
        x = self.pet.x
        y = self.pet.top_y() - 34
        self.canvas.coords(txt, x, y)
        x0, y0, x1, y1 = self.canvas.bbox(txt)
        pad = 6
        self.canvas.coords(rect, x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def _toggle_status_panel(self, e):
        """📊 เปิด/ปิดแผงสถานะ (ออกทางซ้าย)"""
        self.show_status_panel = not self.show_status_panel
        self._draw_hud()
        return "break"

    def _toggle_actions(self, e):
        """🍎 เปิด/ปิดเมนูให้อาหาร–ลูบหัว"""
        self.show_actions = not self.show_actions
        self._draw_hud()
        return "break"

    def _toggle_combat(self, e):
        """⚔/🛡 สลับโหมดต่อสู้ ↔ เลี้ยงอย่างเดียว"""
        self.combat_enabled = not self.combat_enabled
        if not self.combat_enabled and self.monster is not None:
            self.monster.destroy()          # ปิดต่อสู้ = เอามอนสเตอร์ออกทันที
            self.monster = None
            if self.pet.behavior != "ko":
                self.pet.behavior = "wander"
                self.pet.vx = 0
        self.show_bubble("⚔ เปิดโหมดต่อสู้!" if self.combat_enabled
                         else "🛡 โหมดเลี้ยงอย่างเดียว")
        self._save_progress()
        self._draw_hud()
        return "break"

    def _menu_click(self, action):
        """กดปุ่มเมนูซ้าย — สั่งงานแล้ววาดใหม่ทันที"""
        action()
        self._draw_hud()
        return "break"

    def _on_settings_click(self, e):
        """กดปุ่ม ⚙ = เปิด/ปิดป๊อปอัปตั้งค่า (เด้งเหนือปุ่ม)"""
        if getattr(self, "_settings_win", None) is not None:
            self._close_settings_popup()
        else:
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

    def _show_settings_popup(self):
        """ป๊อปอัปตั้งค่าแบบกำหนดเอง: ธีมเข้ม มี hover เด้งเหนือปุ่ม ⚙"""
        items = [
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
        # วางเหนือปุ่ม ⚙ (ชิดขวาตรงกับปุ่ม)
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        gx0, gy0, gx1, gy1 = getattr(self, "_gear_canvas", (0, 0, 0, 0))
        rootx, rooty = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        x = rootx + gx1 - w                          # ขอบขวาเมนู = ขอบขวาปุ่ม
        y = rooty + gy0 - 6 - h                       # เหนือปุ่ม เว้น 6px
        win.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        self._settings_win = win
        win.bind("<FocusOut>", lambda e: self._close_settings_popup())
        win.bind("<Escape>", lambda e: self._close_settings_popup())
        win.focus_force()

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
                                 font=("Segoe UI Emoji", 18), tags=tags)

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
        """แผงสถานะแบบติดมุมขวาล่างของ 'จอหลัก' (เห็นชัดเสมอ ไม่ติดตามเพ็ท)"""
        self.canvas.delete("hud")
        if not self.show_hud:
            return
        p = self.pet
        margin = 18
        # มุมขวาล่างของจอหลัก; ใช้ขอบบน taskbar เป็นฐานล่าง (แผงจึงอยู่เหนือ taskbar)
        right = -self.vx0 + self.primary_w
        bottom = self._work_bottom_at(right - margin)

        x1, y1 = right - margin, bottom - margin

        # ===== คอลัมน์ปุ่มไอคอนแนวตั้ง (ชิดขวาล่าง เรียงขึ้นบน) =====
        bw, gap = 44, 8

        def col_rect(i):                       # i=0 = ล่างสุด
            btm = y1 - i * (bw + gap)
            return (x1 - bw, btm - bw, x1, btm)

        sx0, sy0, sx1, sy1 = col_rect(0)       # ⚙ ตั้งค่า
        cx0, cy0, cx1, cy1 = col_rect(1)       # ⚔ ต่อสู้
        ax0, ay0, ax1, ay1 = col_rect(2)       # 🍎 เลี้ยง
        tx0, ty0, tx1, ty1 = col_rect(3)       # 📊 สถานะ

        self._draw_icon_button(tx0, ty0, tx1, ty1, "📊", "btn_status",
                               accent=self.show_status_panel)
        self._draw_icon_button(ax0, ay0, ax1, ay1, "🍎", "btn_actions",
                               accent=self.show_actions)
        self._draw_icon_button(cx0, cy0, cx1, cy1,
                               "⚔" if self.combat_enabled else "🛡", "btn_combat",
                               accent=self.combat_enabled, accent_color="#c0392b")
        self._draw_icon_button(sx0, sy0, sx1, sy1, "⚙", "btn_settings")
        self._gear_canvas = (sx0, sy0, sx1, sy1)   # ไว้วางเมนูตั้งค่าเหนือปุ่ม

        # ===== ป้ายเวฟ/โหมด: ซ้ายของปุ่ม ⚔ (แสดงจำนวนเวฟ) =====
        if self.combat_enabled:
            if self.monster is not None and self.monster.is_boss:
                wtext = f"⚔ เวฟ {self.wave_round} · 👑 บอส"
            else:
                wtext = f"⚔ เวฟ {self.wave_round} · {self.wave_step}/{config.WAVE_LENGTH}"
            wcolor = "#f1c40f"
        else:
            wtext, wcolor = "🛡 โหมดเลี้ยง", "#9aa0a6"
        self._draw_pill(cx0 - 10, (cy0 + cy1) / 2, wtext, wcolor)

        # ===== 🍎 เมนูเลี้ยง: ไอคอน ✋/🍎 ออกซ้ายจากปุ่ม (แถวเดียวกัน) =====
        if self.show_actions:
            feed_on = self.monster is None and self.pet.behavior != "ko"
            pat_on = self.pet.behavior != "ko"
            self._draw_icon_button(ax0 - 12 - bw, ay0, ax0 - 12, ay1,
                                   "✋", "btn_pat", enabled=pat_on)
            self._draw_icon_button(ax0 - 12 - 2 * bw - gap, ay0,
                                   ax0 - 12 - bw - gap, ay1,
                                   "🍎", "btn_feed", enabled=feed_on)

        # ===== 📊 แผงสถานะ: ป๊อปอัปออกซ้ายจากปุ่ม 📊 (เรียงขึ้นบน) =====
        if self.show_status_panel:
            pw, ph = 300, 168
            qx1 = tx0 - 12
            qx0 = qx1 - pw
            qy1 = ty1
            qy0 = qy1 - ph
            self.canvas.create_rectangle(qx0, qy0, qx1, qy1, fill="#1e1e1e",
                                         outline="#5a5a5a", width=3, tags="hud")
            ib = 32
            ibx0, iby0 = qx0 + 14, qy0 + 12
            ibx1, iby1 = ibx0 + ib, iby0 + ib
            self.canvas.create_rectangle(ibx0, iby0, ibx1, iby1, fill="#2c3e50",
                                         outline="#888888", width=2,
                                         tags=("hud", "btn_char"))
            self.canvas.create_text((ibx0 + ibx1) / 2, (iby0 + iby1) / 2, text="🐾",
                                    font=("Segoe UI Emoji", 15), tags=("hud", "btn_char"))
            char_name = self.character or "เพ็ท"
            self.canvas.create_text(ibx1 + 12, qy0 + 28, anchor="w",
                                    text=f"{char_name}   Lv.{p.level}",
                                    fill="#ffffff", font=("Segoe UI", 14, "bold"),
                                    tags="hud")
            rows = [
                ("HP", p.alive_ratio(), "#e74c3c", f"{int(p.hp)}/{p.max_hp()}"),
                ("อิ่ม", p.fullness / 100.0, "#f39c12", f"{int(p.fullness)}"),
                ("สุข", p.happy / 100.0, "#e84393", f"{int(p.happy)}"),
                ("XP", p.xp_ratio(), "#3498db", f"{p.xp}/{p.xp_to_next()}"),
            ]
            bar_x = qx0 + 60
            bar_w = pw - 60 - 18
            bar_h = 16
            for i, (label, ratio, color, text) in enumerate(rows):
                cy = qy0 + 56 + i * 28
                self.canvas.create_text(qx0 + 18, cy + bar_h / 2, anchor="w", text=label,
                                        fill="#dddddd", font=("Segoe UI", 11), tags="hud")
                self.canvas.create_rectangle(bar_x, cy, bar_x + bar_w, cy + bar_h,
                                             fill="#3a3a3a", outline="", tags="hud")
                self.canvas.create_rectangle(bar_x, cy,
                                             bar_x + bar_w * max(0, min(1, ratio)),
                                             cy + bar_h, fill=color, outline="", tags="hud")
                self.canvas.create_text(bar_x + bar_w / 2, cy + bar_h / 2, text=text,
                                        fill="#ffffff", font=("Segoe UI", 10, "bold"),
                                        tags="hud")

    # ----------------------------------------------------------- hunger alert
    def _check_hunger(self):
        """ถ้าความอิ่มต่ำกว่าเกณฑ์ ให้แจ้งเตือน (เด้งทันทีตอนเริ่มหิว และเตือนซ้ำตามรอบ)"""
        hungry = (self.pet.fullness < config.HUNGRY_THRESHOLD
                  and self.pet.behavior != "ko")
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
                    "พามาหาอะไรกินหน่อยนะ 🐾  (คลิกขวาที่เพ็ท → ให้อาหาร)")
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

    def _entities(self):
        ents = [self.pet]
        if self.monster is not None:
            ents.append(self.monster)
        if self.food is not None:
            ents.append(self.food)
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
                "  • คลิกซ้าย : ลูบหัว / เล่นด้วย\n"
                "  • ลาก         : ย้ายตำแหน่ง\n"
                "  • คลิกขวา  : เปลี่ยนตัวละคร / ดูสถานะ\n"
                "  • ปุ่ม ⚙       : ตั้งค่า (อัพเดท / ออก)\n\n"
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

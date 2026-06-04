# -*- coding: utf-8 -*-
"""โลกของ Desktop Pet: หน้าต่างโปร่งใสเต็มจอ + ลูปเกม + อินพุต + การต่อสู้"""
import ctypes
from ctypes import wintypes
import random
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
        self.effects = []          # [{"item":id, "ttl":int, "dy":float}]
        self.bubble_items = []
        self.bubble_ttl = 0
        self.show_hud = True          # แผงสถานะมุมขวาล่างของจอหลัก
        self.tick_count = 0

        # อินพุต
        self._down = False
        self._dragged = False
        self._press_xy = (0, 0)
        self.canvas.tag_bind(self.pet.item, "<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Button-3>", self.on_menu)
        self.root.bind("<Escape>", lambda e: self.quit())

        self._build_menu()

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
        แต่ละร่างใช้ไฟล์ชื่อ '{prefix}_{state}.gif/png' (state เดียวกับ PET_SPRITES)"""
        states = list(config.PET_SPRITES.keys())
        forms = []
        for ev in config.PET_EVOLUTIONS:
            prefix = ev["prefix"]
            spritemap = {s: [f"{prefix}_{s}.gif", f"{prefix}_{s}.png"] for s in states}
            anims = self._load_anims(spritemap, "pet",
                                     ev.get("size", config.PET_SIZE), ev.get("color"))
            forms.append({"level": ev["level"], "name": ev.get("name", prefix), "anims": anims})
        if not forms:   # สำรอง ถ้าไม่ได้ตั้ง PET_EVOLUTIONS ไว้
            anims = self._load_anims(config.PET_SPRITES, "pet", config.PET_SIZE)
            forms.append({"level": 1, "name": "pet", "anims": anims})
        return forms

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
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="🍎  ให้อาหาร", command=self.feed)
        m.add_command(label="⚔  ปล่อยมอนสเตอร์", command=self.spawn_monster)
        m.add_command(label="✋  ลูบหัว / เล่นด้วย", command=self.pet_react)
        m.add_separator()
        m.add_command(label="📊  ดูสถานะ / เลเวล", command=self.show_status)
        m.add_command(label="🖥  เปิด/ปิด แผงสถานะ (มุมจอ)", command=self.toggle_hud)
        m.add_command(label="❌  ออกจากโปรแกรม", command=self.quit)
        self.menu = m

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
        if self.food is not None or self.pet.behavior == "ko":
            return
        x = random.uniform(self.sw * 0.15, self.sw * 0.85)
        self.food = Food(self.canvas, self.food_anims, x, 0)
        self._drop_to_ground(self.food)
        self.food.sync_position()
        if self.pet.behavior != "fight":
            self.pet.behavior = "goto_food"
            self.pet.eat_timer = None

    def spawn_monster(self):
        if self.monster is not None or self.pet.behavior == "ko":
            return
        from_left = random.random() < 0.5
        x = -config.MONSTER_SIZE if from_left else self.sw + config.MONSTER_SIZE
        self.monster = Monster(self.canvas, self.monster_anims, x, 0)
        self.monster.max_hp = config.MONSTER_MAX_HP + (self.pet.level - 1) * config.MONSTER_HP_PER_LEVEL
        self.monster.hp = self.monster.max_hp
        self._drop_to_ground(self.monster)
        self.monster.sync_position()
        self.pet.behavior = "fight"
        self.show_bubble("มาสู้กัน!")

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

    def _save_progress(self):
        p = self.pet
        save.save({
            "level": p.level,
            "xp": p.xp,
            "hp": round(p.hp, 1),
            "fullness": round(p.fullness, 1),
            "happy": round(p.happy, 1),
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
        if self.tick_count % max(1, int(1000 / config.TICK_MS)) == 0:
            self._decay_stats()
        if self.tick_count % max(1, int(1000 / config.TICK_MS) * 20) == 0:
            self._save_progress()   # เซฟอัตโนมัติทุก ~20 วินาที

        if self.pet.behavior == "ko":
            self._update_ko()
        elif self.monster is not None:
            self._update_combat()
        elif self.pet.behavior == "goto_food" and self.food is not None:
            self._update_eating()
        elif self.pet.behavior == "drag":
            pass  # ตำแหน่งถูกคุมโดยเมาส์
        else:
            self._update_wander()

        self.pet.sync_position()
        self._update_effects()
        self._update_bubble()
        self._draw_hud()
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
                m.hp -= self.pet.attack()
                self.pet.set_state("attack")
                self.spawn_effect(m.x, m.top_y(), "💥")
                self.pet.attack_cd = config.ATTACK_COOLDOWN
            if m.attack_cd == 0:                     # มอนสเตอร์โจมตี
                self.pet.hp -= config.MONSTER_ATTACK
                self.pet.set_state("hurt")
                self.pet.happy = max(0, self.pet.happy - 3)
                self.spawn_effect(self.pet.x, self.pet.top_y(), "💢")
                m.attack_cd = config.ATTACK_COOLDOWN

        m.sync_position()

        if m.hp <= 0:                                # ชนะ
            self.spawn_effect(m.x, m.top_y(), "✨")
            m.destroy()
            self.monster = None
            self.pet.happy = min(100, self.pet.happy + 20)
            self.pet.behavior = "wander"
            self.pet.vx = 0
            self.show_bubble("ชนะแล้ว! 🎉")
            self.add_xp(config.XP_PER_WIN)
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

    def _draw_hud(self):
        """แผงสถานะแบบติดมุมขวาล่างของ 'จอหลัก' (เห็นชัดเสมอ ไม่ติดตามเพ็ท)"""
        self.canvas.delete("hud")
        if not self.show_hud:
            return
        p = self.pet
        panel_w, panel_h, margin = 300, 168, 18
        # มุมขวาล่างของจอหลัก; ใช้ขอบบน taskbar เป็นฐานล่าง (แผงจึงอยู่เหนือ taskbar)
        right = -self.vx0 + self.primary_w
        bottom = self._work_bottom_at(right - margin)
        x1, y1 = right - margin, bottom - margin
        x0, y0 = x1 - panel_w, y1 - panel_h

        self.canvas.create_rectangle(x0, y0, x1, y1, fill="#1e1e1e",
                                     outline="#5a5a5a", width=3, tags="hud")
        self.canvas.create_text(x0 + 18, y0 + 24, anchor="w",
                                text=f"🐾 เพ็ท   Lv.{p.level}",
                                fill="#ffffff", font=("Segoe UI", 15, "bold"), tags="hud")
        rows = [
            ("HP", p.alive_ratio(), "#e74c3c", f"{int(p.hp)}/{p.max_hp()}"),
            ("อิ่ม", p.fullness / 100.0, "#f39c12", f"{int(p.fullness)}"),
            ("สุข", p.happy / 100.0, "#e84393", f"{int(p.happy)}"),
            ("XP", p.xp_ratio(), "#3498db", f"{p.xp}/{p.xp_to_next()}"),
        ]
        bar_x = x0 + 60
        bar_w = panel_w - 60 - 18
        bar_h = 16
        for i, (label, ratio, color, text) in enumerate(rows):
            cy = y0 + 52 + i * 28
            self.canvas.create_text(x0 + 18, cy + bar_h / 2, anchor="w", text=label,
                                    fill="#dddddd", font=("Segoe UI", 11), tags="hud")
            self.canvas.create_rectangle(bar_x, cy, bar_x + bar_w, cy + bar_h,
                                         fill="#3a3a3a", outline="", tags="hud")
            self.canvas.create_rectangle(bar_x, cy, bar_x + bar_w * max(0, min(1, ratio)),
                                         cy + bar_h, fill=color, outline="", tags="hud")
            self.canvas.create_text(bar_x + bar_w / 2, cy + bar_h / 2, text=text,
                                    fill="#ffffff", font=("Segoe UI", 10, "bold"), tags="hud")

    def _entities(self):
        ents = [self.pet]
        if self.monster is not None:
            ents.append(self.monster)
        if self.food is not None:
            ents.append(self.food)
        return ents

    def quit(self):
        self._save_progress()
        self.root.destroy()

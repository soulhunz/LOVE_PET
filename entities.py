# -*- coding: utf-8 -*-
"""วัตถุต่าง ๆ บนหน้าจอ: Entity พื้นฐาน, Pet, Monster, Food

โลจิกการตัดสินใจ/ต่อสู้อยู่ใน game.py — ที่นี่เก็บแค่ข้อมูลและการเรนเดอร์
"""
import config


class Entity:
    """วัตถุที่วาดด้วย 1 รูปบน canvas โดยสลับเฟรมเพื่อทำอนิเมชัน

    x, y = จุดกึ่งกลางของวัตถุ
    """

    def __init__(self, canvas, anims, x, y, state="idle"):
        self.canvas = canvas
        self.anims = anims        # dict: state -> Animation
        self.state = state
        self.x = float(x)
        self.y = float(y)
        self.frame_i = 0
        self.facing = config.SPRITE_DEFAULT_DIR   # 1 = ขวา, -1 = ซ้าย
        a = self.current_anim()
        self.item = canvas.create_image(x, y, image=a.frame(0))

    def current_anim(self):
        # สถานะที่ไม่มีภาพ จะใช้ภาพ idle แทน
        return self.anims.get(self.state) or self.anims["idle"]

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.frame_i = 0

    def _render(self):
        flip = self.facing != config.SPRITE_DEFAULT_DIR
        self.canvas.itemconfigure(self.item,
                                  image=self.current_anim().frame(self.frame_i, flip))

    def face(self, dx):
        """หันตามทิศเคลื่อนที่ dx (>0 ขวา, <0 ซ้าย); อัปเดตรูปทันทีถ้าหันกลับ"""
        new = 1 if dx > 0 else (-1 if dx < 0 else self.facing)
        if new != self.facing:
            self.facing = new
            self._render()

    def advance_frame(self):
        self.frame_i += 1
        self._render()

    def sync_position(self):
        self.canvas.coords(self.item, self.x, self.y)

    def top_y(self):
        return self.y - self.current_anim().h / 2

    def destroy(self):
        self.canvas.delete(self.item)


class Pet(Entity):
    def __init__(self, canvas, anims, x, y):
        super().__init__(canvas, anims, x, y, state="idle")
        self.level = 1
        self.xp = 0
        self.hp = self.max_hp()
        self.fullness = 80.0
        self.happy = 80.0
        self.behavior = "wander"   # wander | stay | goto_food | fight | drag | ko
        self.vx = 0.0
        self.wtimer = 0            # ตัวจับเวลาสำหรับสุ่มพฤติกรรมเดินเล่น
        self.stay_timer = 0        # ตัวจับเวลาสำหรับหันซ้าย-ขวาตอนยืนเฉย ๆ
        self.eat_timer = None
        self.attack_cd = 0
        self.ko_timer = 0

    # ค่าที่คำนวณจากเลเวล
    def max_hp(self):
        return config.PET_MAX_HP + (self.level - 1) * config.HP_PER_LEVEL

    def attack(self):
        return config.PET_ATTACK + (self.level - 1) * config.ATTACK_PER_LEVEL

    def xp_to_next(self):
        return int(config.BASE_XP_TO_LEVEL * (config.XP_GROWTH ** (self.level - 1)))

    def alive_ratio(self):
        return max(0.0, self.hp) / self.max_hp()

    def xp_ratio(self):
        return max(0.0, min(1.0, self.xp / self.xp_to_next()))


class Monster(Entity):
    def __init__(self, canvas, anims, x, y):
        super().__init__(canvas, anims, x, y, state="walk")
        self.max_hp = config.MONSTER_MAX_HP
        self.hp = self.max_hp
        self.atk = config.MONSTER_ATTACK   # ดาเมจของมอนตัวนี้ (ตั้งจริงตอนเกิด)
        self.is_boss = False               # เป็นบอสประจำเวฟหรือไม่
        self.attack_cd = 0

    def hp_ratio(self):
        return max(0.0, self.hp) / self.max_hp


class Food(Entity):
    def __init__(self, canvas, anims, x, y):
        super().__init__(canvas, anims, x, y, state="idle")

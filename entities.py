# -*- coding: utf-8 -*-
"""วัตถุต่าง ๆ บนหน้าจอ: Entity พื้นฐาน, Pet, Monster, Food

โลจิกการตัดสินใจ/ต่อสู้อยู่ใน game.py — ที่นี่เก็บแค่ข้อมูลและการเรนเดอร์
"""
import config


def _build_per(line_id):
    """ค่าที่เพิ่มต่อ 1 แต้มของสายบิลด์ (อ่านจาก config.BUILD_LINES)"""
    for b in config.BUILD_LINES:
        if b["id"] == line_id:
            return b["per"]
    return 0.0


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
        self._anim_accum = 0       # ตัวสะสมเวลา (ms) สำหรับหน่วงเฟรมแบบรายสถานะ
        self.facing = config.SPRITE_DEFAULT_DIR   # 1 = ขวา, -1 = ซ้าย
        a = self.current_anim()
        self.item = canvas.create_image(x, y, image=a.frame(0))

    def current_anim(self):
        # สถานะที่ไม่มีภาพ → ใช้ภาพสถานะสำรอง (เช่น dead→hurt→idle) สุดท้าย idle
        a = self.anims.get(self.state)
        if a:
            return a
        fb = config.STATE_FALLBACK.get(self.state)
        if fb and self.anims.get(fb):
            return self.anims[fb]
        return self.anims["idle"]

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
        self.atk_mult = 1.0        # ตัวคูณพลังโจมตี (จากนิสัย)
        self.train = {"atk": 0, "hp": 0, "speed": 0}  # ฝึกฝน (ต้องมีก่อนคำนวณ max_hp)
        # ── บิลด์/แต้มสกิล (ลงเองตอนเลเวลอัพ) + รีบอร์น (ต้องมีก่อนคำนวณ max_hp) ──
        self.sp = 0                # แต้มสกิลที่ยังไม่ได้ลง
        self.build = {"crit": 0, "dodge": 0, "lifesteal": 0, "skill": 0}
        self.rebirths = 0          # จำนวนครั้งที่รีบอร์น (โบนัสถาวร)
        self.rarity = "common"     # ระดับความหายาก (จากไข่ที่ฟัก) → โบนัส ATK/HP
        # ── สถานะระหว่างต่อสู้ (ไม่เซฟ) ──
        self.rage = 0              # เกจเดือด (เต็มแล้วปล่อยท่าไม้ตาย)
        self.burn_ttl = 0          # ไฟไหม้เหลือกี่ tick
        self.hp = self.max_hp()
        self.fullness = 80.0
        self.happy = 80.0
        self.energy = 80.0         # พลังงาน (ลดเรื่อย ๆ; นอนเพื่อฟื้น)
        self.cleanliness = 80.0    # ความสะอาด (ลดเรื่อย ๆ; อาบน้ำเพื่อฟื้น)
        self.affection = 0.0       # สายสัมพันธ์ระยะยาว 0..100 (โตจากการดูแลดี)
        self.sick = False          # กำลังป่วยหรือไม่ (ถูกละเลยนาน ๆ จะป่วย)
        self.behavior = "wander"   # wander | stay | goto_food | fight | drag | ko | sleep
        # ── ข้อมูลเฉพาะตัว (ใช้ตอนเลี้ยงหลายตัว) ──
        self.gender = "m"          # เพศ: "m" ผู้ / "f" เมีย (สุ่มตอนเกิด)
        self.skill = ""            # สกิลติดตัว 1 อย่าง (id จาก config.SKILLS)
        self.act_state = ""        # สถานะอนิเมชันแอ็กชันชั่วคราว (อาบน้ำ/ลูบหัว)
        self.act_timer = 0
        self.anim_ms = {}          # หน่วงเฟรมรายสถานะ (state -> ms) จาก pet.json
        self.character = None      # ชื่อตัวละคร (โฟลเดอร์อาร์ต) ของน้องตัวนี้
        self.likes = []            # อาหารที่ชอบ (จาก pet.json)
        self.dislikes = []         # อาหารที่ไม่ชอบ
        # นิสัยประจำตัว (trait) — ค่าผลถูกตั้งโดย game._apply_trait
        self.trait = ""            # id นิสัย
        self.decay_mult = 1.0      # ตัวคูณการลดสเตตัส (จากนิสัย)
        self.trait_speed = 0.0     # โบนัสความเร็ว (จากนิสัย)
        self.feed_happy = 0        # สุขพิเศษเมื่อกินอาหาร (จากนิสัย)
        self.away_until = 0.0      # ถ้า > เวลาปัจจุบัน = กำลังออกผจญภัย (ซ่อนตัว)
        self.away_mins = 0         # ระยะเวลาผจญภัยที่เลือก (ไว้คำนวณรางวัลตอนกลับ)
        self.tricks_taught = []    # ทริคที่น้องตัวนี้เรียนรู้แล้ว
        self.name = ""             # ชื่อเล่นของน้อง
        self.birth_date = ""       # วันแรกที่เริ่มเลี้ยง (อายุ)
        self.food = None           # อาหารชิ้นที่กำลังกิน (Food entity)
        self.food_type = None      # ชนิดอาหารที่กำลังกิน
        self.bar_stat = ""         # สเตตัสที่กำลังโชว์หลอดลอยเหนือหัว ("" = ไม่โชว์)
        self.bar_ttl = 0           # นับถอยหลังเฟรมที่เหลือของหลอด
        self.vx = 0.0
        self.wtimer = 0            # ตัวจับเวลาสำหรับสุ่มพฤติกรรมเดินเล่น
        self.stay_timer = 0        # ตัวจับเวลาสำหรับหันซ้าย-ขวาตอนยืนเฉย ๆ
        self.eat_timer = None
        self.attack_cd = 0
        self._atk_hit = False      # ปล่อยหมัดของสวิงนี้ไปแล้วหรือยัง (กันตีซ้ำในสวิงเดียว)
        self.ko_timer = 0

    def rebirth_mult(self):
        """ตัวคูณถาวรจากการรีบอร์น (ใช้กับ ATK/HP)"""
        return 1.0 + self.rebirths * config.REBIRTH_BONUS

    def rarity_mult(self):
        """ตัวคูณ ATK/HP ตามระดับความหายาก"""
        return config.rarity_by_id(self.rarity).get("stat_mult", 1.0)

    # ค่าที่คำนวณจากเลเวล (+ ฝึกฝน + นิสัย + รีบอร์น + ความหายาก)
    def max_hp(self):
        base = (config.PET_MAX_HP + (self.level - 1) * config.HP_PER_LEVEL
                + self.train["hp"] * config.TRAIN_HP_STEP)
        return int(base * self.rebirth_mult() * self.rarity_mult())

    def attack(self):
        base = (config.PET_ATTACK + (self.level - 1) * config.ATTACK_PER_LEVEL
                + self.train["atk"] * config.TRAIN_ATK_STEP)
        return int(base * self.atk_mult * self.rebirth_mult() * self.rarity_mult())

    # ── ค่าต่อสู้จากบิลด์ (แต้มสกิล) ──
    def crit_chance(self):
        return min(config.CRIT_CHANCE_MAX,
                   config.CRIT_BASE + self.build["crit"] * _build_per("crit"))

    def dodge_chance(self):
        return min(config.DODGE_CHANCE_MAX,
                   config.DODGE_BASE + self.build["dodge"] * _build_per("dodge"))

    def lifesteal_pct(self):
        return min(config.LIFESTEAL_MAX, self.build["lifesteal"] * _build_per("lifesteal"))

    def ult_damage(self):
        mult = config.ULT_BASE_MULT + self.build["skill"] * _build_per("skill")
        return int(self.attack() * mult)

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
        self.stun_ttl = 0                  # โดนท่าไม้ตาย/แช่แข็งสตัน เหลือกี่ tick (นิ่ง)
        self.poison_ttl = 0                # ติดพิษเหลือกี่ tick
        self.poison_dmg = 0                # ดาเมจพิษต่อ tick

    def hp_ratio(self):
        return max(0.0, self.hp) / self.max_hp


class Food(Entity):
    def __init__(self, canvas, anims, x, y):
        super().__init__(canvas, anims, x, y, state="idle")

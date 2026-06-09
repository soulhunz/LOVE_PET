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
        # ระบบป้องกัน/สกิลกดใช้ (active) — โล่ดูดดาเมจ / อมตะ / คูลดาวน์สกิล / กันตายครั้งเดียว
        self.shield = 0            # โล่ดูดดาเมจคงเหลือ (ลดก่อนเข้า HP)
        self.invuln_ttl = 0        # อมตะเหลือกี่ tick (รับดาเมจ 0)
        self.skill_cd = {}         # คูลดาวน์รายสกิลใช้งาน {skill_id: ticks เหลือ}
        self.last_stand_used = False   # ใช้ "ไม่ยอมตาย" ไปแล้วในรอบนี้หรือยัง
        # ระบบความเร็วโจมตี/สแต็ก (รำดาบ/พายุคลั่ง/ล็อคเป้า)
        self.as_stacks = 0         # สแต็กความเร็วโจมตี (รำดาบ Blade Dance)
        self.as_ttl = 0            # สแต็กความเร็วเหลือกี่ tick ก่อนหมด
        self.wf_count = 0          # นับหมัด (พายุคลั่ง Windfury — ทุกหมัดที่ N)
        self.wf_ttl = 0            # บัฟพายุคลั่งเหลือกี่ tick
        self.focus_target = None   # มอนที่ตีซ้ำ (ล็อคเป้า Focus)
        self.focus_stacks = 0      # สแต็กดาเมจจากการตีซ้ำเป้าเดิม
        self.seed_used = False     # ใช้เมล็ดพันธุ์ชีวิต (Life Seed) ไปแล้วในรอบนี้หรือยัง
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
        self.skills = []           # สกิลติดตัว (หลายสกิลได้ จากการผสมพันธุ์) — list ของ id
        self.act_state = ""        # สถานะอนิเมชันแอ็กชันชั่วคราว (อาบน้ำ/ลูบหัว)
        self.act_timer = 0
        self.anim_ms = {}          # หน่วงเฟรมรายสถานะ (state -> ms) จาก pet.json
        self.character = None      # ชื่อตัวละคร (โฟลเดอร์อาร์ต) ของน้องตัวนี้
        self.range_type = "melee"  # ประเภทการตีปกติ: melee (ประชิด) / ranged (ยิงโปรเจกไทล์)
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

    @property
    def skill(self):
        """สกิลแรก (เพื่อความเข้ากันได้กับโค้ดที่อ้าง .skill เดี่ยว)"""
        return self.skills[0] if self.skills else ""

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
        # ── ระดับ/ประเภทการตี/สกิล (กำหนดต่อมอนใน manager) ──
        self.rarity = "common"             # ระดับความหายาก → ตัวคูณ HP/ATK
        self.range_type = "melee"          # melee (ประชิด) / ranged (ยิงโปรเจกไทล์ใส่น้อง)
        self.skill = ""                    # สกิลที่ถูกกำหนดให้ ("" = ไม่มีสกิล)
        # ── สถานะป้องกัน/สกิล active ของมอน ──
        self.shield = 0                    # โล่ดูดดาเมจ (สกิลบาเรีย)
        self.invuln_ttl = 0                # อมตะเหลือกี่ tick
        self.rage = 0                      # เกจไม้ตาย (เฉพาะมอนที่มีสกิลใช้งาน) → ปล่อยสกิล active
        self.skill_cd = 0                  # คูลดาวน์สกิลใช้งานของมอน (ticks)
        self.last_stand_used = False
        self.stun_ttl = 0                  # โดนท่าไม้ตาย/แช่แข็งสตัน เหลือกี่ tick (นิ่ง)
        self.poison_ttl = 0                # ติดพิษเหลือกี่ tick
        self.poison_dmg = 0                # ดาเมจพิษต่อ tick
        self.bleed_ttl = 0                 # เลือดไหล (bleed) เหลือกี่ tick
        self.bleed_dmg = 0                 # ดาเมจเลือดไหลต่อวินาที (จาก on_hit/bleed)
        self.armor = 0.0                   # เกราะ (ลดดาเมจ 0..1) — บอสมีติดตัว
        self.armor_shred = 0.0             # เกราะถูกทำลาย (ทำลายเกราะ/กรด) ลดเกราะจริง
        self.doom_ttl = 0                  # คำสาปสั่งตาย/ระเบิดเวลา นับถอยหลังกี่ tick
        self.doom_dmg = 0                  # ดาเมจตอนคำสาปครบกำหนด
        self.plague = False                # ติดโรคระบาด → ตายแล้วแพร่พิษใส่ตัวข้าง ๆ
        self.slow_ttl = 0                  # ถูกลดความเร็ว (slow) เหลือกี่ tick
        self.slow_pct = 0.0                # ลดความเร็ว/รอบโจมตีกี่ส่วน (0.4 = ช้าลง 40%)
        self.vuln_ttl = 0                  # ติดคำสาป/เปราะ (vulnerable) เหลือกี่ tick
        self.vuln_pct = 0.0                # รับดาเมจเพิ่มกี่ส่วน (0.15 = +15%)
        self.blind_ttl = 0                 # ตาบอด (โจมตีมีโอกาสพลาด) เหลือกี่ tick
        self.blind_miss = 0.0              # โอกาสพลาดตอนตาบอด

    def hp_ratio(self):
        return max(0.0, self.hp) / self.max_hp


class Food(Entity):
    def __init__(self, canvas, anims, x, y):
        super().__init__(canvas, anims, x, y, state="idle")


class Projectile:
    """ลูกกระสุนของการตีปกติแบบ ranged — วาดเป็นวงกลมเล็ก เลื่อนเข้าหาเป้าทุก tick
    ข้อมูลเป้า/ผู้ยิง/บัฟทีม (target/pet/team) ถูกตั้งจากฝั่ง game หลังสร้าง"""

    def __init__(self, canvas, x, y, color="#ffd23f", r=7):
        self.canvas = canvas
        self.x = float(x)
        self.y = float(y)
        self.r = r
        self.source = "pet"        # ผู้ยิง: "pet" (ยิงใส่มอน) หรือ "monster" (ยิงใส่น้อง)
        self.target = None         # เป้าที่กำลังพุ่งเข้าหา
        self.pet = None            # น้องผู้ยิง (ใช้คิดดาเมจตอนโดน)
        self.monster = None        # มอนผู้ยิง (กรณี source=monster)
        self.team = None           # บัฟทีม ณ ตอนยิง
        self.item = canvas.create_oval(x - r, y - r, x + r, y + r,
                                       fill=color, outline="#aa7700")

    def move_to(self, x, y):
        self.x, self.y = x, y
        self.canvas.coords(self.item, x - self.r, y - self.r, x + self.r, y + self.r)

    def destroy(self):
        self.canvas.delete(self.item)

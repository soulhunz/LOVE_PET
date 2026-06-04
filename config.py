# -*- coding: utf-8 -*-
"""ค่าตั้งต่าง ๆ ของ Desktop Pet — แก้ที่นี่ที่เดียวเพื่อปรับลักษณะ/พฤติกรรม"""

# สีคีย์สำหรับทำพื้นหลังโปร่งใส (พิกเซลสีนี้จะโปร่งใส + คลิกทะลุได้บน Windows)
# หากใช้ไฟล์ภาพของตัวเอง พื้นหลังของภาพควรเป็นสีนี้ (หรือใช้ PNG แบบมี alpha)
TRANSPARENT_KEY = "magenta"      # = '#ff00ff'

# โฟลเดอร์เก็บไฟล์ภาพของผู้ใช้ (ดู assets/README.txt)
ASSETS_DIR = "assets"

# ชื่อไฟล์ภาพของแต่ละสถานะ (ค้นในโฟลเดอร์ ASSETS_DIR ตามลำดับ — เจออันแรกใช้อันนั้น)
# รองรับ .gif (หลายเฟรม = อนิเมชัน) และ .png
PET_SPRITES = {
    "idle":   ["pet_idle.gif", "pet_idle.png"],
    "walk":   ["pet_walk.gif", "pet_walk.png"],
    "eat":    ["pet_eat.gif", "pet_eat.png"],
    "attack": ["pet_attack.gif", "pet_attack.png"],
    "hurt":   ["pet_hurt.gif", "pet_hurt.png"],
}
MONSTER_SPRITES = {
    "walk": ["monster_walk.gif", "monster_walk.png", "monster.gif", "monster.png"],
    "hurt": ["monster_hurt.gif", "monster_hurt.png"],
}
FOOD_SPRITES = ["food.png", "food.gif"]

# ขนาดตัวละครสำรอง (พิกเซล) เมื่อไม่มีไฟล์ภาพ
PET_SIZE = 90
MONSTER_SIZE = 78
FOOD_SIZE = 38

# ── ระบบแปลงร่าง (Evolution) ──────────────────────────────────────────────
# เมื่อเพ็ทถึงเลเวลที่กำหนด จะเปลี่ยนเป็น "ร่าง" ใหม่ (ชุดสไปรต์ใหม่)
# เรียงจากเลเวลน้อย -> มาก โปรแกรมเลือกร่างสูงสุดที่ level <= เลเวลปัจจุบัน
# ไฟล์สไปรต์ของแต่ละร่างตั้งชื่อตาม prefix เช่น prefix="pet2" -> pet2_idle.png,
#   pet2_walk.png, pet2_eat.png, pet2_attack.png, pet2_hurt.png (วางในโฟลเดอร์ assets)
# size/color ใช้กับ "ตัวสำรอง" เมื่อยังไม่มีไฟล์ภาพ (เห็นการแปลงร่างได้แม้ไม่มีอาร์ต)
PET_EVOLUTIONS = [
    {"level": 1,  "prefix": "pet",  "name": "ร่างที่ 1", "size": 90,  "color": "#5ec8f0"},
    {"level": 5,  "prefix": "pet2", "name": "ร่างที่ 2", "size": 120, "color": "#7ed957"},
    {"level": 10, "prefix": "pet3", "name": "ร่างที่ 3", "size": 150, "color": "#ffb02e"},
]

# การเคลื่อนไหว
TICK_MS = 33        # รอบอัปเดตเกม (~30 FPS)
ANIM_MS = 1000      # เวลาต่อ 1 เฟรมอนิเมชัน (1000 = 1 วินาที/เฟรม; ยิ่งน้อยยิ่งเร็ว)
WALK_SPEED = 2      # ความเร็วเดินของเพ็ท (พิกเซล/รอบ)
MONSTER_SPEED = 1.6 # ความเร็วมอนสเตอร์
GROUND_OFFSET = 0   # ตัวละครยืนสูงจากขอบบน taskbar เท่านี้ (0 = ยืนบน taskbar พอดี)
# ทิศที่รูปต้นฉบับ "หันหน้า" ไป: 1 = ขวา, -1 = ซ้าย
# เวลาตัวละครเดินสวนทาง โปรแกรมจะ flip รูปแนวนอนให้อัตโนมัติ
# ถ้าอาร์ตของคุณหันซ้ายอยู่แล้ว ให้เปลี่ยนเป็น -1
SPRITE_DEFAULT_DIR = 1

# สเตตัส (0..100 ยิ่งมากยิ่งดี)
PET_MAX_HP = 100
FULLNESS_DECAY = 0.6    # ความอิ่มลดต่อวินาที
HAPPY_DECAY = 0.35      # ความสุขลดต่อวินาที

# การต่อสู้
MONSTER_MAX_HP = 60
PET_ATTACK = 13         # ดาเมจพื้นฐานที่เพ็ทตีมอนสเตอร์ (เลเวล 1)
MONSTER_ATTACK = 7      # ดาเมจที่มอนสเตอร์ตีเพ็ท
ATTACK_RANGE = 95       # ระยะที่เริ่มโจมตีกันได้
ATTACK_COOLDOWN = 18    # หน่วงเวลาระหว่างการโจมตี (รอบ)
MONSTER_HP_PER_LEVEL = 8    # มอนสเตอร์เลือดเพิ่มตามเลเวลเพ็ท (ยิ่งสูงยิ่งท้าทาย)

# ระบบเลเวล / ค่าประสบการณ์ (XP)
XP_PER_FEED = 8         # XP ที่ได้เมื่อกินอาหารอิ่ม
XP_PER_PET = 3          # XP ที่ได้เมื่อถูกลูบหัว
XP_PER_WIN = 25         # XP ที่ได้เมื่อชนะมอนสเตอร์
BASE_XP_TO_LEVEL = 50   # XP ที่ต้องใช้เลื่อนจากเลเวล 1 -> 2
XP_GROWTH = 1.35        # ตัวคูณ XP ที่ต้องใช้ในแต่ละเลเวลถัดไป
HP_PER_LEVEL = 12       # เลือดสูงสุดที่เพิ่มต่อเลเวล
ATTACK_PER_LEVEL = 2    # พลังโจมตีที่เพิ่มต่อเลเวล

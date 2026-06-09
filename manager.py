# -*- coding: utf-8 -*-
"""LOVE_PET — เครื่องมือจัดการข้อมูล (หลังบ้าน) แยกจากตัวเกม

3 ระบบในหน้าต่างเดียว (แท็บ):
  1) จัดการสกิล      → แก้ assets/skills.json (เพิ่ม/แก้/ลบ + ฟอร์ม effects)
  2) จัดการมอนสเตอร์ → โฟลเดอร์ monsters/ (อัปโหลด walk/hurt)
  3) จัดการตัวละคร    → โฟลเดอร์ characters/ (sprite + ระดับ/ความชอบ/สกิลที่สุ่มได้)

รัน:  python manager.py   (หรือดับเบิลคลิก manage.bat)
ทุกอย่างอ่าน/เขียนผ่าน assets.py ชุดเดียวกับเกม — ข้อมูลจึงตรงกันเสมอ
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ให้ path สัมพัทธ์ชี้ที่โฟลเดอร์โปรแกรมเสมอ (เหมือน main.py)
_APP_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
try:
    os.chdir(_APP_DIR)
except OSError:
    pass

import config        # noqa: E402
import assets        # noqa: E402

# ── นิยามชนิดเอฟเฟกต์สกิล (ให้ฟอร์มสร้าง dropdown + ช่องกรอกค่าอัตโนมัติ) ──
# schema: type -> {hook, scope(bool), params:[(key, label, default)]}
EFFECT_TYPES = {
    # passive (มีผลตลอดตอนสู้) — scope=True = เลือกได้ว่าผลกับตัวเอง/ทั้งทีม
    "atk_mult":   {"hook": "passive", "scope": True,
                   "params": [("value", "ตัวคูณโจมตี (1.25 = +25%)", 1.25)]},
    "dmg_reduce": {"hook": "passive", "scope": True,
                   "params": [("value", "ลดดาเมจที่รับ (0.25 = 25%)", 0.25)]},
    "regen":      {"hook": "passive", "scope": True,
                   "params": [("value", "ฟื้นเลือด %/วินาที", 5)]},
    "crit_add":   {"hook": "passive", "scope": True,
                   "params": [("value", "+โอกาสคริ (%)", 25)]},
    "dodge_add":  {"hook": "passive", "scope": False,
                   "params": [("value", "+โอกาสหลบ (%)", 15)]},
    "rage_mult":  {"hook": "passive", "scope": False,
                   "params": [("value", "ตัวคูณเกจเดือด (1.6)", 1.6)]},
    "weaken":     {"hook": "passive", "scope": False,
                   "params": [("value", "ลดพลังโจมตีมอน (0.3 = 30%)", 0.3)]},
    "lifesteal":  {"hook": "passive", "scope": True,
                   "params": [("value", "ดูดเลือด % ของดาเมจ", 5)]},
    # ── ความเร็วโจมตี / สแต็ก ──
    "atk_speed":  {"hook": "passive", "scope": True,
                   "params": [("value", "⏩ +ความเร็วโจมตี (0.15 = +15%)", 0.15)]},
    "windfury":   {"hook": "passive", "scope": False,
                   "params": [("value", "🌪 ทุกหมัดที่ 3 +ความเร็ว (0.4)", 0.4)]},
    "blade_dance": {"hook": "passive", "scope": False,
                    "params": [("value", "🌀 +ความเร็วต่อสแต็ก (0.05 สูงสุด 5)", 0.05)]},
    "focus":      {"hook": "passive", "scope": False,
                   "params": [("value", "🎯 +ดาเมจต่อการตีเป้าเดิม (0.1 สูงสุด 5)", 0.1)]},
    # ── ระบบป้องกัน (passive แบบมีเงื่อนไข) ──
    "dmg_cap":    {"hook": "passive", "scope": False,
                   "params": [("value", "💎 ดาเมจไม่เกิน % ของเลือดสูงสุด (0.2)", 0.2)]},
    "vigor":      {"hook": "passive", "scope": False,
                   "params": [("value", "🏔 เลือดยิ่งน้อยยิ่งกันดาเมจ (สูงสุด +0.5)", 0.5)]},
    "second_wind": {"hook": "passive", "scope": False,
                    "params": [("value", "🌬 เลือด<25% → ฟื้น %/วินาที", 6)]},
    "last_stand": {"hook": "passive", "scope": False,
                   "params": [("value", "🆘 กันตายครั้งเดียว → อมตะกี่วินาที", 3)]},
    # ── สกิลใช้งาน (active = ปล่อยตอนเกจไม้ตายเต็ม) ──
    "shield":     {"hook": "active", "scope": False,
                   "params": [("pct", "🛡 โล่ = % ของเลือดสูงสุด (0.2)", 0.2)]},
    "invuln":     {"hook": "active", "scope": False,
                   "params": [("secs", "✨ อมตะกี่วินาที", 2)]},
    "heal_burst": {"hook": "active", "scope": False,
                   "params": [("pct", "💉 ฮีล % ของเลือดสูงสุด (0.25)", 0.25)]},
    "resurrect":  {"hook": "active", "scope": False,
                   "params": [("pct", "🌟 ชุบคืน % ของเลือด (0.3)", 0.3)]},
    "purify":     {"hook": "active", "scope": False, "params": []},
    "energize":   {"hook": "active", "scope": False,
                   "params": [("value", "⚡ เติมเกจ % (0.3)", 0.3)]},
    "life_seed":  {"hook": "passive", "scope": False,
                   "params": [("value", "🌱 เลือด<30% → ฮีล % ครั้งเดียว (0.4)", 0.4)]},
    # on_hit (ตอนน้องตีโดนมอน)
    "double":  {"hook": "on_hit", "scope": False,
                "params": [("chance", "โอกาสตีซ้ำ (0.25)", 0.25)]},
    "poison":  {"hook": "on_hit", "scope": False,
                "params": [("dps", "ดาเมจพิษต่อวินาที", 8),
                           ("chance", "โอกาสติด (1.0=100%, 0.2=20%)", 1.0)]},
    "freeze":  {"hook": "on_hit", "scope": False,
                "params": [("chance", "โอกาสแช่แข็ง (0.18)", 0.18),
                           ("ticks", "สตันกี่ tick", 7)]},
    "execute": {"hook": "on_hit", "scope": False,
                "params": [("below", "มอนเลือดต่ำกว่า (0.3)", 0.3),
                           ("mult", "+ดาเมจ (0.5 = +50%)", 0.5)]},
    "bleed":   {"hook": "on_hit", "scope": False,
                "params": [("pct", "%เลือดมอน/วินาที (0.02)", 0.02),
                           ("secs", "นานกี่วินาที", 6),
                           ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "cleave":  {"hook": "on_hit", "scope": False,
                "params": [("pct", "%ดาเมจกระจาย (0.3)", 0.3),
                           ("max_targets", "ใส่กี่ตัว", 3)]},
    "chain":   {"hook": "on_hit", "scope": False,
                "params": [("pct", "%ดาเมจชิ่ง (0.5)", 0.5)]},
    "giant_killer": {"hook": "on_hit", "scope": False,
                     "params": [("mult", "+ดาเมจใส่บอส/ตัวอึด (0.25)", 0.25)]},
    "lone_wolf": {"hook": "on_hit", "scope": False,
                  "params": [("mult", "+ดาเมจถ้าไม่มีเพื่อนใกล้ (0.3)", 0.3)]},
    "vulnerable": {"hook": "on_hit", "scope": False,
                   "params": [("pct", "มอนรับดาเมจเพิ่ม (0.15)", 0.15),
                              ("secs", "นานกี่วินาที", 5),
                              ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "slow":    {"hook": "on_hit", "scope": False,
                "params": [("pct", "ลดความเร็วมอน (0.4)", 0.4),
                           ("secs", "นานกี่วินาที", 4)]},
    "stun":    {"hook": "on_hit", "scope": False,
                "params": [("chance", "โอกาสสตัน (0.1)", 0.1),
                           ("ticks", "สตันกี่ tick", 45)]},
    "blind":   {"hook": "on_hit", "scope": False,
                "params": [("chance", "โอกาสติดตาบอด (0.5)", 0.5),
                           ("miss", "โอกาสมอนพลาด (0.5)", 0.5)]},
    "knockback": {"hook": "on_hit", "scope": False,
                  "params": [("chance", "โอกาสผลัก (0.2)", 0.2),
                             ("dist", "ระยะผลัก (px)", 60)]},
    "armor_break": {"hook": "on_hit", "scope": False,
                    "params": [("amount", "⛏ ลดเกราะมอนต่อตี (0.04 สะสม)", 0.04),
                               ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "doom":    {"hook": "on_hit", "scope": False,
                "params": [("secs", "☠ นับถอยหลังกี่วินาที", 8),
                           ("mult", "ดาเมจระเบิด = โจมตี ×(3.0)", 3.0),
                           ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "plague":  {"hook": "on_hit", "scope": False,
                "params": [("dps", "🦠 พิษ/วินาที (ตายแล้วแพร่)", 10),
                           ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "poison_stack": {"hook": "on_hit", "scope": False,
                     "params": [("dps", "🧪 +พิษ/วินาทีต่อตี (สะสม)", 5),
                                ("secs", "นานกี่วินาที", 5),
                                ("chance", "โอกาสติด (1.0=100%)", 1.0)]},
    "pierce":  {"hook": "passive", "scope": False,
                "params": [("value", "⛏ เพิกเฉยเกราะมอน % (0.5)", 0.5)]},
    # on_hurt (ตอนน้องโดนมอนตี)
    "thorns":  {"hook": "on_hurt", "scope": False,
                "params": [("pct", "%สะท้อนกลับ (0.15)", 0.15)]},
    # on_kill (ตอนฆ่ามอนด้วยหมัดนี้)
    "fatality": {"hook": "on_kill", "scope": False,
                 "params": [("value", "คืนเกจไม้ตาย (0.2 = 20%)", 0.2)]},
}
_INT_PARAMS = {"ticks", "secs", "max_targets"}      # พารามิเตอร์ที่เก็บเป็นจำนวนเต็ม

# สล็อตรูปของตัวละคร (idle จำเป็น ที่เหลือไม่บังคับ)
PET_SLOTS = ["idle", "walk", "attack", "hurt", "eat", "dead",
             "taken", "sleep", "bathe", "pet"]
SLOT_LABEL = {"idle": "ยืน (จำเป็น)", "walk": "เดิน", "attack": "โจมตี", "hurt": "เจ็บ",
              "eat": "กิน", "dead": "ตาย", "taken": "ถูกอุ้ม", "sleep": "นอน",
              "bathe": "อาบน้ำ", "pet": "ลูบหัว"}
IMG_TYPES = [("รูปภาพ", "*.png *.gif"), ("ทั้งหมด", "*.*")]


def _num(s, default=0.0, as_int=False):
    """แปลงสตริงเป็นตัวเลข (คืน default ถ้าพัง)"""
    try:
        v = float(str(s).strip())
        return int(round(v)) if as_int else v
    except (TypeError, ValueError):
        return default


def _effect_str(e):
    """แปลง effect เป็นข้อความอ่านง่ายสำหรับโชว์ในลิสต์"""
    t = e.get("type", "?")
    parts = [f"{p}={e[p]}" for p in e if p not in ("hook", "type", "scope")]
    sc = f" [{e['scope']}]" if e.get("scope") else ""
    return f"{e.get('hook', '?'):8s} · {t}{sc}  {' '.join(parts)}"


# 4 สายของสกิล (เรียงลำดับการแสดงผล) — แยกสายป้องกันออกจากบัพด้วยออร่าฟ้า
SKILL_CATEGORIES = [
    ("attack",  "⚔ สายต่อสู้"),
    ("defense", "🛡 สายป้องกัน"),
    ("buff",    "✨ สายบัพ"),
    ("debuff",  "☠ สายดีบัพ"),
]


def skill_category(s):
    """จัดสายของสกิลจาก type (+ ออร่า): buff+ออร่าฟ้า = สายป้องกัน"""
    t = s.get("type", "buff")
    if t in ("attack", "defense", "debuff"):
        return t
    return "defense" if s.get("aura") == "blue" else "buff"


def skill_is_active(s):
    """สกิลใช้งาน (active) = ปล่อยตอนเกจไม้ตายเต็ม
    ใช้ธง 'active' ที่ตั้งเอง ถ้าไม่ได้ตั้งให้เดาจากมี effect hook 'active'"""
    if "active" in s:
        return bool(s["active"])
    return any(e.get("hook") == "active" for e in s.get("effects", []))


def skill_kind_label(s):
    return "⚡ สกิลใช้งาน (ปล่อยตอนไม้ตายเต็ม)" if skill_is_active(s) else "🟢 พาสซีฟ (ทำงานเอง)"


# ---------------------------------------------------------------------------
class ManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LOVE_PET — เครื่องมือจัดการข้อมูล (หลังบ้าน)")
        self.geometry("760x560")
        self.minsize(680, 480)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_skill = ttk.Frame(nb)
        self.tab_mon = ttk.Frame(nb)
        self.tab_pet = ttk.Frame(nb)
        nb.add(self.tab_skill, text="  ⚡ จัดการสกิล  ")
        nb.add(self.tab_mon, text="  👾 จัดการมอนสเตอร์  ")
        nb.add(self.tab_pet, text="  🐾 จัดการตัวละคร  ")

        self._build_skill_tab()
        self._build_monster_tab()
        self._build_pet_tab()
        self._refresh_skills()
        self._refresh_monsters()
        self._refresh_pets()

    # ============================================================ SKILLS
    def _build_skill_tab(self):
        f = self.tab_skill
        ttk.Label(f, text="สกิลทั้งหมด  (⚡ = สกิลใช้งาน/ปล่อยตอนไม้ตาย, 🟢 = พาสซีฟ/ทำงานเอง)",
                  font=("Segoe UI", 10)).pack(anchor="w", padx=10, pady=(10, 4))
        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10)
        self.skill_list = tk.Listbox(mid, font=("Consolas", 10), activestyle="none")
        self.skill_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.skill_list.yview)
        sb.pack(side="left", fill="y")
        self.skill_list.config(yscrollcommand=sb.set)
        self.skill_list.bind("<Double-Button-1>", lambda e: self._skill_edit())
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar, text="➕ เพิ่มสกิลใหม่", command=self._skill_new).pack(side="left")
        ttk.Button(bar, text="✏️ แก้ไข", command=self._skill_edit).pack(side="left", padx=6)
        ttk.Button(bar, text="🗑 ลบ / รีเซ็ต", command=self._skill_delete).pack(side="left")
        ttk.Button(bar, text="ℹ️ คำอธิบาย Effect",
                   command=self._show_effect_help).pack(side="right")
        ttk.Button(bar, text="ℹ️ ชนิดสกิล",
                   command=self._show_skilltype_help).pack(side="right", padx=6)

    # ---- ป๊อปอัพคำอธิบาย ----
    def _help_popup(self, title, text, parent=None):
        parent = parent or self
        win = tk.Toplevel(parent)
        win.title(title)
        win.transient(parent)
        win.grab_set()                           # ให้กดได้แม้เปิดทับหน้าต่างที่ grab อยู่
        win.geometry("580x540")
        frm = ttk.Frame(win)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        txt = tk.Text(frm, wrap="word", font=("Segoe UI", 10), bd=0)
        txt.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frm, command=txt.yview)
        sb.pack(side="left", fill="y")
        txt.config(yscrollcommand=sb.set)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        ttk.Button(win, text="ปิด", command=win.destroy).pack(pady=6)

    def _all_skills_help_text(self):
        """ข้อความรวมคำอธิบายสกิล 'ทั้งหมด' แยกตามสาย"""
        groups = {cat: [] for cat, _ in SKILL_CATEGORIES}
        for s in assets.load_skills():
            groups[skill_category(s)].append(s)
        lines = ["คำอธิบายสกิลทั้งหมด (แยกตามสาย)", "─" * 46, ""]
        for cat, label in SKILL_CATEGORIES:
            rows = groups[cat]
            if not rows:
                continue
            lines.append(f"{label}  ({len(rows)})")
            for s in rows:
                tag = "  ⚡ใช้งาน" if skill_is_active(s) else ""
                if not s.get("pool", True):
                    tag += "  (ปิดสุ่ม)"
                lines.append(f"   {s.get('emoji', '')} {s.get('name', s['id'])} "
                             f"({s['id']}){tag}")
                lines.append(f"        {s.get('desc', '-')}")
            lines.append("")
        return ("🟢 พาสซีฟ = ทำงานเองตลอด   |   ⚡ สกิลใช้งาน = ปล่อยตอนเกจไม้ตายเต็ม\n"
                "─" * 46 + "\n\n" + "\n".join(lines))

    def _show_effect_help(self):
        """คำอธิบายชนิด effect ทั้งหมด — สร้างจาก EFFECT_TYPES อัตโนมัติ (ตรงกับฟอร์มเสมอ)"""
        hook_th = {
            "passive":  "🟢 PASSIVE — มีผลตลอดเวลาที่อยู่ในทีมสู้",
            "on_hit":   "⚔ ON_HIT — ทำงานตอนน้องตีโดนมอน (ranged = ตอนลูกไปโดน)",
            "on_hurt":  "🛡 ON_HURT — ทำงานตอนน้องโดนมอนตี",
            "on_kill":  "💀 ON_KILL — ทำงานตอนฆ่ามอนด้วยหมัดนั้น",
            "active":   "⏱ ACTIVE — สกิลกดใช้ (ทำงานเองอัตโนมัติทุก ๆ คูลดาวน์วินาที)",
        }
        groups = {}
        for t, sch in EFFECT_TYPES.items():
            groups.setdefault(sch["hook"], []).append((t, sch))
        lines = [
            "เอฟเฟกต์ (effect) คือ 'ผล' ของสกิล",
            "1 สกิลใส่ได้หลาย effect — แต่ละตัวผูกกับ 'จังหวะทำงาน (hook)'",
            "[self/team] = เลือกได้ว่าผลกับตัวเอง หรือทั้งทีม",
            "─" * 46, "",
        ]
        for hook in ("passive", "on_hit", "on_hurt", "on_kill", "active"):
            if hook not in groups:
                continue
            lines.append(hook_th.get(hook, hook))
            for t, sch in sorted(groups[hook]):
                sc = "  [self/team]" if sch.get("scope") else ""
                lines.append(f"   • {t}{sc}")
                for _k, label, _d in sch["params"]:
                    lines.append(f"        - {label}")
            lines.append("")
        self._help_popup("คำอธิบาย Effect ของสกิล", "\n".join(lines))

    def _show_skilltype_help(self):
        """คำอธิบายฟิลด์ระดับสกิล (ชนิด/เป้า/ออร่า/กองสุ่ม ฯลฯ)"""
        text = (
            "ชนิดและฟิลด์ของสกิล (ส่วนหัวของแต่ละสกิล)\n"
            "─────────────────────────────────────────────\n\n"
            "🟢⚡ การใช้สกิล (พาสซีฟ / สกิลใช้งาน)\n"
            "   • 🟢 พาสซีฟ = effect แบบ passive/on_hit/on_hurt/on_kill\n"
            "        → ทำงานเองตลอดเวลาที่สู้ ไม่ต้องรอเกจ\n"
            "   • ⚡ สกิลใช้งาน = สกิลที่มี effect hook 'active'\n"
            "        → เก็บเกจไม้ตายจนเต็มแล้ว 'ปล่อย' สกิลนั้น\n"
            "        (น้อง: แทนท่าไม้ตายดาเมจปกติ | มอน/บอส: ก็ทำเหมือนกัน)\n\n"
            "🏷 ประเภท (type) — ใช้จัดกลุ่ม/แสดงผล ไม่ได้บังคับกลไก\n"
            "   • attack  = สายต่อสู้\n"
            "   • defense = สายป้องกัน\n"
            "   • buff    = สายบัพ (เสริม/ฮีล)\n"
            "   • debuff  = สายดีบัพ (พิษ/ลดพลัง/ควบคุม)\n\n"
            "🎯 เป้า (target)\n"
            "   • self = ผลเฉพาะน้องตัวที่มีสกิล\n"
            "   • all  = ผลทั้งทีมที่ร่วมสู้ (ออร่า/บัฟหมู่)\n"
            "   *ใช้คู่กับ effect แบบ passive ที่ตั้ง scope = team\n\n"
            "🌈 ออร่า (aura) — วงแสงใต้เท้าตอนสู้\n"
            "   • red = โจมตี   • blue = ป้องกัน   • green = ฮีล\n"
            "   • เว้นว่าง = ไม่มีวงแสง\n\n"
            "🎲 อยู่ในกองสุ่ม (pool)\n"
            "   • ติ๊ก = สุ่มแจกให้น้องตอนเกิด/ฟักได้\n"
            "   • ไม่ติ๊ก = เก็บไว้แต่ยังไม่ออกสุ่ม (เช่นกำลังทดลอง)\n\n"
            "⚖ น้ำหนักสุ่ม (weight)\n"
            "   • ยิ่งมาก ยิ่งออกบ่อย (เทียบกันภายในกองสุ่ม)\n\n"
            "⭐ ระดับขั้นต่ำ (rarity_min)\n"
            "   • สุ่มออกเฉพาะน้องที่ความหายาก ≥ ระดับนี้\n"
            "   • เว้นว่าง = ทุกระดับสุ่มได้\n\n"
            "─────────────────────────────────────────────\n"
            "สรุปความสัมพันธ์:\n"
            "  • 'ชนิดสกิล' = ป้าย + การแสดงผล + กติกาการสุ่ม\n"
            "  • 'Effect'    = ผลจริงในการต่อสู้ (ดูปุ่มคำอธิบาย Effect)\n"
            "  • จำกัดสกิลที่น้องแต่ละตัวสุ่มได้ → ตั้ง allow-list\n"
            "    ในแท็บ '🐾 จัดการตัวละคร'"
        )
        self._help_popup("คำอธิบายชนิดของสกิล", text)

    def _load_skill_state(self):
        """โหลดสถานะสกิล: base (config) + custom (skills.json) → คืน (ids, base, custom)"""
        base = {s["id"]: s for s in config.SKILLS}
        custom = {e["id"]: e for e in assets.load_user_skills()}
        ids = list(base.keys()) + [i for i in custom if i not in base]
        return ids, base, custom

    def _refresh_skills(self):
        self.skill_list.delete(0, "end")
        ids, base, custom = self._load_skill_state()
        # จัดสกิลเข้าสาย
        groups = {cat: [] for cat, _ in SKILL_CATEGORIES}
        for sid in ids:
            eff = custom.get(sid) or base.get(sid) or {}
            groups[skill_category(eff)].append((sid, eff))
        self._skill_ids = []                     # ขนาน 1:1 กับแถวใน listbox (header = None)
        for cat, label in SKILL_CATEGORIES:
            rows = groups[cat]
            if not rows:
                continue
            self.skill_list.insert("end", f"━━━ {label}  ({len(rows)}) ━━━━━━━━━━")
            self.skill_list.itemconfig("end", foreground="#1a5fb4")
            self._skill_ids.append(None)
            for sid, eff in rows:
                tag = ("กำหนดเอง" if sid not in base else
                       ("ทับค่าเดิม" if sid in custom else "มากับเกม"))
                pool = "" if eff.get("pool", True) else "  (ปิดสุ่ม)"
                kind = "⚡" if skill_is_active(eff) else "🟢"   # สกิลใช้งาน / พาสซีฟ
                self.skill_list.insert(
                    "end",
                    f"  {kind} {eff.get('emoji', '')} {sid:12s} {eff.get('name', sid):16s} [{tag}]{pool}")
                self._skill_ids.append(sid)

    def _selected_skill_id(self):
        sel = self.skill_list.curselection()
        if not sel:
            return None
        return self._skill_ids[sel[0]]           # None ถ้าเลือกโดนแถวหัวข้อ

    def _skill_effective(self, sid):
        """นิยามสกิลที่ใช้แก้ไข — custom ถ้ามี ไม่งั้นสังเคราะห์จาก base"""
        _ids, base, custom = self._load_skill_state()
        if sid in custom:
            import copy
            return copy.deepcopy(custom[sid])
        s = dict(base.get(sid, {}))
        s["effects"] = assets._synth_effects(s)
        return s

    def _skill_new(self):
        self._skill_dialog(None)

    def _skill_edit(self):
        sid = self._selected_skill_id()
        if not sid:
            return
        self._skill_dialog(sid)

    def _skill_delete(self):
        sid = self._selected_skill_id()
        if not sid:
            return
        _ids, base, custom = self._load_skill_state()
        if sid in base and sid not in custom:
            messagebox.showinfo("ลบไม่ได้",
                                "สกิลนี้มากับเกม ลบไม่ได้\n(กด 'แก้ไข' เพื่อ override หรือปิดกองสุ่มได้)",
                                parent=self)
            return
        what = "รีเซ็ตเป็นค่าเดิม" if sid in base else "ลบสกิลนี้"
        if not messagebox.askyesno("ยืนยัน", f"{what}: {sid} ?", parent=self):
            return
        custom.pop(sid, None)
        assets.save_user_skills(list(custom.values()))
        self._refresh_skills()

    def _skill_dialog(self, sid):
        """ฟอร์มเพิ่ม/แก้สกิล (รวมตัวแก้ effects แบบ dropdown)"""
        editing = sid is not None
        data = self._skill_effective(sid) if editing else {
            "id": "", "emoji": "✨", "type": "attack", "name": "", "desc": "",
            "aura": "", "target": "self", "pool": True, "weight": 1.0,
            "rarity_min": "", "effects": []}
        effects = [dict(e) for e in data.get("effects", [])]

        win = tk.Toplevel(self)
        win.title(f"แก้ไขสกิล: {sid}" if editing else "เพิ่มสกิลใหม่")
        win.transient(self)
        win.grab_set()
        pad = {"padx": 6, "pady": 3}

        def row(r, label):
            ttk.Label(win, text=label).grid(row=r, column=0, sticky="e", **pad)

        v_id = tk.StringVar(value=data.get("id", ""))
        v_emoji = tk.StringVar(value=data.get("emoji", ""))
        v_name = tk.StringVar(value=data.get("name", ""))
        v_desc = tk.StringVar(value=data.get("desc", ""))
        v_type = tk.StringVar(value=data.get("type", "attack"))
        v_aura = tk.StringVar(value=data.get("aura", "") or "")
        v_target = tk.StringVar(value=data.get("target", "self"))
        v_pool = tk.BooleanVar(value=bool(data.get("pool", True)))
        v_weight = tk.StringVar(value=str(data.get("weight", 1.0)))
        v_rarity = tk.StringVar(value=data.get("rarity_min", "") or "")
        _KIND_PASSIVE = "🟢 พาสซีฟ (ทำงานเอง)"
        _KIND_ACTIVE = "⚡ สกิลใช้งาน (ปล่อยตอนไม้ตาย)"
        v_kind = tk.StringVar(value=_KIND_ACTIVE if skill_is_active(data) else _KIND_PASSIVE)
        v_cd = tk.StringVar(value=str(data.get("cd", config.SKILL_CD_DEFAULT)))

        row(0, "id (อังกฤษ)")
        e_id = ttk.Entry(win, textvariable=v_id, width=24)
        e_id.grid(row=0, column=1, sticky="w", **pad)
        if editing:
            e_id.config(state="disabled")
        row(1, "ชื่อ")
        ttk.Entry(win, textvariable=v_name, width=24).grid(row=1, column=1, sticky="w", **pad)
        row(2, "อิโมจิ")
        ttk.Entry(win, textvariable=v_emoji, width=8).grid(row=2, column=1, sticky="w", **pad)
        row(3, "คำอธิบาย")
        ttk.Entry(win, textvariable=v_desc, width=40).grid(row=3, column=1, sticky="w", **pad)
        row(4, "ประเภท")
        ttk.Combobox(win, textvariable=v_type, values=["attack", "defense", "buff", "debuff"],
                     width=12, state="readonly").grid(row=4, column=1, sticky="w", **pad)
        row(5, "ออร่า")
        ttk.Combobox(win, textvariable=v_aura, values=["", "red", "blue", "green"],
                     width=12, state="readonly").grid(row=5, column=1, sticky="w", **pad)
        row(6, "เป้า (ตัวเอง/ทีม)")
        ttk.Combobox(win, textvariable=v_target, values=["self", "all"],
                     width=12, state="readonly").grid(row=6, column=1, sticky="w", **pad)
        row(7, "อยู่ในกองสุ่ม")
        ttk.Checkbutton(win, variable=v_pool).grid(row=7, column=1, sticky="w", **pad)
        row(8, "น้ำหนักสุ่ม")
        ttk.Entry(win, textvariable=v_weight, width=8).grid(row=8, column=1, sticky="w", **pad)
        row(9, "ระดับขั้นต่ำ")
        ttk.Combobox(win, textvariable=v_rarity, width=12, state="readonly",
                     values=["", "common", "rare", "epic", "legendary"]
                     ).grid(row=9, column=1, sticky="w", **pad)
        row(10, "การใช้สกิล")
        ttk.Combobox(win, textvariable=v_kind, width=26, state="readonly",
                     values=[_KIND_PASSIVE, _KIND_ACTIVE]
                     ).grid(row=10, column=1, sticky="w", **pad)
        row(11, "คูลดาวน์ วิ (active)")
        ttk.Entry(win, textvariable=v_cd, width=8).grid(row=11, column=1, sticky="w", **pad)

        # ── ตัวแก้ effects ──
        ef = ttk.LabelFrame(win, text="เอฟเฟกต์ (effects)")
        ef.grid(row=0, column=2, rowspan=13, sticky="nsew", padx=8, pady=6)
        ttk.Label(ef, text="(on_hit/พิษ/ดีบัฟ: พาสซีฟ=ติดทุกหมัด | สกิลใช้งาน=ปล่อยตอนไม้ตาย)",
                  foreground="#888", wraplength=300).pack(anchor="w", padx=4, pady=(4, 0))
        lb = tk.Listbox(ef, width=46, height=8, font=("Consolas", 9))
        lb.pack(fill="both", expand=True, padx=4, pady=4)

        def refresh_eff():
            lb.delete(0, "end")
            for e in effects:
                lb.insert("end", _effect_str(e))

        ctl = ttk.Frame(ef)
        ctl.pack(fill="x", padx=4, pady=2)
        v_etype = tk.StringVar(value="atk_mult")
        v_scope = tk.StringVar(value="self")
        ttk.Label(ctl, text="ชนิด").grid(row=0, column=0, sticky="e")
        cb_type = ttk.Combobox(ctl, textvariable=v_etype, width=14, state="readonly",
                               values=list(EFFECT_TYPES.keys()))
        cb_type.grid(row=0, column=1, sticky="w")
        scope_box = ttk.Combobox(ctl, textvariable=v_scope, width=8, state="readonly",
                                 values=["self", "team"])
        lbl_scope = ttk.Label(ctl, text="scope")
        # ช่องพารามิเตอร์ (สูงสุด 3)
        p_lbls = [ttk.Label(ctl, text="") for _ in range(3)]
        p_vars = [tk.StringVar() for _ in range(3)]
        p_ents = [ttk.Entry(ctl, textvariable=p_vars[i], width=10) for i in range(3)]

        def on_type(*_):
            schema = EFFECT_TYPES[v_etype.get()]
            params = schema["params"]
            for i in range(3):
                if i < len(params):
                    key, label, default = params[i]
                    p_lbls[i].config(text=label)
                    p_vars[i].set(str(default))
                    p_lbls[i].grid(row=1 + i, column=0, sticky="e", pady=1)
                    p_ents[i].grid(row=1 + i, column=1, sticky="w", pady=1)
                else:
                    p_lbls[i].grid_remove()
                    p_ents[i].grid_remove()
            if schema.get("scope"):
                lbl_scope.grid(row=0, column=2, sticky="e", padx=(8, 0))
                scope_box.grid(row=0, column=3, sticky="w")
            else:
                lbl_scope.grid_remove()
                scope_box.grid_remove()

        cb_type.bind("<<ComboboxSelected>>", on_type)
        on_type()

        def add_eff():
            t = v_etype.get()
            schema = EFFECT_TYPES[t]
            e = {"hook": schema["hook"], "type": t}
            for i, (key, _lbl, _d) in enumerate(schema["params"]):
                e[key] = _num(p_vars[i].get(), as_int=(key in _INT_PARAMS))
            if schema.get("scope"):
                e["scope"] = v_scope.get()
            effects.append(e)
            refresh_eff()

        def del_eff():
            sel = lb.curselection()
            if sel:
                effects.pop(sel[0])
                refresh_eff()

        btns = ttk.Frame(ef)
        btns.pack(fill="x", padx=4, pady=4)
        ttk.Button(btns, text="➕ เพิ่มเอฟเฟกต์", command=add_eff).pack(side="left")
        ttk.Button(btns, text="🗑 ลบที่เลือก", command=del_eff).pack(side="left", padx=6)
        refresh_eff()

        # ── บันทึก ──
        def save():
            sk_id = (sid if editing else v_id.get().strip())
            if not sk_id or not sk_id.isascii():
                messagebox.showwarning("ผิดพลาด", "ต้องมี id เป็นภาษาอังกฤษ", parent=win)
                return
            _ids, base, custom = self._load_skill_state()
            if not editing and (sk_id in base or sk_id in custom):
                messagebox.showwarning("ผิดพลาด", f"id '{sk_id}' มีอยู่แล้ว", parent=win)
                return
            entry = {
                "id": sk_id,
                "emoji": v_emoji.get().strip(),
                "type": v_type.get(),
                "name": v_name.get().strip() or sk_id,
                "desc": v_desc.get().strip(),
                "target": v_target.get(),
                "pool": bool(v_pool.get()),
                "weight": _num(v_weight.get(), 1.0),
                "active": v_kind.get() == _KIND_ACTIVE,   # พาสซีฟ/สกิลใช้งาน (ตั้งเอง)
                "cd": _num(v_cd.get(), config.SKILL_CD_DEFAULT),  # คูลดาวน์ (ใช้เมื่อ active)
                "effects": effects,
            }
            if v_aura.get():
                entry["aura"] = v_aura.get()
            if v_rarity.get():
                entry["rarity_min"] = v_rarity.get()
            custom[sk_id] = entry
            assets.save_user_skills(list(custom.values()))
            self._refresh_skills()
            win.destroy()

        sbar = ttk.Frame(win)
        sbar.grid(row=12, column=0, columnspan=2, pady=10)
        ttk.Button(sbar, text="💾 บันทึก", command=save).pack(side="left", padx=4)
        ttk.Button(sbar, text="ยกเลิก", command=win.destroy).pack(side="left")
        win.columnconfigure(2, weight=1)
        win.rowconfigure(11, weight=1)

    # ============================================================ MONSTERS
    def _build_monster_tab(self):
        f = self.tab_mon
        ttk.Label(f, text="มอนสเตอร์ (แต่ละตัว = 1 โฟลเดอร์ใน monsters/ ต้องมีรูป 'เดิน' อย่างน้อย)",
                  font=("Segoe UI", 10)).pack(anchor="w", padx=10, pady=(10, 4))
        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10)
        self.mon_list = tk.Listbox(mid, font=("Segoe UI", 10))
        self.mon_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.mon_list.yview)
        sb.pack(side="left", fill="y")
        self.mon_list.config(yscrollcommand=sb.set)
        self.mon_list.bind("<Double-Button-1>", lambda e: self._monster_edit())
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar, text="➕ เพิ่มมอน", command=self._monster_new).pack(side="left")
        ttk.Button(bar, text="✏️ แก้ไข", command=self._monster_edit).pack(side="left", padx=6)
        ttk.Button(bar, text="🗑 ลบ", command=self._monster_delete).pack(side="left")

    def _refresh_monsters(self):
        self.mon_list.delete(0, "end")
        self._mon_names = assets.list_monsters()
        for n in self._mon_names:
            mm = assets.load_monster_meta(n)
            rar = config.rarity_by_id(mm.get("rarity", "common"))
            sk = mm.get("skill", "")
            tags = f"[{rar['name']} {'⭐' * rar['stars']}]"
            if mm.get("range_type") == "ranged":
                tags += " 🏹"
            if sk:
                tags += f" ⚡{sk}"
            self.mon_list.insert("end", f"👾  {n}    {tags}")
        if not self._mon_names:
            self.mon_list.insert("end", "(ยังไม่มีมอนที่เพิ่มเอง — ใช้มอนเริ่มต้นจาก assets/)")

    def _selected_monster(self):
        sel = self.mon_list.curselection()
        if sel and self._mon_names and sel[0] < len(self._mon_names):
            return self._mon_names[sel[0]]
        return None

    def _monster_new(self):
        self._monster_dialog(None)

    def _monster_edit(self):
        n = self._selected_monster()
        if n:
            self._monster_dialog(n)

    def _monster_delete(self):
        n = self._selected_monster()
        if not n:
            return
        if messagebox.askyesno("ยืนยัน", f"ลบมอน '{n}' ?", parent=self):
            assets.delete_monster(n)
            self._refresh_monsters()

    def _existing_slot(self, folder, slot):
        """หาไฟล์ของสล็อตในโฟลเดอร์ (full path) หรือ None"""
        import glob
        found = sorted(glob.glob(os.path.join(folder, slot + ".*"))
                       + glob.glob(os.path.join(folder, slot + "_*.*")))
        return found[0] if found else None

    def _monster_dialog(self, name):
        editing = name is not None
        win = tk.Toplevel(self)
        win.title(f"แก้ไขมอน: {name}" if editing else "เพิ่มมอนใหม่")
        win.transient(self)
        win.grab_set()
        pad = {"padx": 8, "pady": 5}

        meta = assets.load_monster_meta(name) if editing else {}
        v_name = tk.StringVar(value=name or "")
        ttk.Label(win, text="ชื่อ").grid(row=0, column=0, sticky="e", **pad)
        e_name = ttk.Entry(win, textvariable=v_name, width=30)
        e_name.grid(row=0, column=1, sticky="w", **pad)
        if editing:
            e_name.config(state="disabled")

        ttk.Label(win, text="ระดับความหายาก").grid(row=1, column=0, sticky="e", **pad)
        v_rarity = tk.StringVar(value=meta.get("rarity", "common"))
        ttk.Combobox(win, textvariable=v_rarity, state="readonly", width=14,
                     values=[r["id"] for r in config.RARITIES]
                     ).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(win, text="ประเภทการตี").grid(row=2, column=0, sticky="e", **pad)
        v_range = tk.StringVar(value=meta.get("range_type", "melee"))
        ttk.Combobox(win, textvariable=v_range, state="readonly", width=14,
                     values=["melee", "ranged"]).grid(row=2, column=1, sticky="w", **pad)

        # สกิล (เราเลือกให้เอง 1 อย่าง; ว่าง = ไม่มีสกิล)
        skill_holder = {"id": meta.get("skill", "")}
        ttk.Label(win, text="สกิล").grid(row=3, column=0, sticky="e", **pad)
        v_skill = tk.StringVar()
        ttk.Label(win, textvariable=v_skill, foreground="#1a5fb4").grid(
            row=3, column=1, sticky="w", **pad)

        def refresh_skill_label():
            sid = skill_holder["id"]
            if not sid:
                v_skill.set("(ไม่มีสกิล)")
            else:
                by = {s["id"]: s for s in assets.load_skills()}
                s = by.get(sid, {})
                v_skill.set(f"{s.get('emoji', '')} {sid} — {s.get('name', sid)}")

        def pick_skill():
            res = self._skill_picker(win, [skill_holder["id"]] if skill_holder["id"] else [],
                                     single=True)
            if res is not None:
                skill_holder["id"] = res[0] if res else ""
                refresh_skill_label()

        sb_ = ttk.Frame(win)
        sb_.grid(row=3, column=2, sticky="w", **pad)
        ttk.Button(sb_, text="เลือก", width=6, command=pick_skill).pack(side="left")
        ttk.Button(sb_, text="ไม่มี", width=5,
                   command=lambda: (skill_holder.update(id=""), refresh_skill_label())).pack(side="left")
        refresh_skill_label()

        folder = assets.monster_path(name) if editing else None
        # รูป 6 สถานะ (เหมือนตัวละคร แต่ไม่มีอาหาร): ยืน/เดิน/โจมตี/เจ็บ/ติด CC/ตาย
        slots = [("idle", "ยืน"), ("walk", "เดิน (จำเป็น)"), ("attack", "โจมตี"),
                 ("hurt", "เจ็บ"), ("cc", "ติด CC"), ("dead", "ตาย")]
        pick_vars = {}
        for i, (slot, label) in enumerate(slots):
            cur = self._existing_slot(folder, slot) if folder else None
            var = tk.StringVar(value=cur or "")
            pick_vars[slot] = var
            r = 4 + i
            ttk.Label(win, text=label).grid(row=r, column=0, sticky="e", **pad)
            ttk.Entry(win, textvariable=var, width=40).grid(row=r, column=1, sticky="w", **pad)
            ttk.Button(win, text="...", width=3,
                       command=lambda v=var: v.set(filedialog.askopenfilename(
                           parent=win, filetypes=IMG_TYPES) or v.get())
                       ).grid(row=r, column=2, **pad)

        def save():
            nm = v_name.get().strip()
            if not nm:
                messagebox.showwarning("ผิดพลาด", "ต้องตั้งชื่อ", parent=win)
                return
            files = {s: v.get().strip() for s, v in pick_vars.items()
                     if v.get().strip() and os.path.isfile(v.get().strip())}
            if not (files.get("walk") or files.get("idle")):
                messagebox.showwarning("ผิดพลาด", "ต้องมีรูป 'เดิน' หรือ 'ยืน' อย่างน้อย", parent=win)
                return
            new_meta = dict(meta)
            new_meta.update({"rarity": v_rarity.get(), "range_type": v_range.get()})
            if skill_holder["id"]:
                new_meta["skill"] = skill_holder["id"]
            else:
                new_meta.pop("skill", None)
            if assets.add_monster(nm, files, new_meta) is None:
                messagebox.showerror("ผิดพลาด", "บันทึกไม่สำเร็จ (ตรวจไฟล์รูป)", parent=win)
                return
            self._refresh_monsters()
            win.destroy()

        bar = ttk.Frame(win)
        bar.grid(row=12, column=0, columnspan=3, pady=12)
        ttk.Button(bar, text="💾 บันทึก", command=save).pack(side="left", padx=4)
        ttk.Button(bar, text="ยกเลิก", command=win.destroy).pack(side="left")

    # ============================================================ PETS / CHARACTERS
    def _build_pet_tab(self):
        f = self.tab_pet
        ttk.Label(f, text="ตัวละคร (แต่ละตัว = 1 โฟลเดอร์ใน characters/ ต้องมีรูป 'ยืน' อย่างน้อย)",
                  font=("Segoe UI", 10)).pack(anchor="w", padx=10, pady=(10, 4))
        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10)
        self.pet_list = tk.Listbox(mid, font=("Segoe UI", 10))
        self.pet_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.pet_list.yview)
        sb.pack(side="left", fill="y")
        self.pet_list.config(yscrollcommand=sb.set)
        self.pet_list.bind("<Double-Button-1>", lambda e: self._pet_edit())
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar, text="➕ สร้างตัวละคร", command=self._pet_new).pack(side="left")
        ttk.Button(bar, text="✏️ แก้ไข", command=self._pet_edit).pack(side="left", padx=6)
        ttk.Button(bar, text="🗑 ลบ", command=self._pet_delete).pack(side="left")

    def _refresh_pets(self):
        self.pet_list.delete(0, "end")
        self._pet_names = assets.list_characters()
        for n in self._pet_names:
            rar = config.rarity_by_id(assets.character_rarity(n))
            self.pet_list.insert("end", f"🐾  {n}    [{rar['name']} {'⭐' * rar['stars']}]")
        if not self._pet_names:
            self.pet_list.insert("end", "(ยังไม่มีตัวละคร)")

    def _selected_pet(self):
        sel = self.pet_list.curselection()
        if sel and self._pet_names and sel[0] < len(self._pet_names):
            return self._pet_names[sel[0]]
        return None

    def _pet_new(self):
        self._pet_dialog(None)

    def _pet_edit(self):
        n = self._selected_pet()
        if n:
            self._pet_dialog(n)

    def _pet_delete(self):
        n = self._selected_pet()
        if not n:
            return
        if messagebox.askyesno("ยืนยัน", f"ลบตัวละคร '{n}' ?", parent=self):
            assets.delete_character(n)
            self._refresh_pets()

    def _pet_dialog(self, name):
        editing = name is not None
        meta = assets.load_character_meta(name) if editing else {}
        folder = assets.character_path(name) if editing else None

        win = tk.Toplevel(self)
        win.title(f"แก้ไขตัวละคร: {name}" if editing else "สร้างตัวละครใหม่")
        win.transient(self)
        win.grab_set()
        pad = {"padx": 6, "pady": 3}

        # ── ซ้าย: ชื่อ + ระดับ + รูป ──
        left = ttk.Frame(win)
        left.grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        v_name = tk.StringVar(value=name or "")
        ttk.Label(left, text="ชื่อ").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(left, textvariable=v_name, width=22).grid(row=0, column=1, columnspan=2,
                                                            sticky="w", **pad)
        ttk.Label(left, text="ระดับความหายาก").grid(row=1, column=0, sticky="e", **pad)
        v_rarity = tk.StringVar(value=meta.get("rarity", "common"))
        ttk.Combobox(left, textvariable=v_rarity, state="readonly", width=14,
                     values=[r["id"] for r in config.RARITIES]
                     ).grid(row=1, column=1, columnspan=2, sticky="w", **pad)
        ttk.Label(left, text="ประเภทการตี").grid(row=2, column=0, sticky="e", **pad)
        v_range = tk.StringVar(value=meta.get("range_type", "melee"))
        ttk.Combobox(left, textvariable=v_range, state="readonly", width=14,
                     values=["melee", "ranged"]
                     ).grid(row=2, column=1, columnspan=2, sticky="w", **pad)

        pick_vars = {}
        for i, slot in enumerate(PET_SLOTS):
            cur = self._existing_slot(folder, "pet_" + slot) if folder else None
            var = tk.StringVar(value=cur or "")
            pick_vars[slot] = var
            r = 3 + i
            ttk.Label(left, text=SLOT_LABEL[slot]).grid(row=r, column=0, sticky="e", **pad)
            ttk.Entry(left, textvariable=var, width=30).grid(row=r, column=1, sticky="w", **pad)
            ttk.Button(left, text="...", width=3,
                       command=lambda v=var: v.set(filedialog.askopenfilename(
                           parent=win, filetypes=IMG_TYPES) or v.get())
                       ).grid(row=r, column=2, **pad)

        # ── ขวา: ความชอบ + สกิลที่สุ่มได้ ──
        right = ttk.Frame(win)
        right.grid(row=0, column=1, sticky="nw", padx=8, pady=8)

        likes0 = set(meta.get("likes", []) or [])
        dislikes0 = set(meta.get("dislikes", []) or [])
        like_vars, dislike_vars = {}, {}
        lf = ttk.LabelFrame(right, text="อาหารที่ชอบ 🍖")
        lf.pack(fill="x")
        df = ttk.LabelFrame(right, text="อาหารที่ไม่ชอบ")
        df.pack(fill="x", pady=(6, 0))
        for ft in config.FOOD_TYPES:
            lv = tk.BooleanVar(value=ft["id"] in likes0)
            dv = tk.BooleanVar(value=ft["id"] in dislikes0)
            like_vars[ft["id"]] = lv
            dislike_vars[ft["id"]] = dv
            ttk.Checkbutton(lf, text=f"{ft['emoji']} {ft['name']}", variable=lv).pack(anchor="w")
            ttk.Checkbutton(df, text=f"{ft['emoji']} {ft['name']}", variable=dv).pack(anchor="w")

        sf = ttk.LabelFrame(right, text="สกิลที่ตัวนี้สุ่มได้ (ว่าง = สุ่มจากกองรวม)")
        sf.pack(fill="both", expand=True, pady=(6, 0))
        allowed_ids = list(meta.get("skills", []) or [])
        sk_display = tk.Listbox(sf, height=6, font=("Consolas", 9))
        sk_display.pack(fill="both", expand=True, padx=4, pady=4)

        def refresh_allowed():
            sk_display.delete(0, "end")
            by = {s["id"]: s for s in assets.load_skills()}
            if not allowed_ids:
                sk_display.insert("end", "(ทั้งหมด — สุ่มจากกองรวม)")
            for sid in allowed_ids:
                s = by.get(sid, {})
                sk_display.insert("end", f"{s.get('emoji', '')} {sid} — {s.get('name', sid)}")

        def pick_skills():
            res = self._skill_picker(win, allowed_ids)
            if res is not None:
                allowed_ids[:] = res
                refresh_allowed()

        sbtn = ttk.Frame(sf)
        sbtn.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(sbtn, text="➕ เลือกสกิล", command=pick_skills).pack(side="left")
        ttk.Button(sbtn, text="🗑 ล้าง",
                   command=lambda: (allowed_ids.clear(), refresh_allowed())).pack(side="left", padx=6)
        refresh_allowed()

        def save():
            nm = v_name.get().strip()
            if not nm:
                messagebox.showwarning("ผิดพลาด", "ต้องตั้งชื่อ", parent=win)
                return
            # เปลี่ยนชื่อ (ตอนแก้ไข) ก่อน
            target = name
            if editing and nm != name:
                target = assets.rename_character(name, nm)
                if not target:
                    messagebox.showerror("ผิดพลาด", "เปลี่ยนชื่อไม่ได้ (ชื่อซ้ำ?)", parent=win)
                    return
            elif not editing:
                target = nm
            # ไฟล์รูป (ที่เลือก/ของเดิม) — ถ้าแก้ชื่อแล้ว ของเดิมอยู่ในโฟลเดอร์ใหม่
            new_folder = assets.character_path(target)
            files = {}
            for slot, var in pick_vars.items():
                p = var.get().strip()
                if p and os.path.isfile(p):
                    files[slot] = p
                elif editing:
                    ex = self._existing_slot(new_folder, "pet_" + slot)
                    if ex:
                        files[slot] = ex
            if not files.get("idle"):
                messagebox.showwarning("ผิดพลาด", "ต้องมีรูป 'ยืน' (idle) อย่างน้อย", parent=win)
                return
            likes = [k for k, v in like_vars.items() if v.get()]
            dislikes = [k for k, v in dislike_vars.items() if v.get() and k not in likes]
            allowed = list(allowed_ids)
            new_meta = dict(meta)
            new_meta.update({"rarity": v_rarity.get(), "range_type": v_range.get(),
                             "likes": likes, "dislikes": dislikes})
            if allowed:
                new_meta["skills"] = allowed
            else:
                new_meta.pop("skills", None)
            if assets.add_character(target, files, new_meta) is None:
                messagebox.showerror("ผิดพลาด", "บันทึกไม่สำเร็จ (ตรวจรูป idle)", parent=win)
                return
            self._refresh_pets()
            win.destroy()

        bar = ttk.Frame(win)
        bar.grid(row=1, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="💾 บันทึก", command=save).pack(side="left", padx=4)
        ttk.Button(bar, text="ยกเลิก", command=win.destroy).pack(side="left")

    def _skill_picker(self, parent, preselected, single=False, title=None):
        """หน้าต่างเลือกสกิล แยกตามสายให้ชัดเจน — คืน list (หรือ [id]/[] ถ้า single) หรือ None ถ้ายกเลิก"""
        win = tk.Toplevel(parent)
        win.title(title or ("เลือกสกิล" if single else "เลือกสกิลที่สุ่มได้"))
        win.transient(parent)
        win.grab_set()
        win.geometry("440x560")
        ttk.Label(win, text=("เลือกสกิล 1 อย่าง (แยกตามสาย)" if single
                             else "ติ๊กสกิลที่อนุญาตให้ตัวนี้สุ่มได้ (แยกตามสาย)")).pack(
            anchor="w", padx=8, pady=6)
        frm = ttk.Frame(win)
        frm.pack(fill="both", expand=True, padx=8)
        lb = tk.Listbox(frm, selectmode=("browse" if single else "multiple"),
                        font=("Consolas", 9), activestyle="none")
        lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frm, command=lb.yview)
        sb.pack(side="left", fill="y")
        lb.config(yscrollcommand=sb.set)

        groups = {cat: [] for cat, _ in SKILL_CATEGORIES}
        for s in assets.load_skills():
            groups[skill_category(s)].append(s)
        row_ids = []                             # ขนานกับแถว: None = หัวข้อสาย
        pre = set(preselected or [])
        for cat, label in SKILL_CATEGORIES:
            rows = groups[cat]
            if not rows:
                continue
            lb.insert("end", f"━━━ {label} ━━━")
            lb.itemconfig(lb.size() - 1, foreground="#1a5fb4")
            row_ids.append(None)
            for s in rows:
                act = " ⚡" if skill_is_active(s) else ""
                lb.insert("end", f"    {s.get('emoji', '')} {s['id']} — {s.get('name', '')}{act}")
                if s["id"] in pre:
                    lb.selection_set(lb.size() - 1)
                row_ids.append(s["id"])

        result = {}

        def ok():
            result["v"] = [row_ids[i] for i in lb.curselection() if row_ids[i]]
            win.destroy()

        def show_detail():
            # ดับเบิลคลิก = ดูรายละเอียดสกิลตัวที่คลิก (ข้ามแถวหัวข้อ)
            idx = lb.index("active")
            sid = row_ids[idx] if 0 <= idx < len(row_ids) else None
            if sid:
                messagebox.showinfo(f"สกิล: {sid}", self._skill_detail_text(sid), parent=win)

        lb.bind("<Double-Button-1>", lambda e: show_detail())

        bar = ttk.Frame(win)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="✔ ตกลง", command=ok).pack(side="left", padx=8)
        ttk.Button(bar, text="ยกเลิก", command=win.destroy).pack(side="left")
        ttk.Button(bar, text="ℹ️ คำอธิบายสกิลทั้งหมด",
                   command=lambda: self._help_popup("คำอธิบายสกิลทั้งหมด",
                                                    self._all_skills_help_text(), parent=win)
                   ).pack(side="right", padx=8)
        ttk.Label(win, text="(ดับเบิลคลิกที่สกิลเพื่อดูรายละเอียดตัวนั้น)",
                  foreground="#888").pack(pady=(0, 4))
        parent.wait_window(win)
        return result.get("v")                   # None = กดยกเลิก

    def _skill_detail_text(self, sid):
        """ข้อความรายละเอียดสกิล 1 ตัว (ชื่อ/สาย/ประเภท/เป้า/คำอธิบาย/เอฟเฟกต์)"""
        s = next((x for x in assets.load_skills() if x["id"] == sid), None)
        if not s:
            return f"{sid}: (ไม่พบ)"
        cat = dict(SKILL_CATEGORIES).get(skill_category(s), "-")
        typ = config.SKILL_TYPE_LABEL.get(s.get("type", ""), s.get("type", ""))
        tgt = "ทั้งทีม" if s.get("target") == "all" else "ตัวเอง"
        lines = [
            f"{s.get('emoji', '')} {s.get('name', sid)}   ({sid})",
            "",
            f"สาย: {cat}",
            f"การใช้: {skill_kind_label(s)}"
            + (f"  (คูลดาวน์ {s.get('cd', config.SKILL_CD_DEFAULT)} วิ)" if skill_is_active(s) else ""),
            f"ประเภท: {typ}    เป้า: {tgt}",
            f"คำอธิบาย: {s.get('desc', '-')}",
            f"กองสุ่ม: {'ใช่' if s.get('pool', True) else 'ไม่'}    น้ำหนัก: {s.get('weight', 1.0)}",
        ]
        if s.get("rarity_min"):
            lines.append(f"ระดับขั้นต่ำ: {s['rarity_min']}")
        lines += ["", "เอฟเฟกต์ (effect):"]
        for e in s.get("effects", []):
            lines.append("   • " + _effect_str(e))
        return "\n".join(lines)


def main():
    ManagerApp().mainloop()


if __name__ == "__main__":
    main()

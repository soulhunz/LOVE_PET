# -*- coding: utf-8 -*-
"""ระบบตลาดซื้อขายไข่ — แยก 'ชั้น backend' ออกจากตัวเกม

ตอนนี้ใช้ LocalMarketBackend (เก็บ offers เป็นไฟล์ JSON ในเครื่อง) เพื่อให้ระบบ
ทำงาน/ทดสอบได้ก่อน  อนาคตเปลี่ยนเป็น RemoteMarketBackend (เรียก API/Supabase)
โดย "ไม่ต้องแก้โค้ดเกม/UI" — แค่สลับคลาส backend ที่ฉีดให้ game

โครงสร้าง 1 รายการขาย (offer) = dict:
  {
    "id": str,                # รหัสรายการ (uuid)
    "seller_id": str,         # รหัสผู้ขาย (uuid; "npc:..." = ของระบบ)
    "seller_name": str,       # ชื่อโชว์ของผู้ขาย
    "price": int,             # ราคาขาย (เหรียญ)
    "created_at": float,      # เวลาที่ลงขาย (epoch)
    "kind": str,              # "egg" (ไข่) หรือ "pet" (สัตว์เลี้ยง)
    "rarity": str,            # ระดับ (ไว้โชว์/เรียง)
    "character": str|None,    # ชื่อตัวละคร (ไว้โชว์)
    "data": dict,             # ข้อมูลเต็มไว้สร้างของจริงตอนซื้อ
                              #   egg → {character,rarity,trait,skills,likes,dislikes}
                              #   pet → ผลของ game._pet_to_data(pet)
  }
"""
import json
import os
import time
import uuid

import paths


# ---------------------------------------------------------------------------
class MarketBackend:
    """อินเทอร์เฟซกลางของ 'แหล่งข้อมูลตลาด' — RemoteMarketBackend ในอนาคตทำ 3 เมธอดนี้
    ให้คืน/รับชนิดข้อมูลเดียวกัน แล้วเกมจะใช้งานได้เหมือนเดิม"""

    def fetch(self):
        """คืนรายการ offer ทั้งหมดในตลาด (list[dict])"""
        raise NotImplementedError

    def post(self, offer):
        """ลงขาย 1 รายการ — คืน id ของรายการ (หรือ None ถ้าล้มเหลว)"""
        raise NotImplementedError

    def remove(self, offer_id):
        """เอารายการออก (ถูกซื้อ/ยกเลิก) — คืน offer ที่เอาออก หรือ None ถ้าไม่พบ/ถูกตัดหน้า"""
        raise NotImplementedError

    def available(self):
        """พร้อมใช้งานไหม (ออนไลน์/ตั้งค่าแล้ว) — local = True เสมอ"""
        return True


class LocalMarketBackend(MarketBackend):
    """ตลาดจำลองในเครื่อง: เก็บ offers เป็นไฟล์ JSON (อะตอมิก) ที่ %APPDATA%
    *นี่คือชั้นที่จะถูกแทนด้วย RemoteMarketBackend (API) ในอนาคต*"""

    def __init__(self, path=None):
        self.path = path or paths.data_path("market.json")

    def fetch(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return [o for o in data if isinstance(o, dict) and "id" in o]
        except (OSError, ValueError):
            return []

    def _write(self, offers):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(offers, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    def post(self, offer):
        offers = self.fetch()
        offers.append(offer)
        return offer["id"] if self._write(offers) else None

    def remove(self, offer_id):
        offers = self.fetch()
        found = next((o for o in offers if o.get("id") == offer_id), None)
        if found is None:
            return None
        self._write([o for o in offers if o.get("id") != offer_id])
        return found


# class RemoteMarketBackend(MarketBackend):
#     """(อนาคต) เรียก API จริง เช่น Supabase REST ผ่าน urllib ในเธรดแยก
#     ทำ fetch/post/remove ให้คืนชนิดเดียวกับ LocalMarketBackend แล้วสลับใน game ได้เลย"""


def new_id():
    return uuid.uuid4().hex[:12]


def make_offer(seller_id, seller_name, price, kind, data):
    """สร้าง offer — kind="egg"/"pet", data=ข้อมูลไข่ หรือ pet_to_data(pet)"""
    return {
        "id": new_id(),
        "seller_id": seller_id,
        "seller_name": seller_name,
        "price": int(price),
        "created_at": time.time(),
        "kind": kind,
        "rarity": data.get("rarity", "common"),
        "character": data.get("character"),
        "data": dict(data),
    }

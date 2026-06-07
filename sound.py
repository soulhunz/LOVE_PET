# -*- coding: utf-8 -*-
"""เสียงประกอบแบบ 8-bit — สังเคราะห์คลื่นเสียงเองด้วยโค้ด (ไม่มีไฟล์/ไม่มีลิขสิทธิ์)
เล่นผ่าน winsound (stdlib, เฉพาะ Windows). ปิด/เปิดได้ด้วย set_enabled()."""
import math
import struct
import threading

try:
    import winsound
except ImportError:           # ไม่ใช่ Windows -> เงียบ
    winsound = None

_SR = 22050                   # sample rate
_enabled = True


def set_enabled(on):
    global _enabled
    _enabled = bool(on)


def is_enabled():
    return _enabled


# --------------------------------------------------------------- สังเคราะห์เสียง
def _wav_bytes(samples):
    """แปลงลิสต์ตัวอย่าง (-1..1) เป็นไบต์ WAV (16-bit mono)"""
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
                      for s in samples)
    size = len(frames)
    return (b"RIFF" + struct.pack("<I", 36 + size) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, _SR, _SR * 2, 2, 16)
            + b"data" + struct.pack("<I", size) + frames)


def _tone(freq, dur, vol=0.5, wave="square", decay=True):
    """สร้างโน้ตเดียว"""
    n = max(1, int(_SR * dur))
    out = []
    for i in range(n):
        ph = (freq * i / _SR) % 1.0
        if wave == "square":
            v = 1.0 if ph < 0.5 else -1.0
        elif wave == "saw":
            v = 2.0 * ph - 1.0
        else:
            v = math.sin(2 * math.pi * ph)
        env = (1.0 - i / n) if decay else 1.0       # ค่อย ๆ เบาลง
        out.append(v * vol * env)
    return out


def _seq(notes, vol=0.5, wave="square"):
    out = []
    for freq, dur in notes:
        out += _tone(freq, dur, vol, wave)
    return out


# เสียงแต่ละเหตุการณ์ (สร้างครั้งเดียวตอน import — เร็ว)
_cache = {
    "eat":     _wav_bytes(_seq([(523, 0.05), (784, 0.07)], 0.4, "square")),
    "attack":  _wav_bytes(_tone(170, 0.09, 0.5, "saw")),
    "hurt":    _wav_bytes(_seq([(330, 0.05), (180, 0.10)], 0.45, "square")),
    "win":     _wav_bytes(_seq([(523, 0.07), (659, 0.07), (784, 0.13)], 0.45, "square")),
    "levelup": _wav_bytes(_seq([(523, 0.06), (659, 0.06), (784, 0.06),
                                (1047, 0.16)], 0.45, "square")),
    "boss":    _wav_bytes(_seq([(196, 0.12), (165, 0.12), (131, 0.20)], 0.5, "saw")),
    "click":   _wav_bytes(_tone(880, 0.025, 0.25, "square")),
    "pet":     _wav_bytes(_seq([(659, 0.05), (988, 0.06)], 0.35, "sine")),
}


def _safe_play(data):
    try:
        winsound.PlaySound(data, winsound.SND_MEMORY)
    except Exception:
        pass


def play(name):
    """เล่นเสียงตามชื่อเหตุการณ์ (เล่นในเธรดแยก ไม่บล็อก UI)"""
    if not _enabled or winsound is None:
        return
    data = _cache.get(name)
    if data:
        threading.Thread(target=_safe_play, args=(data,), daemon=True).start()

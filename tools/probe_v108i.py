"""V108/鼠标: 深挖 FF04 feature 电池集合，并检查 V108 是否有等价通道。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GW = 0x40000000
GR = 0x80000000


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def dump(d, label):
    h = _kernel32.CreateFileW(d.path, GW | GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        print(f"{label}: open fail")
        return
    try:
        fl = d.feature_len
        print(f"\n=== {label}  up={d.usage_page:04X} u={d.usage:04X} feat={fl}")
        seen = {}
        for round_i in range(3):
            for rid in range(0, 32):
                buf = ctypes.create_string_buffer(fl)
                buf[0] = bytes([rid])
                if not _hid.HidD_GetFeature(wintypes.HANDLE(h), buf, fl):
                    continue
                body = bytes(buf.raw)
                if not any(body[1:]):
                    continue
                key = rid
                prev = seen.get(key)
                if prev is None or prev != body:
                    seen[key] = body
                    print(f"  r{round_i} rid={rid:2d}: {hexs(body)}")
            time.sleep(0.6)
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


def main():
    devs = enumerate_devices()
    for d in devs:
        if d.pid == 0x1A05 and d.feature_len == 8 and d.usage_page in (0xFF04, 0xFF00, 0xFF01):
            dump(d, f"MOUSE 391D:1A05")
    for d in devs:
        if d.pid == 0x2A02 and d.feature_len in (6, 8) and d.is_vendor_collection:
            dump(d, f"KBD 391D:2A02")


if __name__ == "__main__":
    main()

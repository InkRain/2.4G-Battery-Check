"""V108: 扫描所有集合的 SetFeature 可写性，并尝试 feature 方式的电量查询。"""
import ctypes
import sys

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GW = 0x40000000
GR = 0x80000000


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    devs = [d for d in enumerate_devices() if d.pid in (0x2A02, 0x1A05)]
    for d in devs:
        if not d.is_vendor_collection:
            continue
        h = _kernel32.CreateFileW(d.path, GW | GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE_VALUE, -1):
            continue
        try:
            parts = []
            if d.feature_len:
                fl = d.feature_len
                for rid in range(0, 24):
                    buf = ctypes.create_string_buffer(fl)
                    buf[0] = bytes([rid])
                    ok = _hid.HidD_SetFeature(wintypes.HANDLE(h), buf, fl)
                    if ok:
                        # 读回看是否变化
                        rb = ctypes.create_string_buffer(fl)
                        rb[0] = bytes([rid])
                        got = _hid.HidD_GetFeature(wintypes.HANDLE(h), rb, fl)
                        parts.append(f"SETrid{rid}=OK" + (f"/read={hexs(bytes(rb.raw)[:10])}" if got else ""))
            if parts:
                print(f"up={d.usage_page:04X} u={d.usage:04X} feat={d.feature_len}")
                for p in parts:
                    print("   ", p)
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

"""V108: 对比 HidD_SetOutputReport / WriteFile 在 rid=1,4 的差异；试探 GetInputReport。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
HidD_GetInputReport = getattr(_hid, "HidD_GetInputReport", None)


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02]
    d = next(x for x in devs if x.usage_page == 0xFF02 and x.usage == 0x0002)
    print(f"in={d.input_len} out={d.output_len}")
    h = _kernel32.CreateFileW(d.path, GENERIC_WRITE | GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        print("open fail", ctypes.get_last_error())
        return
    try:
        # A) HidD_SetOutputReport，长度 20 / 21
        print("-- HidD_SetOutputReport --")
        for size in (d.output_len, d.output_len + 1):
            for rid in (1, 2, 4, 5, 8):
                buf = ctypes.create_string_buffer(size)
                buf[0] = bytes([rid])
                ok = _hid.HidD_SetOutputReport(wintypes.HANDLE(h), buf, size)
                err = ctypes.get_last_error() if not ok else 0
                print(f"   size={size} rid={rid}: ok={bool(ok)} err={err}")

        # B) HidD_GetInputReport rid 探测
        if HidD_GetInputReport:
            print("-- HidD_GetInputReport --")
            for rid in (1, 2, 4, 8):
                buf = ctypes.create_string_buffer(d.input_len)
                buf[0] = bytes([rid])
                ok = HidD_GetInputReport(wintypes.HANDLE(h), buf, d.input_len)
                err = ctypes.get_last_error() if not ok else 0
                body = bytes(buf.raw)
                print(f"   rid={rid}: ok={bool(ok)} err={err} data={hexs(body) if ok else ''}")

        # C) 先 HidD_SetOutputReport 打开 FF00/FF01 feature 通道做握手，再回 FF02 写
        print("-- handshake via feature then retry output --")
        for rid in (5, 10):
            flen = 6 if rid == 5 else 8
            fb = ctypes.create_string_buffer(flen)
            if _hid.HidD_GetFeature(wintypes.HANDLE(h), fb, flen):
                print(f"   feat rid={rid}: {hexs(bytes(fb.raw))}")
        for rid in (1, 4):
            buf = ctypes.create_string_buffer(d.output_len)
            buf[0] = bytes([rid])
            buf[1] = b"\x04"
            ok = _hid.HidD_SetOutputReport(wintypes.HANDLE(h), buf, d.output_len)
            print(f"   after-handshake rid={rid}: ok={bool(ok)} err={0 if ok else ctypes.get_last_error()}")
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

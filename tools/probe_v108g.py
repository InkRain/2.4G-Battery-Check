"""V108 对照实验：探测 vendor 通道写入，用于判断是否被其他进程独占。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def probe(label):
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02]
    print(f"\n===== {label} =====")
    for d in devs:
        if not d.is_vendor_collection:
            continue
        line = f"  up={d.usage_page:04X} u={d.usage:04X} in={d.input_len} out={d.output_len} feat={d.feature_len}"
        h = _kernel32.CreateFileW(d.path, GENERIC_WRITE | GENERIC_READ,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE_VALUE, -1):
            print(line + f"  OPEN_FAIL err={ctypes.get_last_error()}")
            continue
        try:
            results = []
            if d.output_len:
                for rid in (0, 1, 2, 3, 4, 5, 6, 8, 16):
                    buf = ctypes.create_string_buffer(d.output_len)
                    buf[0] = bytes([rid])
                    ok = _hid.HidD_SetOutputReport(wintypes.HANDLE(h), buf, d.output_len)
                    err = 0 if ok else ctypes.get_last_error()
                    results.append(f"rid{rid}:{err if not ok else 'OK'}")
            if d.feature_len:
                fl = min(d.feature_len, 64)
                for rid in (0, 5, 10):
                    buf = ctypes.create_string_buffer(fl)
                    buf[0] = bytes([rid])
                    ok = _hid.HidD_GetFeature(wintypes.HANDLE(h), buf, fl)
                    if ok and any(bytes(buf.raw)[1:]):
                        results.append(f"feat{rid}={hexs(bytes(buf.raw)[:12])}")
                    elif not ok:
                        results.append(f"feat{rid}:err{ctypes.get_last_error()}")
            print(line + "  " + " ".join(results))
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    probe(sys.argv[1] if len(sys.argv) > 1 else "probe")

"""V108: 直接打印 WriteFile / WriteFileEx 的原生错误码，判断 err=87 的真实来源。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000


def open_dev(path, access):
    h = _kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE or h == -1:
        return None, ctypes.get_last_error()
    return h, 0


def try_write(h, data):
    n = wintypes.DWORD(0)
    ok = _kernel32.WriteFile(wintypes.HANDLE(h), data, len(data), ctypes.byref(n), None)
    return bool(ok), n.value, ctypes.get_last_error()


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02]
    d = next(x for x in devs if x.usage_page == 0xFF02 and x.usage == 0x0002)
    print(f"target: {d.path}")
    print(f"in={d.input_len} out={d.output_len} feat={d.feature_len}")

    for access, aname in ((GENERIC_WRITE | GENERIC_READ, "RW"),
                          (GENERIC_WRITE, "W"),
                          (0, "none")):
        h, err = open_dev(d.path, access)
        if not h:
            print(f"  open {aname}: FAIL err={err}")
            continue
        print(f"  open {aname}: OK")
        for size in (d.output_len, d.output_len + 1, 21, 22):
            for rid in (0, 1, 4, 8):
                frame = bytes(size)
                frame = bytes([rid]) + frame[1:]
                ok, n, err = try_write(h, frame)
                print(f"    size={size:3d} rid={rid}: ok={ok} n={n} err={err}")
        _kernel32.CloseHandle(wintypes.HANDLE(h))
        break


if __name__ == "__main__":
    main()

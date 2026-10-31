"""V108: 判断 FF02:0002 是否为独占打开问题。
方法: 同一路径连续开两个句柄, 看第二个是否失败 ShareViolation(32)。
同时在持有句柄时再枚举写入。
"""
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
    d = next(x for x in enumerate_devices()
             if x.pid == 0x2A02 and x.usage_page == 0xFF02 and x.usage == 0x0002)
    print(f"path={d.path}")
    print(f"in={d.input_len} out={d.output_len}")

    # 独占测试: 不同 share mode
    for share, sname in ((0, "EXCLUSIVE(share=0)"),
                         (FILE_SHARE_READ | FILE_SHARE_WRITE, "SHARED_RW")):
        h1 = _kernel32.CreateFileW(d.path, GW | GR, share, None, OPEN_EXISTING, 0, None)
        e1 = ctypes.get_last_error()
        ok1 = h1 not in (INVALID_HANDLE_VALUE, -1)
        h2 = _kernel32.CreateFileW(d.path, GW | GR, share, None, OPEN_EXISTING, 0, None)
        e2 = ctypes.get_last_error()
        ok2 = h2 not in (INVALID_HANDLE_VALUE, -1)
        print(f"  {sname}: h1_ok={ok1}(err{e1}) h2_ok={ok2}(err{e2})")
        for hh in (h1, h2):
            if hh not in (INVALID_HANDLE_VALUE, -1):
                _kernel32.CloseHandle(wintypes.HANDLE(hh))

    # 用 share=0 独占句柄再试写
    h = _kernel32.CreateFileW(d.path, GW | GR, 0, None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        print(f"  exclusive open failed err={ctypes.get_last_error()}")
        return
    try:
        print("  -- exclusive handle write attempts --")
        for rid in (0, 1, 2, 4):
            for size in (d.output_len, d.output_len + 1):
                buf = ctypes.create_string_buffer(size)
                buf[0] = bytes([rid])
                ok = _hid.HidD_SetOutputReport(wintypes.HANDLE(h), buf, size)
                n = wintypes.DWORD(0)
                ok2 = _kernel32.WriteFile(wintypes.HANDLE(h), bytes(buf.raw), size,
                                          ctypes.byref(n), None)
                print(f"    rid={rid} size={size}: SetOut={bool(ok)}({0 if ok else ctypes.get_last_error()}) "
                      f"WriteFile={bool(ok2)}({0 if ok2 else ctypes.get_last_error()})")
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

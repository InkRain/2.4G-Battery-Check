"""GX-01: 用 IOCTL_HID_GET_REPORT_DESCRIPTOR 读取完整 HID 描述符，解析 usage 页。"""
import ctypes
import sys
from ctypes import wintypes

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING)

IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0000 | (0x0000 << 2) | 0  # 简写
# 正确: HID_BUFFER 版本
IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0000
FILE_DEVICE_UNKNOWN = 0x00000022
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0
IOCTL_HID_GET_REPORT_DESCRIPTOR = (FILE_DEVICE_UNKNOWN << 16) | (FILE_ANY_ACCESS << 14) | (0x0000 << 2) | METHOD_BUFFERED
IOCTL_HID_GET_PRODUCT_STRING = (FILE_DEVICE_UNKNOWN << 16) | (FILE_ANY_ACCESS << 14) | (0x0001 << 2) | METHOD_BUFFERED


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def ioctl(h, code, out_size):
    buf = ctypes.create_string_buffer(out_size)
    n = wintypes.DWORD(0)
    ok = _kernel32.DeviceIoControl(wintypes.HANDLE(h), code, None, 0,
                                   buf, out_size, ctypes.byref(n), None)
    if not ok:
        return None, ctypes.get_last_error()
    return bytes(buf.raw[:n.value]), 0


def parse_usage_pages(desc: bytes):
    """粗略解析 HID 描述符，列出所有 usage page 与 usage。"""
    i = 0
    g_page = 0
    g_usage = 0
    usages = []
    while i < len(desc):
        prefix = desc[i]
        size = (0, 1, 2, 4)[prefix & 0x03] if (prefix & 0x03) != 3 else 4
        typ = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        data = desc[i + 1:i + 1 + size]
        val = int.from_bytes(data, "little") if data else 0
        if typ == 1:  # Global
            if tag == 0x0:    # usage page
                g_page = val
            elif tag == 0x8 and size == 4:  # report id
                pass
        elif typ == 2:  # Local
            if tag == 0x0:  # usage
                g_usage = val
                usages.append((g_page, val))
        elif typ == 0:  # Main
            if tag == 0x8:  # Input
                usages.append((g_page, g_usage, "INPUT"))
        i += 1 + size
    return usages


def main():
    devs = [d for d in enumerate_devices() if d.vid == 0x4C4A]
    for d in devs:
        print(f"\n=== {d.path}")
        h = _kernel32.CreateFileW(d.path, 0x80000000, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE_VALUE, -1):
            print("  open fail", ctypes.get_last_error())
            continue
        try:
            desc, err = ioctl(h, IOCTL_HID_GET_REPORT_DESCRIPTOR, 2048)
            if desc is None:
                print(f"  IOCTL failed err={err}")
                continue
            print(f"  descriptor {len(desc)}B:")
            for i in range(0, len(desc), 24):
                print("    " + hexs(desc[i:i + 24]))
            u = parse_usage_pages(desc)
            pgs = sorted({p for p, _ in ((a, b) for a, b, *rest in
                                        [(x[0], x[1]) for x in u])})
            print(f"  usage pages: {', '.join(f'{p:04X}' for p in pgs)}")
            has_batt = any(p == 0x06 for p in pgs)
            print(f"  >>> Has HID Battery page (0x06)? {has_batt}")
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

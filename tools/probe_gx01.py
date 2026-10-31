"""GX-01 (4C4A:4155) 深挖：完整 HID 报告描述符 + 所有 usage / caps。"""
import ctypes
import sys

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, HidDevice, _hid, _kernel32,
                          INVALID_HANDLE_VALUE, FILE_SHARE_READ, FILE_SHARE_WRITE,
                          OPEN_EXISTING, wintypes, HIDP_VALUE_CAPS, HIDD_ATTRIBUTES)

GW = 0x40000000
GR = 0x80000000


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def dump_descriptor(path):
    h = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        return None
    try:
        # HidD_GetReportDescriptor
        buf = ctypes.create_string_buffer(4096)
        n = wintypes.ULONG(0)
        a = HIDD_ATTRIBUTES()
        a.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if _hid.HidD_GetAttributes(wintypes.HANDLE(h), ctypes.byref(a)):
            print(f"  ATTR vid={a.VendorID:04X} pid={a.ProductID:04X} ver={a.VersionNumber:04X}")
        # 产品字符串
        for fn, label in (("HidD_GetProductString", "product"),
                          ("HidD_GetManufacturerString", "mfr"),
                          ("HidD_GetSerialNumberString", "serial")):
            f = getattr(_hid, fn, None)
            if not f:
                continue
            sb = ctypes.create_string_buffer(256)
            if f(wintypes.HANDLE(h), sb, 256):
                raw = bytes(sb.raw)
                try:
                    txt = raw.decode("utf-16-le").rstrip("\x00")
                except Exception:
                    txt = repr(raw[:40])
                if txt:
                    print(f"  {label}: {txt!r}")
        if _hid.HidD_GetReportDescriptor(wintypes.HANDLE(h), buf, 4096,
                                        ctypes.byref(n)):
            desc = bytes(buf.raw[:n.value])
            print(f"  REPORT_DESC ({n.value}B):")
            for i in range(0, len(desc), 24):
                print("    " + hexs(desc[i:i + 24]))
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


def main():
    devs = [d for d in enumerate_devices() if d.vid == 0x4C4A]
    print(f"4C4A collections: {len(devs)}")
    for d in devs:
        print(f"\n=== up={d.usage_page:04X} u={d.usage:04X} in={d.input_len} out={d.output_len} feat={d.feature_len}")
        print(f"    {d.path}")
        dump_descriptor(d.path)


if __name__ == "__main__":
    main()

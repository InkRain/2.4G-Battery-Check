"""GX-01: 通过 preparsed data 列出所有 value caps（含 usage page），确认有无电池页。"""
import ctypes
import sys

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GR = 0x80000000


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [
        ("UsagePage", wintypes.USHORT), ("ReportID", ctypes.c_ubyte),
        ("IsAlias", ctypes.c_ubyte), ("BitField", wintypes.USHORT),
        ("LinkCollection", wintypes.USHORT), ("LinkUsagePage", wintypes.USHORT),
        ("IsRange", wintypes.USHORT), ("IsStringRange", wintypes.USHORT),
        ("IsDesignatorRange", wintypes.USHORT), ("IsAbsolute", wintypes.USHORT),
        ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
        ("BitSize", wintypes.USHORT), ("ReportCount", wintypes.USHORT),
        ("Reserved2", ctypes.c_ubyte * 10),
        ("LogicalMin", ctypes.c_ulong), ("LogicalMax", ctypes.c_ulong),
        ("PhysicalMin", ctypes.c_ulong), ("PhysicalMax", ctypes.c_ulong),
        ("UnitsExp", ctypes.c_ulong), ("Units", ctypes.c_ulong),
    ]


def main():
    for d in enumerate_devices():
        if d.vid != 0x4C4A:
            continue
        print(f"=== {d.path}")
        h = _kernel32.CreateFileW(d.path, GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE_VALUE, -1):
            print("  open fail", ctypes.get_last_error())
            continue
        try:
            ppd = ctypes.c_void_p()
            if not _hid.HidD_GetPreparsedData(wintypes.HANDLE(h), ctypes.byref(ppd)):
                print("  preparsed fail", ctypes.get_last_error())
                continue
            try:
                for rtype, name in ((0, "INPUT"), (1, "OUTPUT"), (2, "FEATURE")):
                    cnt = wintypes.USHORT(64)
                    arr = (HIDP_VALUE_CAPS * 64)()
                    st = _hid.HidP_GetValueCaps(rtype, arr, ctypes.byref(cnt), ppd)
                    if st != 0x110000:
                        continue
                    for i in range(cnt.value):
                        c = arr[i]
                        print(f"  {name:8s} rid={c.ReportID:3d} up={c.UsagePage:04X} "
                              f"bits={c.BitSize:2d} count={c.ReportCount} "
                              f"logMin={c.LogicalMin} logMax={c.LogicalMax}")
            finally:
                _hid.HidD_FreePreparsedData(ppd)
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

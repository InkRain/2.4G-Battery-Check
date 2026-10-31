"""系统性扫描 V108 dongle：输出报告 ID 试探 + feature 报告全扫描。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, HidDevice, _hid, _kernel32,
                          INVALID_HANDLE_VALUE, FILE_SHARE_READ, FILE_SHARE_WRITE,
                          OPEN_EXISTING, wintypes)


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def dump_output_caps(path: str):
    handle = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                   OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        return
    try:
        ppd = ctypes.c_void_p()
        if not _hid.HidD_GetPreparsedData(wintypes.HANDLE(handle), ctypes.byref(ppd)):
            return
        try:
            from app.hid.core import HIDP_VALUE_CAPS
            for rtype, rname in ((1, "OUT"), (2, "FEAT")):
                count = wintypes.USHORT(128)
                arr = (HIDP_VALUE_CAPS * 128)()
                st = _hid.HidP_GetValueCaps(rtype, arr, ctypes.byref(count), ppd)
                if st == 0x110000 and count.value:
                    for i in range(min(count.value, 20)):
                        c = arr[i]
                        print(f"    [{rname}] rid={c.ReportID} up={c.UsagePage:04X} "
                              f"bits={c.BitSize} count={c.ReportCount}")
        finally:
            _hid.HidD_FreePreparsedData(ppd)
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


def main():
    devs = enumerate_devices()
    targets = [d for d in devs if d.pid == 0x2A02 and d.is_vendor_collection]
    for d in targets:
        print(f"\n=== up={d.usage_page:04X} u={d.usage:04X} in={d.input_len} "
              f"out={d.output_len} feat={d.feature_len}")
        if d.output_len:
            dump_output_caps(d.path)
        try:
            dev = HidDevice(d.path)
        except OSError as e:
            print(f"  open failed: {e}")
            continue
        try:
            # 1) 输出报告 ID 扫描：rid 1..16 × size 20
            if d.output_len:
                print("  --- output rid scan (20B) ---")
                for rid in range(1, 17):
                    frame = bytearray(20)
                    frame[0] = rid
                    ok = dev.write(bytes(frame))
                    if ok:
                        r = dev.read(21, 400)
                        print(f"    rid={rid}: WRITE OK, read={hexs(r) if r else None}")
                    else:
                        err = ctypes.get_last_error()
                        if err != 87:
                            print(f"    rid={rid}: write failed err={err}")
            # 2) feature 报告全扫描 rid 0..255
            if d.feature_len:
                print(f"  --- feature scan (len={d.feature_len}) ---")
                flen = min(d.feature_len, 64)
                for rid in range(0, 256):
                    buf = dev.get_feature(rid, flen)
                    if buf and any(buf[1:]):
                        cands = [b for b in buf[1:] if 1 <= b <= 100]
                        print(f"    rid={rid:3d}: {hexs(buf)}" + (f"  cand={cands}" if cands else ""))
        finally:
            dev.close()


if __name__ == "__main__":
    main()

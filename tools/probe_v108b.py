"""解析 V108 dongle 各厂商集合的 value caps 结构 + 被动监听输入报告。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, HidDevice, _hid, _kernel32,
                          HIDP_VALUE_CAPS, HidP_Input, HidP_Output, HidP_Feature,
                          INVALID_HANDLE_VALUE, FILE_SHARE_READ, FILE_SHARE_WRITE,
                          OPEN_EXISTING, wintypes)


def dump_value_caps(path: str):
    handle = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                   OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        print("  open failed")
        return
    try:
        ppd = ctypes.c_void_p()
        if not _hid.HidD_GetPreparsedData(wintypes.HANDLE(handle), ctypes.byref(ppd)):
            print("  no preparsed")
            return
        try:
            for rtype, rname in ((HidP_Input, "IN"), (HidP_Output, "OUT"), (HidP_Feature, "FEAT")):
                count = wintypes.USHORT(128)
                arr = (HIDP_VALUE_CAPS * 128)()
                st = _hid.HidP_GetValueCaps(rtype, arr, ctypes.byref(count), ppd)
                if st == 0x110000 and count.value:
                    print(f"  [{rname}] value caps:")
                    for i in range(min(count.value, 20)):
                        c = arr[i]
                        print(f"    rid={c.ReportID:3d} up={c.UsagePage:04X} "
                              f"bits={c.BitSize} count={c.ReportCount} link={c.LinkCollection} lup={c.LinkUsagePage:04X} lu={c.LinkUsage:04X} "
                              f"range=[{c.LogicalMin},{c.LogicalMax}]")
        finally:
            _hid.HidD_FreePreparsedData(ppd)
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


def monitor_input(path: str, seconds: float = 8.0, size: int = 65):
    print(f"  --- 被动监听输入 {seconds}s ---")
    try:
        dev = HidDevice(path)
    except OSError as e:
        print(f"  open failed: {e}")
        return
    try:
        dev.flush_input()
        seen = {}
        t0 = time.time()
        while time.time() - t0 < seconds:
            r = dev.read(size, 300)
            if r:
                key = r[:1]
                seen.setdefault(bytes(r[:16]), 0)
                seen[bytes(r[:16])] += 1
        for k, v in sorted(seen.items(), key=lambda x: -x[1])[:8]:
            print(f"    x{v:3d}: {' '.join(f'{b:02X}' for b in k)}")
    finally:
        dev.close()


def main():
    devs = enumerate_devices()
    targets = [d for d in devs if d.pid == 0x2A02]
    for d in targets:
        print(f"\n=== {d.usage_page:04X}:{d.usage:04X} in={d.input_len} out={d.output_len} feat={d.feature_len}")
        if d.is_vendor_collection:
            dump_value_caps(d.path)
            if d.input_len and d.input_len <= 32:
                monitor_input(d.path, 6.0, d.input_len + 1)


if __name__ == "__main__":
    main()

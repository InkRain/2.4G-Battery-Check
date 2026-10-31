"""V108: 暴力扫描所有集合 + 所有访问方式的组合，输出存在“能写”的通道。"""
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
    for pid in (0x2A02,):
        devs = [d for d in enumerate_devices() if d.pid == pid]
        for d in devs:
            if not d.is_vendor_collection:
                continue
            h = _kernel32.CreateFileW(d.path, GW | GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                      None, OPEN_EXISTING, 0, None)
            if h in (INVALID_HANDLE_VALUE, -1):
                print(f"up={d.usage_page:04X} u={d.usage:04X} OPEN={ctypes.get_last_error()}")
                continue
            try:
                hits = []
                # 输出报告: 尝试所有长度
                if d.output_len:
                    for rid in range(0, 12):
                        for size in (d.output_len, d.output_len + 1):
                            buf = ctypes.create_string_buffer(size)
                            buf[0] = bytes([rid])
                            if _hid.HidD_SetOutputReport(wintypes.HANDLE(h), buf, size):
                                hits.append(f"OUT rid{rid} size{size}=OK")
                            n = wintypes.DWORD(0)
                            if _kernel32.WriteFile(wintypes.HANDLE(h), bytes(buf.raw), size,
                                                   ctypes.byref(n), None):
                                hits.append(f"WF rid{rid} size{size}=OK")
                # 特性报告写入
                if d.feature_len:
                    fl = min(d.feature_len, 1032)
                    for rid in range(0, 12):
                        buf = ctypes.create_string_buffer(fl)
                        buf[0] = bytes([rid])
                        if _hid.HidD_SetFeature(wintypes.HANDLE(h), buf, fl):
                            hits.append(f"FEAT rid{rid} len{fl}=SET_OK")
                if hits:
                    print(f"\nup={d.usage_page:04X} u={d.usage:04X} in={d.input_len} out={d.output_len} feat={d.feature_len}")
                    for x in hits:
                        print("   ", x)
            finally:
                _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

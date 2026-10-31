"""V108: 探测 FF00 feat=1032 大通道（疑似 VIA/QMK raw HID）。
VIA 协议: 32 字节 payload + 32 字节 retbuf, 封装在 report 内。
"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GW = 0x40000000
GR = 0x80000000


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02 and d.feature_len >= 1000]
    if not devs:
        print("no big feature collection")
        return
    d = devs[0]
    print(f"up={d.usage_page:04X} u={d.usage:04X} feat={d.feature_len}")
    h = _kernel32.CreateFileW(d.path, GW | GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        print("open fail", ctypes.get_last_error())
        return
    try:
        FL = d.feature_len
        # 尝试用不同 rid 的 SetFeature 写入 VIA 风格查询
        # VIA: id=0x01 get protocol version, id=0x11 get keycode, id=0x00 get keyboard value
        for rid in (0, 1, 2, 3, 4, 6):
            for via_id, name in ((0x01, "get_protocol_version"), (0x00, "get_keyboard_value")):
                pay = bytearray(FL)
                pay[0] = rid
                # report 内容: [rid][via_id][...]
                off = 1
                pay[off] = via_id
                if via_id == 0x00:
                    pay[off + 1] = 0x01  # uptime
                setbuf = ctypes.create_string_buffer(bytes(pay), FL)
                ok = _hid.HidD_SetFeature(wintypes.HANDLE(h), setbuf, FL)
                if not ok:
                    continue
                time.sleep(0.08)
                getbuf = ctypes.create_string_buffer(FL)
                getbuf[0] = bytes([rid])
                got = _hid.HidD_GetFeature(wintypes.HANDLE(h), getbuf, FL)
                body = bytes(getbuf.raw)
                if got and any(body[1:60]):
                    print(f"  rid={rid} {name}: {hexs(body[:32])}")
                else:
                    print(f"  rid={rid} {name}: set_ok get={'ok' if got else 'fail'} empty")
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


if __name__ == "__main__":
    main()

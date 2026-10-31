"""V108: 全面被动监听所有输入集合，观察是否有主动推送（尤其 FF02:0001 in=4, 0001:0080 in=2）。"""
import ctypes
import sys
import threading
import time

sys.path.insert(0, ".")
from app.hid.core import (enumerate_devices, _hid, _kernel32, INVALID_HANDLE_VALUE,
                          FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING, wintypes)

GW = 0x40000000
GR = 0x80000000
INVALID_SET_FILE_POINTER = -1


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


results = []


def listen(d, seconds=6.0):
    h = _kernel32.CreateFileW(d.path, GR, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if h in (INVALID_HANDLE_VALUE, -1):
        results.append((d, f"open fail {ctypes.get_last_error()}", []))
        return
    frames = []
    try:
        kb = _kernel32
        t0 = time.time()
        while time.time() - t0 < seconds:
            ov = ctypes.create_string_buffer(32)
            size = d.input_len
            ov_lp = ctypes.cast(ov, ctypes.c_void_p)
            # 简化: 用同步 ReadFile 非阻塞前先检查可用性
            n = wintypes.DWORD(0)
            buf = ctypes.create_string_buffer(size)
            ok = kb.ReadFile(wintypes.HANDLE(h), buf, size, ctypes.byref(n), None)
            if ok and n.value:
                frames.append(bytes(buf.raw[:n.value]))
            else:
                err = ctypes.get_last_error()
                if err == 0:
                    time.sleep(0.02)
                elif err == 1167:
                    time.sleep(0.02)
                else:
                    time.sleep(0.05)
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))
    results.append((d, "ok", frames))


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02 and d.input_len > 0]
    print(f"listening on {len(devs)} input collections for 6s...")
    print(">>> PLEASE TYPE ON THE V108 KEYBOARD NOW <<<")
    threads = [threading.Thread(target=listen, args=(d,)) for d in devs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for d, status, frames in results:
        print(f"\nup={d.usage_page:04X} u={d.usage:04X} in={d.input_len} -> {status}, {len(frames)} frames")
        for f in frames[:8]:
            print("    ", hexs(f))


if __name__ == "__main__":
    main()

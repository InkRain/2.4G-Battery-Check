"""深入调试 V108 键盘 dongle 的写入与协议。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, HidDevice, _kernel32, INVALID_HANDLE_VALUE


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def main():
    devs = enumerate_devices()
    v108 = [d for d in devs if d.pid == 0x2A02 and d.usage_page >= 0xFF00]
    print(f"V108 vendor collections: {len(v108)}")
    for d in v108:
        print(f"\n=== up={d.usage_page:04X} u={d.usage:04X} in={d.input_len} "
              f"out={d.output_len} feat={d.feature_len}")
        try:
            dev = HidDevice(d.path)
        except OSError as e:
            print(f"  open failed: {e}")
            continue
        try:
            if d.output_len:
                for size in (17, 20, d.output_len):
                    frame = bytearray(size)
                    frame[0] = 0x08
                    frame[1] = 0x04
                    frame[size - 1] = 0x49
                    dev.flush_input()
                    ok = dev.write(bytes(frame))
                    err = ctypes.get_last_error()
                    print(f"  write({size}B) -> {ok} lasterr={err}")
                    if ok:
                        r = dev.read(size + 1, 800)
                        print(f"    read: {hexs(r) if r else None}")
                        if r and len(r) >= 8 and r[0] == 8 and r[1] == 4:
                            print(f"    *** percent={r[6]} wired={r[7]}")
                            return
            if d.feature_len:
                print("  --- feature scan ---")
                for rid in range(1, 25):
                    buf = dev.get_feature(rid, min(d.feature_len, 64))
                    if buf and any(buf):
                        cands = [b for b in buf[1:] if 1 <= b <= 100]
                        print(f"  feat id={rid:3d}: {hexs(buf)}" +
                              (f"  cand={cands}" if cands else ""))
        finally:
            dev.close()


if __name__ == "__main__":
    main()

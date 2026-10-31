"""V108: 串行被动监听（用 HidDevice 带超时的 read）。"""
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, HidDevice


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02 and d.input_len > 0]
    print(f"collections: {len(devs)}")
    for d in devs:
        print(f"  up={d.usage_page:04X} u={d.usage:04X} in={d.input_len}")

    print("\n>>> 请在 V108 键盘上打字（按几个键），监听 8 秒 <<<\n")
    t0 = time.time()
    handles = []
    for d in devs:
        try:
            handles.append((d, HidDevice(d.path)))
        except OSError as e:
            print(f"  open fail up={d.usage_page:04X} u={d.usage:04X}: {e}")
    try:
        while time.time() - t0 < 8.0:
            for d, dev in handles:
                r = dev.read(d.input_len, 120)
                if r:
                    print(f"  [{time.time()-t0:5.2f}s] up={d.usage_page:04X} u={d.usage:04X}: {hexs(r)}")
    finally:
        for _, dev in handles:
            dev.close()


if __name__ == "__main__":
    main()

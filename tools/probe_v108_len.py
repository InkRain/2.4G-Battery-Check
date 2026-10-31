"""V108: 尝试 Nordic52 帧在不同长度/前缀下的写入可行性。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, HidDevice, _hid, _kernel32, wintypes


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    d = next(x for x in enumerate_devices()
             if x.pid == 0x2A02 and x.usage_page == 0xFF02 and x.usage == 0x0002)
    print(f"in={d.input_len} out={d.output_len}")
    try:
        dev = HidDevice(d.path)
    except OSError as e:
        print("open fail", e)
        return
    try:
        variants = []
        # A) 20 字节，rid=8，末字节 0x49
        for size in (17, 18, 19, 20, 21, 22, 32, 64):
            for rid in (0x08, 0x00, 0x01, 0x04):
                f = bytearray(size)
                f[0] = rid
                if size > 2:
                    f[1] = 0x04
                f[size - 1] = 0x49
                dev.flush_input()
                ok = dev.write(bytes(f), 300)
                tag = f"size={size:2d} rid={rid:02X}"
                if ok:
                    r = dev.read(size + 1, 300)
                    print(f"  {tag}: WRITE OK  reply={hexs(r) if r else None}")
                else:
                    if dev.last_error != 87:
                        print(f"  {tag}: err={dev.last_error}")
    finally:
        dev.close()


if __name__ == "__main__":
    main()

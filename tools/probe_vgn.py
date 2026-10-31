"""真实硬件协议探测：对本机 VGN 设备尝试已知电量协议。"""
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, find_battery_value_caps, HidDevice

VGN_KEYBOARD = ("391D", "2A02")   # VGN V108 2.4G Dongle
VGN_MOUSE = ("391D", "1A05")      # Dragonfly 3 Master+


def try_nordic52(dev: HidDevice, size: int) -> bytes | None:
    """Compx/Nordic 52: 17 字节 id=8 sub=4, 电量在回包 offset 6。"""
    frame = bytearray(size)
    frame[0] = 0x08
    frame[1] = 0x04
    frame[size - 1] = 0x49
    dev.flush_input()
    if not dev.write(bytes(frame)):
        print("    write failed")
        return None
    deadline = time.time() + 2.0
    while time.time() < deadline:
        r = dev.read(size + 1, 200)
        if r and len(r) >= 8 and r[0] == 8 and r[1] == 4:
            return r
    return None


def try_evision(dev: HidDevice) -> bytes | None:
    """Evision (320F:5088): reportId 4, [4,32,0,26,6]+zeros, 电量 offset 8。"""
    frame = bytes([4, 32, 0, 26, 6] + [0] * 59)
    dev.flush_input()
    if not dev.write(frame):
        print("    write failed")
        return None
    deadline = time.time() + 3.0
    while time.time() < deadline:
        r = dev.read(65, 200)
        if r and len(r) >= 10 and r[0] == 4 and r[3] == 26:
            return r
    return None


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b[:32])


def main():
    devs = enumerate_devices()
    vgn = [d for d in devs if f"{d.vid:04X}" in (VGN_KEYBOARD[0], VGN_MOUSE[0])]
    print(f"VGN devices: {len(vgn)}")
    for d in vgn:
        print(f"\n=== {d.vid:04X}:{d.pid:04X} up={d.usage_page:04X} u={d.usage:04X} "
              f"in={d.input_len} out={d.output_len} feat={d.feature_len} | {d.product}")
        # 标准电池用法
        caps = find_battery_value_caps(d.path)
        if caps:
            print(f"  [std battery caps] {[(c.report_id, c.report_type) for c in caps]}")
        # 只探测厂商集合
        if not d.is_vendor_collection:
            print("  (非厂商集合，跳过协议探测)")
            continue
        size = max(d.output_len or 0, d.input_len or 0, 17)
        try:
            dev = HidDevice(d.path)
        except OSError as e:
            print(f"  open failed: {e}")
            continue
        try:
            # 1) Nordic52
            r = try_nordic52(dev, size)
            if r:
                print(f"  [Nordic52 reply] {hexs(r)}  -> percent={r[6]} wired={r[7]}")
            else:
                print("  Nordic52: no reply")
            # 2) Evision
            r = try_evision(dev)
            if r:
                print(f"  [Evision reply] {hexs(r)}  -> percent={r[8]} status={r[9]}")
            else:
                print("  Evision: no reply")
            # 3) feature report 扫描 report id 1..16
            for rid in range(1, 17):
                flen = d.feature_len or 64
                buf = dev.get_feature(rid, min(flen, 64))
                if buf and any(buf):
                    interesting = [b for b in buf[1:] if 1 <= b <= 100]
                    print(f"  [feature id={rid}] {hexs(buf)}"
                          + (f"  candidates={interesting}" if interesting else ""))
        finally:
            dev.close()


if __name__ == "__main__":
    main()

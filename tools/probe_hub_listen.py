"""在 VGN HUB 运行时，监听 V108 所有 vendor 输入通道，抓 HUB 查询的应答帧。"""
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, HidDevice


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def main():
    # 只监听 vendor 集合（跳过系统独占的键盘/鼠标）
    devs = [d for d in enumerate_devices()
            if d.pid == 0x2A02 and d.is_vendor_collection and d.input_len > 0]
    handles = []
    for d in devs:
        try:
            handles.append((d, HidDevice(d.path)))
        except OSError as e:
            print(f"open fail up={d.usage_page:04X} u={d.usage:04X}: {e}")
    print(f"listening {len(handles)} collections for 20s... 请保持 VGN HUB 打开")
    t0 = time.time()
    counts = {}
    try:
        while time.time() - t0 < 20.0:
            for d, dev in handles:
                r = dev.read(d.input_len, 100)
                if r:
                    counts[d] = counts.get(d, 0) + 1
                    tag = f"up={d.usage_page:04X} u={d.usage:04X}"
                    if counts[d] <= 15:
                        print(f"  [{time.time()-t0:5.1f}s] {tag}: {hexs(r)}")
    finally:
        for _, dev in handles:
            dev.close()
    print("\n=== 汇总 ===")
    for d, n in counts.items():
        print(f"  up={d.usage_page:04X} u={d.usage:04X}: {n} 帧")
    if not counts:
        print("  (未捕获任何帧)")


if __name__ == "__main__":
    main()

"""V108 定向探测：大 feature 报告 (1032B) / FF01 feat=8 / FF02:0002 out=20 三条通道。"""
import ctypes
import sys
import time

sys.path.insert(0, ".")
from app.hid.core import enumerate_devices, HidDevice


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def nonzero_prefix(b, n=24):
    """返回前 n 字节中非零的摘要"""
    head = b[:n]
    if any(head):
        return hexs(head)
    # 找第一个非零位置
    for i, v in enumerate(b):
        if v:
            return f"first_nz@{i}={v:02X} tail={hexs(b[i:i+16])}"
    return "(all zero)"


def main():
    devs = [d for d in enumerate_devices() if d.pid == 0x2A02]
    targets = {
        "BIG_FEAT_1032": lambda d: d.feature_len >= 1000,
        "FF01_feat8": lambda d: d.feature_len == 8 and d.usage_page == 0xFF01,
        "FF02_0002_out20": lambda d: d.usage_page == 0xFF02 and d.usage == 0x0002,
        "FF00_feat6": lambda d: d.feature_len == 6,
        "FF02_0001_in4": lambda d: d.usage_page == 0xFF02 and d.usage == 0x0001,
    }

    for name, pred in targets.items():
        matched = [d for d in devs if pred(d)]
        if not matched:
            print(f"\n### {name}: NOT PRESENT")
            continue
        d = matched[0]
        print(f"\n### {name}  in={d.input_len} out={d.output_len} feat={d.feature_len}")
        print(f"    {d.path}")
        try:
            dev = HidDevice(d.path)
        except OSError as e:
            print(f"    open failed: {e}")
            continue
        try:
            if d.feature_len:
                print("  -- get_feature rid scan --")
                fl = d.feature_len
                for rid in range(0, 40):
                    buf = dev.get_feature(rid, fl)
                    if buf is None:
                        continue
                    if any(buf):
                        print(f"    rid={rid:3d} len={len(buf):4d} {nonzero_prefix(buf, 40)}")
            if d.input_len:
                print("  -- passive listen 3.5s --")
                got = 0
                t0 = time.time()
                while time.time() - t0 < 3.5 and got < 12:
                    r = dev.read(d.input_len, 600)
                    if r:
                        got += 1
                        print(f"    IN: {hexs(r)}")
                if not got:
                    print("    (no input reports)")
            if d.output_len:
                print("  -- output probes --")
                size = d.output_len
                for rid in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                    for pat_name, pat in (("zeros", 0x00), ("0x04", 0x04)):
                        frame = bytearray(size)
                        frame[0] = rid
                        if pat:
                            frame[1] = 0x04
                        ok = dev.write(bytes(frame))
                        if ok:
                            print(f"    rid={rid} {pat_name}: WRITE OK")
                            for _ in range(3):
                                r = dev.read(d.input_len or 21, 400)
                                if r:
                                    print(f"       IN: {hexs(r)}")
                                    break
                        else:
                            err = ctypes.get_last_error()
                            if err != 87 and err != 1:
                                print(f"    rid={rid} {pat_name}: err={err}")
        finally:
            dev.close()


if __name__ == "__main__":
    main()

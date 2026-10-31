"""诊断：连续扫描多轮，测量耗时与每个设备的状态，定位"卡住/不刷新"的原因。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

from app.engine.scanner import BatteryScanner


def main(rounds=5):
    sc = BatteryScanner()
    print("=" * 72)
    for i in range(rounds):
        t0 = time.time()
        te = time.time()
        devs = sc.enumerate()
        t_enum = time.time() - te
        tq = time.time()
        states = sc.scan_once()
        dur = time.time() - tq
        print(f"[第 {i+1} 轮] enumerate {t_enum:5.2f}s ({len(devs)} 个接口组) | "
              f"scan_once {dur:5.2f}s | 展示 {len(states)} 个 | 总计 {time.time()-t0:5.2f}s")
        for s in states:
            r = s.reading
            print(f"    - {s.info.key} {s.info.kind:<9} status={r.status:<10} "
                  f"pct={r.percent} proto={r.protocol} detail={r.detail}")
        if i < rounds - 1:
            time.sleep(2)
    print("=" * 72)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    main(n)

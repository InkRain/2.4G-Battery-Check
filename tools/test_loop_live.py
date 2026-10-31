"""实机验证：后台扫描循环持续工作，回调不断（检查新看门狗模型不会停摆）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

from app.engine.scanner import BatteryScanner

hits = []


def main(seconds=75, interval=10):
    sc = BatteryScanner()
    sc.interval = interval
    sc.subscribe(lambda states: hits.append((time.time(), len(states))))
    sc.start()
    print(f"启动扫描线程，间隔 {interval}s，观察 {seconds}s ...")
    time.sleep(seconds)
    alive = sc._thread.is_alive() if sc._thread else False
    sc.stop()
    time.sleep(0.5)

    print(f"回调次数 = {len(hits)} | 扫描线程存活 = {alive}")
    if not hits:
        print("FAIL: 没有任何回调")
        return 1
    gaps = [b[0] - a[0] for a, b in zip(hits, hits[1:])]
    if gaps:
        print(f"回调间隔: min={min(gaps):.1f}s max={max(gaps):.1f}s "
              f"avg={sum(gaps)/len(gaps):.1f}s")
    ok = len(hits) >= max(3, seconds // interval - 2)
    ok = ok and alive and (not gaps or max(gaps) <= interval * 2.5)
    print("PASS ✅ 扫描循环持续运行" if ok else "FAIL ❌ 扫描循环异常")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 75))

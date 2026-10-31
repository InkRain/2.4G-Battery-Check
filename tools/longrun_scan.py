"""长测：每 20 秒扫描一次，记录状态与耗时，用于观察"休眠后能否自动恢复"。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

from app.engine.scanner import BatteryScanner
from app.engine.protocols import idle_seconds

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "longrun.log")


def main(minutes=8.0, interval=20.0):
    sc = BatteryScanner()
    t_end = time.time() + minutes * 60
    with open(OUT, "w", encoding="utf-8") as f:
        while time.time() < t_end:
            t0 = time.time()
            try:
                states = sc.scan_once()
            except Exception as e:
                f.write(f"{time.strftime('%H:%M:%S')} SCAN ERROR {e}\n")
                f.flush()
                time.sleep(interval)
                continue
            dur = time.time() - t0
            parts = []
            for s in states:
                r = s.reading
                parts.append(f"{s.info.kind}:{r.status}/{r.percent}%")
            line = (f"{time.strftime('%H:%M:%S')} idle={idle_seconds():6.1f}s "
                    f"scan={dur:5.2f}s | " + "  ".join(parts))
            f.write(line + "\n")
            f.flush()
            time.sleep(max(0.0, interval - dur))


if __name__ == "__main__":
    m = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    main(m)

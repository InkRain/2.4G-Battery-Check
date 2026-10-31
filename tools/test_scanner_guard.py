"""验证扫描看门狗与休眠补扫逻辑（不需要真实硬件）。"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.models import BatteryReading, DeviceInfo, ST_OK, ST_SLEEPING
from app.engine.scanner import BatteryScanner, DeviceState
import app.engine.scanner as scanner_mod


def make_state(kind, status, pct=None):
    info = DeviceInfo(key=f"TEST:{kind}", vid=0x391D, pid=0x1234, kind=kind)
    st = DeviceState(info)
    st.reading = BatteryReading(percent=pct, status=status, protocol="test")
    return st


class FakeScanner(BatteryScanner):
    """可注入 scan_once 行为的测试用扫描器。"""

    def __init__(self, behavior, states=None):
        super().__init__()
        self.SCAN_TIMEOUT = 1.0
        self.HUNG_TIMEOUT = 2.5
        self._behavior = behavior
        self._states_out = states or []

    def scan_once(self):
        if self._behavior == "raise":
            raise RuntimeError("boom")
        if self._behavior == "hang":
            time.sleep(8)
            return []
        return self._states_out


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    assert cond, name


# ---------------- 1. 正常一轮：返回 states，_busy 复位 ----------------
evts = []
sc = FakeScanner("ok", [make_state("keyboard", ST_OK, 88)])
sc.subscribe(lambda s: evts.append(s))
t0 = time.time()
r = sc._tick()
check("正常扫描返回并广播", len(evts) == 1 and r is None, f"耗时 {time.time()-t0:.2f}s")
check("正常后 _busy 复位", sc._busy is False)
check("记录 last_scan_at", sc.last_scan_at > 0)

# ---------------- 2. scan_once 抛异常：不崩、_busy 复位 ----------------
sc = FakeScanner("raise")
sc._tick()
check("scan_once 异常后 _busy 复位", sc._busy is False)

# ---------------- 3. 卡死：超时放弃，之后恢复 ----------------
sc = FakeScanner("hang")
t0 = time.time()
r = sc._tick()
dt = time.time() - t0
check("卡死时按 SCAN_TIMEOUT 超时返回", 0.9 <= dt <= 1.6, f"{dt:.2f}s")
check("超时后 _busy 仍为 True（等看门狗放行）", sc._busy is True)

# 立刻再 tick：stuck < HUNG_TIMEOUT，应跳过且不启动新线程
sc._busy_since = time.time()
r2 = sc._tick()
check("卡死未超容忍期时跳过本轮", r2 is None)

# 把开始时间推到很久以前，模拟已卡死超过 HUNG_TIMEOUT
sc._busy_since = time.time() - sc.HUNG_TIMEOUT - 1
sc2 = FakeScanner("ok", [make_state("mouse", ST_OK, 50)])
# 复用同一实例但换行为，验证强制放行后能再次扫描成功
sc._behavior = "ok"
sc._states_out = [make_state("mouse", ST_OK, 50)]
evts.clear()
sc.subscribe(lambda s: evts.append(s))
r3 = sc._tick()
check("卡死超过容忍期后强制重扫成功", len(evts) == 1, f"广播 {len(evts)} 次")

# ---------------- 4. 休眠且用户有输入 → 触发快速补扫 ----------------
orig_idle = scanner_mod.idle_seconds
try:
    scanner_mod.idle_seconds = lambda: 1.0        # 用户刚动过
    sc = FakeScanner("ok", [make_state("keyboard", ST_SLEEPING, 99)])
    check("休眠+有输入 → 5 秒后补扫", sc._tick() == sc.QUICK_INTERVAL)
    check("补扫计数 +1", sc._quick_retry == 1)

    # 连续补扫达到上限后停止
    for _ in range(sc.MAX_QUICK_RETRY):
        sc._tick()
    check("补扫达上限 → 退回较长间隔",
      sc._tick() == sc.SLEEPING_INTERVAL, f"retry={sc._quick_retry}")

    # 用户长时间无操作 → 不补扫
    scanner_mod.idle_seconds = lambda: 300.0
    sc = FakeScanner("ok", [make_state("keyboard", ST_SLEEPING, 99)])
    check("休眠但用户离开 → 用较长间隔",
      sc._tick() == sc.SLEEPING_INTERVAL)

    # 设备正常 → 补扫计数复位
    scanner_mod.idle_seconds = lambda: 1.0
    sc = FakeScanner("ok", [make_state("keyboard", ST_OK, 99)])
    sc._quick_retry = 3
    sc._tick()
    check("读取成功后补扫计数复位", sc._quick_retry == 0)
finally:
    scanner_mod.idle_seconds = orig_idle

# ---------------- 5. 枚举返回空时保留旧状态 ----------------
sc = BatteryScanner()          # 用真实 scan_once 验证保护逻辑
old = make_state("keyboard", ST_OK, 77)
sc._states[old.key] = old
sc.enumerate = lambda: []
kept = sc.scan_once()
check("枚举为空时保留旧设备", len(kept) == 1 and kept[0].key == old.key)

print("\n全部通过 ✅")

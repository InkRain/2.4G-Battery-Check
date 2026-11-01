"""电量扫描调度器：枚举设备、分组、分发协议、后台刷新。"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from app.engine.models import (BatteryReading, DeviceInfo, ST_OK, ST_SLEEPING,
                               ST_UNSUPPORTED, ST_NO_API, guess_kind, friendly_name,
                               KNOWN_DEVICES, VENDOR_NAMES)
from app.engine.protocols import PROTOCOLS, Protocol, idle_seconds
from app.hid.core import enumerate_devices

log = logging.getLogger("engine.scanner")


class DeviceState:
    """运行时设备状态。"""

    def __init__(self, info: DeviceInfo):
        self.info = info
        self.reading: Optional[BatteryReading] = None
        self.protocol: Optional[Protocol] = None     # 上次成功的协议
        self.last_query = 0.0
        # 最后一次读到的有效电量。不能直接用 reading.percent 当缓存：
        # 每轮都会用新读数覆盖 reading，一旦某轮读不到（休眠 -> None），
        # 缓存就断了，之后托盘图标会一直灰着（用户反馈过的「绿环变灰」）。
        self.last_percent: Optional[int] = None

    @property
    def key(self) -> str:
        return self.info.key


class BatteryScanner:
    """扫描调度器（线程安全）。UI 通过 subscribe 获取结果回调。"""

    # 单轮扫描硬超时：超过就放弃本轮（HID 打开/读取偶尔会被系统挂起卡住）
    SCAN_TIMEOUT = 45.0
    # 上一轮仍在跑时，最多容忍多久；超过则判定卡死并强行开始新一轮
    HUNG_TIMEOUT = 90.0
    # 设备显示休眠、且用户正在操作时，用很短间隔连补几次，抓住唤醒瞬间
    MAX_QUICK_RETRY = 6
    QUICK_INTERVAL = 5.0
    # 设备休眠但用户离开时，仍用较短间隔，保证回来动一下就能很快恢复显示
    SLEEPING_INTERVAL = 20.0

    def __init__(self):
        self._lock = threading.RLock()
        self._states: Dict[str, DeviceState] = {}
        self._callbacks: List[Callable[[List[DeviceState]], None]] = []
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.interval = 60.0
        self._busy = False
        self._busy_since = 0.0
        self._quick_retry = 0
        self.last_scan_at = 0.0

    # ---- 订阅 ----
    def subscribe(self, cb: Callable[[List[DeviceState]], None]) -> None:
        self._callbacks.append(cb)

    def _emit(self, states: List[DeviceState] = None) -> None:
        if states is None:
            with self._lock:
                states = list(self._states.values())
        for cb in self._callbacks:
            try:
                cb(states)
            except Exception:
                log.exception("callback error")

    # ---- 设备枚举与分组 ----
    def enumerate(self) -> List[DeviceInfo]:
        """枚举并按 VID/PID 分组为物理设备。"""
        groups: Dict[str, DeviceInfo] = {}
        for iface in enumerate_devices():
            key = f"{iface.vid:04X}:{iface.pid:04X}"
            if key not in groups:
                groups[key] = DeviceInfo(key=key, vid=iface.vid, pid=iface.pid)
            dev = groups[key]
            dev.interfaces.append(iface)
            if iface.product and not dev.dongle_name:
                dev.dongle_name = iface.product
        result = []
        for dev in groups.values():
            dev.kind = guess_kind(dev)
            result.append(dev)
        # 只保留可能是无线外设的：有厂商集合或已知型号
        result = [d for d in result
                  if d.vendor_collections or (d.vid, d.pid) in KNOWN_DEVICES]
        return result

    # ---- 单设备查询 ----
    def query_device(self, dev: DeviceInfo) -> BatteryReading:
        """按协议优先级查询；缓存成功的协议优先重试。"""
        with self._lock:
            state = self._states.get(dev.key)
            cached_proto = state.protocol if state else None
            last_percent = state.last_percent if state else None
        order = list(PROTOCOLS)
        if cached_proto is not None:
            order.sort(key=lambda p: 0 if p is cached_proto else 1)
        first_reading = None
        for proto in order:
            try:
                if not proto.matches(dev):
                    continue
                reading = proto.query(dev)
            except Exception as e:
                log.warning("protocol %s error: %s", proto.name, e)
                reading = BatteryReading(status="error", protocol=proto.name, detail=str(e))
            if first_reading is None:
                first_reading = reading
            if reading.ok:
                with self._lock:
                    if dev.key in self._states:
                        self._states[dev.key].protocol = proto
                return reading
        # 休眠时保留上次电量读数（灰色展示）
        if (first_reading is not None and first_reading.status == ST_SLEEPING
                and last_percent is not None):
            first_reading.percent = last_percent
        if first_reading is not None:
            return first_reading
        # 没有任何协议匹配：区分「已知型号但无电量通道」与「完全未知」
        if (dev.vid, dev.pid) in KNOWN_DEVICES:
            return BatteryReading(status=ST_NO_API, protocol="—",
                                  connection="USB" if dev.kind == "headset" else "2.4G",
                                  detail="设备无电量上报通道")
        return BatteryReading(status=ST_UNSUPPORTED)

    # ---- 全量扫描 ----
    def _is_relevant(self, dev: DeviceInfo, reading: BatteryReading) -> bool:
        """是否值得展示：读到电量 / 休眠 / 固件未开放接口 / 已知型号或厂商。"""
        if reading.ok or reading.status in (ST_SLEEPING, ST_NO_API):
            return True
        if (dev.vid, dev.pid) in KNOWN_DEVICES:
            return True
        if dev.vid in VENDOR_NAMES:
            return True
        return False

    def scan_once(self) -> List[DeviceState]:
        t0 = time.time()
        devices = self.enumerate()
        if not devices and self._states:
            # 枚举偶尔会因 USB 挂起/驱动重启瞬时返回空，此时不要清空设备列表
            log.warning("本轮未枚举到任何设备，保留上次结果")
            with self._lock:
                return list(self._states.values())
        states: List[DeviceState] = []
        with self._lock:
            for dev in devices:
                if dev.key not in self._states:
                    self._states[dev.key] = DeviceState(dev)
            # 移除已断开
            live = {d.key for d in devices}
            for key in list(self._states.keys()):
                if key not in live:
                    del self._states[key]
        for dev in devices:
            state = self._states[dev.key]
            reading = self.query_device(dev)
            state.reading = reading
            state.last_query = time.time()
            if reading.ok:
                state.last_percent = reading.percent   # 记住最后一次有效电量
            if self._is_relevant(dev, reading):
                states.append(state)
        states = self._merge_duplicates(states)
        log.info("scan_once: %d devices (%d shown) in %.1fs",
                 len(devices), len(states), time.time() - t0)
        return states

    @staticmethod
    def _merge_duplicates(states: List[DeviceState]) -> List[DeviceState]:
        """同一物理设备的合并：鼠标插线充电/有线使用时走 USB 直连接口，
        其 2.4G 接收器会显示"休眠"——此时隐藏休眠的 dongle 条目，避免一鼠标两卡片。
        规则：同 vid 同 kind，存在 USB 直连且读数 ok 的条目时，
        剔除该 vid+kind 下处于 sleeping 的 2.4G 条目。"""
        wired_ok = {(s.info.vid, s.info.kind) for s in states
                    if s.reading and s.reading.status == ST_OK
                    and (s.reading.connection or "").upper() == "USB"}
        if not wired_ok:
            return states
        out = []
        for s in states:
            r = s.reading
            if ((s.info.vid, s.info.kind) in wired_ok
                    and r and r.status == ST_SLEEPING
                    and (r.connection or "").upper() != "USB"):
                log.info("merge: hide sleeping dongle %s (same device wired online)", s.info.key)
                continue
            out.append(s)
        return out

    # ---- 后台线程 ----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="battery-scanner",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            hint = None
            try:
                hint = self._tick()
            except Exception:
                log.exception("scan loop error")
            elapsed = time.time() - t0
            if hint is not None:
                # 设备休眠：按提示的短间隔重扫，尽快捕捉唤醒
                wait = hint
            else:
                # 间隔从本轮**开始**计时，避免「扫描耗时 + 间隔」叠加成超长周期
                wait = max(1.0, self.interval - elapsed)
            self._wake.wait(timeout=wait)
            self._wake.clear()

    def _tick(self) -> Optional[float]:
        """跑一轮扫描。返回下一轮建议的等待秒数（None 表示沿用默认间隔）。"""
        now = time.time()
        if self._busy:
            stuck = now - self._busy_since
            if stuck < self.HUNG_TIMEOUT:
                log.debug("上一轮扫描仍在进行（%.0fs），跳过本轮", stuck)
                return None
            # 无响应的 HID 句柄会把整轮扫描永久挂住 —— 放弃并重新开始
            log.warning("上一轮扫描已卡住 %.0f 秒，强制开始新一轮", stuck)
            self._busy = False

        self._busy = True
        self._busy_since = now
        box: dict = {}
        done = threading.Event()

        def work():
            try:
                box["states"] = self.scan_once()
            except Exception:
                log.exception("scan worker error")
            finally:
                done.set()

        threading.Thread(target=work, name="battery-scan", daemon=True).start()
        if not done.wait(self.SCAN_TIMEOUT):
            # 本轮放弃；_busy 保持 True，等 HUNG_TIMEOUT 后再放行重试
            log.warning("扫描超时（%.0f 秒），本轮放弃", self.SCAN_TIMEOUT)
            return None

        self._busy = False
        states = box.get("states")
        if states is None:
            return None
        self.last_scan_at = time.time()
        self._emit(states)
        return self._next_wait_hint(states)

    def _next_wait_hint(self, states: List[DeviceState]) -> Optional[float]:
        """有设备休眠时缩短重扫间隔，让设备一被唤醒就能很快显示正常电量。"""
        sleeping = [s for s in states
                    if s.reading is not None and s.reading.status == ST_SLEEPING]
        if not sleeping:
            self._quick_retry = 0
            return None
        if idle_seconds() <= 10.0 and self._quick_retry < self.MAX_QUICK_RETRY:
            self._quick_retry += 1
            log.debug("设备休眠中但系统有输入活动，%d/%d 次快速补扫",
                      self._quick_retry, self.MAX_QUICK_RETRY)
            return self.QUICK_INTERVAL
        # 用户已离开：不必高频，但仍比正常间隔短，回来一动就能尽快刷新
        return self.SLEEPING_INTERVAL

    @property
    def busy(self) -> bool:
        return self._busy

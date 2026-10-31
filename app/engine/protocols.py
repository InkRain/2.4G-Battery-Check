"""各厂商 2.4G 电量协议实现。

每个协议提供 matches(device) 判定与 query(device) 读取。
协议知识来源（详见 README 致谢）：
- Evision (VGN S99/VXE75/N75 等 320F:5088)：逆向自 WOB 网页驱动，参考 Rainy75Desktop
- Compx/Nordic 52 (VGN 蜻蜓/ATK/VXE/Dareu 等)：参考 mouse_tray / GearPower，本机实测通过
- Nordic 54L15 (ATK Zero)：参考 GearPower
- Keychron Ultra-Link：参考 HaloBattery (csutcliff/keychron-battery-dkms)
- Logitech HID++ 2.0/1.0：参考 HaloBattery / Solaar
- Realtek (MCHOSE)：参考 mouse_tray
"""
from __future__ import annotations

import ctypes
import logging
import time
from typing import List, Optional

from app.engine.models import (BatteryReading, DeviceInfo, ST_OK, ST_SLEEPING,
                               ST_UNSUPPORTED, ST_ERROR, ST_NO_API)
from app.hid.core import HidDevice, find_battery_value_caps

log = logging.getLogger("engine.protocols")


# ---------------------------------------------------------------- 空闲门控
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """系统键鼠空闲秒数（失败返回 999，表示放行）。"""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 999.0
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 999.0


def hexs(b: bytes, n: int = 24) -> str:
    return " ".join(f"{x:02X}" for x in b[:n])


class Protocol:
    name = "base"
    priority = 50

    def matches(self, device: DeviceInfo) -> bool:
        raise NotImplementedError

    def query(self, device: DeviceInfo) -> BatteryReading:
        raise NotImplementedError


# ================================================================ Evision
class EvisionProtocol(Protocol):
    """VGN S99 / VXE75 / N75 V2 等 Evision 方案键盘（VID 320F）。

    通道：vendor collection usagePage 0xFF1C，reportId 4
    查询帧：[4, 32, 0, 26, 6] + 补零到 64 字节（校验和=后续字节求和）
    响应：回显帧，第 8 字节=电量百分比，第 9 字节=充电状态
    2.4G 回包约 5s 一班，首包可能 5~12s，监听窗口需 ≥15s。
    """
    name = "Evision (VGN 键盘)"
    priority = 90

    VID = 0x320F
    USAGE_PAGE = 0xFF1C
    FRAME = bytes([4, 32, 0, 26, 6] + [0] * 59)
    WINDOW = 15.0
    FRAME_GAP = 1.5
    IDLE_GATE = 0.3

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid != self.VID:
            return False
        return any(i.usage_page == self.USAGE_PAGE for i in device.interfaces)

    def query(self, device: DeviceInfo) -> BatteryReading:
        colls = [i for i in device.interfaces if i.usage_page == self.USAGE_PAGE]
        colls.sort(key=lambda i: i.usage == 0x92, reverse=True)
        path = colls[0].path if colls else None
        if not path:
            return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
        t0 = time.time()
        sent = 0
        next_send = 0.0
        try:
            dev = HidDevice(path)
        except OSError as e:
            log.warning("evision open failed: %s", e)
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        try:
            dev.flush_input()
            while time.time() - t0 < self.WINDOW:
                if time.time() >= next_send and idle_seconds() >= self.IDLE_GATE:
                    if not dev.write(self.FRAME):
                        return BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                              detail="写入被拒绝（键盘可能休眠）")
                    sent += 1
                    next_send = time.time() + self.FRAME_GAP
                r = dev.read(65, 200)
                if r and len(r) >= 10 and r[0] == 4 and r[3] == 26:
                    percent, status = r[8], r[9]
                    if 0 < percent <= 100:
                        return BatteryReading(percent=percent, status=ST_OK,
                                              protocol=self.name,
                                              charging=bool(status),
                                              connection="2.4G",
                                              detail=f"{sent} 帧 / {time.time()-t0:.1f}s")
                    log.info("evision implausible payload: %s", hexs(r))
            return BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                  detail="窗口内无响应（接收器未插或键盘关机）")
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        finally:
            dev.close()


# ================================================================ 电压换算
# 与 VGN HUB 一致的放电曲线表（mV），每档间隔代表 5%
_VOLTAGES = [3050, 3420, 3480, 3540, 3600, 3660, 3720, 3760, 3800, 3840,
             3880, 3920, 3940, 3960, 3980, 4000, 4020, 4040, 4060, 4080, 4110]


def voltage_to_level(voltage: int, charging: bool) -> int:
    """按 HUB 的 voltageToLevel 算法把电压换算为电量百分比。"""
    level = 0.0
    if voltage > _VOLTAGES[-1]:
        level = 99 if charging else 100
    else:
        index = -1
        for i, v in enumerate(_VOLTAGES):
            if voltage < v:
                index = i
                break
        if index != -1:
            if index == 0:
                level = 0
            else:
                interval = (_VOLTAGES[index] - _VOLTAGES[index - 1]) / 5
                level = (voltage - _VOLTAGES[index - 1]) / interval + (index - 1) * 5
            if level in (0, 15):
                level += 1
        else:
            level = 100
    return round(level)


# ================================================================ 背赢 Beiying
class BeiyingProtocol(Protocol):
    """背赢（Beiying）方案键盘 dongle，VGN V108 等（从 VGN HUB 逆向）。

    通道：vendor collection usagePage 0xFF02 usage 0x0002（in/out 各 20 字节）
    写输出报告 id 19：负载 19 字节 = [0x4A, 0x01, 0, ...]，
    末字节 CRC = (19 + 负载前段之和) & 0xFF。
    电量查询命令 [0x4A, 0x01, 0, 0, 0]，设备以输入报告（rid 19）异步应答：
    content[0]=0x4A 回显，content[4]=电量%，content[5] 高 4 位=1 表示充电中。
    实测：VGN V108 2.4G dongle，回包 TX=13 4A 01 ... 5E → RX=13 4A 01 00 02 64 01 ... C5。
    """
    name = "Beiying (VGN V108)"
    priority = 95          # 高于 Nordic52：避免误发 Nordic52 帧触发 err

    REPORT_ID = 19
    USAGE_PAGE = 0xFF02
    USAGE = 0x0002

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid != 0x391D:
            return False
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=19)
        # 必须是 20 字节输出集合（键盘 dongle）；鼠标 dongle 是 17 字节，排除
        return coll is not None and coll.output_len >= 19

    def _build_frame(self, cmd: bytes, out_len: int) -> bytes:
        content = bytearray(out_len - 1)
        content[:len(cmd)] = cmd
        content[-1] = (self.REPORT_ID + sum(content[:-1])) & 0xFF
        return bytes([self.REPORT_ID]) + bytes(content)

    def query(self, device: DeviceInfo) -> BatteryReading:
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=19)
        if coll is None:
            return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
        out_len = coll.output_len
        frame = self._build_frame(bytes([0x4A, 0x01, 0x00, 0x00, 0x00]), out_len)
        last_err = 0
        for attempt in range(3):
            try:
                dev = HidDevice(coll.path)
            except OSError as e:
                return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
            try:
                dev.flush_input()
                if not dev.write(frame, 400):
                    last_err = dev.last_error
                    time.sleep(0.15 * (attempt + 1))
                    continue
                deadline = time.time() + 1.8
                while time.time() < deadline:
                    r = dev.read(out_len, 250)
                    if not r or len(r) < 7 or r[0] != self.REPORT_ID:
                        continue
                    content = r[1:]
                    if content[0] != 0x4A:
                        continue
                    # CRC 校验：content 末字节 = (19 + 之前各字节和) & 0xFF
                    crc = content[-1]
                    calc = (self.REPORT_ID + sum(content[:-1])) & 0xFF
                    if crc != calc:
                        log.debug("beiying crc mismatch: %02X != %02X", crc, calc)
                        continue
                    percent = content[4]
                    charging = ((content[5] >> 4) & 0xF) == 1
                    if 0 <= percent <= 100:
                        return BatteryReading(
                            percent=percent, status=ST_OK, protocol=self.name,
                            charging=charging and percent < 100,
                            full=charging and percent >= 100,
                            connection="2.4G", detail="")
                    log.info("beiying implausible battery: %s", hexs(r))
            except OSError as e:
                return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
            finally:
                dev.close()
        if last_err == 1:
            return BatteryReading(status=ST_NO_API, protocol=self.name,
                                  detail="接收器固件未开放电量接口")
        # 写入成功但无应答：设备休眠或 dongle 无设备配对
        return BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="无响应")


# ================================================================ Nordic 52
class Nordic52Protocol(Protocol):
    """Compx/Nordic 52840 方案（VGN 蜻蜓、ATK、VXE、Dareu、G-Wolves 等）。

    17 字节报告 id 0x08，子命令 0x04：
      write  08 04 00*15 49
      read   08 04 00 00 00 <st> <%> <wired> <mV:2> ... <cksum>
    电量在 offset 6，offset 7 为有线/充电标志。本机 VGN Dragonfly 实测通过。
    """
    name = "Compx/Nordic 52 (VGN 鼠标)"
    priority = 90

    VIDS = (0x373B, 0x3554, 0x260D, 0x33E4, 0x391D)
    USAGE_PAGE = 0xFF02
    USAGE = 0x0002

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid not in self.VIDS:
            return False
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=17)
        return coll is not None

    def query(self, device: DeviceInfo) -> BatteryReading:
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=17)
        if coll is None:
            return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
        size = max(coll.output_len, coll.input_len, 17)
        frame = bytearray(size)
        frame[0] = 0x08
        frame[1] = 0x04
        frame[size - 1] = 0x49

        last = BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="无响应")
        # dongle 偶尔会短暂 busy（尤其多接收器并存时），重试几次再判定
        for attempt in range(3):
            if attempt:
                time.sleep(0.18 * attempt)
            try:
                dev = HidDevice(coll.path)
            except OSError as e:
                last = BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
                continue
            try:
                dev.flush_input()
                if not dev.write(bytes(frame)):
                    if dev.last_error == 1:
                        # err=1 (ERROR_INVALID_FUNCTION)：集合存在但固件未实现该命令，
                        # 不是休眠——2.4G 接收器没有开放电量查询接口。
                        return BatteryReading(status=ST_NO_API, protocol=self.name,
                                              detail="接收器固件未开放电量接口")
                    last = BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                          detail=f"写入被拒绝 err={dev.last_error}")
                    continue
                deadline = time.time() + 1.6
                while time.time() < deadline:
                    r = dev.read(size + 1, 220)
                    if r and len(r) >= 8 and r[0] == 0x08 and r[1] == 0x04:
                        raw_percent = r[6]
                        charging = (r[7] == 1)
                        mv = (r[8] << 8) | r[9] if len(r) >= 10 else 0
                        # 与 VGN HUB 一致：优先用电压查表换算（固件原始百分比偏差大）
                        if mv >= 3050:
                            percent = voltage_to_level(mv, charging)
                        else:
                            percent = raw_percent
                        if 0 <= percent <= 100:
                            return BatteryReading(
                                percent=percent, status=ST_OK, protocol=self.name,
                                charging=charging and percent < 100,
                                full=charging and percent >= 100,
                                connection="USB" if charging else "2.4G",
                                detail=f"{mv} mV" if mv else "")
                        last = BatteryReading(status=ST_ERROR, protocol=self.name,
                                              detail=f"异常回包 {hexs(r)}")
                        break
                else:
                    last = BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                          detail="无响应")
            except OSError as e:
                last = BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
                dev = None
                continue
            finally:
                if dev is not None:
                    dev.close()
        # 连续重试都写不进且 err=87（报告 ID 不被该集合支持）→ 固件无此功能
        if last.status == ST_SLEEPING and getattr(dev, "last_error", 0) == 87:
            return BatteryReading(status=ST_NO_API, protocol=self.name,
                                  detail="接收器不支持电量查询")
        return last


# ================================================================ Nordic 54
class Nordic54Protocol(Protocol):
    """Compx/Nordic 54L15 方案（ATK Zero 等）：64 字节报告，命令 0x72 子命令 7。"""
    name = "Compx/Nordic 54"
    priority = 80

    VIDS = (0x373B, 0x3554, 0x260D, 0x33E4)
    USAGE_PAGE = 0xFF05
    USAGE = 0x0001

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid not in self.VIDS:
            return False
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=64)
        if coll:
            return True
        return any(i.output_len >= 64 for i in device.vendor_collections)

    def query(self, device: DeviceInfo) -> BatteryReading:
        coll = device.pick_collection(self.USAGE_PAGE, self.USAGE, min_output=64)
        if coll is None:
            colls = [i for i in device.vendor_collections if i.output_len >= 64]
            if not colls:
                return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
            coll = colls[0]
        size = max(coll.output_len, 64)
        frame = bytearray(size)
        frame[0] = 0x72
        frame[1] = 0x07
        try:
            dev = HidDevice(coll.path)
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        try:
            dev.flush_input()
            if not dev.write(bytes(frame)):
                return BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                      detail="写入被拒绝")
            deadline = time.time() + 2.0
            while time.time() < deadline:
                r = dev.read(size + 1, 250)
                if r and len(r) >= 8 and r[0] == 0x72:
                    # 电池字节在多个候选位置，取第一个 0-100 的合理值
                    for off in (6, 7, 8, 9, 10):
                        if len(r) > off and 0 < r[off] <= 100:
                            return BatteryReading(percent=r[off], status=ST_OK,
                                                  protocol=self.name, connection="2.4G")
                    return BatteryReading(status=ST_ERROR, protocol=self.name,
                                          detail=f"异常回包 {hexs(r)}")
            return BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="无响应")
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        finally:
            dev.close()


# ================================================================ Keychron
class KeychronProtocol(Protocol):
    """Keychron Ultra-Link 8K / M5：vendor collection 接口4，
    请求 feature 报告 b3 06，回包输入报告 b4 06，电量在 byte 20。"""
    name = "Keychron Ultra-Link"
    priority = 70

    VID = 0x3434
    PIDS = {0xD028: "Keychron Ultra-Link 8K", 0xD048: "Keychron M5"}
    USAGE_PAGE = 0
    USAGE = 0
    VENDOR_INTERFACE = 4
    REPORT_ID_CMD = 0xB3
    REPORT_ID_RESP = 0xB4
    CMD_STATUS = 0x06
    BATTERY_OFFSET = 20
    REPORT_SIZE = 64

    def matches(self, device: DeviceInfo) -> bool:
        return device.vid == self.VID and device.pid in self.PIDS

    def query(self, device: DeviceInfo) -> BatteryReading:
        colls = [i for i in device.vendor_collections]
        coll = None
        for i in colls:
            if getattr(i, "interface_number", None) == self.VENDOR_INTERFACE:
                coll = i
                break
        if coll is None and colls:
            coll = sorted(colls, key=lambda i: i.output_len, reverse=True)[0]
        if coll is None:
            return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
        req = [self.REPORT_ID_CMD, self.CMD_STATUS] + [0] * (self.REPORT_SIZE - 2)
        try:
            dev = HidDevice(coll.path)
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        try:
            for attempt in range(3):
                if attempt:
                    time.sleep(0.1)
                try:
                    dev.set_feature(bytes(req))
                except OSError:
                    continue
                r = dev.read(self.REPORT_SIZE + 1, 500)
                if not r:
                    continue
                if (len(r) > self.BATTERY_OFFSET and r[0] == self.REPORT_ID_RESP
                        and r[1] == self.CMD_STATUS):
                    level = r[self.BATTERY_OFFSET]
                    if 0 <= level <= 100:
                        return BatteryReading(percent=level, status=ST_OK,
                                              protocol=self.name, connection="2.4G")
            return BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="无有效回包")
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        finally:
            dev.close()


# ================================================================ Logitech HID++
class LogitechHidppProtocol(Protocol):
    """罗技 Unifying/Lightspeed/Bolt 接收器：HID++ 2.0/1.0 电量查询。

    参考 HaloBattery / Solaar 实现。short=ff00:0001(7B) long=ff00:0002(20B)。
    """
    name = "Logitech HID++"
    priority = 70

    VID = 0x046D
    RECEIVER_PIDS = {
        0xC548, 0xC52B, 0xC532, 0xC52F, 0xC518, 0xC51A, 0xC51B, 0xC521,
        0xC525, 0xC526, 0xC52E, 0xC531, 0xC534, 0xC535, 0xC537, 0xC539,
        0xC53A, 0xC53D, 0xC53F, 0xC541, 0xC545, 0xC547, 0xC54D,
    }
    SWIDS = (0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F)
    F_ROOT = 0x0000
    F_UNIFIED, F_STATUS, F_VOLTAGE = 0x1004, 0x1000, 0x1001
    BATTERY_FEATURES = (F_UNIFIED, F_STATUS, F_VOLTAGE)
    REG_BATTERY_CHARGE = 0x0D
    STATUS_LEVELS = {7: 90, 5: 50, 3: 20, 1: 5}
    VOLTAGE_CURVE = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60),
                     (3811, 50), (3778, 40), (3751, 30), (3717, 20), (3671, 10),
                     (3646, 5), (3579, 2), (3500, 0))
    ON_CHARGER = (1, 2, 3, 4)
    TIMEOUT = 0.8

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid != self.VID:
            return False
        if device.pid in self.RECEIVER_PIDS:
            return True
        return any(i.usage_page == 0xFF00 for i in device.vendor_collections)

    # ---- 底层通道 ----
    def _open_channel(self, device: DeviceInfo):
        short = long_ = None
        for i in device.vendor_collections:
            if i.usage_page == 0xFF00:
                if i.usage == 0x0001 and i.input_len >= 7 and not short:
                    short = i
                if i.usage == 0x0002 and i.input_len >= 20:
                    long_ = i
        if long_ is None:  # 退化：任意 ff00 集合
            ff = [i for i in device.vendor_collections if i.usage_page == 0xFF00]
            if not ff:
                return None
            long_ = sorted(ff, key=lambda i: i.input_len, reverse=True)[0]
        devs = []
        try:
            dl = HidDevice(long_.path)
            devs.append(dl)
            if short is not None and short.path != long_.path:
                try:
                    devs.append(HidDevice(short.path))
                except OSError:
                    pass
        except OSError:
            for d in devs:
                d.close()
            return None
        return devs

    def _request(self, devs, idx: int, feat: int, func: int, params=()):
        """发送 HID++ 请求并等待回包，返回 params 列表或 None。"""
        swid = self.SWIDS[int(time.time() * 10) % len(self.SWIDS)]
        fn = (func << 4) | swid
        req = [0x11, idx, feat, fn] + list(params)
        frame = bytes(req + [0] * (20 - len(req)))
        try:
            devs[0].write(frame)
        except OSError:
            return None
        deadline = time.time() + self.TIMEOUT
        while time.time() < deadline:
            for d in devs:
                r = d.read(64, 60)
                if not r or len(r) < 5 or r[1] != idx:
                    continue
                if r[2] in (0x8F, 0xFF) and len(r) >= 6 and r[3] == feat and r[4] == fn:
                    return None
                if r[2] == feat and r[3] == fn:
                    return list(r[4:])
            time.sleep(0.005)
        return None

    def _read_register(self, devs, idx: int, reg: int):
        if len(devs) < 2:
            return None
        try:
            devs[1].write(bytes([0x10, idx, 0x81, reg, 0, 0, 0]))
        except OSError:
            return None
        deadline = time.time() + self.TIMEOUT
        while time.time() < deadline:
            for d in devs:
                r = d.read(64, 60)
                if not r or len(r) < 4 or r[1] != idx:
                    continue
                if r[2] in (0x8F, 0xFF) and len(r) >= 6 and r[3] == 0x81 and r[4] == reg:
                    return None
                if r[2] == 0x81 and r[3] == reg:
                    return list(r[4:])
            time.sleep(0.005)
        return None

    def _voltage_to_percent(self, mv: int) -> int:
        if mv >= self.VOLTAGE_CURVE[0][0]:
            return 100
        curve = self.VOLTAGE_CURVE
        for (hi_mv, hi_p), (lo_mv, lo_p) in zip(curve, curve[1:]):
            if mv >= lo_mv:
                return round(lo_p + (mv - lo_mv) * (hi_p - lo_p) / (hi_mv - lo_mv))
        return 0

    def query(self, device: DeviceInfo) -> BatteryReading:
        devs = self._open_channel(device)
        if not devs:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail="无法打开通道")
        try:
            for d in devs:
                d.flush_input()
            slots = [0xFF] + list(range(1, 7))
            for slot in slots:
                # ping：槽位是否有设备
                if slot != 0xFF:
                    pong = self._request(devs, slot, self.F_ROOT, 1)
                    if pong is None:
                        continue
                for feat in self.BATTERY_FEATURES:
                    fidx = self._request(devs, slot, self.F_ROOT, 0,
                                         [feat & 0xFF, (feat >> 8) & 0xFF])
                    if not fidx or len(fidx) < 1 or fidx[0] == 0:
                        continue
                    fidx = fidx[0]
                    fn = 1 if feat == self.F_UNIFIED else 0
                    p = self._request(devs, slot, fidx, fn)
                    if not p:
                        continue
                    percent, charging, conn = self._parse(feat, p)
                    if percent is not None:
                        return BatteryReading(percent=percent, status=ST_OK,
                                              protocol=self.name, charging=charging,
                                              connection=conn or "2.4G")
                # HID++ 1.0 退化
                p = self._read_register(devs, slot, self.REG_BATTERY_CHARGE)
                if p and len(p) >= 1 and 0 < p[0] <= 100:
                    charging = len(p) > 2 and (p[2] & 0xF0) in (0x50, 0x90)
                    return BatteryReading(percent=p[0], status=ST_OK,
                                          protocol=self.name + " 1.0",
                                          charging=charging, connection="2.4G")
            return BatteryReading(status=ST_SLEEPING, protocol=self.name,
                                  detail="接收器在线但无设备响应（设备可能休眠）")
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        finally:
            for d in devs:
                d.close()

    def _parse(self, feat: int, p: List[int]):
        percent, charging, conn = None, False, "2.4G"
        if feat == self.F_UNIFIED:
            if len(p) >= 3:
                charging = p[2] in self.ON_CHARGER
            if p and 0 < p[0] <= 100:
                percent = p[0]
        elif feat == self.F_STATUS:
            if p and 0 < p[0] <= 100:
                percent = p[0]
            if len(p) >= 3:
                charging = p[2] in self.ON_CHARGER
        elif feat == self.F_VOLTAGE:
            if len(p) >= 2:
                mv = (p[0] << 8) | p[1]
                if mv >= 2500:
                    percent = self._voltage_to_percent(mv)
                if len(p) >= 3:
                    charging = bool(p[2] & 0x80)
        return percent, charging, conn


# ================================================================ Realtek 推送
class RealtekPushProtocol(Protocol):
    """MCHOSE 等 Realtek 方案：设备周期性推送 report id 0x13，
    负载 XOR 0xFF 混淆，电量在解码后 offset 5。需被动监听。"""
    name = "Realtek 推送"
    priority = 60

    VIDS = (0x5253,)
    USAGE_PAGE = 0xFF01
    REPORT_ID = 0x13
    SUBTYPE = 0x1D
    WATCH = 8.0

    def matches(self, device: DeviceInfo) -> bool:
        if device.vid not in self.VIDS:
            return False
        return any(i.usage_page == self.USAGE_PAGE and i.input_len >= 16
                   for i in device.vendor_collections)

    def query(self, device: DeviceInfo) -> BatteryReading:
        colls = [i for i in device.vendor_collections
                 if i.usage_page == self.USAGE_PAGE and i.input_len >= 16]
        if not colls:
            return BatteryReading(status=ST_UNSUPPORTED, protocol=self.name)
        try:
            dev = HidDevice(colls[0].path)
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        try:
            dev.flush_input()
            t0 = time.time()
            while time.time() - t0 < self.WATCH:
                r = dev.read(colls[0].input_len + 1, 300)
                if not r or len(r) < 16 or r[0] != self.REPORT_ID:
                    continue
                if r[1] != self.SUBTYPE:
                    continue
                dec = bytes(b ^ 0xFF for b in r)
                percent = dec[5]
                wired = len(dec) > 4 and dec[4] == 1
                if 0 <= percent <= 100:
                    return BatteryReading(percent=percent, status=ST_OK,
                                          protocol=self.name,
                                          charging=wired and percent < 100,
                                          connection="USB" if wired else "2.4G")
            return BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="未收到推送")
        except OSError as e:
            return BatteryReading(status=ST_ERROR, protocol=self.name, detail=str(e))
        finally:
            dev.close()


# ================================================================ 通用 HID 电池
class GenericBatteryProtocol(Protocol):
    """标准 HID 电池用法（UsagePage 0x06 / Usage 0x20）。

    Windows 自身也通过此用法在设置里显示电量。支持 feature 报告读取
    与 input 报告监听两种方式。
    """
    name = "标准 HID 电池"
    priority = 40

    def matches(self, device: DeviceInfo) -> bool:
        for i in device.interfaces:
            caps = find_battery_value_caps(i.path)
            if caps:
                return True
        return False

    def query(self, device: DeviceInfo) -> BatteryReading:
        best = None
        for i in device.interfaces:
            caps = find_battery_value_caps(i.path)
            if not caps:
                continue
            try:
                dev = HidDevice(i.path)
            except OSError:
                continue
            try:
                for cap in caps:
                    if cap.report_type == 2:  # feature
                        size = (i.feature_len or 64) + 1
                        buf = dev.get_feature(cap.report_id, size)
                        if buf:
                            p = self._extract(buf, cap)
                            if p is not None:
                                best = BatteryReading(percent=p, status=ST_OK,
                                                      protocol=self.name,
                                                      connection="2.4G")
                                break
                    else:  # input：短监听
                        t0 = time.time()
                        while time.time() - t0 < 3.0:
                            r = dev.read((i.input_len or 32) + 1, 250)
                            if r:
                                p = self._extract(r, cap)
                                if p is not None:
                                    best = BatteryReading(percent=p, status=ST_OK,
                                                          protocol=self.name,
                                                          connection="2.4G")
                                    break
                        if best:
                            break
            except OSError:
                pass
            finally:
                dev.close()
            if best:
                break
        if best:
            return best
        return BatteryReading(status=ST_SLEEPING, protocol=self.name, detail="无电池数据")

    @staticmethod
    def _extract(report: bytes, cap) -> Optional[int]:
        """从报告中按 bit 偏移提取电池值（简化：按字节对齐处理）。"""
        try:
            if cap.bit_size and cap.bit_size % 8 == 0:
                # HidP 未提供 byte offset 时，回退：找 0..100 的字节
                for b in report[1:]:
                    if 0 < b <= 100 and cap.logical_min <= b <= max(cap.logical_max, 100):
                        return b
        except Exception:
            pass
        return None


# ---------------------------------------------------------------- 注册表
PROTOCOLS: List[Protocol] = [
    BeiyingProtocol(),
    EvisionProtocol(),
    Nordic52Protocol(),
    Nordic54Protocol(),
    KeychronProtocol(),
    LogitechHidppProtocol(),
    RealtekPushProtocol(),
    GenericBatteryProtocol(),
]

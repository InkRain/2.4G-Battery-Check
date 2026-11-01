"""引擎数据模型。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from app.hid.core import HidInterfaceInfo

# 设备状态
ST_OK = "ok"                # 正常读到电量
ST_SLEEPING = "sleeping"    # 设备休眠/链路断开（写不进去）
ST_UNSUPPORTED = "unsupported"  # 未识别协议
ST_ERROR = "error"          # 读取失败
ST_NO_API = "no_api"        # 接收器固件未开放电量接口（可写通道存在但无电量数据）

KIND_LABELS = {
    "keyboard": "键盘",
    "mouse": "鼠标",
    "headset": "耳机",
    "controller": "手柄",
    "other": "设备",
}


@dataclass
class DeviceInfo:
    """一个物理设备（同一 VID/PID 的多个 HID 接口合并）。"""
    key: str                       # "391D:2A02"
    vid: int
    pid: int
    dongle_name: str = ""          # 产品字符串，如 "VGN S99 2.4G Dongle"
    interfaces: List[HidInterfaceInfo] = field(default_factory=list)
    kind: str = "other"

    @property
    def vendor_collections(self) -> List[HidInterfaceInfo]:
        return [i for i in self.interfaces if i.is_vendor_collection]

    @property
    def display_name(self) -> str:
        return self.dongle_name or f"{self.key} 设备"

    def pick_collection(self, usage_page: int = None, usage: int = None,
                        min_output: int = 0, min_input: int = 0,
                        prefer_output: bool = False) -> Optional[HidInterfaceInfo]:
        """按条件挑选最合适的厂商集合。"""
        cands = self.vendor_collections
        if usage_page is not None:
            exact = [i for i in cands if i.usage_page == usage_page
                     and (usage is None or i.usage == usage)]
            if exact:
                cands = exact
        if min_output:
            with_out = [i for i in cands if i.output_len >= min_output]
            if with_out:
                cands = with_out
        if min_input and not prefer_output:
            with_in = [i for i in cands if i.input_len >= min_input]
            if with_in:
                cands = with_in
        if not cands:
            return None
        # 优先 output 最大的
        cands.sort(key=lambda i: (i.output_len, i.input_len), reverse=True)
        return cands[0]


@dataclass
class BatteryReading:
    """一次电量读取结果。"""
    percent: Optional[int] = None
    charging: bool = False
    full: bool = False
    status: str = ST_OK
    protocol: str = ""
    connection: str = "2.4G"       # 2.4G / USB / 蓝牙
    detail: str = ""               # 附加信息（电压等）
    ts: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.status == ST_OK and self.percent is not None


# ---------------------------------------------------------------- 设备识别
# 已知 VGN / 常见设备型号表（PID -> 名称/类型）
KNOWN_DEVICES = {
    # VGN 键盘（Evision 方案）
    (0x320F, 0x5088): ("VGN S99 2.4G Dongle", "keyboard"),
    (0x320F, 0x5055): ("VGN S99 有线", "keyboard"),
    # VGN 鼠标（Compx/Nordic 方案）
    (0x3554, 0xF503): ("VGN F1 Pro 接收器", "mouse"),
    (0x3554, 0xF502): ("VGN F1 Pro 有线", "mouse"),
    (0x3554, 0xFB3E): ("VGN F2 Pro Max 接收器", "mouse"),
    (0x3554, 0xFB3D): ("VGN F2 Pro Max 有线", "mouse"),
    (0x3554, 0xFB49): ("VGN 蜻蜓 F2 Ultra+ 接收器", "mouse"),
    (0x3554, 0xF58A): ("VXE R1 Pro Max 接收器", "mouse"),
    (0x3554, 0xF58E): ("VXE R1 SE+ 接收器", "mouse"),
    # VGN 蜻蜓系列（391D）
    (0x391D, 0x1A05): ("Dragonfly 3 Master+ 2.4G Dongle", "mouse"),
    # VGN V108 键盘（391D）
    (0x391D, 0x2A02): ("VGN V108 2.4G Dongle", "keyboard"),
    # Keychron
    (0x3434, 0xD028): ("Keychron Ultra-Link 8K 接收器", "keyboard"),
    (0x3434, 0xD048): ("Keychron M5", "keyboard"),
    # 金运 KINYO GX-01 2.4G 耳机（THI Headphone）
    (0x4C4A, 0x4155): ("金运 GX-01 2.4G 耳机", "headset"),
    # 罗技 Lightspeed（示例）
    (0x046D, 0xC547): ("Logitech USB Receiver", "mouse"),
}

VENDOR_NAMES = {
    0x320F: "VGN",
    0x3554: "VGN/VXE",
    0x391D: "VGN",
    0x373B: "ATK/VXE",
    0x3434: "Keychron",
    0x046D: "Logitech",
    0x260D: "Dareu",
    0x33E4: "G-Wolves",
    0x4C4A: "金运 KINYO",
}


def guess_kind(device: DeviceInfo) -> str:
    """判断设备类型。

    坑：2.4G 接收器几乎都是复合设备，同一份描述符里同时挂着键盘接口
    （0x01:0x06）和鼠标接口（0x01:0x02），且两者的先后顺序由固件决定、
    并不固定。VGN V108 键盘和 Dragonfly 鼠标都出现过这种情况：

    - 早期实现「取第一个命中的 0x01 接口」→ V108 先命中鼠标接口，被判成鼠标，
      于是和真鼠标归成同一类，托盘按类合并后只剩一个图标（键盘图标消失）。
    - 改成「有键盘接口就算键盘」→ 反过来把 Dragonfly 判成了键盘。

    所以这里有明确的判据顺序：型号表 → 产品名关键词 → 接口能力兜底。
    """
    known = KNOWN_DEVICES.get((device.vid, device.pid))
    if known:
        return known[1]

    name = (device.dongle_name or "").lower()
    for words, kind in (
        (("headset", "headphone", "earbud", "耳机"), "headset"),
        (("keyboard", "键盘"), "keyboard"),
        (("mouse", "鼠标"), "mouse"),
    ):
        if any(w in name for w in words):
            return kind

    usages = {(i.usage_page, i.usage) for i in device.interfaces}
    if (0x01, 0x06) in usages:
        return "keyboard"
    if (0x01, 0x02) in usages:
        return "mouse"
    return "other"


def friendly_name(device: DeviceInfo) -> str:
    """设备的显示名称。"""
    name = (device.dongle_name or "").strip()
    if name:
        return name
    known = KNOWN_DEVICES.get((device.vid, device.pid))
    if known:
        return known[0]
    vendor = VENDOR_NAMES.get(device.vid)
    if vendor:
        return f"{vendor} 设备"
    return f"USB 设备 {device.key}"

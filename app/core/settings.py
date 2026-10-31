"""应用设置持久化（QSettings）。"""
from __future__ import annotations

from PySide6.QtCore import QSettings

REFRESH_OPTIONS = [
    ("15 秒", 15),
    ("30 秒", 30),
    ("1 分钟", 60),
    ("5 分钟", 300),
]

LOW_THRESHOLD_OPTIONS = [10, 20, 30]

THEME_OPTIONS = [
    ("白天", "light"),
    ("夜间", "dark"),
    ("跟随系统", "auto"),
]

APP_ORG = "VGN Battery"
APP_NAME = "2.4G Battery Check"      # QSettings 存储 key（保持兼容，勿改）
APP_TITLE = "外设电量监控"            # 显示名称


class AppSettings:
    def __init__(self):
        self.s = QSettings(APP_ORG, APP_NAME)

    # ---- 刷新间隔 ----
    @property
    def refresh_seconds(self) -> int:
        return int(self.s.value("refresh_seconds", 60))

    @refresh_seconds.setter
    def refresh_seconds(self, v: int):
        self.s.setValue("refresh_seconds", int(v))

    # ---- 主题 ----
    @property
    def theme(self) -> str:
        return str(self.s.value("theme", "light"))

    @theme.setter
    def theme(self, v: str):
        self.s.setValue("theme", v)

    # ---- 开机自启 ----
    @property
    def autostart(self) -> bool:
        return str(self.s.value("autostart", "false")).lower() == "true"

    @autostart.setter
    def autostart(self, v: bool):
        self.s.setValue("autostart", "true" if v else "false")

    # ---- 低电量提醒 ----
    @property
    def low_battery_alert(self) -> bool:
        return str(self.s.value("low_battery_alert", "true")).lower() == "true"

    @low_battery_alert.setter
    def low_battery_alert(self, v: bool):
        self.s.setValue("low_battery_alert", "true" if v else "false")

    # ---- 低电量阈值 ----
    @property
    def low_battery_threshold(self) -> int:
        try:
            return max(1, min(99, int(self.s.value("low_battery_threshold", 20))))
        except (TypeError, ValueError):
            return 20

    @low_battery_threshold.setter
    def low_battery_threshold(self, v: int):
        self.s.setValue("low_battery_threshold", int(v))

    # ---- 托盘图标显示电量数字 ----
    @property
    def tray_show_percent(self) -> bool:
        return str(self.s.value("tray_show_percent", "false")).lower() == "true"

    @tray_show_percent.setter
    def tray_show_percent(self, v: bool):
        self.s.setValue("tray_show_percent", "true" if v else "false")

    # ---- 游戏模式：按进程屏蔽 Win 键 ----
    @property
    def winkey_block(self) -> bool:
        return str(self.s.value("winkey_block", "false")).lower() == "true"

    @winkey_block.setter
    def winkey_block(self, v: bool):
        self.s.setValue("winkey_block", "true" if v else "false")

    @property
    def winkey_processes(self) -> list:
        raw = self.s.value("winkey_processes", "")
        if not raw:
            return []
        try:
            import json
            data = json.loads(str(raw))
            return [str(x) for x in data] if isinstance(data, list) else []
        except Exception:
            return []

    @winkey_processes.setter
    def winkey_processes(self, v: list):
        import json
        self.s.setValue("winkey_processes",
                        json.dumps([str(x) for x in (v or [])], ensure_ascii=False))

    # ---- 设备自定义名称 {device_key: name} ----
    @property
    def custom_names(self) -> dict:
        raw = self.s.value("custom_names", "")
        if not raw:
            return {}
        try:
            import json
            data = json.loads(str(raw))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @custom_names.setter
    def custom_names(self, v: dict):
        import json
        self.s.setValue("custom_names", json.dumps(v, ensure_ascii=False))

    def set_custom_name(self, key: str, name: str):
        names = self.custom_names
        name = (name or "").strip()
        if name:
            names[key] = name
        else:
            names.pop(key, None)
        self.custom_names = names

    def display_name(self, key: str, fallback: str) -> str:
        return self.custom_names.get(key) or fallback

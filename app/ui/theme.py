"""主题与配色（浅色 / 深色 / 跟随系统）。"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_AUTO = "auto"


def system_is_dark() -> bool:
    """读取 Windows 注册表判断系统深色模式。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return val == 0
    except Exception:
        return False


def resolve_theme(setting: str) -> str:
    if setting == THEME_AUTO:
        return THEME_DARK if system_is_dark() else THEME_LIGHT
    return setting


class Theme:
    """一套完整的界面颜色（液态玻璃风格：背景带 alpha，叠 DWM 亚克力）。"""

    def __init__(self, name: str):
        self.name = name
        if name == THEME_DARK:
            self.window_bg = QColor("#1F1F1F")
            self.glass_bg = QColor(26, 26, 30, 205)
            self.glass_sheen = QColor(255, 255, 255, 16)
            self.glass_border = QColor(255, 255, 255, 36)
            self.card_bg = QColor(255, 255, 255, 18)
            self.card_bg_solid = QColor("#2D2D2D")
            self.card_border = QColor(255, 255, 255, 30)
            self.panel_bg = QColor("#282828")
            self.text = QColor("#F0F0F0")
            self.text_dim = QColor("#9E9E9E")
            self.text_faint = QColor("#757575")
            self.btn_bg = QColor(255, 255, 255, 22)
            self.btn_hover = QColor(255, 255, 255, 40)
            self.btn_text = QColor("#E8E8E8")
            self.hover_shadow = QColor(0, 0, 0, 90)
            self.tray_bg = QColor(30, 30, 34, 215)
            self.tray_border = QColor(255, 255, 255, 34)
            self.divider = QColor(255, 255, 255, 26)
        else:
            self.window_bg = QColor("#F3F3F3")
            self.glass_bg = QColor(250, 250, 252, 196)
            self.glass_sheen = QColor(255, 255, 255, 130)
            self.glass_border = QColor(255, 255, 255, 170)
            self.card_bg = QColor(255, 255, 255, 150)
            self.card_bg_solid = QColor("#FFFFFF")
            self.card_border = QColor(255, 255, 255, 200)
            self.panel_bg = QColor("#FAFAFA")
            self.text = QColor("#1B1B1B")
            self.text_dim = QColor("#5F5F5F")
            self.text_faint = QColor("#8A8A8A")
            self.btn_bg = QColor(255, 255, 255, 140)
            self.btn_hover = QColor(255, 255, 255, 220)
            self.btn_text = QColor("#333333")
            self.hover_shadow = QColor(0, 0, 0, 28)
            self.tray_bg = QColor(250, 250, 252, 210)
            self.tray_border = QColor(255, 255, 255, 170)
            self.divider = QColor(30, 30, 30, 22)

        # 电量颜色（两个主题一致）
        self.batt_ok = QColor("#2FA84F" if name == THEME_LIGHT else "#3CB65C")
        self.batt_warn = QColor("#E8A33D")
        self.batt_low = QColor("#D64545")
        self.batt_unknown = QColor("#B0B0B0")
        self.accent = QColor("#0F7B0F")
        self.low_threshold = 20   # 可由设置覆盖（颜色分级与报警用同一定值）

    def battery_color(self, percent, status: str = "ok") -> QColor:
        if status != "ok" or percent is None:
            return self.batt_unknown
        if percent >= 50:
            return self.batt_ok
        if percent >= self.low_threshold:
            return self.batt_warn
        return self.batt_low

    def _c(self, color: QColor) -> str:
        """带 alpha 的颜色串（半透明色 name() 会丢 alpha 变纯色）。"""
        return color.name(QColor.HexArgb)

    def stylesheet(self) -> str:
        return f"""
        QWidget {{ color: {self.text.name()}; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
        QToolTip {{ color: {self.text.name()}; background: {self._c(self.card_bg_solid)};
                   border: 1px solid {self._c(self.card_border)}; padding: 4px; }}
        QComboBox {{ background: {self._c(self.btn_bg)}; color: {self.btn_text.name()};
                    border: 1px solid {self._c(self.card_border)}; border-radius: 4px;
                    padding: 3px 8px; min-width: 72px; }}
        QComboBox:hover {{ background: {self._c(self.btn_hover)}; }}
        QComboBox::drop-down {{ border: none; width: 16px; }}
        QComboBox QAbstractItemView {{ background: {self._c(self.card_bg_solid)};
                    color: {self.text.name()}; border: 1px solid {self._c(self.card_border)};
                    selection-background-color: {self._c(self.btn_hover)}; }}
        QCheckBox {{ spacing: 6px; }}
        QPushButton {{ background: {self._c(self.btn_bg)}; color: {self.btn_text.name()};
                    border: 1px solid {self._c(self.card_border)}; border-radius: 6px;
                    padding: 5px 14px; }}
        QPushButton:hover {{ background: {self._c(self.btn_hover)}; }}
        QSpinBox {{ background: {self._c(self.btn_bg)}; color: {self.btn_text.name()};
                   border: 1px solid {self._c(self.card_border)}; border-radius: 4px; }}
        """

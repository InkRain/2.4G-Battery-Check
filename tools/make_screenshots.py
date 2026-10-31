"""生成 README / docs 用的界面截图（演示数据）。

特点：
- 使用临时 ini 作为设置存储，不污染用户真实配置；
- 屏蔽开机自启相关读写，绝不改注册表；
- 不启动扫描线程、不装键盘钩子，纯渲染，产物直接写 docs/。

用法：python tools/make_screenshots.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DOCS = os.path.join(ROOT, "docs")

# ---------------------------------------------------------------- 保护：先打补丁再导入 UI
import app.core.autostart as _autostart  # noqa: E402

_autostart.is_enabled = lambda: True          # 设置面板显示"开"（用户机器上确实是开的）
_autostart.set_enabled = lambda enabled: True  # 不写注册表
_autostart.sync_path = lambda: False           # 不自愈改写注册表

from PySide6.QtCore import QRectF, QSettings, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app.core.settings import AppSettings  # noqa: E402
from app.engine.models import (BatteryReading, DeviceInfo, ST_OK,  # noqa: E402
                               ST_SLEEPING)
from app.engine.scanner import DeviceState  # noqa: E402
from app.ui import main_window as _mw  # noqa: E402

_mw.autostart_enabled = lambda: True    # 模块级导入已发生，重新绑定


class DemoSettings(AppSettings):
    """设置写到临时 ini，避免动到用户真实的 QSettings 配置。"""

    def __init__(self, path: str):
        self.s = QSettings(path, QSettings.IniFormat)

    def display_name(self, key: str, fallback: str) -> str:
        return self.custom_names.get(key) or fallback


def _state(name: str, key: str, kind: str, percent, charging=False,
           status=ST_OK, conn="2.4G") -> DeviceState:
    vid, pid = (int(x, 16) for x in key.split(":"))
    info = DeviceInfo(key=key, vid=vid, pid=pid, dongle_name=name, kind=kind)
    st = DeviceState(info)
    st.display_name = name
    st.reading = BatteryReading(percent=percent, status=status, protocol="演示",
                                charging=charging, connection=conn)
    return st


def demo_states(charging: bool = False) -> list[DeviceState]:
    """与实机截图同一对设备，保证 README 里几张图观感一致。"""
    return [
        _state("VGN V108 2.4G Dongle", "391D:2A02", "keyboard", 99),
        _state("Dragonfly 3 Master+", "391D:1A05", "mouse",
               100 if charging else 80, charging=charging),
    ]


def on_backdrop(pm: QPixmap, pad: int = 18, radius: int = 20, dark: bool = False) -> QImage:
    """把带透明边角的窗口贴到柔和渐变底上，深色/浅色看图都清楚。

    注意：窗口本身是半透明玻璃（依赖桌面透出来），grab() 拿到的是带 alpha 的图，
    直接存 PNG 会被看图软件用白底合成，深色主题会变成"白底浅字"，所以必须自己铺底。
    另外高 DPI 下 grab() 是物理像素、devicePixelRatio=2，这里按源尺寸 1:1 贴。
    """
    w, h = pm.width() + pad * 2, pm.height() + pad * 2
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    grad = QLinearGradient(0, 0, w, h)
    if dark:
        grad.setColorAt(0.0, QColor("#24272E"))
        grad.setColorAt(0.5, QColor("#1B1E24"))
        grad.setColorAt(1.0, QColor("#2A2230"))
    else:
        grad.setColorAt(0.0, QColor("#EEF1F6"))
        grad.setColorAt(0.5, QColor("#E3E8F1"))
        grad.setColorAt(1.0, QColor("#EAE7F2"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(0, 0, w, h, radius, radius)
    p.drawPixmap(QRectF(pad, pad, pm.width(), pm.height()), pm, QRectF(pm.rect()))
    p.end()
    return img


def save(widget: QWidget, name: str, backdrop: bool = True, dark: bool = False):
    pm = widget.grab()
    path = os.path.join(DOCS, name)
    if backdrop:
        on_backdrop(pm, dark=dark).save(path)
    else:
        pm.save(path)
    print(f"  {name}  {pm.width()}x{pm.height()}")


def main() -> int:
    os.makedirs(DOCS, exist_ok=True)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)

    def make_settings(name: str, theme: str) -> "DemoSettings":
        ini = os.path.join(os.environ.get("TEMP", ROOT), name)
        if os.path.exists(ini):
            os.remove(ini)
        s = DemoSettings(ini)
        s.theme = theme
        s.autostart = True
        s.low_battery_alert = True
        s.low_battery_threshold = 20
        s.refresh_seconds = 60
        # 让设置面板展示"屏蔽 Win 键"这项新功能
        s.winkey_block = True
        s.winkey_processes = ["cs2.exe", "VALORANT-Win64-Shipping.exe"]
        return s

    from app.ui.app import BatteryApp

    # 深浅两套各自独立建实例：切主题后立刻 grab 容易抓到未重绘的残影
    light = BatteryApp(make_settings("wbshot_light.ini", "light"))
    dark = BatteryApp(make_settings("wbshot_dark.ini", "dark"))
    for a, off in ((light, 120), (dark, 820)):
        a.window.move(off, 120)
        a.window.show()
        a._on_states(demo_states())

    def step_light_main():
        print("浅色主界面")
        save(light.window, "screenshot_main_light.png")
        save(light.window, "theme_light.png")

    def step_popup_light():
        print("托盘面板（浅色）")
        light.popup.update_states(light._last_states)
        light.popup.show()
        QTimer.singleShot(220, lambda: (save(light.popup, "screenshot_popup.png"),
                                        light.popup.close()))

    def step_toast():
        print("低电量提醒")
        from app.ui.toast import Toast
        t = Toast.notify(light.window.theme, "低电量提醒",
                         "Dragonfly 3 Master+ 电量仅剩 15%，请及时充电",
                         QColor("#D64545"))
        QTimer.singleShot(200, lambda: (save(t, "screenshot_toast.png"), t.close()))

    def step_charging():
        print("充电中")
        light._on_states(demo_states(charging=True))
        QTimer.singleShot(200, lambda: save(light.window, "screenshot_charging.png"))

    def step_dark():
        print("夜间主界面")
        save(dark.window, "screenshot_main_dark.png", dark=True)
        save(dark.window, "theme_dark.png", dark=True)

    def step_glass():
        print("托盘面板（夜间玻璃）")
        dark.popup.update_states(dark._last_states)
        dark.popup.show()
        QTimer.singleShot(220, lambda: (save(dark.popup, "screenshot_glass.png", dark=True),
                                        dark.popup.close()))

    def step_tray_icons():
        print("托盘图标")
        from app.ui.app import _make_kind_icon
        for name, kind, pct, chg, text in [
            ("tray_kb.png", "keyboard", 99, False, False),
            ("tray_kb_num.png", "keyboard", 99, False, True),
            ("tray_mouse.png", "mouse", 80, False, False),
            ("tray_mouse_num.png", "mouse", 80, False, True),
            ("tray_charging.png", "mouse", 80, True, False),
        ]:
            _make_kind_icon(kind, pct, chg, False, text).pixmap(64, 64).save(
                os.path.join(DOCS, name))
        print("  tray_*.png done")

    steps = [step_light_main, step_dark, step_popup_light, step_toast,
             step_charging, step_glass, step_tray_icons]
    idx = {"i": 0}

    def tick():
        if idx["i"] >= len(steps):
            print("ALL SCREENSHOTS SAVED")
            for a in (light, dark):
                a.scanner.stop()
            qt.quit()
            return
        fn = steps[idx["i"]]
        idx["i"] += 1
        try:
            fn()
        except Exception as exc:  # 单步失败不影响其它图
            print(f"  !! {fn.__name__} 失败: {exc}")
        QTimer.singleShot(800, tick)

    QTimer.singleShot(900, tick)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())

"""验证托盘图标颜色：设备休眠时仍应按真实电量显示彩色环，不能变灰。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _testenv  # noqa: 备份/还原真实自启项，避免测试改写注册表

from PySide6.QtWidgets import QApplication

from app.core.settings import AppSettings
from app.engine.models import BatteryReading, DeviceInfo, ST_OK, ST_SLEEPING
from app.engine.scanner import DeviceState
from app.ui.app import BatteryApp


def make_state(key, kind, status, pct):
    vid, pid = key.split(":")
    info = DeviceInfo(key=key, vid=int(vid, 16), pid=int(pid, 16), kind=kind,
                      dongle_name=f"{kind}-test")
    st = DeviceState(info)
    st.reading = BatteryReading(percent=pct, status=status, protocol="test")
    return st


def green_pixels(icon, size=32):
    """统计图标里的绿色像素数量（电量环颜色 #2FA84F 附近）。"""
    img = icon.pixmap(size, size).toImage()
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 40:
                continue
            if c.green() > 110 and c.green() > c.red() + 45 and c.green() > c.blue() + 45:
                n += 1
    return n


def gray_pixels(icon, size=32):
    """统计中性灰像素（说明环被画成了灰色）。"""
    img = icon.pixmap(size, size).toImage()
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 40:
                continue
            r, g, b = c.red(), c.green(), c.blue()
            if max(r, g, b) - min(r, g, b) < 12 and 110 < r < 200:
                n += 1
    return n


app = QApplication.instance() or QApplication(sys.argv)
settings = AppSettings()
ba = BatteryApp(settings)

# ---- 场景 1：两个设备都休眠，但保留着上次电量（用户截图的情况）----
states = [make_state("391D:2A02", "keyboard", ST_SLEEPING, 99),
          make_state("391D:1A05", "mouse", ST_SLEEPING, 100)]
ba._sync_tray_icons(states)

k_tray = ba.kind_trays.get("keyboard")
m_tray = ba.kind_trays.get("mouse")
assert k_tray is not None and m_tray is not None, "键盘/鼠标托盘图标未创建"

k_green = green_pixels(k_tray.icon())
m_green = green_pixels(m_tray.icon())
print(f"[休眠] 键盘图标绿色像素={k_green}  鼠标图标绿色像素={m_green}")
assert k_green > 30, "休眠时键盘托盘环变灰了！"
assert m_green > 30, "休眠时鼠标托盘环变灰了！"
print("[OK ] 休眠时托盘仍显示彩色（绿色）电量环")

# ---- 场景 2：在线设备不能被同类的休眠设备覆盖 ----
states = [make_state("391D:2A02", "keyboard", ST_OK, 80),
          make_state("391D:2A02B", "keyboard", ST_SLEEPING, 5)]
ba._sync_tray_icons(states)
img = ba.kind_trays["keyboard"].icon().pixmap(32, 32).toImage()
# 80% 应为绿色；若被休眠的 5% 覆盖会变成红色
red = sum(1 for y in range(img.height()) for x in range(img.width())
          if (c := img.pixelColor(x, y)).alpha() > 40
          and c.red() > 150 and c.green() < 110)
print(f"[在线优先] 红色像素={red}（若被休眠的 5% 覆盖会明显变红）")
assert green_pixels(ba.kind_trays["keyboard"].icon()) > 10, "在线设备未被优先采用"
print("[OK ] 在线设备优先于同类的休眠设备")

# ---- 场景 3：完全无电量信息（固件未开放）仍为灰色 ----
states = [make_state("391D:FFFF", "headset", "no_api", None)]
ba._sync_tray_icons(states)
h_tray = ba.kind_trays.get("headset")
assert h_tray is not None
print(f"[无数据] 灰色像素={gray_pixels(h_tray.icon())}  绿色像素={green_pixels(h_tray.icon())}")
assert green_pixels(h_tray.icon()) < 10, "无电量信息时不该画彩色环"
print("[OK ] 真正无电量信息时仍保持灰色")

print("\n全部通过 ✅")

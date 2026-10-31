"""复现：设置面板分段按钮消失 / 卡片被截断。打印各关键控件几何。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _testenv  # noqa: 备份/还原真实自启项，避免测试改写注册表
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from app.core.settings import AppSettings
from app.engine.models import BatteryReading, DeviceInfo
from app.engine.scanner import DeviceState
from app.ui.main_window import MainWindow

app = QApplication([])
settings = AppSettings()
win = MainWindow(settings, "light")

demo = [
    ("391D:2A02", "VGN V108 2.4G Dongle", "keyboard", 78, "2.4G"),
    ("391D:1A05", "Dragonfly 3 Master+", "mouse", 94, "2.4G"),
]
states = []
for key, name, kind, pct, conn in demo:
    info = DeviceInfo(key=key, vid=int(key[:4], 16), pid=int(key[5:], 16),
                      dongle_name=name, kind=kind)
    st = DeviceState(info)
    st.reading = BatteryReading(percent=pct, status="ok", protocol="demo", connection=conn)
    states.append(st)

win.show()
win.update_devices(states)
for _ in range(5):
    app.processEvents()

def dump():
    print("== 窗口 ==", win.width(), "x", win.height(), "  min:", win.minimumHeight(),
          " user_resized:", win._user_resized)
    print("== 屏幕可用高 ==", win.screen().availableGeometry().height())
    print("== content sizeHint ==", win._content.sizeHint())
    panel = win.findChild(QWidget, "settingsPanel")
    print("== panel ==", panel.geometry(), " sizeHint:", panel.sizeHint())
    for nm in ("seg_refresh", "seg_alert", "seg_low", "seg_autostart", "seg_theme"):
        w = getattr(win, nm, None)
        print(f"   {nm}: visible={w.isVisible()} geom={w.geometry()} hint={w.sizeHint()}")
    for i, card in enumerate(win._cards.values()):
        print(f"   card{i}: geom={card.geometry()}")
    print("== cards_host ==", win.cards_host.geometry(), " hint:", win.cards_host.sizeHint())

dump()
print("A height:", win.height())
print("content minimumSizeHint:", win._content.minimumSizeHint(), " minimumHeight:", win._content.minimumHeight())
print("scroll viewport:", win._scroll.viewport().size(), " scrollbarVisible:", win._scroll.verticalScrollBar().isVisible())
pm = win.grab()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repro.png")
pm.save(out)
print("saved", out)

# 再模拟一次 DPI 放大后重新布局
os.environ["QT_SCALE_FACTOR"] = "1.0"

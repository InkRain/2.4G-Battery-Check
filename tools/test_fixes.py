"""回归验证：窗口高度自适应 + 设置面板完整可见 + 托盘弹窗贴任务栏。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])

# ---- 1) 主窗口：真实流程（伪造设备状态 → update_devices）----
from app.core.settings import AppSettings
from app.engine.models import BatteryReading, DeviceInfo
from app.engine.scanner import DeviceState
from app.ui.main_window import MainWindow

settings = AppSettings()
win = MainWindow(settings, "light")
win.show()

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
win.update_devices(states)
for _ in range(5):
    app.processEvents()

content_h = win._content.sizeHint().height()
needed = 56 + content_h
panel = win.findChild(QWidget, "settingsPanel")
panel_bottom = panel.y() + panel.height()
seg_heights = [getattr(win, n).height() for n in
               ("seg_refresh", "seg_alert", "seg_low", "seg_autostart", "seg_theme")]
print(f"[主窗口] 窗口={win.width()}x{win.height()}  内容高={content_h}  needed={needed}")
print(f"[主窗口] 设置面板 bottom={panel_bottom}（窗口高={win.height()}）  分段按钮高度={seg_heights}")

assert win.height() >= needed - 8, f"窗口高度不足: {win.height()} < {needed}"
assert panel_bottom <= win.height() + 2, "设置面板被裁切!"
assert all(h >= 20 for h in seg_heights), f"分段按钮被压扁: {seg_heights}"
print("[主窗口] OK：设置面板与分段按钮完整可见")

# ---- 2) 屏幕过矮时：内容不压扁，出滚动条 ----
win._scroll.setFixedHeight(300)   # 模拟矮窗口
app.processEvents()
print(f"[矮窗口] 内容 minimumHeight={win._content.minimumHeight()}"
      f"  滚动条可见={win._scroll.verticalScrollBar().isVisible()}")
assert win._content.minimumHeight() >= 550, "内容最小高度未锁定，会被压扁"
win._scroll.setFixedHeight(16777215)  # 还原
for _ in range(3):
    app.processEvents()

# ---- 3) 托盘弹窗贴任务栏 ----
from app.ui.tray_popup import TrayPopup
from app.ui.theme import Theme

popup = TrayPopup(Theme("dark"))
popup.setFixedWidth(312)
popup.setFixedHeight(200)
popup._anchor()
avail = QApplication.primaryScreen().availableGeometry()
gap = avail.bottom() - (popup.y() + popup.height())
print(f"[托盘] 任务栏上沿={avail.bottom()}  弹窗底={popup.y()+popup.height()}  间隙={gap}px")
assert gap <= 8, f"托盘弹窗未贴合任务栏（间隙 {gap}px）"
assert (popup.x() + popup.width()) <= avail.right() + 1, "弹窗超出右边界"
print("[托盘] OK：弹窗紧贴任务栏")

print("\n全部回归通过 ✅")

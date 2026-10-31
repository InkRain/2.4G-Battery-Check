"""UI 验证：演示模式下抓取主窗口与托盘弹窗截图。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication

from app.core.settings import AppSettings
from app.engine.models import BatteryReading, DeviceInfo
from app.engine.scanner import DeviceState
from app.ui.app import BatteryApp


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    settings = AppSettings()
    app = BatteryApp(settings)

    demo = [
        ("320F:5088", "VGN S99 2.4G Dongle", "keyboard", 78, "2.4G"),
        ("046D:C547", "Logitech Pro X Superlight", "mouse", 94, "2.4G"),
    ]
    states = []
    for key, name, kind, pct, conn in demo:
        info = DeviceInfo(key=key, vid=int(key[:4], 16), pid=int(key[5:], 16),
                          dongle_name=name, kind=kind)
        st = DeviceState(info)
        st.reading = BatteryReading(percent=pct, status="ok", protocol="演示",
                                    connection=conn)
        states.append(st)
    app._on_states(states)
    app.scanner.stop()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(out_dir, exist_ok=True)

    def grab_all():
        app.window.show()
        app.window.raise_()
        pm = app.window.grab()
        pm.save(os.path.join(out_dir, "screenshot_main_light.png"))
        # 深色主题
        app.apply_theme("dark")
        QTimer.singleShot(300, grab_dark)

    def grab_dark():
        pm = app.window.grab()
        pm.save(os.path.join(out_dir, "screenshot_main_dark.png"))
        # 托盘弹窗
        app.popup.update_states(states)
        app.popup.show()
        QTimer.singleShot(300, grab_popup)

    def grab_popup():
        pm = app.popup.grab()
        pm.save(os.path.join(out_dir, "screenshot_popup.png"))
        print("SCREENSHOTS SAVED")
        qt.quit()

    QTimer.singleShot(800, grab_all)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())

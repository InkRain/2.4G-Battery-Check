"""验证新版 UI：玻璃窗口/托盘多图标/弹窗/toast。"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.core.settings import AppSettings
from app.ui.app import BatteryApp
from app.ui.toast import Toast

def main():
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    settings = AppSettings()
    app = BatteryApp(settings)
    app.run()

    def fake():
        from app.engine.models import DeviceInfo, BatteryReading, ST_OK
        from app.engine.scanner import DeviceState
        states = []
        for key, name, kind, pct, chg in [
            ("391D:2A02", "VGN V108", "keyboard", 18, False),
            ("391D:1005", "Dragonfly 3 Master+", "mouse", 100, True)]:
            info = DeviceInfo(key=key, vid=0x391D, pid=0x2A02, dongle_name=name, kind=kind)
            st = DeviceState(info)
            st.display_name = name
            st.reading = BatteryReading(percent=pct, status=ST_OK, protocol="mock",
                                        charging=chg,
                                        connection="USB" if chg else "2.4G", detail="")
            states.append(st)
        app._on_states(states)

    def shot():
        app.window.show()
        app.window.raise_()
        app.window.grab().save(os.path.join(ROOT, "docs", "screenshot_glass.png"))
        for name, kind, pct, chg, num in [
            ("tray_kb.png", "keyboard", 18, False, False),
            ("tray_mouse.png", "mouse", 100, True, False),
            ("tray_kb_num.png", "keyboard", 18, False, True),
            ("tray_mouse_num.png", "mouse", 100, True, True)]:
            from app.ui.app import _make_kind_icon
            _make_kind_icon(kind, pct, chg, False, num).pixmap(64, 64).save(
                os.path.join(ROOT, "docs", name))
        app.popup.show()
        QTimer.singleShot(600, shot2)

    def shot2():
        app.popup.grab().save(os.path.join(ROOT, "docs", "screenshot_popup.png"))
        Toast.notify(app.window.theme, "低电量提醒", "VGN V108 电量仅剩 18%，请及时充电",
                   app.window.theme.batt_low)
        QTimer.singleShot(800, grab_toast)

    def grab_toast():
        from app.ui import toast as toast_mod
        if toast_mod._active:
            toast_mod._active[0].grab().save(os.path.join(ROOT, "docs", "screenshot_toast.png"))
        print("ALL SAVED")
        qt.quit()

    QTimer.singleShot(400, fake)
    QTimer.singleShot(900, shot)
    return qt.exec()

if __name__ == "__main__":
    sys.exit(main())

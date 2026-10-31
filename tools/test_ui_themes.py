"""浅色/夜间两套主题截图验证。"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.core.settings import AppSettings
from app.ui.app import BatteryApp

def make_app(theme):
    settings = AppSettings()
    settings.theme = theme
    app = BatteryApp(settings)
    app.run()
    return app

def inject(app):
    from app.engine.models import DeviceInfo, BatteryReading, ST_OK
    from app.engine.scanner import DeviceState
    states = []
    for key, name, kind, pct, chg in [
        ("391D:2A02", "VGN V108 2.4G Dongle", "keyboard", 99, False),
        ("391D:1A05", "Dragonfly 3 Master+", "mouse", 100, False)]:
        info = DeviceInfo(key=key, vid=0x391D, pid=0x2A02, dongle_name=name, kind=kind)
        st = DeviceState(info)
        st.display_name = name
        st.reading = BatteryReading(percent=pct, status=ST_OK, protocol="mock",
                                    charging=chg, connection="2.4G", detail="")
        states.append(st)
    app._on_states(states)

def main():
    qt = QApplication(sys.argv)
    results = {}
    apps = {}
    for theme in ("light", "dark"):
        a = make_app(theme)
        apps[theme] = a
        inject(a)
        a.window.show()
    def grab():
        for theme, a in apps.items():
            a.window.grab().save(os.path.join(ROOT, "docs", f"theme_{theme}.png"))
        print("THEMES SAVED")
        qt.quit()
    QTimer.singleShot(800, grab)
    return qt.exec()

if __name__ == "__main__":
    sys.exit(main())

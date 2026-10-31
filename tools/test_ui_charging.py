"""模拟充电状态，验证主窗口/卡片/托盘的充电显示。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.settings import AppSettings
from app.engine.models import BatteryReading, ST_OK
from app.engine.scanner import DeviceState
from app.ui.app import BatteryApp, _make_tray_icon
from app.ui.theme import resolve_theme


def main():
    qt = QApplication(sys.argv)
    settings = AppSettings()
    app = BatteryApp(settings)
    app.run()

    # 构造充电中的假数据
    def fake_states():
        from app.engine.models import DeviceInfo
        infos = [
            ("391D:2A02", 0x391D, 0x2A02, "VGN V108 2.4G Dongle", "keyboard", 65, True),
            ("391D:1A05", 0x391D, 0x1A05, "Dragonfly 3 Master+", "mouse", 88, True),
            ("4C4A:4155", 0x4C4A, 0x4155, "GX-01", "headset", None, False),
        ]
        out = []
        for key, vid, pid, name, kind, pct, chg in infos:
            info = DeviceInfo(key=key, vid=vid, pid=pid, dongle_name=name, kind=kind)
            st = DeviceState(info)
            if pct is None:
                st.reading = BatteryReading(status="no_api", protocol="—",
                                            connection="USB", detail="设备无电量上报通道")
            else:
                st.reading = BatteryReading(percent=pct, status=ST_OK, protocol="mock",
                                            charging=chg, connection="USB" if chg else "2.4G",
                                            detail="")
            out.append(st)
        return out

    states = fake_states()

    def show():
        app.window.show()
        app.window.raise_()
        app._on_states(states)
        QTimer.singleShot(1200, grab)

    def grab():
        out_dir = os.path.join(ROOT, "docs")
        os.makedirs(out_dir, exist_ok=True)
        app.window.grab().save(os.path.join(out_dir, "screenshot_charging.png"))
        # 托盘图标也导出对比
        icon = _make_tray_icon(65, True, False)
        icon.pixmap(64, 64).save(os.path.join(out_dir, "tray_charging.png"))
        print("CHARGING SCREENSHOT SAVED")
        qt.quit()

    QTimer.singleShot(500, show)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())

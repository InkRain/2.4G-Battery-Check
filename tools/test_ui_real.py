"""真实硬件 UI 验证：运行完整应用，扫描后抓图。"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.settings import AppSettings
from app.ui.app import BatteryApp


def main():
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    settings = AppSettings()
    app = BatteryApp(settings)
    app.run()

    out_dir = os.path.join(ROOT, "docs")

    def grab():
        app.window.show()
        app.window.raise_()
        pm = app.window.grab()
        pm.save(os.path.join(out_dir, "screenshot_real.png"))
        print("REAL SCREENSHOT SAVED")
        qt.quit()

    # 等待两轮扫描（设备无响应时单轮可达 ~12s）
    QTimer.singleShot(26000, grab)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())

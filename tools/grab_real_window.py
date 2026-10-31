"""用源码实例抓一张"实机运行"截图（真实 HID 读数，当前 UI）。

安全措施：
- 全程屏蔽开机自启的注册表写入（只读判定），不会把 Run 项改成 python 路径；
- 不 acquire 单实例锁，不影响已在托盘里跑的那份；
- 抓完直接退出，不驻留。

用法：python tools/grab_real_window.py [输出文件]
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app.core.autostart as _as  # noqa: E402

_as.sync_path = lambda: False
_as.is_enabled = lambda: True
_as.set_enabled = lambda enabled: True

from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui import main_window as _mw  # noqa: E402

_mw.autostart_enabled = lambda: True

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "screenshot_real.png")


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    qt = QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)

    from app.core.settings import AppSettings
    from app.ui.app import BatteryApp

    settings = AppSettings()
    app = BatteryApp(settings)
    app.scanner.interval = 60
    app.scanner.start()
    app.window.show()
    app.window.move(200, 120)

    deadline = time.time() + 25
    shot = {"done": False}

    def poll():
        states = getattr(app, "_last_states", [])
        if states:
            print("设备：", [(getattr(s, "display_name", None) or s.info.dongle_name,
                            s.reading.percent if s.reading else None,
                            s.reading.status if s.reading else None)
                           for s in states])
        # 等到有真实读数（或超时）再抓
        if states and app.window.isVisible():
            QTimer.singleShot(600, grab)
            return
        if time.time() > deadline:
            print("超时：没有等到扫描结果，仍然抓一张")
            grab()
            return
        QTimer.singleShot(500, poll)

    def grab():
        if shot["done"]:
            return
        shot["done"] = True
        pm = app.window.grab()
        # 窗口是半透明玻璃，直接存 PNG 会被看图软件按白底合成，先铺一层浅色底
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from make_screenshots import on_backdrop
        on_backdrop(pm).save(OUT)
        print(f"saved {OUT} {pm.width()}x{pm.height()}")
        app.scanner.stop()
        qt.quit()
    QTimer.singleShot(1200, poll)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())

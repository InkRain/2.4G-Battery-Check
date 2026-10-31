"""2.4G Battery Check — 入口。

用法：
    python main.py          正常启动（托盘 + 主窗口）
    python main.py --tray   静默启动：只驻留托盘，不弹主窗口（开机自启用）
    python main.py --demo   演示模式（模拟设备数据，预览界面）
    python main.py --diag   诊断模式（导出 HID 枚举与协议探测日志）
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)])
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), "2.4GBatteryCheck")
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
        fh.setLevel(logging.DEBUG if debug else logging.WARNING)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass


def sweep_temp_dir():
    """后台清扫单文件版遗留的 _MEI* 解压目录（不阻塞启动）。"""
    try:
        from app.core.temp_cleanup import cleanup_stale_temp_dirs
        n = cleanup_stale_temp_dirs()
        if n:
            logging.getLogger(__name__).info("已清理 %d 个残留临时目录", n)
    except Exception:
        pass


def run_demo():
    """演示模式：不访问真实硬件，展示 UI。"""
    from PySide6.QtWidgets import QApplication
    from app.core.settings import AppSettings
    from app.engine.models import BatteryReading, DeviceInfo
    from app.engine.scanner import DeviceState
    from app.engine import friendly_name
    from app.ui.app import BatteryApp

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
    app.window.show()
    return app.exec()


def run_diag():
    """诊断模式：导出枚举与协议探测结果。"""
    from app.engine.scanner import BatteryScanner
    from app.engine.models import friendly_name

    print("=" * 70)
    print("2.4G Battery Check 诊断报告")
    print("=" * 70)
    scanner = BatteryScanner()
    devices = scanner.enumerate()
    print(f"\n发现 {len(devices)} 个候选设备：\n")
    for dev in devices:
        print(f"[{dev.key}] {friendly_name(dev)} ({dev.kind})")
        print(f"  产品字符串: {dev.dongle_name}")
        for i in dev.interfaces:
            print(f"    接口 {i.usage_page:04X}:{i.usage:04X} in={i.input_len} "
                  f"out={i.output_len} feat={i.feature_len} vendor={i.is_vendor_collection}")
        r = scanner.query_device(dev)
        print(f"  => status={r.status} percent={r.percent} proto={r.protocol} "
              f"detail={r.detail}")
        print()
    print("\n提示：键盘类设备在休眠时会拒绝查询，请先按任意键唤醒后再运行诊断。")
    out = os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), "2.4GBatteryCheck",
                       "diagnostics.txt")
    print(f"\n（完整日志见 {out}）")


def main():
    parser = argparse.ArgumentParser(description="2.4G 外设电量监控")
    parser.add_argument("--demo", action="store_true", help="演示模式")
    parser.add_argument("--diag", action="store_true", help="诊断模式")
    parser.add_argument("--tray", action="store_true",
                        help="静默启动：只驻留托盘，不弹出主窗口（开机自启使用）")
    parser.add_argument("--debug", action="store_true", help="调试日志")
    args = parser.parse_args()
    setup_logging(args.debug)

    # 单文件版会解压到 %TEMP%，异常退出时不会自动清理，这里补一次
    threading.Thread(target=sweep_temp_dir, name="temp-sweep", daemon=True).start()

    if args.diag:
        run_diag()
        return 0
    if args.demo:
        return run_demo()

    from PySide6.QtWidgets import QApplication
    from app.core.settings import AppSettings
    from app.ui.app import BatteryApp

    # 单实例：重复双击会多开托盘图标和扫描线程，只允许跑一份
    from app.core import single_instance
    if not single_instance.acquire():
        # 静默启动（开机自启）时不要弹框打扰，直接退出即可
        if not args.tray:
            single_instance.notify_already_running()
        return 0

    app_qt = QApplication(sys.argv)
    app_qt.setQuitOnLastWindowClosed(False)  # 托盘常驻
    settings = AppSettings()
    controller = BatteryApp(settings, silent=args.tray)
    controller.run()
    return app_qt.exec()


if __name__ == "__main__":
    sys.exit(main())

"""验证开机自启「静默驻留托盘」：

1. 自启命令行带 --tray
2. 旧版（无 --tray）的自启项会被自动升级
3. 静默启动时主窗口保持隐藏，托盘图标正常、首轮不弹低电量 toast
4. 非静默启动仍然显示主窗口
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _testenv  # noqa: 备份/还原真实自启项，避免测试改写注册表
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import winreg
from PySide6.QtWidgets import QApplication

app = QApplication([])

from app.core import autostart
from app.core.settings import AppSettings
from app.ui.app import BatteryApp

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
ok = 0
bad = 0


def check(name, cond, extra=""):
    global ok, bad
    print(("[OK] " if cond else "[FAIL] ") + name + (f"  {extra}" if extra else ""))
    if cond:
        ok += 1
    else:
        bad += 1


def read_raw():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            return winreg.QueryValueEx(k, autostart.APP_REG_NAME)[0]
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(k)
    except Exception:
        return None


def write_raw(value):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    try:
        if value is None:
            try:
                winreg.DeleteValue(k, autostart.APP_REG_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, autostart.APP_REG_NAME, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(k)


saved = read_raw()
print(f"[自启] 原始值 = {saved!r}")
try:
    # ---------- 1) 写入的命令行 ----------
    assert autostart.set_enabled(True)
    val = read_raw()
    check("自启命令行包含 --tray", "--tray" in (val or ""), repr(val))
    check("路径带引号（含空格也能启动）", (val or "").startswith('"'), repr(val))
    check("注册表状态识别为已启用", autostart.is_enabled())

    # ---------- 2) 旧版无参数的自启项自动升级 ----------
    write_raw(autostart._exe_path())          # 旧格式：没有 --tray
    check("旧格式先就位", "--tray" not in (read_raw() or ""))
    changed = autostart.sync_path()
    check("旧格式被自动改写", changed and "--tray" in (read_raw() or ""), repr(read_raw()))
    check("已是新格式时 sync_path 不再改动", autostart.sync_path() is False)

    # ---------- 3) 静默启动：窗口不显示 ----------
    settings = AppSettings()
    ba = BatteryApp(settings, silent=True)
    ba.run()
    app.processEvents()
    check("静默启动后主窗口保持隐藏", not ba.window.isVisible())
    check("托盘图标已挂载", ba.tray.isVisible())
    check("首轮低电量提示被跳过（标记存在）", ba._silent_skip_alert is True)
    ba.scanner.stop()
    ba.winkey.stop()

    # ---------- 4) 普通启动：窗口正常显示 ----------
    ba2 = BatteryApp(settings, silent=False)
    ba2.run()
    app.processEvents()
    check("普通启动会显示主窗口", ba2.window.isVisible())
    check("普通启动不跳过低电量提示", ba2._silent_skip_alert is False)
    ba2.window.close()
    ba2.scanner.stop()
    ba2.winkey.stop()
finally:
    write_raw(saved)
    print(f"[自启] 已还原 = {read_raw()!r}")

print(f"\n通过 {ok} 项，失败 {bad} 项")
sys.exit(0 if bad == 0 else 1)

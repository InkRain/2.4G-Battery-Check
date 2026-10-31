"""新功能验证：开机自启 + 按进程屏蔽 Win 键 + 新增设置行布局。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _testenv  # noqa: 备份/还原真实自启项，避免测试改写注册表
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])

# ============ 1) 开机自启：注册表往返 ============
# 注意：必须备份注册表**原始值**再测，结束时原样写回。
# 不能用 is_enabled() 判断"原来是否开启"——源码运行时它会比对路径，
# 与打包 exe 的路径不符会判为 False，从而把用户真实的自启项删掉。
import winreg
from app.core import autostart

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _read_run_raw():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
    except OSError:
        return None
    try:
        return winreg.QueryValueEx(k, autostart.APP_REG_NAME)[0]
    except FileNotFoundError:
        return None
    finally:
        winreg.CloseKey(k)


def _restore_run(raw):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    try:
        if raw is None:
            try:
                winreg.DeleteValue(k, autostart.APP_REG_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, autostart.APP_REG_NAME, 0, winreg.REG_SZ, raw)
    finally:
        winreg.CloseKey(k)


prev_raw = _read_run_raw()
print(f"[自启] 原始注册表值 = {prev_raw!r}")
assert autostart.set_enabled(True), "开启自启失败"
print(f"[自启] 开启后 is_enabled = {autostart.is_enabled()}")
assert autostart.is_enabled(), "注册表写入后读取失败"
k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
val, _ = winreg.QueryValueEx(k, autostart.APP_REG_NAME)
winreg.CloseKey(k)
print(f"[自启] Run 项值 = {val}")
assert val.startswith('"'), "exe 路径未加引号（含空格会启动失败）"
assert "--tray" in val, "自启命令行缺少 --tray，开机时会把主窗口弹出来"
assert autostart.set_enabled(False), "关闭自启失败"
assert _read_run_raw() is None, "关闭后注册表项仍存在"
_restore_run(prev_raw)
print(f"[自启] 已还原为原值 = {_read_run_raw()!r}")
print("[自启] OK：开关可正确写入/删除注册表，路径已加引号")

# ============ 2) Win 键屏蔽钩子 ============
from app.core.winkey_guard import (WinKeyGuard, foreground_process_name,
                                   list_windowed_processes)
procs = list_windowed_processes()
fg = foreground_process_name()
print(f"[Win键] 枚举到 {len(procs)} 个有窗口的程序，示例: {procs[:6]}")
print(f"[Win键] 当前前台进程 = {fg!r}")
assert isinstance(procs, list) and len(procs) >= 1, "进程枚举失败"

guard = WinKeyGuard()
guard.apply_settings(True, ["notepad.exe"])
import time
time.sleep(0.6)
print(f"[Win键] 启用后 active = {guard.active}")
assert guard.active, "钩子未成功安装（SetWindowsHookEx 失败）"
guard.apply_settings(True, [])          # 列表为空 → 自动停用
time.sleep(0.3)
print(f"[Win键] 列表为空时 active = {guard.active}")
assert not guard.active, "列表为空时不应启用"
guard.apply_settings(False, ["notepad.exe"])
time.sleep(0.3)
print(f"[Win键] 关闭后 active = {guard.active}")
assert not guard.active, "关闭后钩子仍在"
guard.stop()
print("[Win键] OK：钩子可安装/卸载，空列表与关闭态均不生效")

# ============ 3) 新设置行布局 ============
from app.core.settings import AppSettings
from app.engine.models import BatteryReading, DeviceInfo
from app.engine.scanner import DeviceState
from app.ui.main_window import MainWindow

settings = AppSettings()
settings.winkey_processes = ["cs2.exe"]
settings.winkey_block = True
win = MainWindow(settings, "light")
win.show()
demo = [("391D:2A02", "VGN V108", "keyboard", 78, "2.4G"),
        ("391D:1A05", "Dragonfly 3", "mouse", 94, "2.4G")]
states = []
for key, name, kind, pct, conn in demo:
    info = DeviceInfo(key=key, vid=int(key[:4], 16), pid=int(key[5:], 16),
                      dongle_name=name, kind=kind)
    st = DeviceState(info)
    st.reading = BatteryReading(percent=pct, status="ok", protocol="demo", connection=conn)
    states.append(st)
win.update_devices(states)
for _ in range(6):
    app.processEvents()

panel = win.findChild(QWidget, "settingsPanel")
print(f"[布局] 窗口={win.width()}x{win.height()}  content={win._content.sizeHint().height()}")
print(f"[布局] 面板 bottom={panel.y()+panel.height()}（窗口高={win.height()}）")
print(f"[布局] seg_winkey 可见={win.seg_winkey.isVisible()} 高={win.seg_winkey.height()}"
      f"  列表文本={win.lbl_winkey.text()!r}")
assert panel.y() + panel.height() <= win.height() + 2, "新增行后设置面板被裁切"
assert win.seg_winkey.height() >= 20, "游戏模式开关被压扁"
assert "cs2.exe" in win.lbl_winkey.text() or "cs2" in win.lbl_winkey.toolTip(), "屏蔽列表未显示"
print("[布局] OK：新增两行完整显示，面板未被裁切")

pm = win.grab()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "features.png")
pm.save(out)
print("saved", out)

# 复原设置，避免污染用户配置
settings.winkey_processes = []
settings.winkey_block = False
print("\n全部验证通过 ✅")

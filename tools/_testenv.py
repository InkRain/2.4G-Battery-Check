"""测试环境隔离：自动备份并在退出时还原「开机自启」注册表项。

为什么需要：UI 测试会构造 BatteryApp，其 __init__ 里有自启路径自愈
（autostart.sync_path()），run() 里还可能调用 set_enabled()。用 python 源码
跑测试时，这些调用会把真实的 Run 项改写成「pythonw.exe ... 某个测试脚本.py」，
跑完就把用户的开机自启弄坏了。

用法：在构造 BatteryApp / 触发自启逻辑之前 `import _testenv  # noqa`
（tools 目录需在 sys.path 中，测试脚本一般已插入项目根，这里同时兼容）。
"""
from __future__ import annotations

import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "2.4GBatteryCheck"


def _key(access):
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)


def read_run_value():
    """读取原始值（不存在返回 None）。"""
    try:
        import winreg
        k = _key(winreg.KEY_READ)
        try:
            return winreg.QueryValueEx(k, _NAME)[0]
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(k)
    except Exception:
        return None


def write_run_value(value):
    """写回原始值；value 为 None 表示删除该项。"""
    try:
        import winreg
        k = _key(winreg.KEY_SET_VALUE)
        try:
            if value is None:
                try:
                    winreg.DeleteValue(k, _NAME)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(k)
        return True
    except Exception:
        return False


SAVED = read_run_value()


@atexit.register
def _restore():
    current = read_run_value()
    if current != SAVED:
        write_run_value(SAVED)
        print(f"[测试隔离] 已还原开机自启项 = {SAVED!r}")

"""开机自启（注册表 Run 项）与桌面链接。"""
from __future__ import annotations

import os
import sys

APP_REG_NAME = "2.4GBatteryCheck"

# 开机启动时附加的参数：直接驻留托盘，不弹主窗口
AUTOSTART_ARGS = "--tray"


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        # 必须加引号：exe 路径含空格（"2.4G Battery Check.exe"），否则 Run 项启动失败
        return f'"{sys.executable}"'
    # 源码运行：用 pythonw 无窗口启动
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(pythonw):
        return f'"{pythonw}" "{os.path.abspath(sys.argv[0])}"'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def _run_command() -> str:
    """写进 Run 项的完整命令行：带 --tray，开机时静默驻留托盘。"""
    return f"{_exe_path()} {AUTOSTART_ARGS}"


def _normalized(cmd: str) -> str:
    """命令行归一化（压缩空白 + 小写），用于比较是否需要改写。"""
    return " ".join((cmd or "").split()).lower()


def _target_of(cmd: str) -> str:
    """取命令行里的首个可执行文件路径（去掉引号，统一小写比较）。"""
    cmd = (cmd or "").strip()
    if not cmd:
        return ""
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return (cmd[1:end] if end > 0 else cmd.strip('"')).lower()
    return cmd.split(" ")[0].lower()


def _read_run_value() -> str | None:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            return str(value)
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except Exception:
        return None


def is_enabled() -> bool:
    """注册表存在**且指向当前 exe**。路径变了（例如换目录/改单文件）视为未启用。"""
    value = _read_run_value()
    if value is None:
        return False
    return _target_of(value) == _target_of(_exe_path())


def sync_path() -> bool:
    """自愈：注册表项存在但路径/参数与当前不一致时，改写成当前命令行。

    覆盖两种情况：exe 换了位置（单文件/挪目录），或旧版本写的是「无 --tray」的
    旧命令行——后者开机时会把主窗口弹出来，这里顺手升级成静默启动。
    """
    value = _read_run_value()
    if value is None:
        return False
    if _normalized(value) == _normalized(_run_command()):
        return False
    return set_enabled(True)


def set_enabled(enabled: bool) -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_SET_VALUE)
        try:
            if enabled:
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, _run_command())
            else:
                winreg.DeleteValue(key, APP_REG_NAME)
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

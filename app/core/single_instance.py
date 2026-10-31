"""单实例保护：避免重复双击开出多份托盘图标和扫描线程。

单文件版每次启动都会解压一份 ~100MB 到临时目录，多开一份就多占一份内存和磁盘，
托盘上还会出现重复的图标组，很容易让人以为程序出了问题。
"""
from __future__ import annotations

import ctypes
import logging

log = logging.getLogger(__name__)

MUTEX_NAME = "Local\\2.4GBatteryCheck.SingleInstance"
_MUTEX_NAME = MUTEX_NAME        # 兼容旧引用
_ERROR_ALREADY_EXISTS = 183
_MB_ICONINFORMATION = 0x40

_handle = None


def acquire(name: str | None = None) -> bool:
    """尝试取得单实例锁。返回 True 表示首次启动，False 表示已有实例在运行。

    name 仅供测试注入独立锁名使用（避免干扰正在运行的真实实例）。
    """
    global _handle
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        k32.CreateMutexW.restype = ctypes.c_void_p
        handle = k32.CreateMutexW(None, False, name or MUTEX_NAME)
        err = ctypes.get_last_error()
        if not handle:
            log.warning("创建单实例锁失败（err=%s），继续启动", err)
            return True
        _handle = handle
        return err != _ERROR_ALREADY_EXISTS
    except Exception:
        log.exception("单实例检查异常，继续启动")
        return True


def notify_already_running() -> None:
    """提示用户程序已在托盘运行（不弹窗则静默忽略）。"""
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "外设电量监控已经在运行了。\n\n请在屏幕右下角的托盘区查看图标（可能藏在 ^ 展开箭头里）。",
            "外设电量监控", _MB_ICONINFORMATION)
    except Exception:
        pass

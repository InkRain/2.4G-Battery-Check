"""清理 PyInstaller onefile 模式在临时目录留下的 _MEI* 残留。

单文件版每次启动都会把自身解压到 ``%TEMP%\\_MEIxxxxx``，正常退出时由引导器删除。
但进程被强制结束 / 崩溃 / 断电时不会清理，单个残留约 100MB，堆积起来会明显占空间。

为什么不用「探测目录是否被占用」来判断？
    实测在 Windows 10/11 上两种常用判据都不成立：
    - 以 share=0 打开已加载的 DLL 会**成功**（LoadLibrary 加载完就关掉了自己的句柄）；
    - 重命名已映射的 DLL 也会**成功**（系统支持 POSIX 语义）。
    按这两种判断去删，会把「正在运行的另一个实例」的目录删掉，属于破坏性操作。

改为「留主人标记」：每个实例在自己的解压目录里写 ``_owner.json``（记进程号）。
下次启动扫到别人的目录时，读文件判断那个进程还活不活：活着就不动，死了才删。
没有标记的旧目录（早期版本留下的）只按天数兜底，绝不激进删除。
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import sys
import tempfile
import time

log = logging.getLogger(__name__)

# 本程序打包时一定带的特征文件，用来确认目录确实是本程序解压出来的
MARKER = os.path.join("app", "resources", "app.ico")
# 主人标记文件名（放在解压根目录）
OWNER_FILE = "_owner.json"
# 没有主人标记的旧目录，超过这么多天才清（早期版本没有标记）
LEGACY_DAYS = 3.0

_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102


def _pid_alive(pid: int) -> bool:
    """进程是否仍存活。打不开一律当作「不存活」，但下面会附带时间兜底，只会少删。"""
    if pid <= 0:
        return False
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        k32.WaitForSingleObject.restype = ctypes.c_ulong
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = k32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            return k32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return False


def _current_meipass() -> str:
    raw = getattr(sys, "_MEIPASS", "") or ""
    return os.path.abspath(raw) if raw else ""


def _read_owner(path: str) -> dict | None:
    try:
        with open(os.path.join(path, OWNER_FILE), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_owner(path: str) -> None:
    try:
        with open(os.path.join(path, OWNER_FILE), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "exe": sys.executable,
                       "ts": int(time.time())}, f)
    except OSError:
        log.debug("无法写入主人标记：%s", path)


def _remove_dir(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, MARKER)):
        return False                      # 不是本程序的目录，绝不碰
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        log.debug("临时目录未能完全删除：%s", path)
        return False
    log.info("已清理残留临时目录 %s", path)
    return True


def cleanup_stale_temp_dirs(root: str | None = None) -> int:
    """清理已退出实例的解压目录，返回删除数量。

    ``root`` 仅测试用；不传则使用系统临时目录。
    """
    if not getattr(sys, "frozen", False):
        return 0

    base = root or tempfile.gettempdir()
    current = os.path.normcase(_current_meipass())
    removed = 0

    try:
        entries = os.listdir(base)
    except OSError:
        entries = []

    for name in entries:
        if not name.startswith("_MEI") or ".del" in name:
            continue
        path = os.path.join(base, name)
        if os.path.normcase(os.path.abspath(path)) == current:
            continue                      # 自己正在用

        owner = _read_owner(path)
        if owner is not None:
            pid = int(owner.get("pid") or 0)
            if _pid_alive(pid):
                log.debug("临时目录仍被进程 %s 使用，跳过：%s", pid, path)
                continue                  # 另一个实例还活着
            if _remove_dir(path):
                removed += 1
            continue

        # 没有主人标记 —— 早期版本留下的，按天数兜底
        try:
            age_days = (time.time() - os.path.getmtime(path)) / 86400.0
        except OSError:
            continue
        if age_days < LEGACY_DAYS:
            continue
        if _remove_dir(path):
            removed += 1

    # 给自己打上标记，供下次启动判断
    me = _current_meipass()
    if me and os.path.isdir(me):
        _write_owner(me)

    return removed

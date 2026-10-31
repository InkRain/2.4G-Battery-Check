"""按进程屏蔽 Win 键（游戏模式）—— 全局低级键盘钩子。

只有在「当前前台进程 ∈ 屏蔽列表」时才吞掉 Win / 右键菜单键，
其它任何时候都不接管键盘，正常使用完全不受影响。
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_QUIT = 0x0012
VK_LWIN = 0x5B
VK_RWIN = 0x5C
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

LRESULT = ctypes.c_ssize_t
HHOOK = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# ---- 函数签名（64 位下句柄必须显式声明，否则会被截断导致崩溃）----
_user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, HINSTANCE, wintypes.DWORD)
_user32.SetWindowsHookExW.restype = HHOOK
_user32.UnhookWindowsHookEx.argtypes = (HHOOK,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.CallNextHookEx.argtypes = (HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32.CallNextHookEx.restype = LRESULT
_user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM)
_user32.PostThreadMessageW.restype = wintypes.BOOL
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.IsWindowVisible.argtypes = (wintypes.HWND,)
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
_user32.EnumWindows.restype = wintypes.BOOL

_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD))
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL


def _process_name(pid: int) -> str:
    if not pid:
        return ""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        _kernel32.CloseHandle(h)
    return ""


def foreground_process_name() -> str:
    """当前前台窗口所属进程名（小写，如 cs2.exe）。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _process_name(pid.value)


def list_windowed_processes() -> list:
    """枚举有可见窗口的进程名（去重、排序），供设置界面选择。"""
    found: set = set()

    def _cb(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        if _user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _process_name(pid.value)
        if name:
            found.add(name)
        return True

    _user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return sorted(found)


class WinKeyGuard:
    """全局低级键盘钩子：仅当「前台进程在屏蔽列表」时吞掉 Win 键。"""

    def __init__(self):
        self._enabled = False
        self._processes: set = set()
        self._thread = None
        self._hook = None
        self._proc = None          # 必须持有回调引用，否则会被 GC 回收导致崩溃
        self._tid = 0
        self._cache_hwnd = 0
        self._cache_name = ""
        self._cache_at = 0.0

    # ---------------------------------------------------------------- 对外
    def apply_settings(self, enabled: bool, processes):
        """按设置启用/停用。启用需同时满足「开关打开」且「列表非空」。"""
        self._enabled = bool(enabled)
        self._processes = {str(p).lower() for p in (processes or []) if str(p).strip()}
        if self._enabled and self._processes:
            self._start()
        else:
            self._stop()

    @property
    def active(self) -> bool:
        return self._hook is not None and self._enabled

    def stop(self):
        self._enabled = False
        self._stop()

    # ---------------------------------------------------------------- 线程
    def _start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="WinKeyGuard", daemon=True)
        self._thread.start()

    def _stop(self):
        tid = self._tid
        if tid:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=1.5)
        self._thread = None
        self._tid = 0

    def _run(self):
        self._tid = _kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._hook_cb)
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self._proc = None
            return
        msg = wintypes.MSG()
        try:
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            try:
                _user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None

    # ---------------------------------------------------------------- 钩子
    def _fg_name(self) -> str:
        hwnd = _user32.GetForegroundWindow()
        now = time.monotonic()
        if hwnd == self._cache_hwnd and (now - self._cache_at) < 0.2:
            return self._cache_name
        pid = wintypes.DWORD()
        if hwnd:
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _process_name(pid.value)
        self._cache_hwnd, self._cache_name, self._cache_at = hwnd, name, now
        return name

    def _hook_cb(self, nCode, wParam, lParam):
        if nCode == 0 and self._enabled and self._processes:
            try:
                kb = ctypes.cast(ctypes.c_void_p(lParam),
                                 ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if kb.vkCode in (VK_LWIN, VK_RWIN):
                    if self._fg_name() in self._processes:
                        return 1        # 吞掉该键，Win 失效
            except Exception:
                pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

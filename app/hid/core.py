"""Windows HID 底层封装（纯 ctypes，零第三方依赖）。

能力：
- SetupAPI 枚举 HID 设备接口（含 usage page / usage / 报告长度）
- 打开设备（共享模式 + Overlapped I/O，带超时读取，不与系统键鼠驱动冲突）
- 中断读/写（interrupt reports）、Feature 报告读写
- HidP 能力查询（usage/value caps，用于标准电池用法探测）
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------- constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000

INVALID_HANDLE_VALUE = -1
WAIT_TIMEOUT = 0x00000102
WAIT_OBJECT_0 = 0x00000000
ERROR_IO_PENDING = 997
ERROR_IO_INCOMPLETE = 996

HidP_Input = 0
HidP_Output = 1
HidP_Feature = 2

# HID 设备接口 GUID {4D1E55B2-F16F-11CF-88CB-001111000030}
_GUID_HID = bytes.fromhex("b2551e4d6ff1cf1188cb001111000030")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def hid(cls) -> "GUID":
        g = cls()
        ctypes.memmove(ctypes.byref(g), _GUID_HID, 16)
        return g


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD),
                ("Reserved", ctypes.c_size_t)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", ctypes.c_ulong),
                ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT),
                ("VersionNumber", wintypes.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class HIDP_VALUE_CAPS(ctypes.Structure):
    """对应 hidpi.h 的 HIDP_VALUE_CAPS（止于 PhysicalMax，共 52 字节）。"""
    _fields_ = [
        ("UsagePage", wintypes.USHORT), ("ReportID", ctypes.c_ubyte),
        ("IsAlias", wintypes.BOOLEAN), ("BitField", wintypes.USHORT),
        ("LinkCollection", wintypes.USHORT),
        ("LinkUsage", wintypes.USHORT), ("LinkUsagePage", wintypes.USHORT),
        ("BitSize", wintypes.USHORT), ("ReportCount", wintypes.USHORT),
        ("Reserved2", wintypes.USHORT * 5),
        ("UnitsExp", ctypes.c_ulong), ("Units", ctypes.c_ulong),
        ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long),
        ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


# ---------------------------------------------------------------- libraries
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_hid = ctypes.WinDLL("hid", use_last_error=True)
_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
_kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                          ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

_setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
_setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                  ctypes.POINTER(GUID), wintypes.DWORD,
                                                  ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                       ctypes.c_void_p, wintypes.DWORD,
                                                       ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

_hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
_hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
_hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
_hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
_hid.HidP_GetSpecificValueCaps.argtypes = [ctypes.c_int, wintypes.USHORT, wintypes.USHORT,
                                           wintypes.USHORT, ctypes.c_void_p,
                                           ctypes.POINTER(wintypes.USHORT), ctypes.c_void_p]
_hid.HidD_GetFeature.restype = wintypes.BOOLEAN
_hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
_hid.HidD_SetFeature.restype = wintypes.BOOLEAN
_hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
_hid.HidD_SetOutputReport.restype = wintypes.BOOLEAN
_hid.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
_hid.HidD_GetInputReport.restype = wintypes.BOOLEAN
_hid.HidD_GetInputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]


def _str(handle: int) -> str:
    """读设备产品字符串。"""
    if not handle:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _hid.HidD_GetProductString(wintypes.HANDLE(handle), buf, 126)
    return buf.value or ""


# ---------------------------------------------------------------- data types
@dataclass
class HidInterfaceInfo:
    path: str
    vid: int = 0
    pid: int = 0
    product: str = ""
    usage_page: int = 0
    usage: int = 0
    input_len: int = 0
    output_len: int = 0
    feature_len: int = 0
    instance_id: str = ""      # 去掉 \??\ 前缀的路径尾段，可作稳定 key
    container_id: str = ""     # 同物理设备的 container id（若有）
    interface_number: int = -1  # 从路径 MI_xx 解析的接口号

    @property
    def is_vendor_collection(self) -> bool:
        return self.usage_page >= 0xFF00

    @property
    def device_key(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"


@dataclass
class BatteryCaps:
    """标准 HID 电池用法信息（usage 0x06/0x20）。"""
    report_id: int
    report_type: int          # HidP_Input / HidP_Feature
    bit_size: int
    logical_min: int
    logical_max: int


# ---------------------------------------------------------------- enumerate
def enumerate_devices() -> List[HidInterfaceInfo]:
    """枚举当前所有 HID 设备接口。"""
    guid = GUID.hid()
    hdev = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                          DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev == INVALID_HANDLE_VALUE:
        return []
    out: List[HidInterfaceInfo] = []
    idx = 0
    detail_cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
    try:
        while True:
            ifdata = SP_DEVICE_INTERFACE_DATA()
            ifdata.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), idx,
                                                         ctypes.byref(ifdata)):
                break
            idx += 1
            need = wintypes.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifdata), None, 0,
                                                       ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.memmove(buf, ctypes.byref(wintypes.DWORD(detail_cb_size)), 4)
            if not _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifdata), buf,
                                                              need.value, ctypes.byref(need), None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            info = _describe(path)
            if info:
                out.append(info)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _describe(path: str) -> Optional[HidInterfaceInfo]:
    handle = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                   OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if handle == INVALID_HANDLE_VALUE:
        # 只以查询方式打开拿属性
        handle = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                       OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE_VALUE:
            return None
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if not _hid.HidD_GetAttributes(wintypes.HANDLE(handle), ctypes.byref(attrs)):
            return None
        info = HidInterfaceInfo(path=path, vid=attrs.VendorID, pid=attrs.ProductID)
        info.product = _str(handle)
        ppd = ctypes.c_void_p()
        if _hid.HidD_GetPreparsedData(wintypes.HANDLE(handle), ctypes.byref(ppd)):
            caps = HIDP_CAPS()
            if _hid.HidP_GetCaps(ppd, ctypes.byref(caps)) == 0x110000:  # HIDP_STATUS_SUCCESS
                info.usage_page = caps.UsagePage
                info.usage = caps.Usage
                info.input_len = caps.InputReportByteLength
                info.output_len = caps.OutputReportByteLength
                info.feature_len = caps.FeatureReportByteLength
            _hid.HidD_FreePreparsedData(ppd)
        # instance id: 路径去掉接口后缀
        info.instance_id = path.split("#")[1] if "#" in path else path
        # 接口号：路径中 MI_xx（HID 接口路径形如 \\?\hid#vid_xxx&pid_xxx&mi_02#...）
        import re
        m = re.search(r"&mi_([0-9a-f]{2})", path, re.IGNORECASE)
        if m:
            info.interface_number = int(m.group(1), 16)
        return info
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


def find_battery_value_caps(path: str) -> List[BatteryCaps]:
    """查询设备是否暴露标准电池用法（UsagePage 0x06, Usage 0x20）。"""
    handle = _kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                   OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        return []
    try:
        ppd = ctypes.c_void_p()
        if not _hid.HidD_GetPreparsedData(wintypes.HANDLE(handle), ctypes.byref(ppd)):
            return []
        try:
            out: List[BatteryCaps] = []
            for rtype, rname in ((HidP_Feature, "feature"), (HidP_Input, "input")):
                count = wintypes.USHORT(64)
                caps_arr = (HIDP_VALUE_CAPS * 64)()
                status = _hid.HidP_GetSpecificValueCaps(rtype, 0x06, 0x20, 0, ppd,
                                                        ctypes.byref(count), caps_arr)
                if status == 0x110000 and count.value:
                    for i in range(count.value):
                        c = caps_arr[i]
                        out.append(BatteryCaps(report_id=c.ReportID, report_type=rtype,
                                               bit_size=c.BitSize, logical_min=c.LogicalMin,
                                               logical_max=c.LogicalMax))
            return out
        finally:
            _hid.HidD_FreePreparsedData(ppd)
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


# ---------------------------------------------------------------- device io
class HidDevice:
    """打开一个 HID 接口，提供带超时的读 / 写 / feature 报告。"""

    def __init__(self, path: str, access: int = GENERIC_READ | GENERIC_WRITE):
        self.path = path
        self.last_error = 0          # 最近一次 write/set_feature 的 Win32 错误码
        self.handle = _kernel32.CreateFileW(
            path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
            OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if self.handle == INVALID_HANDLE_VALUE:
            raise OSError(f"CreateFile failed: {ctypes.get_last_error()}")

    def close(self) -> None:
        if getattr(self, "handle", None):
            _kernel32.CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = None

    def __enter__(self) -> "HidDevice":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- overlapped read with timeout -------------------------------
    def read(self, size: int, timeout_ms: int) -> Optional[bytes]:
        """读一条输入报告（含 report id 字节），超时返回 None。"""
        ev = _kernel32.CreateEventW(None, True, False, None)
        if not ev:
            return None
        try:
            ov = OVERLAPPED()
            ov.hEvent = ev
            buf = ctypes.create_string_buffer(size)
            n = wintypes.DWORD()
            ok = _kernel32.ReadFile(wintypes.HANDLE(self.handle), buf, size,
                                    ctypes.byref(n), ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err != ERROR_IO_PENDING:
                    return None
                wait = _kernel32.WaitForSingleObject(ev, timeout_ms)
                if wait == WAIT_TIMEOUT:
                    _kernel32.CancelIoEx(wintypes.HANDLE(self.handle), ctypes.byref(ov))
                    _kernel32.WaitForSingleObject(ev, 2000)  # 等取消完成
                    return None
                if not _kernel32.GetOverlappedResult(wintypes.HANDLE(self.handle),
                                                     ctypes.byref(ov), ctypes.byref(n), False):
                    return None
            return buf.raw[:n.value] if n.value else None
        finally:
            _kernel32.CloseHandle(ev)

    def write(self, data: bytes, timeout_ms: int = 500) -> bool:
        """写一条输出报告（data[0] 必须是 report id）。

        失败原因记录在 self.last_error：
          87 (ERROR_INVALID_PARAMETER) -> 报告 ID / 长度不被该集合支持
          1  (ERROR_INVALID_FUNCTION)  -> 集合存在但固件未实现该功能（非休眠）
          1167                          -> 设备已拔出
        """
        self.last_error = 0
        ev = _kernel32.CreateEventW(None, True, False, None)
        if not ev:
            return False
        try:
            ov = OVERLAPPED()
            ov.hEvent = ev
            buf = ctypes.create_string_buffer(bytes(data), len(data))
            n = wintypes.DWORD()
            ok = _kernel32.WriteFile(wintypes.HANDLE(self.handle), buf, len(data),
                                     ctypes.byref(n), ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err != ERROR_IO_PENDING:
                    self.last_error = err
                    return False
                wait = _kernel32.WaitForSingleObject(ev, timeout_ms)
                if wait == WAIT_TIMEOUT:
                    _kernel32.CancelIoEx(wintypes.HANDLE(self.handle), ctypes.byref(ov))
                    _kernel32.WaitForSingleObject(ev, 2000)
                    self.last_error = 1460  # WAIT_TIMEOUT
                    return False
                if not _kernel32.GetOverlappedResult(wintypes.HANDLE(self.handle),
                                                     ctypes.byref(ov), ctypes.byref(n), False):
                    self.last_error = ctypes.get_last_error()
                    return False
            return True
        finally:
            _kernel32.CloseHandle(ev)

    def get_feature(self, report_id: int, size: int) -> Optional[bytes]:
        buf = ctypes.create_string_buffer(size)
        buf[0] = report_id
        if _hid.HidD_GetFeature(wintypes.HANDLE(self.handle), buf, size):
            return buf.raw[:size]
        return None

    def set_feature(self, data: bytes) -> bool:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        return bool(_hid.HidD_SetFeature(wintypes.HANDLE(self.handle), buf, len(data)))

    def set_output_report(self, data: bytes) -> bool:
        """控制传输方式写输出报告（部分 dongle 只认这种方式）。"""
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        return bool(_hid.HidD_SetOutputReport(wintypes.HANDLE(self.handle), buf, len(data)))

    def get_input_report(self, report_id: int, size: int) -> Optional[bytes]:
        """控制传输方式读输入报告。"""
        buf = ctypes.create_string_buffer(size)
        buf[0] = report_id
        if _hid.HidD_GetInputReport(wintypes.HANDLE(self.handle), buf, size):
            return buf.raw[:size]
        return None

    def flush_input(self, rounds: int = 8, timeout_ms: int = 1) -> None:
        """清掉积压的迟到输入报告。"""
        for _ in range(rounds):
            if not self.read(65, timeout_ms):
                break


# ReadFile / WriteFile / GetProductString 原型（wintypes 参数）
_kernel32.ReadFile.restype = wintypes.BOOL
_kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
_hid.HidD_GetProductString.restype = wintypes.BOOLEAN
_hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]

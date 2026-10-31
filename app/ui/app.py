"""应用装配：QApplication + 系统托盘 + 扫描器接线。"""
from __future__ import annotations

import logging
import sys
import time

from PySide6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.core.settings import AppSettings
from app.engine.models import ST_OK, ST_SLEEPING, friendly_name
from app.engine.scanner import DeviceState
from app.engine.scanner import BatteryScanner
from app.ui.main_window import MainWindow, TITLE
from app.ui.theme import THEME_AUTO, resolve_theme
from app.ui.tray_popup import TrayPopup

log = logging.getLogger("ui.app")


def _make_kind_icon(kind: str, percent, charging: bool, dark: bool,
                    show_text: bool = False) -> QIcon:
    """托盘图标：环形电量进度 + 中央白色设备剪影（参考 iOS 外设监控样式）。"""
    size = 32
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if percent is None:
        color = QColor("#9E9E9E")
    elif percent >= 50:
        color = QColor("#2FA84F")
    elif percent >= 20:
        color = QColor("#E8A33D")
    else:
        color = QColor("#D64545")
    ring_bg = QColor("#6E6E73") if dark else QColor("#8E8E93")
    fg = QColor("#F2F2F7") if dark else QColor("#48484A")

    # ---- 外圈：灰底环 + 电量彩色弧 ----
    ring = QRectF(2.5, 2.5, 27, 27)
    p.setPen(QPen(ring_bg, 3.4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(ring, 0, 360 * 16)
    if percent is not None:
        ratio = max(0.02, min(1.0, percent / 100.0))
        if ratio >= 0.999:
            p.setPen(QPen(color, 3.4, Qt.SolidLine, Qt.RoundCap))
            p.drawEllipse(ring)                     # 满环直接画圆
        else:
            # 用路径画弧：Qt drawArc 大跨度时偶发不渲染，arcTo 更可靠
            arc = QPainterPath()
            arc.arcMoveTo(ring, 90)                 # 顶部起点
            arc.arcTo(ring, 90, -360 * ratio)       # 顺时针，跨度=电量比例
            p.setPen(QPen(color, 3.4, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(arc)

    # ---- 中央设备剪影 ----
    p.setPen(Qt.NoPen)
    p.setBrush(fg)
    if kind == "keyboard":
        p.drawRoundedRect(6.5, 12.5, 19, 8.5, 2, 2)
        p.setBrush(ring_bg)
        for r in range(2):
            for c in range(7):
                p.drawRoundedRect(7.8 + c * 2.5, 13.6 + r * 3.1, 1.8, 2.1, 0.5, 0.5)
        p.drawRoundedRect(12.8, 19.2, 6.6, 1.4, 0.6, 0.6)
    elif kind == "headset":
        p.setPen(QPen(fg, 2.4))
        p.setBrush(Qt.NoBrush)
        p.drawArc(8, 8.5, 16, 14, 0, 180 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawRoundedRect(7, 15, 5, 9, 2, 2)
        p.drawRoundedRect(20, 15, 5, 9, 2, 2)
    elif kind == "other":
        p.drawRoundedRect(8, 11, 16, 11, 2.5, 2.5)
        p.setBrush(fg)
        p.drawRoundedRect(24.5, 14.5, 2, 4, 1, 1)
    else:   # mouse
        p.drawRoundedRect(10, 7, 12, 19, 6, 6)
        p.setPen(QPen(ring_bg, 1.4))
        p.drawLine(16, 10, 16, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(ring_bg)
        p.drawRoundedRect(15, 10.5, 2, 3.5, 1, 1)

    # ---- 数字模式：中央数字（电量色描边保证可读）----
    if show_text and percent is not None:
        f = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(f)
        txt = str(percent)
        p.setPen(fg)
        p.drawText(QRectF(4, 4, 24, 24), Qt.AlignCenter, txt)

    # ---- 充电：中央叠加小闪电 ----
    if charging and percent is not None:
        cx, cy = 16, 16
        p.setBrush(QColor(0, 0, 0, 130))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 8.5, 8.5)
        bolt = QPainterPath(QPointF(cx - 2, cy - 5.5))
        bolt.lineTo(cx + 2.6, cy - 0.5)
        bolt.lineTo(cx - 0.4, cy + 0.4)
        bolt.lineTo(cx + 2.6, cy + 5.5)
        p.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(bolt)
        p.setPen(QPen(QColor("#2ECC71"), 0.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(bolt)
    p.end()
    return QIcon(pm)


class BatteryApp(QObject):
    """应用总控。"""

    # 扫描结果信号（扫描线程 -> 主线程）
    states_ready = Signal(list)

    def __init__(self, settings: AppSettings, silent: bool = False):
        super().__init__()
        self.settings = settings
        # 静默启动（开机自启）：只驻留托盘，不弹主窗口、不弹提示
        self.silent = silent
        # 首轮扫描不弹低电量 toast（刚开机就蹦窗太吵）
        self._silent_skip_alert = silent
        # 自启路径自愈：exe 换过位置（如改为单文件）时自动改写注册表，避免开机启动失效
        try:
            from app.core import autostart as _autostart
            _autostart.sync_path()
        except Exception:
            pass
        self.theme_name = resolve_theme(settings.theme)
        self.scanner = BatteryScanner()
        self.scanner.interval = max(15, settings.refresh_seconds or 60)
        self.scanner.subscribe(self._emit_states)
        self.states_ready.connect(self._on_states)
        self.window = MainWindow(settings, self.theme_name)
        self.popup = TrayPopup(self.window.theme)
        self.tray = QSystemTrayIcon()
        self._alerted: set[str] = set()
        self._last_states: list = []
        self.kind_trays: dict = {}
        self._build_tray()
        # 游戏模式：按进程屏蔽 Win 键
        from app.core.winkey_guard import WinKeyGuard
        self.winkey = WinKeyGuard()
        # 系统主题变化定时检查
        self._theme_timer = QTimer(self)
        self._theme_timer.timeout.connect(self._check_system_theme)
        self._theme_timer.start(5000)

    def _emit_states(self, states):
        """扫描线程回调：仅发信号，不碰 GUI。"""
        self.states_ready.emit(states)

    # ---------------------------------------------------------------- 托盘
    def _build_tray(self):
        self._menu = QMenu()
        self.act_open = QAction("打开主窗口", self._menu)
        self.act_open.triggered.connect(self._show_window)
        self._menu.addAction(self.act_open)
        self.act_popup = QAction("查看电量面板", self._menu)
        self.act_popup.triggered.connect(self._toggle_popup)
        self._menu.addAction(self.act_popup)
        self.act_refresh = QAction("立即刷新", self._menu)
        self.act_refresh.triggered.connect(self.scanner.refresh_now)
        self._menu.addAction(self.act_refresh)
        self._menu.addSeparator()
        act_quit = QAction("退出", self._menu)
        act_quit.triggered.connect(QApplication.quit)
        self._menu.addAction(act_quit)
        # 主图标：无设备在线时的兜底显示
        self.tray.setIcon(_make_kind_icon("other", None, False, self.theme_name == "dark"))
        self.tray.setToolTip(f"{TITLE}\n正在扫描…")
        self.tray.setContextMenu(self._menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        # 每类设备一个托盘图标（键盘/鼠标/耳机）
        self.kind_trays: dict[str, QSystemTrayIcon] = {}

    def _sync_tray_icons(self, states: list[DeviceState]):
        """按设备类型各显示一个托盘图标：设备外形 + 竖直电量条。"""
        dark = self.theme_name == "dark"
        show_text = self.settings.tray_show_percent
        # 每类取最低电量的在线设备
        per_kind: dict[str, tuple] = {}   # kind -> (percent, charging, name)

        def _set(kind, pct, chg, name, replace):
            cur = per_kind.get(kind)
            if cur is None or cur[0] is None:
                per_kind[kind] = (pct, chg, name)
            elif replace and (pct is None or pct < cur[0]):
                per_kind[kind] = (pct, chg, name)

        # 第一轮：正常在线的设备（优先）
        for s in states:
            r = s.reading
            if r is not None and r.status == ST_OK and r.percent is not None:
                _set(s.info.kind, r.percent, r.charging, friendly_name(s.info), True)
        # 第二轮：休眠设备 —— 电量是上一次的有效读数，仍按真实电量画环，
        # 不能因为休眠就把托盘图标降级成灰色（会让人误以为设备离线/读不到）
        for s in states:
            r = s.reading
            if (r is not None and r.status == ST_SLEEPING and r.percent is not None
                    and s.info.kind not in per_kind):
                per_kind[s.info.kind] = (r.percent, False, friendly_name(s.info))
        # 第三轮：无电量数据的设备（如固件未开放接口），标 None
        for s in states:
            kind = s.info.kind
            if kind not in per_kind:
                per_kind[kind] = (None, False, friendly_name(s.info))
        for kind in ("keyboard", "mouse", "headset", "other"):
            if kind not in per_kind:
                tray = self.kind_trays.pop(kind, None)
                if tray:
                    tray.hide()
                continue
            pct, chg, name = per_kind[kind]
            tray = self.kind_trays.get(kind)
            if tray is None:
                tray = QSystemTrayIcon()
                tray.setContextMenu(self._menu)
                tray.activated.connect(self._on_tray_activated)
                tray.show()
                self.kind_trays[kind] = tray
            tray.setIcon(_make_kind_icon(kind, pct, chg, dark, show_text))
            tip = name
            if pct is not None:
                tip += f": {pct}%" + (" (充电中)" if chg else "")
            else:
                tip += ": 无电量信息"
            tray.setToolTip(tip)
        # 主图标：所有类型都有专属图标时隐藏
        if per_kind:
            self.tray.hide()
        else:
            self.tray.setIcon(_make_kind_icon("other", None, False, dark))
            self.tray.setToolTip(f"{TITLE}\n未检测到设备")
            self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # 左键
            self._toggle_popup()
        elif reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _toggle_popup(self):
        if self.popup.isVisible():
            self.popup.close()
        else:
            # 打开面板时顺带刷一次，避免展示上一次扫描的旧数据
            self.scanner.refresh_now()
            self.popup.update_states(self._last_states)
            self.popup.show()

    def _show_window(self):
        self.window.showNormal()
        self.window.activateWindow()

    def _on_alert_toggled(self, checked: bool):
        self.settings.low_battery_alert = checked

    # ---------------------------------------------------------------- 数据
    def _on_states(self, states: list[DeviceState]):
        self._last_states = states
        # 自定义设备名注入
        for s in states:
            s.display_name = self.settings.display_name(s.key, None)
        self.window.update_devices(states)
        self.popup.update_states(states)
        # 每类设备一个托盘图标（键盘/鼠标/耳机：外形 + 竖直电量条）
        self._sync_tray_icons(states)
        # 低电量提醒：右下角玻璃 toast 弹窗
        # 静默启动（开机自启）时首轮不弹提示——刚开机就蹦窗属于打扰，
        # 电量状态已体现在托盘图标颜色上。这一轮里已经低电的设备记为「已知」，
        # 后续不再补弹（避免开机十秒后又突然冒出来）。之后新增的低电仍正常提醒。
        skip_once = getattr(self, "_silent_skip_alert", False)
        if skip_once:
            self._silent_skip_alert = False
        if self.settings.low_battery_alert:
            threshold = self.settings.low_battery_threshold
            for s in states:
                r = s.reading
                if r and r.status == ST_OK and r.percent is not None and not r.charging \
                        and r.percent <= threshold:
                    if s.key not in self._alerted:
                        self._alerted.add(s.key)
                        if not skip_once:
                            name = s.display_name or friendly_name(s.info)
                            self._show_low_toast(name, r.percent)
                elif r and r.percent is not None and r.percent > threshold + 5:
                    self._alerted.discard(s.key)

    def _show_low_toast(self, name: str, percent: int):
        from PySide6.QtGui import QColor
        from app.ui.toast import Toast
        Toast.notify(self.window.theme, "低电量提醒",
                     f"{name} 电量仅剩 {percent}%，请及时充电",
                     QColor("#D64545"))

    # ---------------------------------------------------------------- 主题
    def _check_system_theme(self):
        if self.settings.theme != THEME_AUTO:
            return
        from app.ui.theme import system_is_dark
        want = "dark" if system_is_dark() else "light"
        if want != self.theme_name:
            self.theme_name = want
            self._apply_theme(want)

    def apply_theme(self, theme_name: str):
        self.theme_name = theme_name
        self._apply_theme(theme_name)

    def _apply_theme(self, theme_name: str):
        from app.ui.theme import Theme
        theme = Theme(theme_name)
        self.window.apply_theme(theme_name)
        self.popup.set_theme(theme)
        dark = theme_name == "dark"
        self.tray.setIcon(_make_kind_icon("other", None, False, dark))
        # 刷新所有设备专属图标配色
        for kind, tray in self.kind_trays.items():
            tray.setIcon(_make_kind_icon(kind, None, False, dark,
                                         self.settings.tray_show_percent))
        if self._last_states:
            self._sync_tray_icons(self._last_states)

    # ---------------------------------------------------------------- 设置变化
    def on_settings_changed(self):
        interval = self.settings.refresh_seconds
        self.scanner.interval = max(15, interval or 60)
        self.apply_theme(resolve_theme(self.settings.theme))
        self.winkey.apply_settings(self.settings.winkey_block,
                                   self.settings.winkey_processes)

    # ---------------------------------------------------------------- 生命周期
    def run(self):
        self.window.refresh_requested.connect(self.scanner.refresh_now)
        self.window.quit_requested.connect(self._quit)
        self.window.settings_changed.connect(self.on_settings_changed)
        # 注册表与实际状态同步
        from app.core import autostart
        if self.settings.autostart and not autostart.is_enabled():
            autostart.set_enabled(True)
        self.winkey.apply_settings(self.settings.winkey_block,
                                   self.settings.winkey_processes)
        self.scanner.start()
        if self.silent:
            # 开机自启：不弹主窗口，只靠托盘图标体现存在感
            # 但仍要建立窗口几何（不显示），保证点「打开主窗口」时尺寸正确
            self.window.ensurePolished()
            log.info("静默启动：主窗口保持隐藏，仅驻留托盘")
        else:
            self.window.show()

    def _quit(self):
        self.winkey.stop()
        self.scanner.stop()
        QApplication.quit()

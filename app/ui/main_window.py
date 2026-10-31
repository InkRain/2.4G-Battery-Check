"""主窗口：按参考截图还原的无边框圆角界面。"""
from __future__ import annotations

import ctypes
import os
import logging
import time

from PySide6.QtCore import (QEvent, QPoint, QRectF, Qt, QTimer, Signal)
from PySide6.QtGui import (QColor, QEnterEvent, QFont, QFontMetrics, QLinearGradient,
                           QMouseEvent, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.core.autostart import is_enabled as autostart_enabled, set_enabled
from app.core.settings import APP_TITLE, LOW_THRESHOLD_OPTIONS, REFRESH_OPTIONS, THEME_OPTIONS
from app.engine.models import ST_OK, ST_SLEEPING, friendly_name
from app.engine.scanner import DeviceState
from app.ui.theme import THEME_AUTO, THEME_DARK, THEME_LIGHT, Theme, resolve_theme
from app.ui.widgets import DeviceCard, SegmentedControl

log = logging.getLogger("ui.main")

TITLE = APP_TITLE

import os as _os
_ICON_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))), "app", "resources", "app.ico")


# ---------------------------------------------------------------- Win11 圆角/亚克力
def _enable_win11_rounding(hwnd: int):
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def _enable_backdrop(hwnd: int) -> bool:
    """Win11 22H2+ 启用 DWM 亚克力背景（液态玻璃），失败返回 False。"""
    try:
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_TRANSIENTWINDOW = 3   # 亚克力
        ret = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(ctypes.c_int(DWMSBT_TRANSIENTWINDOW)), 4)
        return ret == 0
    except Exception:
        return False


class TitleButton(QPushButton):
    """标题栏按钮（最小化/最大化/关闭）。"""

    def __init__(self, text: str, kind: str, theme: Theme, parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self.theme = theme
        self.setFixedSize(46, 32)
        self.setStyleSheet("border: none; background: transparent;")

    def paintEvent(self, event):
        from PySide6.QtWidgets import QStyle, QStyleOptionButton
        opt = QStyleOptionButton()
        opt.initFrom(self)
        hovered = opt.state & QStyle.State_MouseOver
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#C42B1C") if self.kind == "close" else self.theme.btn_hover)
            p.drawRoundedRect(QRectF(self.rect()), 0, 0)
        p.setPen(self.theme.text if not (hovered and self.kind == "close") else QColor("#FFFFFF"))
        f = QFont("Segoe UI", 10)
        p.setFont(f)
        p.drawText(QRectF(self.rect()), Qt.AlignCenter, self.text())
        p.end()

    def enterEvent(self, event: QEnterEvent):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class MainWindow(QWidget):
    refresh_requested = Signal()
    quit_requested = Signal()
    settings_changed = Signal()

    def __init__(self, settings, theme_name: str = THEME_LIGHT):
        super().__init__()
        self.settings = settings
        self.theme = Theme(resolve_theme(settings.theme))
        self._drag_pos: QPoint = None
        self._cards: dict[str, DeviceCard] = {}
        self._states: list[DeviceState] = []
        self._last_update = 0.0
        self._user_resized = False
        self._auto_resizing = False

        self.setWindowTitle(TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(560, 400)
        self.resize(640, 556)
        if os.path.exists(_ICON_PATH):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(_ICON_PATH))
        self.setStyleSheet(self.theme.stylesheet())

        self._build_ui()
        QTimer.singleShot(50, self._apply_rounding)

    # ---------------------------------------------------------------- UI 构建
    def _compact(self, seg: SegmentedControl) -> QWidget:
        """分段按钮紧凑排布（不被 grid 拉伸铺满）。"""
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(seg)
        hl.addStretch(1)
        return holder

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ---- 顶部小标题栏 ----
        header = QWidget()
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 0, 0, 0)
        small = QLabel(f"🔋 {TITLE}")
        small.setStyleSheet(f"color: {self.theme.text_faint.name()}; font-size: 11px;")
        self.small_title = small
        hl.addWidget(small)
        hl.addStretch(1)
        self.btn_refresh = TitleButton("↻", "refresh", self.theme)
        self.btn_refresh.setToolTip("立即刷新")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_min = TitleButton("—", "min", self.theme)
        self.btn_min.clicked.connect(self.hide)
        self.btn_max = TitleButton("▢", "max", self.theme)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close = TitleButton("✕", "close", self.theme)
        self.btn_close.clicked.connect(self.hide)
        hl.addWidget(self.btn_refresh)
        hl.addWidget(self.btn_min)
        hl.addWidget(self.btn_max)
        hl.addWidget(self.btn_close)
        root.addWidget(header)

        # ---- 内容区 ----
        content = QWidget()
        self._content = content   # 供 _auto_height 读取真实高度
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 8, 24, 16)
        cl.setSpacing(14)

        # 大标题
        big = QLabel(TITLE)
        big.setStyleSheet(f"color: {self.theme.text.name()}; font-size: 21px; font-weight: bold;")
        self.big_title = big
        cl.addWidget(big)
        self.subtitle = QLabel("正在扫描设备…")
        self.subtitle.setStyleSheet(f"color: {self.theme.text_dim.name()}; font-size: 12px;")
        cl.addWidget(self.subtitle)

        # 设备卡片网格
        self.cards_host = QWidget()
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        cl.addWidget(self.cards_host)
        cl.addStretch(1)

        # ---- 设置面板（左标签 + 分段按钮，iOS 风格）----
        panel = QWidget()
        panel.setObjectName("settingsPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 12, 16, 12)
        pl.setSpacing(10)

        lbl_set = QLabel("设置")
        lbl_set.setStyleSheet(f"color: {self.theme.text.name()}; font-size: 13px; font-weight: bold;")
        pl.addWidget(lbl_set)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        lbl_col = 150   # 标签列宽

        def _lbl(text):
            w = QLabel(text)
            w.setStyleSheet(f"color: {self.theme.text_dim.name()}; font-size: 12px;")
            w.setFixedWidth(lbl_col)
            return w

        # 立即刷新（放标题右侧）
        self.btn_refresh2 = QPushButton("立即刷新")
        self.btn_refresh2.setToolTip("手动扫描一遍设备电量")
        self.btn_refresh2.clicked.connect(self.refresh_requested.emit)

        # 刷新间隔
        self.seg_refresh = SegmentedControl(REFRESH_OPTIONS)
        self.seg_refresh.set_value(self.settings.refresh_seconds
                                   if self.settings.refresh_seconds in (15, 30, 60, 300) else 60)
        self.seg_refresh.value_changed.connect(self._on_refresh_changed)
        row_refresh = QHBoxLayout()
        row_refresh.addWidget(self.seg_refresh)
        row_refresh.addSpacing(16)
        row_refresh.addWidget(self.btn_refresh2)
        row_refresh.addStretch(1)
        grid.addWidget(_lbl("刷新间隔"), 0, 0)
        grid.addLayout(row_refresh, 0, 1)

        # 低电量提醒（开关 + 阈值同一行）
        self.seg_alert = SegmentedControl([("开", True), ("关", False)])
        self.seg_alert.set_value(self.settings.low_battery_alert)
        self.seg_alert.value_changed.connect(self._on_alert_toggled)
        self.seg_low = SegmentedControl([(f"{v}%", v) for v in LOW_THRESHOLD_OPTIONS])
        low = self.settings.low_battery_threshold
        self.seg_low.set_value(min(LOW_THRESHOLD_OPTIONS, key=lambda v: abs(v - low)))
        self.seg_low.value_changed.connect(self._on_low_threshold_changed)
        row_alert = QHBoxLayout()
        row_alert.setSpacing(14)
        row_alert.addWidget(self.seg_alert)
        row_alert.addWidget(self.seg_low)
        row_alert.addStretch(1)
        grid.addWidget(_lbl("低电量提醒"), 1, 0)
        grid.addLayout(row_alert, 1, 1)

        # 开机自启（以注册表实际状态为准）
        self._autostart_real = autostart_enabled()
        self.settings.autostart = self._autostart_real
        self.seg_autostart = SegmentedControl([("开", True), ("关", False)])
        self.seg_autostart.set_value(self._autostart_real)
        self.seg_autostart.value_changed.connect(self._on_autostart_toggled)
        grid.addWidget(_lbl("开机自启"), 2, 0)
        grid.addWidget(self._compact(self.seg_autostart), 2, 1)

        # 主题
        self.seg_theme = SegmentedControl(THEME_OPTIONS)
        self.seg_theme.set_value(self.settings.theme)
        self.seg_theme.value_changed.connect(self._on_theme_changed)
        grid.addWidget(_lbl("主题"), 3, 0)
        grid.addWidget(self._compact(self.seg_theme), 3, 1)

        # 屏蔽 Win 键：按进程拦截
        self.seg_winkey = SegmentedControl([("开", True), ("关", False)])
        self.seg_winkey.set_value(self.settings.winkey_block)
        self.seg_winkey.value_changed.connect(self._on_winkey_toggled)
        grid.addWidget(_lbl("屏蔽Win键"), 4, 0)
        grid.addWidget(self._compact(self.seg_winkey), 4, 1)

        self.lbl_winkey = QLabel()
        self.lbl_winkey.setStyleSheet(f"color: {self.theme.text_dim.name()}; font-size: 12px;")
        self.btn_winkey_add = QPushButton("添加程序…")
        self.btn_winkey_add.setToolTip("从当前正在运行的程序中选择，进入该程序时自动屏蔽 Win 键")
        self.btn_winkey_add.clicked.connect(self._on_winkey_add)
        self.btn_winkey_clear = QPushButton("清空")
        self.btn_winkey_clear.clicked.connect(self._on_winkey_clear)
        row_winkey = QHBoxLayout()
        row_winkey.setSpacing(8)
        row_winkey.addWidget(self.lbl_winkey, 1)
        row_winkey.addWidget(self.btn_winkey_add)
        row_winkey.addWidget(self.btn_winkey_clear)
        grid.addWidget(_lbl("屏蔽程序"), 5, 0)
        grid.addLayout(row_winkey, 5, 1)
        self._refresh_winkey_label()

        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(14)
        for seg in (self.seg_refresh, self.seg_low, self.seg_autostart,
                    self.seg_alert, self.seg_theme, self.seg_winkey):
            seg.set_theme(self.theme)
        pl.addLayout(grid)

        hint = QLabel("托盘运行中：右键托盘图标即可打开本窗口；重命名设备：右键设备卡片")
        hint.setStyleSheet(f"color: {self.theme.text_faint.name()}; font-size: 11px;")
        pl.addWidget(hint)

        row3 = QHBoxLayout()
        row3.addStretch(1)
        self.btn_quit = QPushButton("退出托盘程序")
        self.btn_quit.setStyleSheet(
            f"background: {'#B3382C' if self.theme.name == THEME_LIGHT else '#8C2A21'};"
            f" color: white; border: none; border-radius: 6px;")
        self.btn_quit.clicked.connect(self.quit_requested.emit)
        row3.addWidget(self.btn_quit)
        pl.addLayout(row3)
        cl.addWidget(panel)

        # ---- 底部状态 ----
        self.footer = QLabel("等待扫描…")
        self.footer.setStyleSheet(f"color: {self.theme.text_faint.name()}; font-size: 11px;")
        cl.addWidget(self.footer)

        # 用滚动区域包裹内容：窗口放不下时滚动，绝不把控件压扁/裁切
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 2px 2px 0; }"
            "QScrollBar::handle:vertical { background: rgba(128,128,128,110); border-radius: 4px;"
            " min-height: 32px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(128,128,128,170); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }")
        scroll.setWidget(content)
        self._scroll = scroll
        root.addWidget(scroll, 1)

    # ---------------------------------------------------------------- 圆角/拖拽
    def _apply_rounding(self):
        hwnd = int(self.winId())
        _enable_win11_rounding(hwnd)
        self._backdrop = _enable_backdrop(hwnd)

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() < 46:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and not self.isMaximized():
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        # 液态玻璃：半透明玻璃底（DWM backdrop 开启时透出亚克力模糊）
        p.fillPath(path, t.glass_bg)
        # 顶部高光渐变（玻璃反光）
        sheen = QLinearGradient(0, 0, 0, self.height())
        sheen.setColorAt(0, t.glass_sheen)
        sheen.setColorAt(0.4, QColor(255, 255, 255, 0))
        sheen.setColorAt(1, QColor(0, 0, 0, 10))
        p.fillPath(path, sheen)
        # 高光描边：左上亮、右下淡
        p.setPen(QPen(t.glass_border, 1.2))
        p.drawPath(path)
        p.end()

    # ---------------------------------------------------------------- 数据更新
    def _display_name(self, st: DeviceState) -> str:
        custom = getattr(st, "display_name", None)
        if custom:
            return custom
        return friendly_name(st.info)

    def _rename_device(self, payload: str):
        key, _, reset = payload.partition("\x00")
        st = next((s for s in self._states if s.key == key), None)
        if not st:
            return
        if reset:
            self.settings.set_custom_name(key, "")
            self._refresh_names()
            return
        from PySide6.QtWidgets import QInputDialog
        current = self._display_name(st)
        name, ok = QInputDialog.getText(self, "重命名设备",
                                        f"自定义设备名称（留空恢复默认）：\n{st.info.key}",
                                        text=current)
        if not ok:
            return
        self.settings.set_custom_name(key, name)
        self._refresh_names()

    def _refresh_names(self):
        """把 settings 中的自定义名同步到所有 DeviceState 并刷新显示。"""
        for st in self._states:
            st.display_name = self.settings.display_name(
                st.key, friendly_name(st.info))
        self.update_devices(self._states)

    def update_devices(self, states: list[DeviceState]):
        self._states = states
        self._last_update = time.time()
        seen = set()
        for st in states:
            seen.add(st.key)
            if st.key not in self._cards:
                card = DeviceCard(self.theme, dev_key=st.key)
                card.clicked.connect(lambda k=st.key: self._copy_device_info(k))
                card.rename_requested.connect(self._rename_device)
                card.copy_requested.connect(self._copy_device_info)
                idx = len(self._cards)
                self._cards[st.key] = card
                self.cards_layout.addWidget(card, idx // 2, idx % 2)
        # 移除失效卡片
        for key in list(self._cards.keys()):
            if key not in seen:
                card = self._cards.pop(key)
                self.cards_layout.removeWidget(card)
                card.deleteLater()
        self._relayout()
        for st in states:
            card = self._cards.get(st.key)
            if not card:
                continue
            r = st.reading
            if r is None:
                continue
            conn = "2.4G" if (r.connection or "2.4G") != "USB" else "USB"
            sub = f"{st.info.key} · {st.info.dongle_name or friendly_name(st.info)}"
            card.set_data(self._display_name(st), sub, conn, r.percent, r.status,
                          st.info.kind, r.charging)
        # 副标题：设备名列表
        names = []
        for st in states:
            if st.reading and st.reading.ok:
                names.append(self._display_name(st))
        if names:
            shown = " + ".join(names[:3]) + (f" 等 {len(names)} 个" if len(names) > 3 else "")
            self.subtitle.setText(shown)
        elif states:
            self.subtitle.setText("、".join(self._display_name(s) for s in states[:3]))
        else:
            self.subtitle.setText("未检测到 2.4G 设备")
        # 底部状态
        ok = sum(1 for s in states if s.reading and s.reading.ok)
        sleeping = sum(1 for s in states
                       if s.reading is not None and s.reading.status == ST_SLEEPING)
        t = time.strftime("%H:%M:%S", time.localtime(self._last_update))
        if ok == 0 and sleeping:
            self.footer.setText(f"设备休眠中，等待唤醒 · 上次更新 {t}")
        elif sleeping:
            self.footer.setText(f"更新于 {t} · {ok} 个在线，{sleeping} 个休眠"
                                f"（用一下设备即可唤醒）")
        else:
            self.footer.setText(f"更新于 {t} · 成功读取 {ok}/{len(states)} 个设备")
        # 延后一拍再算高度：刚 addWidget 时 sizeHint 还没更新，立即读会拿到旧值
        QTimer.singleShot(0, self._apply_auto_height)

    def _apply_auto_height(self):
        self._auto_height(len(self._cards))

    def _auto_height(self, n_cards: int):
        """按内容真实高度自适应窗口高度（用户手动缩放过则不打扰）。"""
        if self._user_resized or self.isMaximized():
            return
        # 用内容区真实 sizeHint（控件保持自然高度，窗口装不下时由滚动区兜底）
        if self._content.layout():
            self._content.layout().activate()
        content_h = self._content.sizeHint().height()
        # 兜底：内容最小高度锁定为自然高度，窗口再矮也不会把控件压扁（改为滚动）
        self._content.setMinimumHeight(content_h)
        # 根布局边距 10+10 + 顶部小标题栏 36
        needed = 56 + content_h
        avail = self.screen().availableGeometry().height()
        needed = min(needed, avail)
        if abs(self.height() - needed) > 8:
            self._auto_resizing = True   # 防止 resizeEvent 误标为用户缩放
            self.resize(self.width(), needed)
            self._auto_resizing = False

    def _relayout(self):
        """按窗口宽度重排卡片（每行 2 个，窄窗 1 个）。"""
        cols = 2 if self.width() >= 620 else 1
        for i, card in enumerate(self._cards.values()):
            self.cards_layout.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, event):
        old = event.oldSize()
        # 首次 show 时 oldSize 无效 (-1,-1)，不是用户缩放，必须排除
        if (not self._user_resized and not self._auto_resizing
                and old.isValid() and old != self.size()):
            self._user_resized = True
        self._relayout()
        super().resizeEvent(event)

    def _copy_device_info(self, key: str):
        st = next((s for s in self._states if s.key == key), None)
        if not st:
            return
        r = st.reading
        pct = f"{r.percent}%" if r and r.percent is not None else "-"
        proto = r.protocol if r else "-"
        text = (f"{self._display_name(st)}\n{st.info.key}\n"
                f"协议: {proto}\n电量: {pct}\n"
                f"集合: {[f'{i.usage_page:04X}:{i.usage:04X}' for i in st.info.vendor_collections]}")
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    # ---------------------------------------------------------------- 设置事件
    def _on_refresh_changed(self, secs):
        self.settings.refresh_seconds = int(secs)
        self.settings_changed.emit()

    def _on_low_threshold_changed(self, v):
        self.settings.low_battery_threshold = int(v)
        self.theme.low_threshold = int(v)
        self.settings_changed.emit()
        if self._states:
            self.update_devices(self._states)

    def _on_theme_changed(self, theme_name):
        self.settings.theme = str(theme_name)
        self.settings_changed.emit()

    def _on_autostart_toggled(self, checked: bool):
        ok = set_enabled(bool(checked))
        if not ok:
            self.seg_autostart.set_value(autostart_enabled())
        else:
            self.settings.autostart = bool(checked)

    def _on_alert_toggled(self, checked: bool):
        self.settings.low_battery_alert = bool(checked)

    # ---------------------------------------------------------------- 游戏模式（屏蔽 Win 键）
    def _refresh_winkey_label(self):
        procs = self.settings.winkey_processes
        if procs:
            full = "、".join(procs)
            fm = QFontMetrics(self.lbl_winkey.font())
            self.lbl_winkey.setText(fm.elidedText(full, Qt.ElideRight, 230))
            self.lbl_winkey.setToolTip("进入以下程序时 Win 键失效：\n" + "\n".join(procs))
        else:
            self.lbl_winkey.setText("未设置（添加程序后生效）")
            self.lbl_winkey.setToolTip("尚未添加任何程序")

    def _on_winkey_toggled(self, checked):
        self.settings.winkey_block = bool(checked)
        self.settings_changed.emit()

    def _on_winkey_add(self):
        from app.core.winkey_guard import list_windowed_processes
        procs = list_windowed_processes()
        current = self.settings.winkey_processes
        choices = [p for p in procs if p not in current]
        if not choices:
            self.footer.setText("没有可添加的程序（可能已全部添加）")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(
            self, "屏蔽 Win 键", "选择进入时要屏蔽 Win 键的程序：", choices, 0, False)
        if ok and name:
            cur = self.settings.winkey_processes
            cur.append(name)
            self.settings.winkey_processes = cur
            self._refresh_winkey_label()
            self.settings_changed.emit()
            self.footer.setText(f"已添加 {name}：进入该程序时 Win 键将失效")

    def _on_winkey_clear(self):
        self.settings.winkey_processes = []
        self._refresh_winkey_label()
        self.settings_changed.emit()
        self.footer.setText("已清空屏蔽程序列表")

    # ---------------------------------------------------------------- 主题
    def apply_theme(self, theme_name: str):
        self.theme = Theme(theme_name)
        self.theme.low_threshold = self.settings.low_battery_threshold
        self.setStyleSheet(self.theme.stylesheet())
        for card in self._cards.values():
            card.theme = self.theme
        self.update()
        self._rebuild_styles()

    def _rebuild_styles(self):
        t = self.theme
        self.subtitle.setStyleSheet(f"color: {t.text_dim.name()}; font-size: 12px;")
        self.footer.setStyleSheet(f"color: {t.text_faint.name()}; font-size: 11px;")
        self.small_title.setStyleSheet(f"color: {t.text_faint.name()}; font-size: 11px;")
        if hasattr(self, "lbl_winkey"):
            self.lbl_winkey.setStyleSheet(f"color: {t.text_dim.name()}; font-size: 12px;")
        self.big_title.setStyleSheet(f"color: {t.text.name()}; font-size: 21px; font-weight: bold;")
        panel = self.findChild(QWidget, "settingsPanel")
        if panel:
            # 必须用 HexArgb，否则半透明色 name() 输出纯白，夜间模式面板会变成白块
            panel.setStyleSheet(
                f"#settingsPanel {{ background: {t.card_bg.name(QColor.HexArgb)};"
                f" border: 1px solid {t.card_border.name(QColor.HexArgb)}; border-radius: 14px; }}")
        self.btn_quit.setStyleSheet(
            f"background: {'#B3382C' if t.name == THEME_LIGHT else '#8C2A21'};"
            f" color: white; border: none; border-radius: 6px;")
        for attr in ("seg_refresh", "seg_low", "seg_autostart",
                     "seg_alert", "seg_theme", "seg_winkey"):
            seg = self.findChild(SegmentedControl, attr) or getattr(self, attr, None)
            if seg:
                seg.set_theme(t)
        if self._states:
            self.update_devices(self._states)

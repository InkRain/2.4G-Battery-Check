"""自定义绘制控件：电池图标、设备插画、设备卡片。"""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Property, QPropertyAnimation, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QHideEvent, QPainter, QPainterPath,
                           QPixmap,
                           QPaintEvent, QPen, QShowEvent, QLinearGradient)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QPushButton, QWidget

from app.engine.models import ST_OK, ST_SLEEPING, ST_UNSUPPORTED, ST_ERROR, ST_NO_API
from app.ui.theme import Theme


# ---------------------------------------------------------------- 电池图标
class BatteryIcon(QWidget):
    """横向电池图形：外框 + 按电量比例的填充 + 正极头。"""

    def __init__(self, size: int = 26, parent=None):
        super().__init__(parent)
        self._percent = -1
        self._color = QColor("#B0B0B0")
        self._charging = False
        self.setFixedSize(size, int(size * 0.52))

    def set_state(self, percent, color: QColor, charging: bool = False):
        self._percent = percent
        self._color = color
        self._charging = charging
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        body_h = h * 0.72
        y0 = (h - body_h) / 2
        cap_w = max(2, w * 0.055)
        # 外框
        p.setPen(QPen(self._color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1, y0, w - cap_w - 2, body_h), 2.5, 2.5)
        # 正极头
        p.setBrush(self._color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(w - cap_w - 1, y0 + body_h * 0.28, cap_w, body_h * 0.44),
                          cap_w / 2, cap_w / 2)
        # 填充
        if self._percent is not None and self._percent >= 0:
            inner = QRectF(3, y0 + 2, (w - cap_w - 6) * 0.94, body_h - 4)
            fill_w = inner.width() * max(0.0, min(1.0, self._percent / 100.0))
            p.setPen(Qt.NoPen)
            p.setBrush(self._color)
            p.drawRoundedRect(QRectF(inner.x(), inner.y(), fill_w, inner.height()), 1.5, 1.5)
            if self._charging:
                # 闪电标记
                p.setPen(QPen(QColor("#FFFFFF"), 1.2))
                cx = inner.x() + inner.width() * 0.5
                cy = inner.y() + inner.height() * 0.5
                path = QPainterPath(QPointF(cx - 1.5, cy - 4))
                path.lineTo(cx + 2, cy - 0.5)
                path.lineTo(cx - 0.5, cy + 0.5)
                path.lineTo(cx + 2, cy + 4)
                p.drawPath(path)
        p.end()


# ---------------------------------------------------------------- 设备插画
def draw_keyboard(p: QPainter, rect: QRectF, theme: Theme):
    """S99 风格键盘插画：米白机身 + 蓝灰/深色键帽。"""
    p.setRenderHint(QPainter.Antialiasing)
    # 机身
    body = QPainterPath()
    body.addRoundedRect(rect, 6, 6)
    p.fillPath(body, QColor("#E8E4DC"))
    p.setPen(QPen(QColor("#C9C4B8"), 1))
    p.drawPath(body)
    # 键区
    margin_x = rect.width() * 0.055
    margin_y = rect.height() * 0.14
    kb = QRectF(rect.x() + margin_x, rect.y() + margin_y,
                rect.width() - margin_x * 2, rect.height() - margin_y * 2)
    rows, cols = 5, 15
    gap = kb.width() * 0.006
    kw = (kb.width() - gap * (cols - 1)) / cols
    kh = (kb.height() - gap * (rows - 1)) / rows
    key_colors = ["#3B4A5A", "#5A6B7C", "#2E3A46"]
    accent = QColor("#6E86A0")
    dark = QColor("#2B3540")
    cream = QColor("#DDE3E8")
    for r in range(rows):
        for c in range(cols):
            x = kb.x() + c * (kw + gap)
            y = kb.y() + r * (kh + gap)
            w = kw
            # 特殊键宽
            if r == 0 and c in (0, cols - 1):
                w = kw * 1.15
            if r == rows - 1 and c == 0:
                w = kw * 1.3
            if r == rows - 1 and c == cols - 3:
                w = kw * 2.2  # 空格
            if r == rows - 1 and c in (cols - 2, cols - 1):
                continue  # 留给空格
            if r == rows - 1 and c > cols - 4:
                continue
            color = dark
            if (r + c) % 5 == 0:
                color = accent
            elif (r * cols + c) % 7 == 3:
                color = cream
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, w, kh), 1.5, 1.5)
    # 顶部装饰条
    p.setBrush(QColor("#8FA3B8"))
    p.drawRoundedRect(QRectF(rect.x() + rect.width() * 0.36, rect.y() + rect.height() * 0.045,
                             rect.width() * 0.28, rect.height() * 0.05), 2, 2)


def draw_mouse(p: QPainter, rect: QRectF, theme: Theme):
    """黑色游戏鼠标插画。"""
    p.setRenderHint(QPainter.Antialiasing)
    cx = rect.center().x()
    top = rect.y() + rect.height() * 0.02
    w = rect.width() * 0.62
    h = rect.height() * 0.96
    x = cx - w / 2
    body = QPainterPath()
    body.addRoundedRect(QRectF(x, top, w, h), w * 0.42, w * 0.42)
    grad = QLinearGradient(0, top, 0, top + h)
    grad.setColorAt(0, QColor("#4A4A4A"))
    grad.setColorAt(1, QColor("#232323"))
    p.fillPath(body, grad)
    p.setPen(QPen(QColor("#141414"), 1))
    p.drawPath(body)
    # 滚轮
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#6A6A6A"))
    p.drawRoundedRect(QRectF(cx - w * 0.05, top + h * 0.20, w * 0.10, h * 0.17),
                      w * 0.05, w * 0.05)
    # 左右键分隔线
    p.setPen(QPen(QColor("#5A5A5A"), 1.2))
    p.drawLine(QPointF(cx, top + h * 0.09), QPointF(cx, top + h * 0.30))
    # 侧键
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1E1E1E"))
    p.drawRoundedRect(QRectF(x - w * 0.05, top + h * 0.40, w * 0.055, h * 0.11), 2, 2)
    # LOGO 点
    p.setBrush(QColor("#7A7A7A"))
    p.drawEllipse(QPointF(cx, top + h * 0.60), w * 0.06, w * 0.06)


def draw_headset(p: QPainter, rect: QRectF, theme: Theme):
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#4A4A4A"), max(2, rect.width() * 0.06)))
    p.drawArc(QRectF(rect.x(), rect.y(), rect.width(), rect.height() * 0.9), 0, 180 * 16)
    p.setBrush(QColor("#333333"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(rect.x() - rect.width() * 0.02, rect.y() + rect.height() * 0.42,
                             rect.width() * 0.14, rect.height() * 0.3), 3, 3)
    p.drawRoundedRect(QRectF(rect.x() + rect.width() * 0.88, rect.y() + rect.height() * 0.42,
                             rect.width() * 0.14, rect.height() * 0.3), 3, 3)


def draw_device_icon(p: QPainter, rect: QRectF, kind: str, theme: Theme):
    if kind == "keyboard":
        draw_keyboard(p, rect, theme)
    elif kind == "mouse":
        draw_mouse(p, rect, theme)
    elif kind == "headset":
        draw_headset(p, rect, theme)
    else:
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(theme.text_dim, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)
        p.drawText(rect, Qt.AlignCenter, "USB")


# ---------------------------------------------------------------- 产品图缓存
_ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "resources")
_ICON_MAP = {
    "391D:2A02": "icon_v108.png",       # VGN V108
    "391D:1A05": "icon_dragonfly.png",  # Dragonfly 3 Master+ (2.4G dongle)
    "391D:1005": "icon_dragonfly.png",  # Dragonfly 3 Master (USB 直连)
    "391D:1A25": "icon_dragonfly.png",  # Dragonfly 3 Ultra（2.4G，与 3 代同外形）
    "391D:1028": "icon_dragonfly.png",  # Dragonfly 3 Ultra（有线）
}
_ICON_CACHE: dict = {}


def device_photo(key: str):
    """返回设备产品图（QPixmap），无则 None。"""
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    pm = None
    fname = _ICON_MAP.get(key)
    if fname:
        path = os.path.join(_ICON_DIR, fname)
        if os.path.exists(path):
            pm = QPixmap(path)
    _ICON_CACHE[key] = pm
    return pm


# ---------------------------------------------------------------- 设备卡片
class DeviceCard(QWidget):
    """主窗口设备卡片：产品图/插画 + 名称 + ID + 连接方式 + 电量。"""
    clicked = Signal()
    rename_requested = Signal(str)    # dev_key
    copy_requested = Signal(str)      # dev_key

    def __init__(self, theme: Theme, dev_key: str = "", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.dev_key = dev_key
        self.setFixedSize(240, 224)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self._name = ""
        self._sub = ""
        self._conn = ""
        self._percent = None
        self._status = ST_UNSUPPORTED
        self._kind = "other"
        self._charging = False
        self._hover = False

    def set_data(self, name: str, sub: str, conn: str, percent, status: str,
                 kind: str, charging: bool = False):
        self._name = name
        self._sub = sub
        self._conn = conn
        self._percent = percent
        self._status = status
        self._kind = kind
        self._charging = charging
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        # 玻璃卡片底：半透明 + 悬停微亮 + 内高光描边
        card = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(Qt.NoPen)
        p.setBrush(t.card_bg)
        p.drawRoundedRect(card, 14, 14)
        if self._hover:
            p.setBrush(QColor(255, 255, 255, 26))
            p.drawRoundedRect(card, 14, 14)
        p.setPen(QPen(t.card_border, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(card, 14, 14)
        # 插画：优先产品图，缺图退回手绘
        dev_key = (self._sub or "").split(" · ")[0]
        photo = device_photo(dev_key)
        if photo is not None and not photo.isNull():
            if self._kind == "keyboard":
                target = QRectF(18, 26, self.width() - 36, 82)
            else:
                target = QRectF(self.width() * 0.5 - 58, 16, 116, 84)
            scaled = photo.scaled(int(target.width()), int(target.height()),
                                  Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(QRectF(
                target.x() + (target.width() - scaled.width()) / 2,
                target.y() + (target.height() - scaled.height()) / 2,
                scaled.width(), scaled.height()).toRect(), scaled)
        else:
            art = QRectF(self.width() * 0.5 - 88, 16, 176, 84)
            if self._kind == "mouse":
                art = QRectF(self.width() * 0.5 - 55, 14, 110, 88)
            draw_device_icon(p, art, self._kind, self.theme)
        # 名称
        f = QFont("Segoe UI", 12, QFont.Bold)
        p.setFont(f)
        p.setPen(self.theme.text)
        name = QFontMetrics(f).elidedText(self._name, Qt.ElideRight, self.width() - 32)
        p.drawText(QRectF(8, 108, self.width() - 16, 22), Qt.AlignCenter, name)
        # ID 行
        f2 = QFont("Segoe UI", 8)
        p.setFont(f2)
        p.setPen(self.theme.text_faint)
        sub = QFontMetrics(f2).elidedText(self._sub, Qt.ElideRight, self.width() - 24)
        p.drawText(QRectF(6, 130, self.width() - 12, 16), Qt.AlignCenter, sub)
        # 底部行
        dot_color = self.theme.battery_color(self._percent, self._status)
        p.setPen(Qt.NoPen)
        p.setBrush(dot_color if self._status == ST_OK else self.theme.batt_unknown)
        p.drawEllipse(QPointF(24, self.height() - 24), 3.5, 3.5)
        f3 = QFont("Segoe UI", 9)
        p.setFont(f3)
        if self._status == ST_OK and self._charging:
            # 充电中：橙色文字提示，优先于连接方式展示
            p.setPen(QPen(QColor("#F0A020"), 1))
            p.drawText(QRectF(32, self.height() - 32, 110, 18), Qt.AlignVCenter, "⚡ 充电中")
        else:
            p.setPen(self.theme.text_dim)
            if self._status == ST_SLEEPING:
                conn_label = "休眠"
            elif self._status == ST_NO_API:
                conn_label = "2.4G"
            else:
                conn_label = self._conn
            p.drawText(QRectF(32, self.height() - 32, 110, 18), Qt.AlignVCenter, conn_label)
        # 电量文字 + 图标
        color = self.theme.battery_color(self._percent, self._status)
        if self._status == ST_OK and self._charging:
            color = QColor("#2ECC71")   # 充电中统一用绿色
        if self._status == ST_OK and self._percent is not None:
            pct_text = f"{self._percent}%"
        elif self._status == ST_SLEEPING:
            pct_text = f"{self._percent}%" if self._percent is not None else "休眠"
        elif self._status == ST_NO_API:
            pct_text = "未开放"
        elif self._status == ST_ERROR:
            pct_text = "失败"
        else:
            pct_text = "不支持"
        f4 = QFont("Segoe UI", 11, QFont.Bold)
        p.setFont(f4)
        p.setPen(color)
        p.drawText(QRectF(self.width() - 122, self.height() - 34, 68, 22),
                   Qt.AlignRight | Qt.AlignVCenter, pct_text)
        # 电池图标
        bw, bh = 26, 13
        bx = self.width() - 20 - bw
        by = self.height() - 27
        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(bx, by, bw - 3, bh), 2.5, 2.5)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(bx + bw, by + bh * 0.3, 3, bh * 0.4), 1.5, 1.5)
        if self._status == ST_OK and self._percent is not None:
            inner_w = (bw - 7) * 0.92
            fill = inner_w * max(0.0, min(1.0, self._percent / 100.0))
            p.drawRoundedRect(QRectF(bx + 2, by + 2, fill, bh - 4), 1.5, 1.5)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_rename = menu.addAction("✏️ 重命名设备")
        act_copy = menu.addAction("📋 复制设备信息")
        act_reset = menu.addAction("↩ 恢复默认名称")
        chosen = menu.exec(event.globalPos())
        if chosen is act_rename:
            self.rename_requested.emit(self.dev_key)
        elif chosen is act_copy:
            self.copy_requested.emit(self.dev_key)
        elif chosen is act_reset:
            self.rename_requested.emit(self.dev_key + "\x00reset")

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)


# ---------------------------------------------------------------- 分段按钮
class SegmentedControl(QWidget):
    """iOS 风格分段选择按钮（单选，选中项实心高亮）。"""
    value_changed = Signal(object)

    def __init__(self, options: list, parent=None):
        """options: [(label, value), ...]"""
        super().__init__(parent)
        self._buttons: list = []
        self._values: list = [v for _, v in options]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for label, value in options:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(30)
            b.setMinimumWidth(58)
            b.clicked.connect(self._on_click)
            lay.addWidget(b)
            self._buttons.append((b, value))
        self._value = None
        self._apply_style(None)

    def _apply_style(self, theme):
        txt = (theme.btn_text.name() if theme else "#333333")
        for b, _ in self._buttons:
            # padding 只用水平值 + min-height，避免垂直 padding 挤压中文行高导致文字被裁
            b.setStyleSheet(
                "QPushButton { background: rgba(128,128,128,36); color: " + txt + ";"
                " border: none; border-radius: 9px; padding: 0 14px; min-height: 24px;"
                " font-size: 12px; }"
                "QPushButton:checked { background: #2FA84F; color: white; font-weight: bold; }"
                "QPushButton:hover:!checked { background: rgba(128,128,128,60); }")

    def set_theme(self, theme):
        self._apply_style(theme)

    def _on_click(self):
        clicked = self.sender()
        for b, v in self._buttons:
            b.setChecked(b is clicked)
        new_val = self.value()
        if new_val != self._value:
            self._value = new_val
            self.value_changed.emit(new_val)

    def set_value(self, v):
        for b, val in self._buttons:
            b.setChecked(val == v)
        self._value = v

    def value(self):
        for b, v in self._buttons:
            if b.isChecked():
                return v
        return None

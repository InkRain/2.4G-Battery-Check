"""托盘弹窗卡片（液态玻璃风格，右下角）。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app.core.settings import APP_TITLE
from app.engine.models import ST_OK, ST_NO_API
from app.engine.scanner import DeviceState
from app.ui.theme import Theme
from app.ui.widgets import device_photo, draw_device_icon

ROW_H = 50
PAD = 14


def _display(st: DeviceState) -> str:
    custom = getattr(st, "display_name", None)
    if custom:
        return custom
    return getattr(st.info, "dongle_name", "") or st.info.key


class TrayPopup(QWidget):
    """点击托盘图标弹出的小卡片。"""

    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self._states: list[DeviceState] = []
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(self.theme.stylesheet())

    def set_theme(self, theme: Theme):
        self.theme = theme
        self.setStyleSheet(theme.stylesheet())

    def update_states(self, states: list[DeviceState]):
        self._states = states
        h = PAD + 26 + len(states) * ROW_H + PAD
        self.setFixedWidth(312)
        self.setFixedHeight(max(h, 92))
        self.update()

    def _anchor(self):
        """定位到屏幕右下角，紧贴任务栏（仅留极小间隙）。"""
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()       # 工作区（已排除任务栏）
        full = screen.geometry()               # 整屏（含任务栏）
        margin = 6                             # 与任务栏之间留 6px，几乎贴合
        x = geo.right() - self.width() - 16    # 右侧留 16px
        # 任务栏在底部（最常见）：弹窗贴在任务栏上沿
        if geo.bottom() < full.bottom():
            y = geo.bottom() - self.height() - margin
        elif geo.top() > full.top():           # 任务栏在顶部
            y = geo.top() + margin
        else:
            y = geo.bottom() - self.height() - margin
        self.move(x, y)

    def showEvent(self, event):
        self._anchor()
        super().showEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        # ---- 玻璃底：半透明面板 + 顶部高光 + 内亮描边 ----
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 18, 18)
        p.fillPath(path, t.tray_bg)
        sheen = QLinearGradient(0, 0, 0, self.height())
        sheen.setColorAt(0, t.glass_sheen)
        sheen.setColorAt(0.45, QColor(255, 255, 255, 0))
        sheen.setColorAt(1, QColor(0, 0, 0, 12))
        p.fillPath(path, sheen)
        p.setPen(QPen(t.tray_border, 1.2))
        p.drawPath(path)

        x, y = PAD, PAD
        # 标题
        f = QFont("Segoe UI", 12, QFont.Bold)
        p.setFont(f)
        p.setPen(t.text)
        p.drawText(QRectF(x, y, self.width() - PAD * 2, 22), Qt.AlignLeft, APP_TITLE)
        y += 26
        # 分割线
        p.setPen(QPen(t.divider, 1))
        p.drawLine(x, y - 4, self.width() - PAD, y - 4)

        if not self._states:
            p.setPen(t.text_dim)
            f2 = QFont("Segoe UI", 10)
            p.setFont(f2)
            p.drawText(QRectF(x, y, self.width() - PAD * 2, ROW_H),
                       Qt.AlignVCenter, "未检测到 2.4G 设备")
            p.end()
            return

        for st in self._states:
            r = st.reading
            # 图标：优先产品图（等比缩放进 36x32 区域内）
            dev_key = st.info.key
            photo = device_photo(dev_key)
            icon_rect = QRectF(x, y + 8, 36, 32)
            if photo is not None and not photo.isNull():
                scaled = photo.scaled(36, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(QRectF(
                    icon_rect.x() + (icon_rect.width() - scaled.width()) / 2,
                    icon_rect.y() + (icon_rect.height() - scaled.height()) / 2,
                    scaled.width(), scaled.height()).toRect(), scaled)
            else:
                draw_device_icon(p, icon_rect, st.info.kind, t)
            # 名称 + 连接
            f3 = QFont("Segoe UI", 10, QFont.Bold)
            p.setFont(f3)
            p.setPen(t.text)
            name = _display(st)
            p.drawText(QRectF(x + 46, y + 4, 168, 18), Qt.AlignLeft, name)
            f4 = QFont("Segoe UI", 8)
            p.setFont(f4)
            p.setPen(t.text_faint)
            sleeping = r is not None and r.status == "sleeping"
            no_api = r is not None and r.status == ST_NO_API
            if r is not None and r.status == ST_OK and r.charging:
                conn = "⚡ 充电中"
            elif sleeping:
                conn = "休眠 · 动一下唤醒"
            else:
                conn = (r.connection if r else "") or "2.4G"
            p.drawText(QRectF(x + 46, y + 24, 168, 16), Qt.AlignLeft, conn)
            # 电量
            color = t.battery_color(r.percent if r else None, r.status if r else "x")
            if sleeping or no_api:
                color = t.batt_unknown
            if r is not None and r.status == ST_OK and r.charging:
                color = QColor("#2ECC71")
            f5 = QFont("Segoe UI", 12, QFont.Bold)
            p.setFont(f5)
            p.setPen(color)
            if r and r.status == ST_OK and r.percent is not None:
                text = f"{r.percent}%"
            elif sleeping:
                text = f"{r.percent}%" if (r and r.percent is not None) else "休眠"
            elif no_api:
                text = "未开放"
            else:
                text = "--"
            p.drawText(QRectF(self.width() - PAD - 76, y + 10, 76, 26),
                       Qt.AlignRight | Qt.AlignVCenter, text)
            # 分隔
            if st is not self._states[-1]:
                p.setPen(QPen(t.divider, 1))
                p.drawLine(x, y + ROW_H - 2, self.width() - PAD, y + ROW_H - 2)
            y += ROW_H
        p.end()

    def mousePressEvent(self, event: QMouseEvent):
        self.close()
        super().mousePressEvent(event)

"""右下角低电量/提醒小弹窗（液态玻璃风格 toast）。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.theme import Theme

W, H = 300, 78
MARGIN = 16
GAP = 10
LIFE_MS = 5000

_active: list["Toast"] = []


class Toast(QWidget):
    """屏幕右下角自动消失的玻璃小弹窗。"""

    def __init__(self, theme: Theme, title: str, body: str, accent: QColor):
        super().__init__()
        self.theme = theme
        self.title = title
        self.body = body
        self.accent = accent
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(W, H)
        _active.append(self)
        self._reposition()
        QTimer.singleShot(LIFE_MS, self._expire)

    # ---- 布局 ----
    @staticmethod
    def _reposition():
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        y = geo.bottom() - 8
        for t in reversed(_active):
            y -= (H + GAP)
            t.move(geo.right() - W - MARGIN, y)

    def _expire(self):
        if self in _active:
            _active.remove(self)
        self.close()
        self.deleteLater()
        Toast._reposition()

    @staticmethod
    def notify(theme: Theme, title: str, body: str, accent: QColor):
        t = Toast(theme, title, body, accent)
        t.show()
        Toast._reposition()
        return t

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.theme
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, W - 2, H - 2), 16, 16)
        p.fillPath(path, t.tray_bg)
        sheen = QLinearGradient(0, 0, 0, H)
        sheen.setColorAt(0, t.glass_sheen)
        sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, sheen)
        p.setPen(QPen(t.tray_border, 1.2))
        p.drawPath(path)
        # 左侧强调竖条
        p.setPen(Qt.NoPen)
        p.setBrush(self.accent)
        p.drawRoundedRect(QRectF(10, 14, 4, H - 28), 2, 2)
        # 标题 + 正文
        f = QFont("Segoe UI", 10, QFont.Bold)
        p.setFont(f)
        p.setPen(t.text)
        p.drawText(QRectF(26, 12, W - 38, 20), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f2 = QFont("Segoe UI", 9)
        p.setFont(f2)
        p.setPen(t.text_dim)
        p.drawText(QRectF(26, 36, W - 38, 34), Qt.AlignLeft | Qt.TextWordWrap, self.body)
        p.end()

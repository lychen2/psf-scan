"""1px polyline sparkline — 给 meter bar 嵌入紧凑的数值趋势。

仪器面板风格:浅色背景、单像素描边、不开 AA。每个像素就是一个像素,
让眼睛对趋势的判断不被插值模糊。
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QWidget

from . import theme


class Sparkline(QWidget):
    """把最近 ``capacity`` 个数值画成 1px 折线;最新值落在右边。

    Y 轴按当前缓冲的 min/max 自适应,常量序列居中渲染。重置 / 清空缓冲后
    会清掉折线,只剩底色。
    """

    def __init__(
        self,
        *,
        width: int = 60,
        height: int = 14,
        capacity: int = 60,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._w = int(width)
        self._h = int(height)
        self._cap = int(capacity)
        self._values: deque[float] = deque(maxlen=self._cap)
        self._bg = QColor(theme.BG0)
        self._fg = QColor(theme.TEXT2)
        # 复用同一支 QPen 而不是每帧 new 一根——cosmetic 1px 都不会变。
        self._pen = QPen(self._fg)
        self._pen.setWidth(1)
        self._pen.setCosmetic(True)
        self.setFixedSize(self._w, self._h)
        self.setAutoFillBackground(False)

    def push(self, value: float) -> None:
        self._values.append(float(value))
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(self._w, self._h)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            p.fillRect(self.rect(), self._bg)
            n = len(self._values)
            if n < 2:
                return
            xs = list(self._values)
            lo = min(xs)
            hi = max(xs)
            span = hi - lo if hi > lo else 0.0
            p.setPen(self._pen)
            inset = 1
            usable_h = self._h - 2 * inset - 1
            x_step = (self._w - 2 * inset) / max(1, n - 1)
            # 一次 drawPolyline 走完 60 段——比 n 次 drawLine 跨 Python/Qt 边界省一个数量级。
            polyline = QPolygon()
            for i, v in enumerate(xs):
                norm = (v - lo) / span if span > 0 else 0.5
                y = self._h - inset - norm * usable_h
                x = inset + i * x_step
                polyline.append(QPoint(int(round(x)), int(round(y))))
            p.drawPolyline(polyline)
        finally:
            p.end()

"""带刻度标记的进度条 — 给一维进度增加几何尺度感。

刻度按比例叠绘在进度条上,无论被填充覆盖与否都可见。配合 PSF 扫描的
"已采 / 计划"语义,让 ``47 / 124`` 这种数字也能凭眼一瞥估出位置。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QProgressBar

from . import theme


class ProgressWithTicks(QProgressBar):
    """QProgressBar 子类:支持在 [0, 1] 区间内绘制若干 1px 刻度。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fractions: list[float] = []
        self._tick_color = QColor(theme.TEXT2)
        self._tick_color.setAlpha(150)
        # QPen 复用——避免每个 paintEvent 都构造一次。1px cosmetic,属性永远不变。
        self._tick_pen = QPen(self._tick_color)
        self._tick_pen.setWidth(1)
        self._tick_pen.setCosmetic(True)

    def set_tick_positions(self, fractions: Sequence[float]) -> None:
        clean = sorted(
            f for f in (float(x) for x in fractions) if 0.0 <= f <= 1.0
        )
        if clean == self._fractions:
            return
        self._fractions = clean
        self.update()

    def clear_ticks(self) -> None:
        if not self._fractions:
            return
        self._fractions = []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().paintEvent(event)
        if not self._fractions:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            p.setPen(self._tick_pen)
            w = self.width()
            h = self.height()
            for f in self._fractions:
                x = int(round(f * (w - 1)))
                p.drawLine(x, 1, x, h - 2)
        finally:
            p.end()

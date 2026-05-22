"""位移台位置可视化 — 单轴 Z 数轴。

颜色绑定到 theme：当前位置 signal，已采样 sampled，未访问 neutral。
软限位用 DANGER 色虚线垂直穿过数轴。
30 Hz 节流重绘以避免被 60 Hz 信号打爆。
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from . import theme
from ..core.i18n import tr
from ..core.safety import SafetyLimits
from .widgets import HintLabel


_BR_PATH = pg.mkBrush(theme.BORDER1)
_BR_DONE = pg.mkBrush(theme.DONE)
_BR_CUR = pg.mkBrush(theme.ACCENT)
_PEN_CUR = pg.mkPen(theme.CANVAS_BG, width=1)
_PEN_LIMIT = pg.mkPen(theme.DANGER, width=1, style=Qt.DashLine)
_AXIS_COLOR = pg.mkColor(theme.TEXT3)

_GHOST_MAX = 12
_STAGE_VIEW_HEIGHT = 118
_Z_PLOT_HEIGHT = 78
_BOTTOM_AXIS_HEIGHT = 36
_AXIS_TICK_TEXT_OFFSET = 8


def _limit_line(angle: int, value: float = 0.0) -> pg.InfiniteLine:
    line = pg.InfiniteLine(pos=value, angle=angle, pen=_PEN_LIMIT, movable=False)
    line.setVisible(False)
    return line


class StageView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StageView")
        self.setStyleSheet(f"background:{theme.BG0};")
        self.setFixedHeight(_STAGE_VIEW_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        plots = QWidget()
        h = QHBoxLayout(plots)
        h.setContentsMargins(theme.G_8, theme.G_4, theme.G_8, theme.G_4)
        h.setSpacing(theme.G_8)
        self._z = self._make_z()
        h.addWidget(self._z, stretch=1)
        outer.addWidget(plots, stretch=1)

        legend = QWidget()
        legend.setStyleSheet(f"background:{theme.BG0};border-top:1px solid {theme.BORDER0};")
        lh = QHBoxLayout(legend)
        lh.setContentsMargins(theme.G_16, theme.G_4, theme.G_16, theme.G_4)
        lh.setSpacing(theme.G_16)
        for color, text, *opt in (
            (theme.ACCENT, tr("stage.current_pos")),
            (theme.ACCENT, tr("stage.trail"), 130),
            (theme.DONE, tr("stage.sampled")),
            (theme.BORDER1, tr("stage.planned")),
            (theme.DANGER, tr("stage.soft_limit")),
        ):
            alpha = opt[0] if opt else 255
            lh.addWidget(_swatch(color, alpha))
            lh.addWidget(HintLabel(text))
        lh.addStretch()
        outer.addWidget(legend)

        # Z items (horizontal: X coordinate used for Z value)
        self._path_z = pg.ScatterPlotItem(size=4, brush=_BR_PATH, pen=None, symbol="o")
        self._ghost_item = pg.ScatterPlotItem(size=5, pen=None, symbol="o")
        self._done_z = pg.ScatterPlotItem(size=7, brush=_BR_DONE, pen=None, symbol="o")
        self._cur_z = pg.ScatterPlotItem(size=14, brush=_BR_CUR, pen=_PEN_CUR, symbol="o")

        # Ensure markers are above axis and grid lines
        for it in (self._path_z, self._ghost_item, self._done_z, self._cur_z):
            it.setZValue(1000)

        self._lim_zmin = _limit_line(90) # Vertical line at Z min
        self._lim_zmax = _limit_line(90) # Vertical line at Z max
        for it in (self._lim_zmin, self._lim_zmax, self._path_z, self._ghost_item, self._done_z, self._cur_z):
            self._z.addItem(it)

        # Pre-computed alpha-fading brushes; index 0 = oldest/faintest, -1 = newest/brightest.
        self._ghost_brushes: list[pg.QtGui.QBrush] = []
        for i in range(_GHOST_MAX):
            alpha = int(round(30 + (180 - 30) * i / (_GHOST_MAX - 1)))
            c = pg.mkColor(theme.ACCENT)
            c.setAlpha(alpha)
            self._ghost_brushes.append(pg.mkBrush(c))
        self._ghost: deque[float] = deque(maxlen=_GHOST_MAX)

        self._latest: Optional[tuple[float, float, float]] = None
        self._done_idx: list[int] = []
        self._path: Optional[np.ndarray] = None
        self._limits_zrange: Optional[tuple[float, float]] = None
        self._dirty = False

        self._tick = QTimer(self)
        self._tick.setInterval(33)  # ~30 Hz
        self._tick.timeout.connect(self._refresh)
        self._tick.start()

    @Slot(object)
    def set_safety_limits(self, limits: SafetyLimits) -> None:
        """更新软限位虚线。仅关注 Z。"""
        on = bool(limits.enabled)
        zmin = float(limits.z_min)
        zmax = float(limits.z_max)
        self._lim_zmin.setPos(zmin)
        self._lim_zmax.setPos(zmax)
        self._lim_zmin.setVisible(on)
        self._lim_zmax.setVisible(on)
        self._limits_zrange = (zmin, zmax) if (on and zmax > zmin) else None
        self._apply_x_range()

    def set_single_axis(self, _on: bool) -> None:
        """不再需要，始终是单轴 Z。"""
        pass

    def _make_z(self) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setBackground(theme.CANVAS_BG)
        pw.setLabel("bottom", tr("stage.z"), units="µm", color=theme.TEXT3)
        pw.getAxis("left").hide()
        pw.showGrid(x=True, alpha=0.18)
        pw.setMouseEnabled(x=False, y=False)
        pw.setMenuEnabled(False)
        pw.setFixedHeight(_Z_PLOT_HEIGHT)

        vb = pw.getViewBox()
        # Y 锁死 (-1, 1) — marker 都在 y=0,不能被 autoRange 压扁;X 自动 View All 跟随数据
        vb.setYRange(-1, 1, padding=0)
        vb.setXRange(-50, 50, padding=0)
        vb.enableAutoRange(axis="x")
        vb.disableAutoRange(axis="y")

        ax = pw.getAxis("bottom")
        ax.setPen(theme.BORDER1)
        ax.setTextPen(theme.TEXT3)
        ax.setHeight(_BOTTOM_AXIS_HEIGHT)
        ax.setTickFont(QFont(theme.SANS, theme.BASE_FONT_PT))
        ax.setStyle(
            tickTextOffset=_AXIS_TICK_TEXT_OFFSET,
            autoExpandTextSpace=True,
            autoReduceTextSpace=False,
        )
        ax.setZValue(-100)

        return pw

    @Slot(float, float, float)
    def set_position(self, x: float, y: float, z: float) -> None:
        if self._latest is not None:
            self._ghost.append(self._latest[2])
        self._latest = (x, y, z)
        self._dirty = True

    @Slot(object)
    def set_scan_path(self, path: np.ndarray) -> None:
        self._path = np.asarray(path, dtype=np.float64)
        self._done_idx = []
        if self._path.size:
            # Horizontal Z: values are on X axis, Y is 0
            self._path_z.setData(x=self._path[:, 2], y=np.zeros(len(self._path)))
        self._done_z.setData(x=[], y=[])
        self._apply_x_range()
        self._dirty = True

    def clear_path(self) -> None:
        self._path = None
        self._done_idx = []
        for s in (self._path_z, self._done_z):
            s.setData(x=[], y=[])
        self._ghost.clear()
        self._ghost_item.setData(x=[], y=[])
        self._apply_x_range()

    @Slot(int)
    def mark_done(self, idx: int) -> None:
        self._done_idx.append(idx)
        self._dirty = True

    def _refresh(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        if self._latest is not None:
            _x, _y, z = self._latest
            self._cur_z.setData(x=[z], y=[0])
            if self._path is None and self._limits_zrange is None:
                self._maybe_recenter_x(z)
        if self._path is not None and self._done_idx:
            done_z = self._path[self._done_idx, 2]
            self._done_z.setData(x=done_z, y=np.zeros(len(done_z)))
        if self._ghost:
            n = len(self._ghost)
            zs = list(self._ghost)
            brushes = self._ghost_brushes[_GHOST_MAX - n:]
            self._ghost_item.setData(x=zs, y=[0.0] * n, brush=brushes)

    def _maybe_recenter_x(self, z: float) -> None:
        """无路径无限位时:marker 进入边缘 10% 才把视窗推过去,避免抖动。"""
        vb = self._z.getViewBox()
        (x0, x1), _ = vb.viewRange()
        width = x1 - x0
        margin = width * 0.1
        if x0 + margin <= z <= x1 - margin:
            return
        new_width = max(width, 100.0)
        vb.disableAutoRange(axis="x")
        vb.setXRange(z - new_width / 2, z + new_width / 2, padding=0)

    def _apply_x_range(self) -> None:
        """X 视图 = scan path 和 soft-limit 范围的并集;两者都缺时恢复 autoRange。"""
        vb = self._z.getViewBox()
        lo: Optional[float] = None
        hi: Optional[float] = None
        if self._path is not None and self._path.size:
            zs = self._path[:, 2]
            lo = float(zs.min())
            hi = float(zs.max())
        if self._limits_zrange is not None:
            zmin, zmax = self._limits_zrange
            soft_pad = max((zmax - zmin) * 0.06, 4.0)
            lo = zmin - soft_pad if lo is None else min(lo, zmin - soft_pad)
            hi = zmax + soft_pad if hi is None else max(hi, zmax + soft_pad)
        if lo is None or hi is None or hi - lo < 1e-9:
            # 没有路径也没有限位时锁回默认 ±50 µm 视图;否则 autoRange 会追单点抖动。
            vb.disableAutoRange(axis="x")
            vb.setXRange(-50, 50, padding=0)
            return
        pad = max((hi - lo) * 0.04, 1.0)
        vb.disableAutoRange(axis="x")
        vb.setXRange(lo - pad, hi + pad, padding=0)


def _swatch(color: str, alpha: int = 255) -> QWidget:
    w = QWidget()
    w.setFixedSize(8, 8)
    c = pg.mkColor(color)
    w.setStyleSheet(f"background:rgba({c.red()},{c.green()},{c.blue()},{alpha});")
    return w

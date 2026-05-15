"""位移台位置可视化 — XY 平面 + Z 条形。

颜色绑定到 theme：当前位置 signal，已采样 sampled，未访问 neutral。
软限位用 DANGER 色虚线画在 z 条形（z_min/z_max）和 xy 平面（x/y 各两条）。
30 Hz 节流重绘以避免被 60 Hz 信号打爆。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from . import theme
from ..core.i18n import tr
from ..core.safety import SafetyLimits
from .widgets import HintLabel


_BR_PATH = pg.mkBrush(theme.BORDER1)
_BR_DONE = pg.mkBrush(theme.DONE)
_BR_CUR = pg.mkBrush(theme.ACCENT)
_PEN_CUR = pg.mkPen(theme.BG0, width=1)
_PEN_LIMIT = pg.mkPen(theme.DANGER, width=1, style=Qt.DashLine)
_AXIS_COLOR = pg.mkColor(theme.TEXT3)


def _limit_line(angle: int, value: float = 0.0) -> pg.InfiniteLine:
    line = pg.InfiniteLine(pos=value, angle=angle, pen=_PEN_LIMIT, movable=False)
    line.setVisible(False)
    return line


class StageView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.BG0};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        plots = QWidget()
        h = QHBoxLayout(plots)
        h.setContentsMargins(8, 8, 8, 4)
        h.setSpacing(6)
        self._xy = self._make_xy()
        self._z = self._make_z()
        h.addWidget(self._xy, stretch=4)
        h.addWidget(self._z)
        outer.addWidget(plots, stretch=1)

        legend = QWidget()
        legend.setStyleSheet(f"background:{theme.BG0};border-top:1px solid {theme.BORDER0};")
        lh = QHBoxLayout(legend)
        lh.setContentsMargins(10, 4, 10, 4)
        lh.setSpacing(14)
        for color, text in (
            (theme.ACCENT, tr("stage.current_pos")),
            (theme.DONE, tr("stage.sampled")),
            (theme.BORDER1, tr("stage.planned")),
            (theme.DANGER, tr("stage.soft_limit")),
        ):
            lh.addWidget(_swatch(color))
            lh.addWidget(HintLabel(text))
        lh.addStretch()
        outer.addWidget(legend)

        # XY
        self._path_xy = pg.ScatterPlotItem(size=4, brush=_BR_PATH, pen=None, symbol="o")
        self._done_xy = pg.ScatterPlotItem(size=7, brush=_BR_DONE, pen=None, symbol="o")
        self._cur_xy = pg.ScatterPlotItem(size=18, brush=_BR_CUR, pen=_PEN_CUR, symbol="+")
        # 软限位虚线 — angle=90 表示垂直线 (x 限位), angle=0 水平 (y 限位)
        self._lim_xmin = _limit_line(90)
        self._lim_xmax = _limit_line(90)
        self._lim_ymin = _limit_line(0)
        self._lim_ymax = _limit_line(0)
        for it in (self._lim_xmin, self._lim_xmax, self._lim_ymin, self._lim_ymax,
                   self._path_xy, self._done_xy, self._cur_xy):
            self._xy.addItem(it)
        # Z
        self._path_z = pg.ScatterPlotItem(size=3, brush=_BR_PATH, pen=None, symbol="o")
        self._done_z = pg.ScatterPlotItem(size=5, brush=_BR_DONE, pen=None, symbol="o")
        self._cur_z = pg.ScatterPlotItem(size=12, brush=_BR_CUR, pen=_PEN_CUR, symbol="o")
        self._lim_zmin = _limit_line(0)
        self._lim_zmax = _limit_line(0)
        for it in (self._lim_zmin, self._lim_zmax, self._path_z, self._done_z, self._cur_z):
            self._z.addItem(it)

        self._latest: Optional[tuple[float, float, float]] = None
        self._done_idx: list[int] = []
        self._path: Optional[np.ndarray] = None
        self._dirty = False

        self._tick = QTimer(self)
        self._tick.setInterval(33)  # ~30 Hz
        self._tick.timeout.connect(self._refresh)
        self._tick.start()

    @Slot(object)
    def set_safety_limits(self, limits: SafetyLimits) -> None:
        """更新软限位虚线 (settings 改后或连接时调用)。enabled=False 时隐藏。"""
        on = bool(limits.enabled)
        for line, value in (
            (self._lim_xmin, limits.x_min), (self._lim_xmax, limits.x_max),
            (self._lim_ymin, limits.y_min), (self._lim_ymax, limits.y_max),
            (self._lim_zmin, limits.z_min), (self._lim_zmax, limits.z_max),
        ):
            line.setPos(float(value))
            line.setVisible(on)

    def set_single_axis(self, on: bool) -> None:
        """单轴 stage (M-531): 隐藏 XY 平面, Z 条形独占。"""
        self._xy.setVisible(not on)

    def _make_xy(self) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setBackground(theme.BG0)
        pw.setLabel("bottom", tr("stage.x"), units="µm", color=theme.TEXT3)
        pw.setLabel("left", tr("stage.y"), units="µm", color=theme.TEXT3)
        pw.setAspectLocked(True)
        pw.showGrid(x=True, y=True, alpha=0.18)
        pw.setRange(xRange=(-50, 50), yRange=(-50, 50))
        for ax in ("bottom", "left"):
            a = pw.getAxis(ax)
            a.setPen(theme.BORDER1); a.setTextPen(theme.TEXT3)
        return pw

    def _make_z(self) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setBackground(theme.BG0)
        pw.setLabel("left", tr("stage.z"), units="µm", color=theme.TEXT3)
        pw.setMaximumWidth(96)
        pw.setRange(yRange=(-30, 30), xRange=(-1, 1))
        pw.getAxis("bottom").hide()
        pw.showGrid(y=True, alpha=0.18)
        a = pw.getAxis("left")
        a.setPen(theme.BORDER1); a.setTextPen(theme.TEXT3)
        return pw

    @Slot(float, float, float)
    def set_position(self, x: float, y: float, z: float) -> None:
        self._latest = (x, y, z)
        self._dirty = True

    @Slot(object)
    def set_scan_path(self, path: np.ndarray) -> None:
        self._path = np.asarray(path, dtype=np.float64)
        self._done_idx = []
        if self._path.size:
            self._path_xy.setData(x=self._path[:, 0], y=self._path[:, 1])
            self._path_z.setData(x=np.zeros(len(self._path)), y=self._path[:, 2])
            self._auto_range()
        self._done_xy.setData(x=[], y=[])
        self._done_z.setData(x=[], y=[])
        self._dirty = True

    def clear_path(self) -> None:
        self._path = None
        self._done_idx = []
        for s in (self._path_xy, self._done_xy, self._path_z, self._done_z):
            s.setData(x=[], y=[])

    @Slot(int)
    def mark_done(self, idx: int) -> None:
        self._done_idx.append(idx)
        self._dirty = True

    def _refresh(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        if self._latest is not None:
            x, y, z = self._latest
            self._cur_xy.setData(x=[x], y=[y])
            self._cur_z.setData(x=[0], y=[z])
        if self._path is not None and self._done_idx:
            done = self._path[self._done_idx]
            self._done_xy.setData(x=done[:, 0], y=done[:, 1])
            self._done_z.setData(x=np.zeros(len(done)), y=done[:, 2])

    def _auto_range(self) -> None:
        assert self._path is not None
        xs, ys, zs = self._path[:, 0], self._path[:, 1], self._path[:, 2]
        pad = 5.0
        self._xy.setRange(
            xRange=(float(min(xs.min(), -10)) - pad, float(max(xs.max(), 10)) + pad),
            yRange=(float(min(ys.min(), -10)) - pad, float(max(ys.max(), 10)) + pad),
        )
        self._z.setRange(yRange=(float(zs.min()) - 1, float(zs.max()) + 1))


def _swatch(color: str) -> QWidget:
    w = QWidget()
    w.setFixedSize(8, 8)
    w.setStyleSheet(f"background:{color};")
    return w

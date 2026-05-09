"""Volume 模式左上角的 Z-MIP 缩略图 + 可拖动 ROI 矩形。

用户拖/缩 ROI → 发 ``roi_changed(x0, y0, x1, y1)``（原始体素坐标）→
:class:`VolumeSurface` 收到后裁切体数据再渲染。Z 维不裁，仅裁 XY。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QGraphicsRectItem, QVBoxLayout, QWidget

from . import theme

THUMB_W = 180
THUMB_H = 180
ROI_PEN = "#2f73a3"
ROI_HOVER_PEN = "#b55345"
RENDERED_HINT_PEN = "#d6892b"  # 暖橙：表示 ROI 被预算回缩后的实际渲染范围


class MipRoiOverlay(QWidget):
    """小尺寸 Z-MIP + RectROI；体素坐标 (x0,y0,x1,y1) 上发出。"""

    roi_changed = Signal(int, int, int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(THUMB_W, THUMB_H)
        self.setStyleSheet(
            f"background:{theme.BG1};border:1px solid {theme.BORDER0};"
        )

        self._plot = pg.PlotWidget(background=theme.BG1)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.setMenuEnabled(False)
        self._plot.hideAxis("bottom")
        self._plot.hideAxis("left")
        vb = self._plot.getViewBox()
        vb.setAspectLocked(True)
        vb.invertY(True)
        vb.setBackgroundColor(theme.BG1)
        # rect zoom 时把可视范围同步到 ROI，让"框选 = 裁切"
        vb.sigRangeChangedManually.connect(self._on_view_range_changed)

        self._image = pg.ImageItem(axisOrder="row-major")
        try:
            self._image.setColorMap(pg.colormap.get("gray", source="matplotlib"))
        except Exception:
            pass
        self._plot.addItem(self._image)

        self._roi: Optional[pg.RectROI] = None
        self._volume_shape: Optional[Tuple[int, int, int]] = None
        self._suppress_emit = False
        self._rect_zoom_on = False
        self._rendered_hint: Optional[QGraphicsRectItem] = None
        self.setToolTip("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(THUMB_W, THUMB_H)

    def set_volume(self, volume: np.ndarray) -> None:
        """传入完整体数据；自动计算 Z-MIP 显示，首次会放置覆盖整个图的 ROI。"""
        if volume.ndim != 3:
            return
        mip = volume.max(axis=0)
        self._image.setImage(mip, autoLevels=True)
        z, h, w = volume.shape
        prev_shape = self._volume_shape
        self._volume_shape = (int(z), int(h), int(w))
        self._plot.setRange(xRange=(0, w), yRange=(0, h), padding=0.0)
        if self._roi is None or prev_shape != self._volume_shape:
            self._install_roi(w, h)

    def set_rect_zoom_mode(self, on: bool) -> None:
        """volume 模式下把 PSF 面板的 rect zoom 控件作用在 MIP 缩略图上。

        启用后整个 MIP 区域都能左键拉框，框出来的范围既是新的可视窗口也
        同步成新的 ROI——3D 立刻按这个矩形重新裁切。要求把 RectROI 的鼠标
        事件临时屏蔽，否则 ROI 会优先吃掉点在自己内部的左键拖动。
        """
        self._rect_zoom_on = bool(on)
        self._plot.setMouseEnabled(x=on, y=on)
        mode = pg.ViewBox.RectMode if on else pg.ViewBox.PanMode
        self._plot.getViewBox().setMouseMode(mode)
        if self._roi is not None:
            self._roi.translatable = not on
            self._roi.resizable = not on
            buttons = pg.QtCore.Qt.NoButton if on else pg.QtCore.Qt.LeftButton
            self._roi.setAcceptedMouseButtons(buttons)

    def reset_view(self) -> None:
        if self._volume_shape is None:
            return
        _z, h, w = self._volume_shape
        self._plot.setRange(xRange=(0, w), yRange=(0, h), padding=0.0)

    def set_rendered_hint(self, roi: Optional[Tuple[int, int, int, int]], reason: str) -> None:
        """ROI 被预算回缩时画一个橙色虚线小框标记真实渲染范围；``roi=None``
        表示没回缩，把提示框/工具提示清干净。"""
        vb = self._plot.getViewBox()
        if roi is None:
            if self._rendered_hint is not None:
                vb.removeItem(self._rendered_hint)
                self._rendered_hint = None
            self.setToolTip("")
            return
        x0, y0, x1, y1 = roi
        rect = (float(x0), float(y0), float(x1 - x0), float(y1 - y0))
        if self._rendered_hint is None:
            pen = QPen()
            pen.setColor(pg.mkColor(RENDERED_HINT_PEN))
            pen.setWidth(0)  # cosmetic：缩放下保持 1px 视觉宽度
            pen.setStyle(Qt.DashLine)
            self._rendered_hint = QGraphicsRectItem()
            self._rendered_hint.setPen(pen)
            self._rendered_hint.setBrush(Qt.NoBrush)
            self._rendered_hint.setZValue(20)  # 压在 ROI 上面
            vb.addItem(self._rendered_hint)
        self._rendered_hint.setRect(*rect)
        self.setToolTip(reason)

    def _on_view_range_changed(self, *_args) -> None:
        if not self._rect_zoom_on or self._volume_shape is None or self._roi is None:
            return
        if self._suppress_emit:
            return
        (x0f, x1f), (y0f, y1f) = self._plot.getViewBox().viewRange()
        _z, h, w = self._volume_shape
        x0 = max(0, min(w - 1, int(round(x0f))))
        x1 = max(x0 + 1, min(w, int(round(x1f))))
        y0 = max(0, min(h - 1, int(round(y0f))))
        y1 = max(y0 + 1, min(h, int(round(y1f))))
        # 静默把 ROI 移到新可视范围，再手动 emit 让 VolumeSurface 重裁
        self.set_roi((x0, y0, x1, y1))
        self.roi_changed.emit(x0, y0, x1, y1)

    def set_roi(self, roi: Tuple[int, int, int, int]) -> None:
        if self._roi is None:
            return
        x0, y0, x1, y1 = roi
        self._suppress_emit = True
        self._roi.setPos((float(x0), float(y0)))
        self._roi.setSize((float(max(1, x1 - x0)), float(max(1, y1 - y0))))
        self._suppress_emit = False

    def current_roi(self) -> Optional[Tuple[int, int, int, int]]:
        if self._roi is None or self._volume_shape is None:
            return None
        pos = self._roi.pos()
        size = self._roi.size()
        _, h, w = self._volume_shape
        x0 = max(0, int(round(pos.x())))
        y0 = max(0, int(round(pos.y())))
        x1 = min(w, x0 + max(1, int(round(size.x()))))
        y1 = min(h, y0 + max(1, int(round(size.y()))))
        return (x0, y0, x1, y1)

    def _install_roi(self, w: int, h: int) -> None:
        if self._roi is not None:
            self._plot.removeItem(self._roi)
        roi = pg.RectROI(
            [0.0, 0.0],
            [float(w), float(h)],
            pen=pg.mkPen(ROI_PEN, width=1.5),
            hoverPen=pg.mkPen(ROI_HOVER_PEN, width=1.5),
            invertible=False,
            rotatable=False,
        )
        roi.maxBounds = pg.QtCore.QRectF(0, 0, w, h)
        roi.sigRegionChangeFinished.connect(self._on_roi_changed)
        self._plot.addItem(roi)
        self._roi = roi

    def _on_roi_changed(self) -> None:
        if self._suppress_emit:
            return
        roi = self.current_roi()
        if roi is None:
            return
        self.roi_changed.emit(*roi)

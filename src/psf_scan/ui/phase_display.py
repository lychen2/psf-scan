"""Preview surface for off-axis phase reconstruction."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal

from ..core.phase import Sideband
from . import theme
from .colormap_resolver import resolve_or_default


class PhaseDisplay(pg.GraphicsLayoutWidget):
    point_clicked = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackground(theme.CANVAS_BG)
        self._plot = self.addPlot(row=0, col=0)
        self._style_plot()
        self._item = pg.ImageItem(axisOrder="col-major")
        self._plot.addItem(self._item)
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=True, y=True, alpha=0.12)
        self._plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        self._sideband_roi = None
        self._plot.scene().sigMouseClicked.connect(self._on_scene_clicked)

    def clear_display(self, text: str = "") -> None:
        self._item.clear()
        self._plot.setTitle(text, color=theme.CANVAS_FG, size="10pt")
        self._clear_sideband()

    def set_image(
        self,
        image: np.ndarray,
        *,
        title: str,
        cmap_name: str = "gray",
        levels: tuple[float, float] | None = None,
        sideband: Sideband | None = None,
    ) -> None:
        data = np.asarray(image, dtype=np.float32)
        self._item.setImage(data.T, autoLevels=levels is None)
        if levels is not None:
            self._item.setLevels(levels)
        self._item.setLookupTable(resolve_or_default(cmap_name).getLookupTable())
        self._item.setRect(0, 0, data.shape[1], data.shape[0])
        self._plot.setTitle(title, color=theme.CANVAS_FG, size="10pt")
        self._draw_sideband(sideband)
        self._plot.setRange(xRange=[0, data.shape[1]], yRange=[0, data.shape[0]], padding=0.0)

    def _style_plot(self) -> None:
        self._plot.getViewBox().setBackgroundColor(theme.CANVAS_BG)
        for axis_name in ("left", "bottom"):
            axis = self._plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(theme.CANVAS_BORDER))
            axis.setTextPen(pg.mkPen(theme.CANVAS_FG))

    def _draw_sideband(self, sideband: Sideband | None) -> None:
        self._clear_sideband()
        if sideband is None:
            return
        roi = pg.CircleROI(
            [sideband.x - sideband.radius, sideband.y - sideband.radius],
            [sideband.radius * 2.0, sideband.radius * 2.0],
            movable=False,
            pen=pg.mkPen(theme.ACCENT_LO, width=2),
        )
        roi.setAcceptedMouseButtons(Qt.NoButton)
        self._plot.addItem(roi)
        self._sideband_roi = roi

    def _clear_sideband(self) -> None:
        if self._sideband_roi is None:
            return
        try:
            self._plot.removeItem(self._sideband_roi)
        finally:
            self._sideband_roi = None

    def _on_scene_clicked(self, event) -> None:
        if not self._plot.sceneBoundingRect().contains(event.scenePos()):
            return
        point = self._plot.vb.mapSceneToView(event.scenePos())
        self.point_clicked.emit(float(point.x()), float(point.y()))

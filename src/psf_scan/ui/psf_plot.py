"""PSF 图面板：2D 正交/MIP 与 3D 等值面。"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMenu, QStackedLayout, QWidget

from . import theme
from .colormap_resolver import resolve_or_default
from .psf_render import RenderImage, RenderOptions
from .psf_volume import VolumeSurface

LOCATOR_FADE_INTERVAL_MS = 30
LOCATOR_FADE_STEPS = 6
PLOT_BG = "#f7f5ef"
PLOT_AXIS = "#626a6c"
PLOT_TITLE = "#171a1c"
LOCATOR = "#2f73a3"


class PsfPlotWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._images = ImageSurface()
        self._volume = VolumeSurface()
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._images)
        self._stack.addWidget(self._volume)

    def clear(self) -> None:
        self._images.clear()
        self._volume.clear()

    def set_rect_zoom_mode(self, on: bool) -> None:
        self._images.set_rect_zoom_mode(on)
        self._volume.set_rect_zoom_mode(on)

    def reset_views(self) -> None:
        self._images.reset_views()
        self._volume.reset_view()

    def set_images(
        self,
        images: list[RenderImage],
        *,
        cmap_name: str,
        levels: tuple[float, float],
        options: RenderOptions,
    ) -> None:
        self._stack.setCurrentWidget(self._images)
        self._images.set_images(images, cmap_name=cmap_name, levels=levels, options=options)

    def set_volume(
        self,
        volume: np.ndarray,
        *,
        levels: tuple[float, float],
        options: RenderOptions,
        z_positions: np.ndarray | None,
        live: bool = False,
    ) -> None:
        self._stack.setCurrentWidget(self._volume)
        self._volume.set_volume(
            volume,
            levels=levels,
            options=options,
            z_positions=z_positions,
            live=live,
        )


class ImageSurface(pg.GraphicsLayoutWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setBackground(PLOT_BG)
        self._plots: dict[int, object] = {}
        self._rects: dict[int, tuple[float, float, float, float]] = {}
        self._locators: list[object] = []
        self._fade_step = 0
        self._rect_zoom = False
        self._fade = QTimer(self)
        self._fade.setInterval(LOCATOR_FADE_INTERVAL_MS)
        self._fade.timeout.connect(self._fade_locators)

    def set_images(
        self,
        images: list[RenderImage],
        *,
        cmap_name: str,
        levels: tuple[float, float],
        options: RenderOptions,
    ) -> None:
        ranges = _view_ranges(self._plots)
        rects = self._rects.copy()
        self._clear_items(clear_rects=False)
        cmap = resolve_or_default(cmap_name)
        for index, image in enumerate(images):
            plot = self.addPlot(row=0, col=index * 2)
            item = pg.ImageItem(image.image.T)
            item.setLevels(levels)
            item.setLookupTable(cmap.getLookupTable())
            item.setRect(*image.rect)
            plot.addItem(item)
            _configure_plot(plot, image, options)
            _restore_range(plot, ranges.get(index), rects.get(index), image.rect)
            self._plots[index] = plot
            self._rects[index] = image.rect
            if self._rect_zoom:
                plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            if options.show_colorbar:
                _add_colorbar(self, col=index * 2 + 1, item=item, cmap=cmap, levels=levels)
        self._start_locator_fade()

    def clear(self) -> None:
        self._clear_items(clear_rects=True)

    def set_rect_zoom_mode(self, on: bool) -> None:
        self._rect_zoom = on
        mode = pg.ViewBox.RectMode if on else pg.ViewBox.PanMode
        for plot in self._plots.values():
            plot.getViewBox().setMouseMode(mode)

    def reset_views(self) -> None:
        for index, plot in self._plots.items():
            rect = self._rects.get(index)
            if rect is None:
                plot.autoRange()
                continue
            x0, y0, w, h = rect
            plot.setRange(xRange=[x0, x0 + w], yRange=[y0, y0 + h], padding=0.0)

    def _clear_items(self, *, clear_rects: bool) -> None:
        self._fade.stop()
        self._locators = []
        self._plots = {}
        if clear_rects:
            self._rects = {}
        self.ci.clear()

    def _start_locator_fade(self) -> None:
        self._locators = _locators(self._plots)
        self._fade_step = 0
        if self._locators:
            self._fade.start()

    def _fade_locators(self) -> None:
        self._fade_step += 1
        opacity = max(0.0, 1.0 - self._fade_step / LOCATOR_FADE_STEPS)
        for item in self._locators:
            item.setOpacity(opacity)
        if opacity <= 0.0:
            self._fade.stop()


def _configure_plot(plot, image: RenderImage, options: RenderOptions) -> None:
    plot.setTitle(image.title, color=PLOT_TITLE, size="10pt")
    plot.setAspectLocked(image.aspect_locked)
    plot.showAxis("bottom", options.show_labels)
    plot.showAxis("left", options.show_labels)
    plot.showAxis("top", False)
    plot.showAxis("right", False)
    if options.show_labels:
        plot.setLabel("bottom", image.x_label)
        plot.setLabel("left", image.y_label)
    _style_axes(plot)
    _simplify_menu(plot)
    if options.show_locator and image.locator is not None:
        _add_locator(plot, image.locator)


def _simplify_menu(plot) -> None:
    """把 pyqtgraph 默认右键菜单（X/Y Axis manual/auto/link/invert、mouse mode、
    plot options 等）替换成只保留 view all + export image。"""
    vb = plot.getViewBox()
    menu = QMenu()
    menu.addAction("view all", vb.autoRange)
    menu.addAction("export image…", lambda: _export_plot(plot))
    vb.menu = menu
    # PlotItem 自己还会向 scene context menu 注入 ctrlMenu / subMenus，一并禁掉
    plot.ctrlMenu = None
    plot.subMenus = []


def _export_plot(plot) -> None:
    from pyqtgraph.exporters import ImageExporter
    exporter = ImageExporter(plot.getViewBox())
    exporter.export()


def _style_axes(plot) -> None:
    for axis_name in ("bottom", "left"):
        axis = plot.getAxis(axis_name)
        axis.setPen(pg.mkPen(PLOT_AXIS, width=1))
        axis.setTextPen(pg.mkPen(PLOT_AXIS, width=1))


def _add_locator(plot, locator: tuple[float, float]) -> None:
    x, y = locator
    pen = pg.mkPen(LOCATOR, width=1)
    line_x = pg.InfiniteLine(x, angle=90, pen=pen)
    line_y = pg.InfiniteLine(y, angle=0, pen=pen)
    line_x.setProperty("role", "locator")
    line_y.setProperty("role", "locator")
    plot.addItem(line_x)
    plot.addItem(line_y)


def _add_colorbar(layout, *, col: int, item, cmap, levels: tuple[float, float]) -> None:
    bar = pg.ColorBarItem(
        values=levels,
        colorMap=cmap,
        label="counts",
        width=14,
        pen=theme.BORDER1,
        hoverPen=theme.ACCENT,
    )
    bar.setImageItem(item)
    layout.addItem(bar, row=0, col=col)


def _view_ranges(plots: dict[int, object]) -> dict[int, list[list[float]]]:
    return {index: plot.viewRange() for index, plot in plots.items()}


def _restore_range(
    plot,
    view_range: list[list[float]] | None,
    old_rect: tuple[float, float, float, float] | None,
    rect: tuple[float, float, float, float],
) -> None:
    x0, y0, width, height = rect
    x_range = [x0, x0 + width] if view_range is None else view_range[0]
    y_range = [y0, y0 + height] if view_range is None else view_range[1]
    if old_rect is not None and _is_full_range(view_range, old_rect):
        x_range = [x0, x0 + width]
        y_range = [y0, y0 + height]
    plot.setRange(xRange=x_range, yRange=y_range, padding=0.0)


def _is_full_range(
    view_range: list[list[float]] | None,
    rect: tuple[float, float, float, float],
) -> bool:
    if view_range is None:
        return False
    x0, y0, width, height = rect
    expected = ([x0, x0 + width], [y0, y0 + height])
    return np.allclose(view_range[0], expected[0]) and np.allclose(view_range[1], expected[1])


def _locators(plots: dict[int, object]) -> list[object]:
    items = []
    for plot in plots.values():
        for item in plot.items:
            if item.property("role") == "locator":
                items.append(item)
    return items

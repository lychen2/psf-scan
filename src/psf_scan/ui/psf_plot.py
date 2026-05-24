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
COLORBAR_WIDTH = 14
COLORBAR_COLUMN_WIDTH = 42


class PsfPlotWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._images = ImageSurface()
        self._volume: VolumeSurface | None = None
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._images)

    def clear(self) -> None:
        self._images.clear()
        if self._volume is not None:
            self._volume.clear()

    def set_rect_zoom_mode(self, on: bool) -> None:
        self._images.set_rect_zoom_mode(on)
        if self._volume is not None:
            self._volume.set_rect_zoom_mode(on)

    def reset_views(self) -> None:
        self._images.reset_views()
        if self._volume is not None:
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
        data_revision: int | None = None,
    ) -> None:
        volume_surface = self._ensure_volume_surface()
        self._stack.setCurrentWidget(volume_surface)
        volume_surface.set_volume(
            volume,
            levels=levels,
            options=options,
            z_positions=z_positions,
            live=live,
            data_revision=data_revision,
        )

    def export_to(self, path: str) -> None:
        """统一导出当前 plot — 2D 走 pyqtgraph exporter，3D 走 framebuffer。"""
        from pathlib import Path as _Path
        target = str(_Path(path))
        if self._volume is not None and self._stack.currentWidget() is self._volume:
            self._volume.export_to(target)
        else:
            from pyqtgraph.exporters import ImageExporter
            ImageExporter(self._images.scene()).export(target)

    def _ensure_volume_surface(self) -> VolumeSurface:
        if self._volume is None:
            self._volume = VolumeSurface()
            self._stack.addWidget(self._volume)
        return self._volume


class ImageSurface(pg.GraphicsLayoutWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setBackground(PLOT_BG)
        self._plots: dict[int, object] = {}
        self._items: dict[int, pg.ImageItem] = {}
        self._colorbars: dict[int, pg.ColorBarItem] = {}
        self._locator_items: dict[int, list] = {}
        self._rects: dict[int, tuple[float, float, float, float]] = {}
        self._locators: list[object] = []
        self._fade_step = 0
        self._rect_zoom = False
        self._last_mode = None
        self._last_show_colorbar = False
        self._last_show_labels = False
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
        cmap = resolve_or_default(cmap_name)
        # 复用条件: plot 数量/模式/可见性都不变 — 仅 cut 位置变化时, 避免 rebuild 抖动
        can_reuse = (
            len(self._plots) == len(images) and len(images) > 0
            and self._last_mode == options.mode
            and self._last_show_colorbar == options.show_colorbar
            and self._last_show_labels == options.show_labels
        )
        if can_reuse:
            self._update_images(images, levels, cmap, options)
        else:
            self._rebuild_images(images, levels, cmap, options)
        self._last_mode = options.mode
        self._last_show_colorbar = options.show_colorbar
        self._last_show_labels = options.show_labels
        self._start_locator_fade()

    def _rebuild_images(self, images, levels, cmap, options) -> None:
        ranges = _view_ranges(self._plots)
        rects = self._rects.copy()
        self._clear_items(clear_rects=False)
        self._items = {}
        self._colorbars = {}
        self._locator_items = {}
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
            self._items[index] = item
            self._rects[index] = image.rect
            self._locator_items[index] = [
                i for i in plot.items if i.property("role") == "locator"
            ]
            if self._rect_zoom:
                plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            if options.show_colorbar:
                self._colorbars[index] = _add_colorbar(
                    self,
                    col=index * 2 + 1,
                    item=item,
                    cmap=cmap,
                    levels=levels,
                )

    def _update_images(self, images, levels, cmap, options) -> None:
        """复用现有 plot/ImageItem, 仅 setImage 数据 — 避免 GraphicsLayout rebuild 抖动。"""
        for index, image in enumerate(images):
            item = self._items[index]
            item.setImage(image.image.T, autoLevels=False)
            item.setLevels(levels)
            item.setLookupTable(cmap.getLookupTable())
            item.setRect(*image.rect)
            plot = self._plots[index]
            plot.setTitle(image.title, color=PLOT_TITLE, size="10pt")
            # 清旧 locator + 加新
            for loc in self._locator_items.get(index, []):
                try: plot.removeItem(loc)
                except Exception: pass  # noqa: BLE001
            self._locator_items[index] = []
            if options.show_locator and image.locator is not None:
                _add_locator(plot, image.locator)
                self._locator_items[index] = [
                    i for i in plot.items if i.property("role") == "locator"
                ]
            self._rects[index] = image.rect
            if options.show_colorbar:
                _update_colorbar(self._colorbars[index], item=item, cmap=cmap, levels=levels)

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
        self._items = {}
        self._colorbars = {}
        self._locator_items = {}
        self._last_mode = None
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


def _add_colorbar(layout, *, col: int, item, cmap, levels: tuple[float, float]) -> pg.ColorBarItem:
    bar = pg.ColorBarItem(
        values=levels,
        colorMap=cmap,
        label="counts",
        width=COLORBAR_WIDTH,
        pen=theme.BORDER1,
        hoverPen=theme.ACCENT,
        interactive=False,
    )
    bar.setImageItem(item)
    layout.addItem(bar, row=0, col=col)
    layout.ci.layout.setColumnFixedWidth(col, COLORBAR_COLUMN_WIDTH)
    return bar


def _update_colorbar(
    bar: pg.ColorBarItem,
    *,
    item: pg.ImageItem,
    cmap,
    levels: tuple[float, float],
) -> None:
    bar.setColorMap(cmap)
    bar.setLevels(values=levels)
    bar.setImageItem(item)


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

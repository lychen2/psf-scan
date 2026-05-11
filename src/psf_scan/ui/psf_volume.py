"""PSF volume view: matplotlib surface, OpenGL volume slices."""

from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from OpenGL import GL
from pyqtgraph.Qt import QtGui
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from . import theme
from .colormap_resolver import resolve_or_default
from .psf_gl_axes import (
    apply_axis_layout, axis_frame, create_axis_ticks, create_axis_titles,
    create_base_grids,
)
from .psf_gl_volume import OpenGLSliceView
from .psf_render import MODE_VOLUME, RenderOptions
from .psf_volume_compute import IsosurfaceWorker, REBUILD_INTERVAL_MS, VOLUME_BG, VOLUME_GRID
from .psf_volume_mip_roi import MipRoiOverlay
from .psf_volume_types import SliceLayer, SurfaceLayer, VoxelLayer
from .volume_memory import fit_roi_to_budget, voxel_budget


VOLUME_COLORBAR_WIDTH = 56
USE_MATPLOT_SURFACE = os.environ.get("PSF_SCAN_MATPLOT_SURFACE", "") == "1"


class VolumeSurface(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._pending: tuple = ()
        self._generation = 0
        self._worker_busy = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._status = QLabel("")
        self._status.setProperty("role", "hint")
        self._surface = MatplotSurfaceView() if USE_MATPLOT_SURFACE else OpenGLSurfaceView()
        self._volume = OpenGLSliceView()
        self._stack = QStackedLayout()
        self._stack.addWidget(self._surface)
        self._stack.addWidget(self._volume)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dispatch_worker)

        self._colorbar_host = pg.GraphicsLayoutWidget()
        self._colorbar_host.setBackground(VOLUME_BG)
        self._colorbar_host.setFixedWidth(VOLUME_COLORBAR_WIDTH)
        self._colorbar_host.ci.setContentsMargins(2, 6, 8, 6)
        self._colorbar_item: pg.ColorBarItem | None = None
        self._colorbar_host.setVisible(False)

        self._mip_overlay = MipRoiOverlay()
        self._mip_overlay.roi_changed.connect(self._on_roi_changed)
        self._roi: tuple[int, int, int, int] | None = None
        self._full_volume: np.ndarray | None = None
        self._last_render_args: tuple | None = None  # (levels, options, z_positions, live)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._mip_overlay, alignment=Qt.AlignTop | Qt.AlignLeft)
        body.addLayout(self._stack, stretch=1)
        body.addWidget(self._colorbar_host)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._status)
        layout.addLayout(body, stretch=1)

    def clear(self) -> None:
        self._timer.stop()
        self._pending = ()
        self._generation += 1
        self._pool.clear()
        self._worker_busy = False
        self._surface.clear()
        self._volume.clear()
        self._status.setText("")
        self._set_colorbar(visible=False)
        self._full_volume = None
        self._roi = None
        self._last_render_args = None

    def set_rect_zoom_mode(self, on: bool) -> None:
        """从 PSF 顶部控件转发：volume 模式下作用到 MIP 缩略图。"""
        self._mip_overlay.set_rect_zoom_mode(on)

    def reset_view(self) -> None:
        self._mip_overlay.reset_view()

    def export_to(self, path: str) -> None:
        """导出当前 3D 视图：GL widget 用 grabFramebuffer，matplotlib 用 savefig。"""
        view = self._stack.currentWidget()
        grabber = getattr(view, "grabFramebuffer", None)
        if callable(grabber):
            img = grabber()
            if not img.save(str(path)):
                raise IOError(f"无法写入 {path}")
            return
        figure = getattr(view, "figure", None)
        if figure is not None:
            figure.savefig(str(path), dpi=200, bbox_inches="tight")
            return
        # fallback — Qt 自带 grab，对非 GL widget 可用
        pix = view.grab()
        if not pix.save(str(path)):
            raise IOError(f"无法写入 {path}")

    def set_volume(
        self,
        volume: np.ndarray,
        *,
        levels: tuple[float, float],
        options: RenderOptions,
        z_positions: np.ndarray | None,
        live: bool = False,
    ) -> None:
        if options.mode != MODE_VOLUME:
            raise ValueError(f"volume surface 收到非 volume 模式: {options.mode}")
        prev_shape = None if self._full_volume is None else self._full_volume.shape
        self._full_volume = volume
        self._mip_overlay.set_volume(volume)
        if self._roi is None or prev_shape != volume.shape:
            self._roi = self._initial_roi(volume.shape)
            self._mip_overlay.set_roi(self._roi)
        self._last_render_args = (levels, options, z_positions, live)
        self._dispatch_with_roi(self._cropped_volume())
        self._update_colorbar(options=options, levels=levels)

    def _initial_roi(self, shape: tuple[int, ...]) -> tuple[int, int, int, int]:
        _z, h, w = shape
        options, live = self._render_args_for_budget()
        return fit_roi_to_budget(
            shape, (0, 0, int(w), int(h)), voxel_budget(),
            options=options, live=live,
        )

    def _render_args_for_budget(self) -> tuple[object | None, bool]:
        if self._last_render_args is None:
            return None, False
        _levels, options, _z_positions, live = self._last_render_args
        return options, bool(live)

    def _cropped_volume(self) -> np.ndarray:
        if self._full_volume is None:
            raise RuntimeError("no full volume to crop")
        if self._roi is None:
            return self._full_volume
        x0, y0, x1, y1 = self._roi
        return self._full_volume[:, y0:y1, x0:x1]

    def _on_roi_changed(self, x0: int, y0: int, x1: int, y1: int) -> None:
        if self._full_volume is None or self._last_render_args is None:
            return
        options, live = self._render_args_for_budget()
        clamped = fit_roi_to_budget(
            self._full_volume.shape, (x0, y0, x1, y1), voxel_budget(),
            options=options, live=live,
        )
        requested = (int(x0), int(y0), int(x1), int(y1))
        if clamped != requested:
            # rect zoom 拉了个超预算的大框：MIP 视野允许停在用户拉的范围，
            # ROI 缩到预算后中心方块；同时给个淡色"实际渲染范围"提示框 + 状态文字
            self._mip_overlay.set_rendered_hint(
                clamped,
                _budget_reason(self._full_volume.shape, requested, clamped, options, live),
            )
        else:
            self._mip_overlay.set_rendered_hint(None, "")
        self._roi = clamped
        levels, options, z_positions, _live = self._last_render_args
        # ROI 改后总是非 live 渲染，避免 live 重复抢
        self._last_render_args = (levels, options, z_positions, False)
        self._dispatch_with_roi(self._cropped_volume())
        self._update_colorbar(options=options, levels=levels)

    def _dispatch_with_roi(self, cropped: np.ndarray) -> None:
        if self._last_render_args is None:
            return
        levels, options, z_positions, live = self._last_render_args
        self._pending = (cropped, levels, options, z_positions, live)
        self._timer.stop()
        self._timer.start(REBUILD_INTERVAL_MS)
        z, h, w = cropped.shape
        self._status.setText(f"volume · queued ({'live' if live else 'full'}) · roi {w}×{h}, z={z}")

    def _update_colorbar(self, *, options: RenderOptions, levels: tuple[float, float]) -> None:
        if not options.show_colorbar:
            self._set_colorbar(visible=False)
            return
        cmap = resolve_or_default(options.volume_cmap)
        if cmap is None:
            self._set_colorbar(visible=False)
            return
        if self._colorbar_item is None:
            bar = pg.ColorBarItem(
                values=levels,
                colorMap=cmap,
                label="counts",
                width=14,
                pen=theme.BORDER1,
                hoverPen=theme.ACCENT,
                interactive=False,
            )
            self._colorbar_host.addItem(bar)
            self._colorbar_item = bar
        else:
            self._colorbar_item.setColorMap(cmap)
            self._colorbar_item.setLevels(values=levels)
        self._set_colorbar(visible=True)

    def _set_colorbar(self, *, visible: bool) -> None:
        if self._colorbar_host.isVisible() != visible:
            self._colorbar_host.setVisible(visible)

    def _dispatch_worker(self) -> None:
        if not self._pending:
            return
        if self._worker_busy:
            self._timer.start(REBUILD_INTERVAL_MS)
            return
        volume, levels, options, z_positions, live = self._pending
        self._pending = ()
        self._generation += 1
        worker = IsosurfaceWorker(
            volume=volume,
            levels=levels,
            options=options,
            z_positions=z_positions,
            live=live,
            generation=self._generation,
        )
        self._worker_busy = True
        worker.signals.done.connect(self._on_volume_done, Qt.QueuedConnection)
        self._pool.start(worker)
        self._status.setText(f"volume · computing ({'live' if live else 'full'})")

    def _on_volume_done(self, gen: int, layers: list, shape: tuple[int, ...] | None) -> None:
        self._worker_busy = False
        if gen != self._generation:
            if self._pending:
                self._timer.start(0)
            return
        if _slice_layers(layers):
            self._stack.setCurrentWidget(self._volume)
            self._volume.set_layers(layers, shape)
            self._set_status("OpenGL", layers, shape)
        else:
            self._stack.setCurrentWidget(self._surface)
            self._surface.set_layers(layers, shape)
            self._set_status("mplot3d", layers, shape)
        if self._pending:
            self._timer.start(0)

    def _set_status(self, backend: str, layers: list, shape: tuple[int, ...] | None) -> None:
        if not layers:
            self._status.setText("volume · no data at current settings")
            return
        if shape is not None:
            self._status.setText(f"volume · {backend} · {len(layers)} layer(s) · {shape[0]}×{shape[1]}×{shape[2]}")


class MatplotSurfaceView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[Poly3DCollection] = []
        self._figure = Figure(facecolor=VOLUME_BG)
        self._figure.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._ax = self._figure.add_subplot(111, projection="3d", facecolor=VOLUME_BG)
        self._ax.set_box_aspect([1.0, 1.0, 1.0])
        self._ax.view_init(elev=28.0, azim=-38.0)
        self._style_axes()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas, stretch=1)

    def clear(self) -> None:
        self._remove_items()
        self._canvas.draw_idle()

    def set_layers(self, layers: list, shape: tuple[int, ...] | None) -> None:
        elev, azim = self._ax.elev, self._ax.azim
        new_items = [_poly_item(layer) for layer in layers]
        for item in new_items:
            self._ax.add_collection3d(item)
        self._remove_items()
        self._items = new_items
        _set_mplot_limits(self._ax, layers, shape)
        self._ax.view_init(elev=elev, azim=azim)
        self._canvas.draw_idle()

    def _style_axes(self) -> None:
        for axis in (self._ax.xaxis, self._ax.yaxis, self._ax.zaxis):
            axis.pane.set_facecolor(VOLUME_BG)
            axis.pane.set_alpha(0.0)
            axis.line.set_color(VOLUME_GRID)
        self._ax.grid(True, color=VOLUME_GRID, alpha=0.4, linewidth=0.5)
        for axis_name in ("x", "y", "z"):
            self._ax.tick_params(axis=axis_name, colors=VOLUME_GRID, labelsize=7)

    def _remove_items(self) -> None:
        for item in self._items:
            try:
                item.remove()
            except Exception:  # noqa: BLE001
                pass
        self._items = []


def _slice_layers(layers: list) -> bool:
    return bool(layers) and isinstance(layers[0], (SliceLayer, VoxelLayer))


def _budget_reason(
    full_shape: tuple[int, ...],
    requested: tuple[int, int, int, int],
    clamped: tuple[int, int, int, int],
    options: object | None,
    live: bool,
) -> str:
    z, _h, _w = full_shape
    rx0, ry0, rx1, ry1 = requested
    cx0, cy0, cx1, cy1 = clamped
    req_voxels = z * (ry1 - ry0) * (rx1 - rx0)
    clip_voxels = z * (cy1 - cy0) * (cx1 - cx0)
    budget = voxel_budget()
    return (
        f"ROI 超预算：请求 {rx1-rx0}×{ry1-ry0}×{z} ≈ {req_voxels/1e6:.1f}M voxels, "
        f"回缩至 {cx1-cx0}×{cy1-cy0}×{z} ≈ {clip_voxels/1e6:.1f}M (预算 {budget/1e6:.1f}M)"
    )


def _poly_item(layer: SurfaceLayer) -> Poly3DCollection:
    return Poly3DCollection(
        layer.vertices[layer.faces],
        facecolors=[layer.color],
        edgecolors="none",
        linewidths=0,
    )


def _set_mplot_limits(ax, layers: list, shape: tuple[int, ...] | None) -> None:
    bounds = _full_mplot_bounds(shape) if shape is not None else _point_bounds(
        [_surface_points(layer) for layer in layers], shape,
    )
    center, half_span = _center_span(bounds)
    ax.set_xlim(center[0] - half_span, center[0] + half_span)
    ax.set_ylim(center[1] - half_span, center[1] + half_span)
    ax.set_zlim(center[2] - half_span, center[2] + half_span)


class OpenGLSurfaceView(gl.GLViewWidget):
    """GPU 加速的等值面渲染，对齐 :class:`MatplotSurfaceView`：

    - 每层 SurfaceLayer 一个 GLMeshItem；用 ``shader='shaded'`` 拿到 mpl3d 那种
      阴影感，``computeNormals=True`` 让光照吃得上。
    - 复用 :mod:`psf_gl_axes` 的轴/刻度/底面网格，同 OpenGLSliceView 一致。
    - camera elev=28°, azim=-38°（与 mpl3d view_init 完全一致）。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setBackgroundColor(VOLUME_BG)
        self.opts["elevation"] = 28
        self.opts["azimuth"] = -38
        self._items: list[gl.GLMeshItem] = []
        self._base_grids = create_base_grids()
        for grid in self._base_grids:
            self.addItem(grid)
        # GLAxisItem 在背左下角画 X/Y/Z 三条带色短线，从典型视角看像中央有
        # 个 L 型——靠 axis_titles 的 "x [px] / y [px] / z [um]" 文字定向已经
        # 够用，三条轴线纯属冗余，干掉。
        self._axis = gl.GLAxisItem(glOptions="opaque")
        self._axis.setSize(x=1.0, y=1.0, z=1.0)
        self._axis.setVisible(False)
        self._axis_titles = create_axis_titles()
        for title in self._axis_titles:
            self.addItem(title)
        self._axis_ticks = create_axis_ticks(24)
        for tick in self._axis_ticks:
            self.addItem(tick)

    def clear(self) -> None:
        for item in self._items:
            self.removeItem(item)
        self._items = []

    def set_layers(self, layers: list, shape: tuple[int, ...] | None) -> None:
        self.clear()
        # 内层 (高 iso, 不透明) 先画、外层 (低 iso, 半透明) 后画 ——
        # 配合 GL_DEPTH_TEST 让外壳不挡住内核
        for layer in reversed(_surface_only(layers)):
            item = _surface_mesh_item(layer)
            if item is not None:
                self._items.append(item)
                self.addItem(item)
        self._frame(layers, shape)
        self.update()

    def _frame(self, layers: list, shape: tuple[int, ...] | None) -> None:
        bounds = _full_mplot_bounds(shape) if shape is not None else _point_bounds(
            [_surface_points(layer) for layer in layers], shape,
        )
        # 与 OpenGLSliceView 同款 axis_frame：把 bounds 拓成方框
        apply_axis_layout(
            self._axis,
            self._axis_titles,
            self._axis_ticks,
            self._base_grids,
            bounds,
            z_um_per_display=1.0,
            z_um_at_display_zero=0.0,
        )
        origin, axis_size = axis_frame(bounds)
        center, half_span = _center_span((origin, origin + axis_size))
        self.setCameraPosition(
            pos=QtGui.QVector3D(float(center[0]), float(center[1]), float(center[2])),
            distance=float(half_span * 2 * 1.9),
        )


def _surface_only(layers: list) -> list[SurfaceLayer]:
    return [l for l in layers if isinstance(l, SurfaceLayer) and len(l.faces) > 0]


class _OOITMeshItem(gl.GLMeshItem):
    """半透明等值面用：保留 depth-test 但关掉 depth-write。

    pyqtgraph 默认的 ``glOptions='translucent'`` 不动 ``glDepthMask``，等于
    开着深度写入。Marching cubes 输出的三角形不是按视空间顺序排的，先到的
    近三角形写完深度后会把同一网格里更远的三角形挡掉，alpha 值堆出来一块
    一块。这里把 ``glDepthMask`` 在 paint 内置 ``GL_FALSE``，paint 完恢复
    ``GL_TRUE``——既不会让同一网格的三角形互相杀，也不会污染下一帧的
    ``glClear(GL_DEPTH_BUFFER_BIT)``（受 depth mask 影响）。
    """

    def paint(self) -> None:
        GL.glDepthMask(GL.GL_FALSE)
        try:
            super().paint()
        finally:
            GL.glDepthMask(GL.GL_TRUE)


def _surface_mesh_item(layer: SurfaceLayer) -> gl.GLMeshItem | None:
    n_faces = len(layer.faces)
    if n_faces == 0:
        return None
    face_colors = np.tile(np.asarray(layer.color, dtype=np.float32), (n_faces, 1))
    mesh = gl.MeshData(
        vertexes=np.ascontiguousarray(layer.vertices, dtype=np.float32),
        faces=np.ascontiguousarray(layer.faces, dtype=np.uint32),
        faceColors=face_colors,
    )
    alpha = float(layer.color[3]) if len(layer.color) >= 4 else 1.0
    if alpha >= 0.999:
        # 内核层（alpha=1）按不透明渲染：写深度，被外层正确遮挡
        return gl.GLMeshItem(
            meshdata=mesh,
            drawFaces=True,
            drawEdges=False,
            smooth=True,
            computeNormals=True,
            shader="shaded",
            glOptions="opaque",
        )
    return _OOITMeshItem(
        meshdata=mesh,
        drawFaces=True,
        drawEdges=False,
        smooth=True,
        computeNormals=True,
        shader="shaded",
        glOptions="translucent",
    )


def _full_mplot_bounds(shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    _depth, height, width = shape
    half_x = max(0.5, (width - 1) / 2.0)
    half_y = max(0.5, (height - 1) / 2.0)
    half_z = max(0.5, max(width, height) * 0.42 / 2.0)
    return (
        np.array([-half_x, -half_y, -half_z], dtype=np.float32),
        np.array([half_x, half_y, half_z], dtype=np.float32),
    )


def _surface_points(layer: SurfaceLayer) -> np.ndarray:
    return layer.vertices


def _point_bounds(points: list[np.ndarray], shape: tuple[int, ...] | None) -> tuple[np.ndarray, np.ndarray]:
    valid = [point for point in points if len(point) > 0]
    if not valid:
        return _fallback_bounds(shape)
    merged = np.concatenate(valid, axis=0)
    return merged.min(axis=0), merged.max(axis=0)


def _center_span(bounds: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, float]:
    mins, maxs = bounds
    center = (mins + maxs) / 2.0
    half_span = max(float(np.max(maxs - mins)) / 2.0, 1.0) * 1.15
    return center, half_span


def _fallback_bounds(shape: tuple[int, ...] | None) -> tuple[np.ndarray, np.ndarray]:
    if shape is None:
        return np.array([-1, -1, -1]), np.array([1, 1, 1])
    _depth, height, width = shape
    half = max(width, height) / 2.0
    return np.array([-half, -half, -half * 0.6]), np.array([half, half, half * 0.6])


__all__ = ["VolumeSurface"]

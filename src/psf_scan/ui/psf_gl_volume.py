"""PyQtGraph OpenGL volume view."""

from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from OpenGL import GL
from pyqtgraph.Qt import QtGui

from .psf_gl_axes import apply_axis_layout, axis_frame, create_axis_ticks, create_axis_titles, create_base_grids
from .psf_volume_compute import VOLUME_BG
from .psf_volume_geometry import VOLUME_RELIEF
from .psf_volume_types import SliceLayer, VoxelLayer


_TRANSMISSION_GL_OPTIONS = {
    GL.GL_DEPTH_TEST: False,
    GL.GL_BLEND: True,
    GL.GL_CULL_FACE: False,
    "glBlendEquationSeparate": (GL.GL_FUNC_ADD, GL.GL_FUNC_ADD),
    "glBlendFuncSeparate": (
        GL.GL_ZERO, GL.GL_SRC_COLOR,
        GL.GL_ZERO, GL.GL_ONE,
    ),
}

_EMISSION_GL_OPTIONS = {
    GL.GL_DEPTH_TEST: False,
    GL.GL_BLEND: True,
    GL.GL_CULL_FACE: False,
    "glBlendEquationSeparate": (GL.GL_FUNC_ADD, GL.GL_FUNC_ADD),
    "glBlendFuncSeparate": (
        GL.GL_SRC_ALPHA, GL.GL_ONE,
        GL.GL_ONE, GL.GL_ONE,
    ),
}

class OpenGLSliceView(gl.GLViewWidget):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[gl.GLGraphicsItem.GLGraphicsItem] = []
        self.setBackgroundColor(VOLUME_BG)
        self.opts["elevation"] = 28
        self.opts["azimuth"] = -38
        self._base_grids = create_base_grids()
        for item in self._base_grids:
            self.addItem(item)
        # 与 OpenGLSurfaceView 一致：隐藏角上的 GLAxisItem L 型，靠文字定向。
        self._axis = gl.GLAxisItem(glOptions="opaque")
        self._axis.setSize(x=1.0, y=1.0, z=1.0)
        self._axis.setVisible(False)
        self._axis_titles = create_axis_titles()
        for item in self._axis_titles:
            self.addItem(item)
        self._axis_ticks = create_axis_ticks(24)
        for item in self._axis_ticks:
            self.addItem(item)

    def clear(self) -> None:
        for item in self._items:
            self.removeItem(item)
        self._items = []

    def set_layers(self, layers: list, shape: tuple[int, ...] | None) -> None:
        self.clear()
        transmission_items: list[gl.GLGraphicsItem.GLGraphicsItem] = []
        emission_items: list[gl.GLGraphicsItem.GLGraphicsItem] = []
        slice_items: list[gl.GLGraphicsItem.GLGraphicsItem] = []
        for layer in layers:
            if isinstance(layer, VoxelLayer):
                transmission, emission = _gl_voxel_items(layer)
                transmission_items.append(transmission)
                emission_items.append(emission)
                continue
            slice_items.append(_slice_item(layer))
        self._items = slice_items + transmission_items + emission_items
        for item in self._items:
            self.addItem(item)
        _set_gl_camera(self, layers, shape)

    def _update_axes(
        self,
        bounds: tuple[np.ndarray, np.ndarray],
        z_um_per_display: float,
        z_um_at_display_zero: float,
    ) -> None:
        apply_axis_layout(
            self._axis,
            self._axis_titles,
            self._axis_ticks,
            self._base_grids,
            bounds,
            z_um_per_display=z_um_per_display,
            z_um_at_display_zero=z_um_at_display_zero,
        )


def _gl_voxel_items(layer: VoxelLayer) -> tuple[gl.GLMeshItem, gl.GLMeshItem]:
    return (
        _mesh_item(layer, layer.transmission_colors, _TRANSMISSION_GL_OPTIONS),
        _mesh_item(layer, layer.face_colors, _EMISSION_GL_OPTIONS),
    )


def _mesh_item(layer: VoxelLayer, face_colors: np.ndarray, gl_options: dict) -> gl.GLMeshItem:
    mesh = gl.MeshData(vertexes=layer.vertices, faces=layer.faces, faceColors=face_colors)
    return gl.GLMeshItem(
        meshdata=mesh,
        drawFaces=True,
        drawEdges=False,
        smooth=False,
        computeNormals=False,
        shader=None,
        glOptions=gl_options,
    )


def _slice_item(layer: SliceLayer) -> gl.GLImageItem:
    image = np.clip(layer.colors.transpose(1, 0, 2) * 255.0, 0.0, 255.0).astype(np.uint8)
    item = gl.GLImageItem(image, smooth=False, glOptions="translucent")
    item.scale(layer.scale_u, layer.scale_v, 1.0)
    _orient_slice_item(item, layer)
    return item


def _orient_slice_item(item: gl.GLImageItem, layer: SliceLayer) -> None:
    if layer.orientation == "xz":
        item.rotate(90, 1, 0, 0)
    if layer.orientation == "yz":
        item.rotate(90, 1, 0, 0)
        item.rotate(90, 0, 0, 1)
    item.translate(*layer.origin)


def _set_gl_camera(view: OpenGLSliceView, layers: list, shape: tuple[int, ...] | None) -> None:
    full_bounds = _full_volume_bounds(shape) if shape is not None else _point_bounds(
        [_layer_points(layer) for layer in layers], shape,
    )
    view._update_axes(full_bounds, _z_um_per_display(layers), _z_um_at_display_zero(layers))
    axis_origin, axis_size = axis_frame(full_bounds)
    center, half_span = _center_span((axis_origin, axis_origin + axis_size))
    span = half_span * 2.0
    view.setCameraPosition(
        pos=QtGui.QVector3D(float(center[0]), float(center[1]), float(center[2])),
        distance=span * 1.9,
    )
    view.update()


def _full_volume_bounds(shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    _depth, height, width = shape
    half_x = max(0.5, (width - 1) / 2.0)
    half_y = max(0.5, (height - 1) / 2.0)
    half_z = max(0.5, max(width, height) * VOLUME_RELIEF / 2.0)
    mins = np.array([-half_x, -half_y, -half_z], dtype=np.float32)
    maxs = np.array([half_x, half_y, half_z], dtype=np.float32)
    return mins, maxs
def _z_um_per_display(layers: list) -> float:
    for layer in layers:
        if isinstance(layer, VoxelLayer):
            return layer.z_um_per_display
    return 1.0


def _z_um_at_display_zero(layers: list) -> float:
    for layer in layers:
        if isinstance(layer, VoxelLayer):
            return layer.z_um_at_display_zero
    return 0.0


def _slice_points(layer: SliceLayer) -> np.ndarray:
    rows, cols = layer.colors.shape[:2]
    return _slice_corners(layer, rows, cols)


def _slice_corners(layer: SliceLayer, rows: int, cols: int) -> np.ndarray:
    x, y, z = layer.origin
    u = layer.scale_u * cols
    v = layer.scale_v * rows
    if layer.orientation == "xy":
        return np.array(((x, y, z), (x + u, y + v, z)), dtype=np.float32)
    if layer.orientation == "xz":
        return np.array(((x, y, z), (x + u, y, z + v)), dtype=np.float32)
    return np.array(((x, y, z), (x, y + u, z + v)), dtype=np.float32)


def _layer_points(layer: SliceLayer | VoxelLayer) -> np.ndarray:
    if isinstance(layer, VoxelLayer):
        return layer.vertices
    return _slice_points(layer)


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


__all__ = ["OpenGLSliceView"]

"""Coordinate mapping helpers for PSF volume views."""

from __future__ import annotations

import numpy as np


VOLUME_RELIEF = 0.42


def display_vertices(
    vertices: np.ndarray,
    shape: tuple[int, ...],
    *,
    z_positions: np.ndarray | None,
    source_shape: tuple[int, ...] | None = None,
    scale_yx: tuple[float, float] = (1.0, 1.0),
    full_shape: tuple[int, ...] | None = None,
    roi_origin: tuple[int, int] = (0, 0),
) -> np.ndarray:
    """把 voxel 索引坐标转换为 3D 显示坐标。

    ``full_shape`` 给定时：返回坐标按"完整 XY 帧"居中，并且把当前裁切体平移
    到 ROI 在原帧里的位置（``roi_origin = (x0, y0)`` 是裁切左上角的 voxel
    索引）。这样无论 MIP 里 ROI 拉到角落还是中心，3D 都贴着原始 XY 平面位置
    画，而不是被强行拽回视图中心。
    """
    x, y, z = _display_coordinates(
        vertices[:, 2],
        vertices[:, 1],
        vertices[:, 0],
        shape=shape,
        z_positions=z_positions,
        source_shape=source_shape,
        scale_yx=scale_yx,
    )
    if full_shape is not None:
        cropped = source_shape if source_shape is not None else shape
        cropped_h, cropped_w = int(cropped[1]), int(cropped[2])
        full_h, full_w = int(full_shape[1]), int(full_shape[2])
        x0, y0 = float(roi_origin[0]), float(roi_origin[1])
        # 当前 x = cropped_voxel_x - (cropped_w - 1)/2
        # 想要 x = (cropped_voxel_x + x0) - (full_w - 1)/2
        # 差 = x0 + (cropped_w - full_w)/2
        x = x + x0 + (cropped_w - full_w) / 2.0
        y = y + y0 + (cropped_h - full_h) / 2.0
    return np.column_stack((x, y, z)).astype(np.float32, copy=False)


def display_points(
    x_idx: np.ndarray,
    y_idx: np.ndarray,
    z_idx: int | np.ndarray,
    *,
    shape: tuple[int, ...],
    z_positions: np.ndarray | None,
    source_shape: tuple[int, ...],
    scale_yx: tuple[float, float],
) -> np.ndarray:
    if isinstance(z_idx, np.ndarray):
        z = z_idx.astype(np.float32, copy=False)
    else:
        z = np.full(x_idx.shape, float(z_idx), dtype=np.float32)
    x, y, z = _display_coordinates(
        x_idx.astype(np.float32, copy=False),
        y_idx.astype(np.float32, copy=False),
        z,
        shape=shape,
        z_positions=z_positions,
        source_shape=source_shape,
        scale_yx=scale_yx,
    )
    return np.column_stack((x, y, z)).astype(np.float32, copy=False)


def render_z_positions(z_positions: np.ndarray | None, *, depth: int) -> np.ndarray | None:
    if z_positions is None or len(z_positions) < 2:
        return z_positions
    z = np.asarray(z_positions, dtype=np.float32)
    return np.linspace(float(z[0]), float(z[-1]), depth, dtype=np.float32)


def axis_scale(render_length: int, source_length: int) -> float:
    if render_length <= 1 or source_length <= 1:
        return 1.0
    return (source_length - 1) / (render_length - 1)


def _display_coordinates(
    x_idx: np.ndarray,
    y_idx: np.ndarray,
    z_idx: np.ndarray,
    *,
    shape: tuple[int, ...],
    z_positions: np.ndarray | None,
    source_shape: tuple[int, ...] | None,
    scale_yx: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    depth, _height, _width = shape
    _, source_height, source_width = source_shape or shape
    scale_y, scale_x = scale_yx
    z_values = _z_values(z_positions, depth)
    z_um = np.interp(z_idx, np.arange(depth), z_values)
    z_span = max(1e-6, float(z_values.max() - z_values.min()))
    z_scale = max(source_width, source_height) * VOLUME_RELIEF / z_span
    x = x_idx * scale_x - (source_width - 1) / 2.0
    y = y_idx * scale_y - (source_height - 1) / 2.0
    z = (z_um - float(z_values.mean())) * z_scale
    return x, y, z


def _z_values(z_positions: np.ndarray | None, depth: int) -> np.ndarray:
    if z_positions is None or len(z_positions) == 0:
        return np.arange(depth, dtype=np.float32)
    values = np.asarray(z_positions, dtype=np.float32)[:depth]
    if len(values) >= depth:
        return values
    step = 1.0 if len(values) == 1 else float(values[-1] - values[-2])
    tail = values[-1] + step * np.arange(1, depth - len(values) + 1, dtype=np.float32)
    return np.concatenate((values, tail))

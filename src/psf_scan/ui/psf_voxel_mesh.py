"""Voxel cube mesh packing for OpenGL volume rendering."""

from __future__ import annotations

import numpy as np

from .psf_volume_geometry import display_points
from .psf_volume_types import VoxelLayer


MIN_CUBE_EXTENT = 1e-3
Z_CUBE_OVERLAP = 1.02

_UNIT_CUBE_VERTICES = np.array(
    [
        [-0.5, -0.5, -0.5],
        [0.5, -0.5, -0.5],
        [0.5, 0.5, -0.5],
        [-0.5, 0.5, -0.5],
        [-0.5, -0.5, 0.5],
        [0.5, -0.5, 0.5],
        [0.5, 0.5, 0.5],
        [-0.5, 0.5, 0.5],
    ],
    dtype=np.float32,
)

_UNIT_CUBE_FACES = np.array(
    [
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1],
        [1, 5, 6], [1, 6, 2],
        [2, 6, 7], [2, 7, 3],
        [3, 7, 4], [3, 4, 0],
    ],
    dtype=np.int32,
)


def voxel_cube_scale(
    *,
    shape: tuple[int, ...],
    source_shape: tuple[int, ...],
    scale_yx: tuple[float, float],
    z_positions: np.ndarray | None,
    scale_xy_stride: int = 1,
) -> np.ndarray:
    """Return display-space cube size for sampled voxels."""
    depth, height, width = shape
    scale_y, scale_x = scale_yx
    stride_xy = max(1, int(scale_xy_stride))
    return np.array(
        [
            max(MIN_CUBE_EXTENT, float(scale_x) * stride_xy),
            max(MIN_CUBE_EXTENT, float(scale_y) * stride_xy),
            max(MIN_CUBE_EXTENT, _z_display_step(
                depth=depth,
                height=height,
                width=width,
                source_shape=source_shape,
                scale_yx=scale_yx,
                z_positions=z_positions,
            ) * Z_CUBE_OVERLAP),
        ],
        dtype=np.float32,
    )


def voxel_layers_batched(
    centers: np.ndarray,
    emission_colors: np.ndarray,
    transmission_colors: np.ndarray,
    cube_scale: np.ndarray,
    *,
    max_voxels: int,
    z_um_per_display: float,
    z_um_at_display_zero: float,
) -> list[VoxelLayer]:
    total = len(centers)
    if total == 0:
        return []
    layers: list[VoxelLayer] = []
    for start in range(0, total, max_voxels):
        end = min(total, start + max_voxels)
        layers.append(_voxel_layer(
            centers[start:end],
            emission_colors[start:end],
            transmission_colors[start:end],
            cube_scale,
            z_um_per_display,
            z_um_at_display_zero,
        ))
    return layers


def _z_display_step(
    *,
    depth: int,
    height: int,
    width: int,
    source_shape: tuple[int, ...],
    scale_yx: tuple[float, float],
    z_positions: np.ndarray | None,
) -> float:
    if depth <= 1:
        return 1.0
    base = _display_z_sample(0, depth, height, width, source_shape, scale_yx, z_positions)
    next_p = _display_z_sample(1, depth, height, width, source_shape, scale_yx, z_positions)
    return float(np.linalg.norm(next_p - base))


def _display_z_sample(
    z_index: int,
    depth: int,
    height: int,
    width: int,
    source_shape: tuple[int, ...],
    scale_yx: tuple[float, float],
    z_positions: np.ndarray | None,
) -> np.ndarray:
    points = display_points(
        np.array([0], dtype=np.int32),
        np.array([0], dtype=np.int32),
        np.array([z_index], dtype=np.int32),
        shape=(depth, height, width),
        z_positions=z_positions,
        source_shape=source_shape,
        scale_yx=scale_yx,
    )
    return points[0]


def _voxel_layer(
    centers: np.ndarray,
    emission_colors: np.ndarray,
    transmission_colors: np.ndarray,
    cube_scale: np.ndarray,
    z_um_per_display: float,
    z_um_at_display_zero: float,
) -> VoxelLayer:
    n = len(centers)
    vertices = _voxel_vertices(centers, cube_scale)
    faces = _voxel_faces(n)
    return VoxelLayer(
        vertices=vertices,
        faces=faces,
        face_colors=_face_colors(emission_colors, n),
        transmission_colors=_face_colors(transmission_colors, n),
        z_um_per_display=float(z_um_per_display),
        z_um_at_display_zero=float(z_um_at_display_zero),
    )


def _voxel_vertices(centers: np.ndarray, cube_scale: np.ndarray) -> np.ndarray:
    offsets = _UNIT_CUBE_VERTICES[None, :, :] * cube_scale[None, None, :]
    return (centers[:, None, :] + offsets).reshape(len(centers) * 8, 3).astype(np.float32, copy=False)


def _voxel_faces(count: int) -> np.ndarray:
    offsets = (np.arange(count, dtype=np.int32) * 8)[:, None, None]
    return (_UNIT_CUBE_FACES[None, :, :] + offsets).reshape(count * 12, 3).astype(np.int32, copy=False)


def _face_colors(colors: np.ndarray, count: int) -> np.ndarray:
    face_count = _UNIT_CUBE_FACES.shape[0]
    repeated = np.repeat(colors[:, None, :], face_count, axis=1).reshape(count * face_count, 4)
    return repeated.astype(np.float32, copy=False)

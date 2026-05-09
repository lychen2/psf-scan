"""Dense voxel-cube RGBA mesh builder for PSF OpenGL volume rendering."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from .colormap_resolver import resolve_or_default
from .psf_render import RenderOptions
from .psf_volume_geometry import VOLUME_RELIEF, display_points
from .psf_volume_selection import cut_render_voxels, select_render_voxels
from .psf_volume_types import VoxelLayer
from .psf_voxel_mesh import voxel_cube_scale, voxel_layers_batched


COLOR_GAMMA = 0.65
VOXEL_ALPHA_MAX = 0.20
VOXEL_ALPHA_MIN = 0.006
TRANSMISSION_STRENGTH = 0.78
EMISSION_ALPHA_SCALE = 0.24
EMISSION_RGB_CEILING = 0.82
MAX_VOXELS_PER_BATCH = 48_000
MIN_Z_DISPLAY_SPAN = 1e-6


def solid_slice_layers(
    data: np.ndarray,
    *,
    source_shape: tuple[int, ...],
    scale_yx: tuple[float, float],
    z_positions: np.ndarray | None,
    options: RenderOptions,
) -> list[VoxelLayer]:
    """Build colored voxel cubes inside current XYZ cut with adaptive sampling."""
    depth, height, width = data.shape
    selection = select_render_voxels(data, options)
    if selection is None:
        return []

    keep = cut_render_voxels(
        selection,
        shape=data.shape,
        source_shape=source_shape,
        options=options,
    )
    if not np.any(keep):
        return []

    z_flat, y_flat, x_flat = np.nonzero(keep)
    x_flat = x_flat.astype(np.int32, copy=False)
    y_flat = y_flat.astype(np.int32, copy=False)
    z_flat = z_flat.astype(np.int32, copy=False)
    norm_flat = selection.norm[keep].astype(np.float32, copy=False)
    alpha_flat = selection.alpha[keep].astype(np.float32, copy=False)
    colors = _rgba_values(norm_flat, alpha_flat, options.volume_cmap)
    emission_colors = _emission_values(colors)
    transmission_colors = _transmission_values(colors)
    centers = display_points(
        x_flat,
        y_flat,
        z_flat,
        shape=(depth, height, width),
        z_positions=z_positions,
        source_shape=source_shape,
        scale_yx=scale_yx,
    )

    cube_scale = voxel_cube_scale(
        shape=(depth, height, width),
        source_shape=source_shape,
        scale_yx=scale_yx,
        z_positions=z_positions,
        scale_xy_stride=selection.scale_xy_stride,
    )
    return voxel_layers_batched(
        centers,
        emission_colors,
        transmission_colors,
        cube_scale,
        max_voxels=MAX_VOXELS_PER_BATCH,
        z_um_per_display=_z_um_per_display(source_shape, z_positions),
        z_um_at_display_zero=_z_um_at_display_zero(z_positions),
    )


def _rgba_values(norm: np.ndarray, alpha: np.ndarray, cmap_name: str) -> np.ndarray:
    cmap = resolve_or_default(cmap_name)
    colors = cmap.map(np.power(norm, COLOR_GAMMA), mode="float").astype(np.float32, copy=False)
    colors[:, 3] = np.clip(alpha, VOXEL_ALPHA_MIN, VOXEL_ALPHA_MAX)
    return colors


def _transmission_values(colors: np.ndarray) -> np.ndarray:
    opacity = np.clip(colors[:, 3:4] * TRANSMISSION_STRENGTH, 0.0, 1.0)
    transmission_rgb = 1.0 - opacity * (1.0 - colors[:, :3])
    transmission_alpha = np.ones((len(colors), 1), dtype=np.float32)
    return np.concatenate((transmission_rgb, transmission_alpha), axis=1).astype(np.float32, copy=False)


def _emission_values(colors: np.ndarray) -> np.ndarray:
    rgb = np.minimum(colors[:, :3], EMISSION_RGB_CEILING)
    alpha = np.clip(colors[:, 3:4] * EMISSION_ALPHA_SCALE, 0.0, 1.0)
    return np.concatenate((rgb, alpha), axis=1).astype(np.float32, copy=False)


def _z_um_per_display(source_shape: tuple[int, ...], z_positions: np.ndarray | None) -> float:
    if z_positions is None or len(z_positions) < 2:
        return 1.0
    z = np.asarray(z_positions, dtype=np.float32)
    z_span_um = abs(float(z[-1] - z[0]))
    _source_depth, source_height, source_width = source_shape
    display_span = max(source_width, source_height) * VOLUME_RELIEF
    return z_span_um / max(MIN_Z_DISPLAY_SPAN, float(display_span))


def _z_um_at_display_zero(z_positions: np.ndarray | None) -> float:
    if z_positions is None or len(z_positions) == 0:
        return 0.0
    z = np.asarray(z_positions, dtype=np.float32)
    return float(z.mean())

"""PSF stack 渲染数据准备。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


MODE_ORTHO = "ORTHO"
MODE_MIP = "MIP"
MODE_VOLUME = "VOLUME"
VOLUME_STYLE_SURFACE = "surface"
VOLUME_STYLE_SLICES = "volume render"
VOLUME_SHIFT_PX = 18
VOLUME_DEPTH_FLOOR = 0.45
DEFAULT_THRESHOLD = 0.30
MIN_THRESHOLD = 0.01
DEFAULT_VOLUME_ALPHA = 1.0


@dataclass(frozen=True)
class RenderOptions:
    mode: str
    slice_index: int
    auto_levels: bool
    level_min: float
    level_max: float
    show_colorbar: bool
    show_labels: bool
    show_locator: bool
    volume_threshold: float
    volume_step: int
    volume_detail: str = "fast"  # "fast" | "fine"
    volume_style: str = VOLUME_STYLE_SURFACE
    volume_alpha: float = DEFAULT_VOLUME_ALPHA
    volume_cmap: str = "viridis"
    volume_cut_x: int = 0
    volume_cut_y: int = 0
    fine_interp_z: float = 2.0
    fine_interp_xy: float = 2.0


@dataclass(frozen=True)
class RenderImage:
    title: str
    image: np.ndarray
    x_label: str
    y_label: str
    locator: tuple[float, float] | None
    aspect_locked: bool
    rect: tuple[float, float, float, float]


def make_volume(frames: np.ndarray) -> np.ndarray:
    if frames.ndim == 4 and frames.shape[-1] in (3, 4):
        frames = frames.mean(axis=-1)
    if frames.ndim != 3:
        raise ValueError(f"PSF stack 必须是 (Z,H,W)，收到 {frames.shape}")
    if frames.shape[0] < 1:
        raise ValueError("PSF stack 为空")
    return frames.astype(np.float32, copy=False)


def resolve_levels(volume: np.ndarray, options: RenderOptions) -> tuple[float, float]:
    if options.mode == MODE_VOLUME or options.auto_levels:
        lo = float(np.nanmin(volume))
        hi = float(np.nanmax(volume))
    else:
        lo = float(options.level_min)
        hi = float(options.level_max)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise ValueError("colorbar 范围必须是有限数值，且 max > min")
    return lo, hi


def render_images(
    volume: np.ndarray,
    options: RenderOptions,
    z_positions: np.ndarray | None = None,
) -> list[RenderImage]:
    z_idx = _bounded_index(options.slice_index, volume.shape[0])
    if options.mode == MODE_ORTHO:
        x_idx = _bounded_index(options.volume_cut_x, volume.shape[2])
        y_idx = _bounded_index(options.volume_cut_y, volume.shape[1])
        return _render_ortho(volume, x_idx, y_idx, z_idx)
    if options.mode == MODE_MIP:
        return _render_mip(volume)
    if options.mode == MODE_VOLUME:
        return [_render_volume(volume, options)]
    raise ValueError(f"未知 PSF 绘图模式: {options.mode!r}")


def _render_ortho(volume: np.ndarray, x_idx: int, y_idx: int, z_idx: int) -> list[RenderImage]:
    zc = z_idx
    yc = y_idx
    xc = x_idx
    x_rect = _pixel_rect(volume.shape[2], volume.shape[1])
    xz_rect = _pixel_rect(volume.shape[2], volume.shape[0])
    yz_rect = _pixel_rect(volume.shape[1], volume.shape[0])
    return [
        RenderImage("XY SLICE", volume[zc], "x px", "y px", (xc, yc), True, x_rect),
        RenderImage("XZ SLICE", volume[:, yc, :], "x px", "z plane", (xc, zc), False, xz_rect),
        RenderImage("YZ SLICE", volume[:, :, xc], "y px", "z plane", (yc, zc), False, yz_rect),
    ]


def _render_mip(volume: np.ndarray) -> list[RenderImage]:
    yc = volume.shape[1] // 2
    xc = volume.shape[2] // 2
    zc = volume.shape[0] // 2
    x_rect = _pixel_rect(volume.shape[2], volume.shape[1])
    xz_rect = _pixel_rect(volume.shape[2], volume.shape[0])
    yz_rect = _pixel_rect(volume.shape[1], volume.shape[0])
    return [
        RenderImage("XY MIP", volume.max(axis=0), "x px", "y px", (xc, yc), True, x_rect),
        RenderImage("XZ MIP", volume.max(axis=1), "x px", "z plane", (xc, zc), False, xz_rect),
        RenderImage("YZ MIP", volume.max(axis=2), "y px", "z plane", (yc, zc), False, yz_rect),
    ]


def _render_volume(volume: np.ndarray, options: RenderOptions) -> RenderImage:
    lo, hi = float(np.nanmin(volume)), float(np.nanmax(volume))
    if hi <= lo:
        image = np.zeros(volume.shape[1:], dtype=np.float32)
    else:
        image = _oblique_projection(volume, (lo, hi), options)
    rect = _pixel_rect(volume.shape[2], volume.shape[1])
    return RenderImage("DEPTH PROJECTION", image, "x px", "y px", None, True, rect)


def _oblique_projection(
    volume: np.ndarray,
    levels: tuple[float, float],
    options: RenderOptions,
) -> np.ndarray:
    lo, hi = levels
    norm = np.clip((volume - lo) / (hi - lo), 0.0, 1.0)
    active = np.where(norm >= options.volume_threshold, norm, 0.0)
    projection = np.zeros(active.shape[1:], dtype=np.float32)
    denom = max(1, active.shape[0] - 1)
    for z_idx in range(0, active.shape[0], max(1, options.volume_step)):
        depth = z_idx / denom
        shift = int(round((depth - 0.5) * VOLUME_SHIFT_PX))
        shade = VOLUME_DEPTH_FLOOR + (1.0 - VOLUME_DEPTH_FLOOR) * depth
        projection = np.maximum(projection, _shift(active[z_idx], shift, -shift) * shade)
    return projection


def _shift(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    shifted = np.zeros_like(image)
    src_y, dst_y = _slices(image.shape[0], dy)
    src_x, dst_x = _slices(image.shape[1], dx)
    shifted[dst_y, dst_x] = image[src_y, src_x]
    return shifted


def _slices(length: int, delta: int) -> tuple[slice, slice]:
    if abs(delta) >= length:
        return slice(0, 0), slice(0, 0)
    if delta >= 0:
        return slice(0, length - delta), slice(delta, length)
    return slice(-delta, length), slice(0, length + delta)


def _bounded_index(index: int, length: int) -> int:
    return min(max(0, int(index)), length - 1)


def _pixel_rect(width: int, height: int) -> tuple[float, float, float, float]:
    return (-0.5, -0.5, float(width), float(height))

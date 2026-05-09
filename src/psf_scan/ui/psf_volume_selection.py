"""Whole-volume voxel selection and adaptive cut mapping."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .psf_render import RenderOptions


ALPHA_GAMMA = 1.2
ALPHA_CUTOFF = 1e-4
VOXEL_ALPHA_SCALE = 0.18
TARGET_VOXELS = 120_000
TARGET_VOXELS_FINE = 300_000
MAX_SELECTED_VOXELS_FAST = 180_000
MAX_SELECTED_VOXELS_FINE = 420_000
MIN_VISIBLE_NORM = 0.0
HIGH_DETAIL_NORM = 0.32
HIGH_GRAD_NORM = 0.08
MIN_BRIGHT_FLOOR = 0.06
FAST_MIN_BRIGHT = 0.09
FAST_GRAD_MIN_BRIGHT = 0.14
CUT_PADDING_FRACTION = 0.08
MIN_CUT_PADDING = 2


@dataclass(frozen=True)
class VoxelSelection:
    keep: np.ndarray
    norm: np.ndarray
    alpha: np.ndarray
    scale_xy_stride: int
    bounds_min: np.ndarray
    bounds_max: np.ndarray


def select_render_voxels(data: np.ndarray, options: RenderOptions) -> VoxelSelection | None:
    peak = max(ALPHA_CUTOFF, float(data.max(initial=0.0)))
    if peak <= ALPHA_CUTOFF:
        return None
    norm = np.clip(data / peak, 0.0, 1.0)
    alpha = _alpha_values(norm, options.volume_alpha)
    if options.volume_detail == "fine":
        keep, stride_xy = _fine_keep(data, norm, alpha, options)
    else:
        keep, stride_xy = _fast_keep(data, norm, alpha, options)
    if not np.any(keep):
        return None
    bounds_min, bounds_max = _mask_bounds(keep)
    return VoxelSelection(keep, norm, alpha, stride_xy, bounds_min, bounds_max)


def cut_render_voxels(
    selection: VoxelSelection,
    *,
    shape: tuple[int, ...],
    source_shape: tuple[int, ...],
    options: RenderOptions,
) -> np.ndarray:
    cuts = _adaptive_cuts(selection, shape=shape, source_shape=source_shape, options=options)
    z_idx, y_idx, x_idx = np.indices(shape, dtype=np.int32)
    return selection.keep & (z_idx <= cuts[0]) & (y_idx <= cuts[1]) & (x_idx <= cuts[2])


def _fine_keep(
    data: np.ndarray,
    norm: np.ndarray,
    alpha: np.ndarray,
    options: RenderOptions,
) -> tuple[np.ndarray, int]:
    active = (data > ALPHA_CUTOFF) & (norm >= MIN_VISIBLE_NORM) & (alpha > ALPHA_CUTOFF)
    if not np.any(active):
        return active, 1
    grad = _gradient_norm(norm)
    active = _fine_significant_mask(active, norm, grad, threshold=options.volume_threshold)
    stride_xy = _adaptive_stride_active(int(np.count_nonzero(active)), target=TARGET_VOXELS_FINE)
    return _tighten_fine_budget(active, norm, stride_xy, MAX_SELECTED_VOXELS_FINE)


def _fast_keep(
    data: np.ndarray,
    norm: np.ndarray,
    alpha: np.ndarray,
    options: RenderOptions,
) -> tuple[np.ndarray, int]:
    active = (data > ALPHA_CUTOFF) & (alpha > ALPHA_CUTOFF)
    if not np.any(active):
        return active, 1
    grad = _gradient_norm(norm)
    active = _fast_significant_mask(active, norm, grad, threshold=options.volume_threshold)
    preserve = _fast_preserve_mask(norm, grad, threshold=options.volume_threshold)
    stride = _adaptive_stride(data.shape, target=TARGET_VOXELS)
    keep = _adaptive_keep_mask(active, norm, stride, preserve=preserve)
    return _cap_keep_mask(keep, norm, max_selected=MAX_SELECTED_VOXELS_FAST), 1


def _adaptive_cuts(
    selection: VoxelSelection,
    *,
    shape: tuple[int, ...],
    source_shape: tuple[int, ...],
    options: RenderOptions,
) -> tuple[int, int, int]:
    values = (options.slice_index, options.volume_cut_y, options.volume_cut_x)
    return tuple(
        _adaptive_cut(values[axis], shape[axis], source_shape[axis], selection, axis)
        for axis in range(3)
    )


def _adaptive_cut(value: int, length: int, source_length: int, selection: VoxelSelection, axis: int) -> int:
    if length <= 0:
        return -1
    if length == 1 or source_length <= 1:
        return 0
    ratio = min(max(float(value) / float(source_length - 1), 0.0), 1.0)
    low, high = _padded_axis_bounds(selection, length, axis)
    return min(max(0, round(low + ratio * (high - low))), length - 1)


def _padded_axis_bounds(selection: VoxelSelection, length: int, axis: int) -> tuple[int, int]:
    low = int(selection.bounds_min[axis])
    high = int(selection.bounds_max[axis])
    span = max(1, high - low)
    padding = max(MIN_CUT_PADDING, int(round(span * CUT_PADDING_FRACTION)))
    return max(0, low - padding), min(length - 1, high + padding)


def _mask_bounds(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    coords = np.column_stack(np.nonzero(mask))
    return coords.min(axis=0).astype(np.int32), coords.max(axis=0).astype(np.int32)


def _alpha_values(norm: np.ndarray, volume_alpha: float) -> np.ndarray:
    alpha = np.power(norm, ALPHA_GAMMA)
    peak = max(ALPHA_CUTOFF, float(alpha.max(initial=0.0)))
    return np.clip(alpha / peak * float(volume_alpha) * VOXEL_ALPHA_SCALE, 0.0, 1.0)


def _adaptive_stride(shape: tuple[int, int, int], target: int) -> int:
    voxels = int(shape[0]) * int(shape[1]) * int(shape[2])
    if voxels <= max(1, target):
        return 1
    stride = int(np.ceil((voxels / max(1, target)) ** (1.0 / 3.0)))
    return max(1, stride)


def _adaptive_stride_active(active_count: int, target: int) -> int:
    if active_count <= max(1, target):
        return 1
    stride = int(np.ceil((active_count / max(1, target)) ** (1.0 / 3.0)))
    return max(1, stride)


def _adaptive_keep_mask(
    active: np.ndarray,
    norm: np.ndarray,
    stride: int,
    *,
    preserve: np.ndarray | None = None,
) -> np.ndarray:
    if stride <= 1:
        return active
    preserve_mask = _preserve_mask(norm) if preserve is None else preserve
    z, y, x = np.indices(active.shape, dtype=np.int32)
    sampled = (z % stride == 0) & (y % stride == 0) & (x % stride == 0)
    return active & (preserve_mask | sampled)


def _adaptive_keep_mask_xy(active: np.ndarray, norm: np.ndarray, stride: int) -> np.ndarray:
    if stride <= 1:
        return active
    preserve = _preserve_mask(norm)
    _z, y, x = np.indices(active.shape, dtype=np.int32)
    sampled = (y % stride == 0) & (x % stride == 0)
    return active & (preserve | sampled)


def _tighten_fine_budget(
    active: np.ndarray,
    norm: np.ndarray,
    stride_xy: int,
    max_selected: int,
) -> tuple[np.ndarray, int]:
    keep = _adaptive_keep_mask_xy(active, norm, stride_xy)
    selected = int(np.count_nonzero(keep))
    while selected > max(1, max_selected):
        stride_xy += 1
        keep = _adaptive_keep_mask_xy(active, norm, stride_xy)
        selected = int(np.count_nonzero(keep))
        if stride_xy >= 12:
            break
    return keep, stride_xy


def _preserve_mask(norm: np.ndarray) -> np.ndarray:
    grad = _gradient_norm(norm)
    return (norm >= HIGH_DETAIL_NORM) | (grad >= HIGH_GRAD_NORM)


def _gradient_norm(norm: np.ndarray) -> np.ndarray:
    dz = np.zeros_like(norm)
    dy = np.zeros_like(norm)
    dx = np.zeros_like(norm)
    dz[1:, :, :] = np.abs(norm[1:, :, :] - norm[:-1, :, :])
    dy[:, 1:, :] = np.abs(norm[:, 1:, :] - norm[:, :-1, :])
    dx[:, :, 1:] = np.abs(norm[:, :, 1:] - norm[:, :, :-1])
    return np.maximum(np.maximum(dz, dy), dx)


def _fine_significant_mask(
    active: np.ndarray,
    norm: np.ndarray,
    grad: np.ndarray,
    *,
    threshold: float,
) -> np.ndarray:
    bright_floor = max(MIN_BRIGHT_FLOOR, float(threshold) * 0.35)
    return active & ((norm >= bright_floor) | (grad >= HIGH_GRAD_NORM))


def _fast_significant_mask(
    active: np.ndarray,
    norm: np.ndarray,
    grad: np.ndarray,
    *,
    threshold: float,
) -> np.ndarray:
    bright_floor = max(FAST_MIN_BRIGHT, float(threshold) * 0.30)
    return active & ((norm >= bright_floor) | ((grad >= HIGH_GRAD_NORM * 1.35) & (norm >= FAST_GRAD_MIN_BRIGHT)))


def _fast_preserve_mask(norm: np.ndarray, grad: np.ndarray, *, threshold: float) -> np.ndarray:
    bright_floor = max(FAST_MIN_BRIGHT, float(threshold) * 0.40)
    return (norm >= max(HIGH_DETAIL_NORM, bright_floor)) | ((grad >= HIGH_GRAD_NORM * 1.45) & (norm >= FAST_GRAD_MIN_BRIGHT))


def _cap_keep_mask(keep: np.ndarray, norm: np.ndarray, *, max_selected: int) -> np.ndarray:
    selected = int(np.count_nonzero(keep))
    if selected <= max(1, max_selected):
        return keep
    flat_keep = keep.ravel()
    idx = np.flatnonzero(flat_keep)
    if len(idx) <= max_selected:
        return keep
    scores = norm.ravel()[idx]
    top = np.argpartition(scores, -max_selected)[-max_selected:]
    capped = np.zeros_like(flat_keep, dtype=bool)
    capped[idx[top]] = True
    return capped.reshape(keep.shape)

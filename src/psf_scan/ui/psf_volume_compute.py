"""PSF volume 纯计算 + 后台等值面 worker。

把 marching cubes / 高斯滤波 / z 插值这些 CPU 密集的事推到 QThreadPool，
不堵 UI 主线程。GL mesh 对象仍由主线程构造。
"""

from __future__ import annotations

import sys

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, Signal
from scipy.ndimage import gaussian_filter, zoom

from .psf_render import MIN_THRESHOLD, RenderOptions, VOLUME_STYLE_SLICES, VOLUME_STYLE_SURFACE
from .psf_volume_geometry import axis_scale, display_vertices, render_z_positions
from .psf_volume_solid import solid_slice_layers
from .psf_volume_types import PreparedVolume, SurfaceLayer

# 渲染常量
ISO_LEVEL_MAX = 0.92
REBUILD_INTERVAL_MS = 250
FAST_MIN_Z = 2
SMOOTH_SIGMA = (0.45, 0.25, 0.25)
VOLUME_BG = "#f7f5ef"
VOLUME_GRID = "#c8d5d7"
SURFACE_SCALE = ("#f0a6a0", "#db7069", "#b84642", "#842a2d", "#4d161e", "#000000")

# fast 常规情况下不改数据网格，极大体数据才只沿 Z 减层。
MAX_VOXELS_FAST = 8 * 1024 * 1024
# fine 上限，避免 2x 三轴插值把内存冲到不可控。
MAX_VOXELS_FINE = 24 * 1024 * 1024


def expected_voxels(
    volume_shape: tuple[int, int, int],
    options: RenderOptions,
    *,
    live: bool = False,
) -> int:
    """预测 ``prepare_volume`` 走完后 worker 持有的体素数。

    fit_roi_to_budget 用这个值替代裸 cropped 体素数，确保预算判定看的是
    fast 减层、fine 升采样之后的真实占用。"""
    z, h, w = int(volume_shape[0]), int(volume_shape[1]), int(volume_shape[2])
    voxels = z * h * w
    if live:
        return voxels
    detail = getattr(options, "volume_detail", "fast")
    style = getattr(options, "volume_style", VOLUME_STYLE_SURFACE)
    if detail == "fast" and style != VOLUME_STYLE_SLICES:
        if voxels > MAX_VOXELS_FAST:
            z_target = max(FAST_MIN_Z, MAX_VOXELS_FAST // max(1, h * w))
            voxels = z_target * h * w
    if detail == "fine":
        z_factor = max(1.0, float(getattr(options, "fine_interp_z", 2.0)))
        xy_req = max(1.0, float(getattr(options, "fine_interp_xy", 2.0)))
        xy_budget = (MAX_VOXELS_FINE / max(1.0, voxels * z_factor)) ** 0.5
        xy_factor = max(1.0, min(xy_req, xy_budget))
        if z_factor > 1.01 or xy_factor > 1.01:
            voxels = int(voxels * z_factor * xy_factor * xy_factor)
    return int(voxels)


def estimate_active_voxels(
    volume: np.ndarray,
    levels: tuple[float, float],
    *,
    threshold: float,
    band: float = 0.12,
) -> int:
    """粗估 marching cubes 实际会吐多少三角形——只数 normalized 值落在 iso
    带 ``[threshold - band, threshold + band]`` 内的体素。

    逻辑动机：等值面只在密度跨过 iso 的那一层产生顶点。外围全黑 / 内部全亮
    都远离 iso，几乎贡献 0；亮斑边缘窄薄一圈才贡献顶点。这个数往往比裸
    cropped 体素小一两个量级，作为 worst-case 内存损耗的内容相关估值。
    """
    lo, hi = levels
    if hi <= lo:
        return 0
    norm = np.clip((volume.astype(np.float32, copy=False) - lo) / (hi - lo), 0.0, 1.0)
    in_band = (norm >= max(0.0, threshold - band)) & (norm <= min(1.0, threshold + band))
    return int(in_band.sum())


# ── 纯计算 helpers ──────────────────────────────────────────


def prepare_volume(
    volume: np.ndarray,
    levels: tuple[float, float],
    *,
    live: bool,
    detail: str = "fast",
    preserve_z: bool = False,
    threshold: float = MIN_THRESHOLD,
    fine_interp_z: float = 2.0,
    fine_interp_xy: float = 2.0,
) -> PreparedVolume:
    """归一化 + fast Z 降采样 + 高斯 + fine 三轴插值 + 重归一化。

    fast 保留原相机横向像素，只在 Z 方向减层。
    fine 走全分辨率体数据，并用线性插值提高等值面网格分辨率。
    """
    norm = _normalized_volume(volume, levels)
    source_shape = norm.shape
    if detail == "fast" and not preserve_z:
        norm = _maybe_downsample_z(norm)
    if live:
        data = norm.astype(np.float32, copy=False)
        return PreparedVolume(data, source_shape)
    smooth = gaussian_filter(norm, sigma=SMOOTH_SIGMA)
    if detail == "fine":
        smooth = _maybe_upsample_fine(
            smooth,
            z_factor_req=fine_interp_z,
            xy_factor_req=fine_interp_xy,
        )
    smooth = smooth.astype(np.float32, copy=False)
    peak = float(smooth.max())
    if peak > 1e-6:
        smooth = smooth / peak
    scale_y = axis_scale(smooth.shape[1], source_shape[1])
    scale_x = axis_scale(smooth.shape[2], source_shape[2])
    return PreparedVolume(smooth, source_shape, scale_y, scale_x)


def iso_levels(options: RenderOptions, *, live: bool) -> np.ndarray:
    """外层 = 用户 iso（最低 iso = 最大壳），内层向 ISO_LEVEL_MAX 递增。

    live 模式下只画用户 iso 那一层，避开多层 marching cubes 雪崩。
    """
    if options.volume_threshold < MIN_THRESHOLD:
        raise ValueError(f"iso threshold 必须 >= {MIN_THRESHOLD:.3f}")
    start = float(options.volume_threshold)
    if live:
        return np.array([start], dtype=np.float32)
    layer_count = max(1, int(options.volume_step))
    stop = float(ISO_LEVEL_MAX)
    if layer_count == 1 or stop <= start:
        return np.array([start], dtype=np.float32)
    return np.linspace(start, stop, layer_count, dtype=np.float32)


def layer_alpha(index: int, layer_count: int) -> float:
    """外壳薄到能透视，内核实色突出。"""
    if layer_count <= 1:
        return 0.85
    t = index / max(1, layer_count - 1)
    return 0.20 + 0.80 * t  # 外 0.20 → 内 1.00


def layer_color(index: int, layer_count: int, alpha: float) -> tuple[float, float, float, float]:
    """单层用外层色（用户 iso 是外壳）；多层从浅红渐到近黑。"""
    if layer_count <= 1:
        return _rgba(SURFACE_SCALE[1], alpha)
    palette_idx = round(index / max(1, layer_count - 1) * (len(SURFACE_SCALE) - 1))
    return _rgba(SURFACE_SCALE[palette_idx], alpha)


def _normalized_volume(volume: np.ndarray, levels: tuple[float, float]) -> np.ndarray:
    lo, hi = levels
    data = (volume.astype(np.float32, copy=False) - lo) / (hi - lo)
    return np.clip(data, 0.0, 1.0)


def _maybe_downsample_z(volume: np.ndarray) -> np.ndarray:
    """fast 保留 XY 原始像素，仅按 Z 减层。"""
    if volume.size <= MAX_VOXELS_FAST:
        return volume
    _, height, width = volume.shape
    z_budget = max(FAST_MIN_Z, MAX_VOXELS_FAST // max(1, height * width))
    z_target = min(volume.shape[0], z_budget)
    factors = (z_target / volume.shape[0], 1.0, 1.0)
    return zoom(volume, factors, order=1).astype(np.float32, copy=False)


def _maybe_upsample_fine(
    volume: np.ndarray,
    *,
    z_factor_req: float,
    xy_factor_req: float,
) -> np.ndarray:
    """fine 保持 Z 插值，XY 受体素预算约束，避免内存峰值过高。"""
    voxels = int(volume.size)
    if voxels <= 0:
        return volume
    z_factor = max(1.0, float(z_factor_req))
    xy_req = max(1.0, float(xy_factor_req))
    xy_budget = np.sqrt(MAX_VOXELS_FINE / max(1.0, float(voxels) * z_factor))
    xy_factor = min(xy_req, float(xy_budget))
    xy_factor = max(1.0, xy_factor)
    if z_factor <= 1.01 and xy_factor <= 1.01:
        return volume
    return zoom(volume, (z_factor, xy_factor, xy_factor), order=1).astype(np.float32, copy=False)


def _rgba(hex_color: str, alpha: float) -> tuple[float, float, float, float]:
    color = pg.mkColor(hex_color)
    return (color.redF(), color.greenF(), color.blueF(), alpha)


# ── 后台等值面 worker ───────────────────────────────────────


class IsosurfaceSignals(QObject):
    # gen, list[SurfaceLayer | SliceLayer], shape
    done = Signal(int, object, object)


class IsosurfaceWorker(QRunnable):
    def __init__(
        self,
        *,
        volume: np.ndarray,
        levels: tuple[float, float],
        options: RenderOptions,
        z_positions: np.ndarray | None,
        live: bool,
        generation: int,
        full_shape: tuple[int, ...] | None = None,
        roi_origin: tuple[int, int] = (0, 0),
    ) -> None:
        super().__init__()
        self._volume = volume
        self._levels = levels
        self._options = options
        self._z_positions = z_positions
        self._live = live
        self._gen = generation
        self._full_shape = full_shape
        self._roi_origin = roi_origin
        self.signals = IsosurfaceSignals()

    def run(self) -> None:
        try:
            # live 时强制 fast；非 live 用 options.volume_detail
            detail = "fast" if self._live else getattr(self._options, "volume_detail", "fast")
            prepared = prepare_volume(
                self._volume,
                self._levels,
                live=self._live,
                detail=detail,
                preserve_z=self._options.volume_style == VOLUME_STYLE_SLICES,
                threshold=self._options.volume_threshold,
                fine_interp_z=getattr(self._options, "fine_interp_z", 2.0),
                fine_interp_xy=getattr(self._options, "fine_interp_xy", 2.0),
            )
            levels = iso_levels(self._options, live=self._live)
            count = len(levels)
            data = prepared.data
            data_c = np.ascontiguousarray(data)
            z_interp = render_z_positions(self._z_positions, depth=data.shape[0])
            if self._options.volume_style == VOLUME_STYLE_SLICES:
                results = solid_slice_layers(
                    data,
                    source_shape=prepared.source_shape,
                    scale_yx=(prepared.scale_y, prepared.scale_x),
                    z_positions=z_interp,
                    options=self._options,
                )
                self.signals.done.emit(self._gen, results, data.shape)
                return
            if self._options.volume_style != VOLUME_STYLE_SURFACE:
                raise ValueError(f"unknown volume style: {self._options.volume_style!r}")
            results: list[SurfaceLayer] = []
            for index, level in enumerate(levels):
                vertices, faces = pg.isosurface(data_c, float(level))
                if len(vertices) == 0 or len(faces) == 0:
                    continue
                alpha = layer_alpha(index, count) * self._options.volume_alpha
                color = layer_color(index, count, alpha)
                disp = display_vertices(
                    vertices,
                    data.shape,
                    z_positions=z_interp,
                    source_shape=prepared.source_shape,
                    scale_yx=(prepared.scale_y, prepared.scale_x),
                    full_shape=self._full_shape,
                    roi_origin=self._roi_origin,
                )
                results.append(SurfaceLayer(
                    np.ascontiguousarray(disp, dtype=np.float32),
                    np.ascontiguousarray(faces),
                    color,
                ))
            self.signals.done.emit(self._gen, results, data.shape)
        except Exception as exc:  # noqa: BLE001
            print(f"IsosurfaceWorker error: {exc!r}", file=sys.stderr)
            self.signals.done.emit(self._gen, [], None)

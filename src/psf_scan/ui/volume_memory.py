"""体绘制内存预算与 ROI 自动收缩。

不依赖 psutil。Linux 读 /proc/meminfo，其它平台退到 sysconf；都失败就用
4 GiB 的保守上限。volume voxel 经 gaussian + isosurface + 副本可达 ~120
bytes/voxel，预算只占可用内存的 25% 留余地。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple


# 估计每个体素在 worker pipeline 里的峰值占用：float32 主数据 + 高斯 +
# isosurface 网格副本 + voxel 颜色 (RGBA float32 emission/transmission) ≈ 120 B
VOXEL_PEAK_BYTES = 120
DEFAULT_BUDGET_FRACTION = 0.25
FALLBACK_AVAILABLE_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB
MIN_ROI_SIDE = 8


def available_memory_bytes() -> int:
    """读"可分配内存"的近似值；失败返回 fallback。"""
    try:
        text = Path("/proc/meminfo").read_text()
        for line in text.splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                return int(parts[1]) * 1024
    except Exception:  # noqa: BLE001
        pass
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return FALLBACK_AVAILABLE_BYTES


def voxel_budget(fraction: float = DEFAULT_BUDGET_FRACTION) -> int:
    return int(available_memory_bytes() * fraction / VOXEL_PEAK_BYTES)


def fit_roi_to_budget(
    volume_shape: Tuple[int, int, int],
    roi: Tuple[int, int, int, int],
    budget: int,
    *,
    options: Optional[object] = None,
    live: bool = False,
) -> Tuple[int, int, int, int]:
    """预算超了就绕 ROI 中心对称收缩 XY，Z 不动。

    ``options`` 给定时按 ``prepare_volume`` 的 fast/fine 后体素数算预算，
    而不是 cropped 原始体素数——避免把"fast 会减一半"或"fine 会乘 8"的
    pipeline 优化漏算。
    """
    z, h, w = volume_shape
    x0, y0, x1, y1 = roi
    x0 = max(0, min(int(x0), w))
    y0 = max(0, min(int(y0), h))
    x1 = max(x0 + 1, min(int(x1), w))
    y1 = max(y0 + 1, min(int(y1), h))
    voxels = _expected_voxels((z, y1 - y0, x1 - x0), options, live)
    if voxels <= budget or budget <= 0:
        return (x0, y0, x1, y1)
    side = _solve_side_for_budget(z, w, h, options, live, budget)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    nx0 = max(0, cx - side // 2)
    ny0 = max(0, cy - side // 2)
    nx1 = min(w, nx0 + side)
    ny1 = min(h, ny0 + side)
    nx0 = max(0, nx1 - side)
    ny0 = max(0, ny1 - side)
    return (nx0, ny0, nx1, ny1)


def _expected_voxels(
    cropped_shape: Tuple[int, int, int],
    options: Optional[object],
    live: bool,
) -> int:
    z, h, w = cropped_shape
    if options is None:
        return z * h * w
    # 延后 import 防止循环（psf_volume_compute 也用 RenderOptions）
    from .psf_volume_compute import expected_voxels
    return expected_voxels((z, h, w), options, live=live)


def _solve_side_for_budget(
    z: int,
    full_w: int,
    full_h: int,
    options: Optional[object],
    live: bool,
    budget: int,
) -> int:
    """二分搜最大 side，使 expected_voxels((z, side, side)) ≤ budget。"""
    lo = MIN_ROI_SIDE
    hi = max(MIN_ROI_SIDE, min(full_w, full_h))
    if _expected_voxels((z, lo, lo), options, live) > budget:
        return lo
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _expected_voxels((z, mid, mid), options, live) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo


def estimate_bytes(volume_shape: Tuple[int, int, int]) -> int:
    z, h, w = volume_shape
    return z * h * w * VOXEL_PEAK_BYTES

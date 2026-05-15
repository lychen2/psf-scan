"""Live camera 快照 & 录像 — 写入用户 data_dir 下的 snapshots/ 与 recordings/。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile
from PIL import Image

from ..ui.colormap_resolver import resolve_or_default


@dataclass(frozen=True)
class SnapshotPaths:
    tiff: Path
    png: Path
    csv: Path
    meta: Path


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _apply_colormap_rgb(frame: np.ndarray, cmap_name: str) -> np.ndarray:
    """对单通道帧上 colormap → RGB uint8。"""
    cmap = resolve_or_default(cmap_name)
    lut = cmap.getLookupTable(0.0, 1.0, 256)[:, :3].astype(np.uint8)
    f = frame.astype(np.float32)
    lo, hi = float(f.min()), float(f.max())
    span = max(1e-12, hi - lo)
    idx = np.clip((f - lo) * 255.0 / span, 0, 255).astype(np.uint8)
    return lut[idx]


def _save_csv(path: Path, frame: np.ndarray) -> None:
    if np.issubdtype(frame.dtype, np.integer):
        np.savetxt(path, frame, delimiter=",", fmt="%d")
    else:
        np.savetxt(path, frame, delimiter=",", fmt="%.6g")


def _save_meta(path: Path, frame: np.ndarray, cmap_name: str) -> None:
    f64 = frame.astype(np.float64, copy=False)
    meta: dict[str, object] = {
        "saved_at": time.time(),
        "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "shape": list(frame.shape),
        "dtype": str(frame.dtype),
        "cmap": cmap_name,
        "min": float(f64.min()),
        "max": float(f64.max()),
        "mean": float(f64.mean()),
        "std": float(f64.std()),
    }
    if np.issubdtype(frame.dtype, np.integer):
        info = np.iinfo(frame.dtype)
        sat_count = int(np.sum(frame >= info.max - 1))
        meta["max_value"] = int(info.max)
        meta["saturated_pixels"] = sat_count
        meta["saturated_fraction"] = sat_count / float(frame.size)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def save_snapshot(base_dir: Path, frame: np.ndarray, cmap_name: str) -> SnapshotPaths:
    """落 4 份原始数据:
    - .tif: 位深无损图
    - .png: colormap 后的预览
    - .csv: 像素强度 2D 矩阵 (utf-8, 逗号分隔; 整型用 %d, 浮点用 %.6g)
    - .json: shape/dtype/colormap/统计/饱和像素元数据
    """
    out = _ensure_dir(Path(base_dir) / "snapshots")
    stem = f"cam_{_timestamp()}"
    paths = SnapshotPaths(
        tiff=out / f"{stem}.tif",
        png=out / f"{stem}.png",
        csv=out / f"{stem}.csv",
        meta=out / f"{stem}.json",
    )
    tifffile.imwrite(paths.tiff, frame)
    Image.fromarray(_apply_colormap_rgb(frame, cmap_name)).save(paths.png)
    _save_csv(paths.csv, frame)
    _save_meta(paths.meta, frame, cmap_name)
    return paths


class VideoRecorder:
    """流式多页 TIFF 录像 — 每帧追加，stop 时关闭文件。"""

    def __init__(self) -> None:
        self._writer: Optional[tifffile.TiffWriter] = None
        self._path: Optional[Path] = None
        self._started_at: float = 0.0
        self._frame_count: int = 0
        self._frame_shape: Optional[tuple[int, ...]] = None
        self._frame_dtype: Optional[np.dtype] = None

    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def start(self, base_dir: Path) -> Path:
        if self._writer is not None:
            raise RuntimeError("已在录像中")
        out = _ensure_dir(Path(base_dir) / "recordings")
        path = out / f"rec_{_timestamp()}.tif"
        self._writer = tifffile.TiffWriter(str(path), bigtiff=True, append=False)
        self._path = path
        self._started_at = time.time()
        self._frame_count = 0
        self._frame_shape = None
        self._frame_dtype = None
        return path

    def append(self, frame: np.ndarray) -> None:
        if self._writer is None:
            return
        if self._frame_shape is None:
            self._frame_shape = frame.shape
            self._frame_dtype = frame.dtype
        elif frame.shape != self._frame_shape or frame.dtype != self._frame_dtype:
            # 录像中改了像素格式 / 分辨率 — 跳过避免 TIFF 损坏
            return
        self._writer.write(frame, contiguous=False)
        self._frame_count += 1

    def stop(self) -> tuple[Path, int, float]:
        if self._writer is None:
            raise RuntimeError("未在录像")
        self._writer.close()
        duration = time.time() - self._started_at
        result = (self._path, self._frame_count, duration)
        self._writer = None
        self._path = None
        self._frame_count = 0
        return result  # type: ignore[return-value]

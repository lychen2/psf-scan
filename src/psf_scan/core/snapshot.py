"""Live camera 快照 & 录像 — 写入用户 data_dir 下的 snapshots/ 与 recordings/。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile
from PIL import Image

from ..ui.colormap_resolver import resolve_or_default


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


def save_snapshot(base_dir: Path, frame: np.ndarray, cmap_name: str) -> tuple[Path, Path]:
    """落两份：原始位深 TIFF + colormap 后的 PNG。返回 (tiff_path, png_path)。"""
    out = _ensure_dir(Path(base_dir) / "snapshots")
    stem = f"cam_{_timestamp()}"
    tiff_path = out / f"{stem}.tif"
    png_path = out / f"{stem}.png"
    tifffile.imwrite(tiff_path, frame)
    Image.fromarray(_apply_colormap_rgb(frame, cmap_name)).save(png_path)
    return tiff_path, png_path


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

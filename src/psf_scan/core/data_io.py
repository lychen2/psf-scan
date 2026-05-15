"""扫描结果保存 — HDF5 + TIFF + CSV + MAT + meta.json。

两条路径:
- ``save_scan`` (legacy): 扫完一次性把整个 stack 写盘 — 内存里要完整 frames.
- ``StreamingScanWriter`` + ``finalize_streamed_scan`` (C.4): 边采边写 stack.h5 +
  最后只补 tif/mat/csv/meta. 适合长扫描 / 防中途崩溃数据丢失.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import tifffile
from scipy.io import savemat

from .scanner import ScanMetadata, ScanParams, ScanResult


class StreamingScanWriter:
    """每采一帧 append + flush 到 stack.h5 — 中途崩溃后已写帧不丢。

    用法:
        w = StreamingScanWriter.open(out_dir, params, name=...)
        for idx, (x, y, z, frame, t) in enumerate(...):
            w.append(idx, x, y, z, frame, t)   # 首帧 lazy-init dataset 用真实 shape/dtype
        w.finalize_attrs(metadata=..., started_at=..., finished_at=...)
        w.close()
        # 之后 finalize_streamed_scan(w.target_dir, result) 补 tif/mat/csv/meta

    并发安全: 仅 scanner 自己的 QThread 调; flush 频繁但 h5py 已有缓冲, 实测 1ms 内.
    """

    def __init__(self, target_dir: Path, h5_path: Path, file: h5py.File,
                 positions_ds: h5py.Dataset, timestamps_ds: h5py.Dataset) -> None:
        self.target_dir = Path(target_dir)
        self.h5_path = Path(h5_path)
        self._file = file
        self._frames: Optional[h5py.Dataset] = None  # lazy init at first append
        self._corrected: Optional[h5py.Dataset] = None
        self._positions = positions_ds
        self._timestamps = timestamps_ds
        self._count = 0
        self._closed = False

    @classmethod
    def open(cls, out_dir: Path, params: ScanParams, *,
             name: str | None = None) -> "StreamingScanWriter":
        out_dir = Path(out_dir)
        if name is None:
            name = time.strftime("psf_%Y%m%d_%H%M%S", time.localtime())
        target = out_dir / name
        target.mkdir(parents=True, exist_ok=True)
        h5_path = target / "stack.h5"
        f = h5py.File(h5_path, "w")
        positions = f.create_dataset(
            "positions", shape=(0, 3), maxshape=(None, 3), dtype="float64",
            chunks=(64, 3),
        )
        timestamps = f.create_dataset(
            "timestamps", shape=(0,), maxshape=(None,), dtype="float64",
            chunks=(64,),
        )
        f.attrs["params"] = json.dumps(asdict(params))
        f.attrs["started_at"] = float(time.time())
        f.attrs["streaming"] = True
        return cls(target, h5_path, f, positions, timestamps)

    def _init_frames_ds(self, frame: np.ndarray) -> None:
        chunks = (1,) + tuple(frame.shape)
        self._frames = self._file.create_dataset(
            "frames", shape=(0,) + tuple(frame.shape),
            maxshape=(None,) + tuple(frame.shape),
            dtype=frame.dtype, chunks=chunks,
            compression="gzip", compression_opts=4,
        )

    def _init_corrected_ds(self, frame: np.ndarray) -> None:
        chunks = (1,) + tuple(frame.shape)
        self._corrected = self._file.create_dataset(
            "frames_corrected", shape=(0,) + tuple(frame.shape),
            maxshape=(None,) + tuple(frame.shape),
            dtype=frame.dtype, chunks=chunks,
            compression="gzip", compression_opts=4,
        )

    def append(self, idx: int, x: float, y: float, z: float,
               frame: np.ndarray, t: float,
               *, corrected: np.ndarray | None = None) -> None:
        if self._closed:
            raise RuntimeError("StreamingScanWriter 已关闭")
        if self._frames is None:
            self._init_frames_ds(frame)
        n = idx + 1
        if n > self._frames.shape[0]:
            self._frames.resize(n, axis=0)
            self._positions.resize(n, axis=0)
            self._timestamps.resize(n, axis=0)
        self._frames[idx] = frame
        if corrected is not None:
            if self._corrected is None:
                self._init_corrected_ds(corrected)
            if n > self._corrected.shape[0]:
                self._corrected.resize(n, axis=0)
            self._corrected[idx] = corrected
        self._positions[idx] = (float(x), float(y), float(z))
        self._timestamps[idx] = float(t)
        self._count = n
        self._file.flush()

    @property
    def count(self) -> int:
        return self._count

    def finalize_attrs(self, *, metadata: ScanMetadata | None,
                       started_at: float, finished_at: float,
                       calibration: dict | None = None,
                       pixel_calibration: dict | None = None) -> None:
        """关闭前写最终的 attrs (供 finalize_streamed_scan 读)。"""
        if self._closed:
            return
        self._file.attrs["metadata"] = json.dumps(asdict(metadata or ScanMetadata()))
        self._file.attrs["started_at"] = float(started_at)
        self._file.attrs["finished_at"] = float(finished_at)
        if calibration is not None:
            self._file.attrs["calibration"] = json.dumps(calibration)
        if pixel_calibration is not None:
            self._file.attrs["pixel_calibration"] = json.dumps(pixel_calibration)
        self._file.attrs["streaming"] = False  # 标记: 写入已正常收尾
        self._file.flush()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._file.close()
        finally:
            self._closed = True


def finalize_streamed_scan(target: Path, result: ScanResult) -> Path:
    """配合 StreamingScanWriter — stack.h5 已写好, 这里只补 tif/mat/csv/meta.

    传入的 ``result`` 必须 frames/positions/timestamps 都齐 (app 层从 h5 回读或
    直接复用 worker 内存中的副本即可)。
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    frames = result.frames
    corrected = result.corrected_frames

    tifffile.imwrite(target / "stack.tif", frames, bigtiff=True)
    if corrected is not None:
        tifffile.imwrite(target / "stack_corrected.tif", corrected, bigtiff=True)
    np.savetxt(
        target / "positions.csv", result.positions, delimiter=",",
        header="x_um,y_um,z_um", comments="",
    )
    mat_payload = {
        "frames": frames,
        "positions": result.positions,
        "timestamps": result.timestamps,
        "params": json.dumps(asdict(result.params)),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
    if corrected is not None:
        mat_payload["frames_corrected"] = corrected
    if result.pixel_calibration is not None:
        mat_payload["pixel_calibration"] = json.dumps(result.pixel_calibration)
    savemat(
        target / "stack.mat",
        mat_payload,
        do_compression=True, oned_as="row",
    )
    meta = {
        "params": asdict(result.params),
        "metadata": asdict(result.metadata or ScanMetadata()),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_s": result.finished_at - result.started_at,
        "n_frames": int(frames.shape[0]),
        "frame_shape": list(frames.shape[1:]),
        "frame_dtype": str(frames.dtype),
        "has_corrected": corrected is not None,
        "calibration": result.calibration,
        "pixel_calibration": result.pixel_calibration,
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return target


def find_orphan_scans(data_dir: Path) -> list[Path]:
    """启动恢复用 — 找出写入未正常收尾的扫描目录。

    判定标准: 目录里有 stack.h5, 没有 meta.json。返回路径列表 (空 = 无未收尾扫描).
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        return []
    orphans: list[Path] = []
    for child in data_dir.iterdir():
        if not child.is_dir():
            continue
        if (child / "stack.h5").exists() and not (child / "meta.json").exists():
            orphans.append(child)
    return sorted(orphans)


def save_scan(out_dir: Path, result: ScanResult, name: str | None = None) -> Path:
    """落到 ``out_dir/<name>/`` 下，包含:

    - ``stack.h5`` — 完整数据 + 元信息 (主存档, HDF5 gzip)
    - ``stack.tif`` — 多页 TIFF，方便 ImageJ 打开
    - ``stack.mat`` — MATLAB v7.3 兼容, 给 Matlab 用户用
    - ``positions.csv`` — 位置表
    - ``meta.json`` — 人类可读元信息
    """
    out_dir = Path(out_dir)
    if name is None:
        name = time.strftime("psf_%Y%m%d_%H%M%S", time.localtime(result.started_at))
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)

    frames = result.frames
    chunk_shape = (1,) + frames.shape[1:]

    with h5py.File(target / "stack.h5", "w") as f:
        f.create_dataset(
            "frames",
            data=frames,
            compression="gzip",
            compression_opts=4,
            chunks=chunk_shape,
        )
        f.create_dataset("positions", data=result.positions)
        f.create_dataset("timestamps", data=result.timestamps)
        if result.corrected_frames is not None:
            f.create_dataset(
                "frames_corrected",
                data=result.corrected_frames,
                compression="gzip",
                compression_opts=4,
                chunks=(1,) + result.corrected_frames.shape[1:],
            )
        f.attrs["params"] = json.dumps(asdict(result.params))
        f.attrs["metadata"] = json.dumps(asdict(result.metadata or ScanMetadata()))
        if result.calibration is not None:
            f.attrs["calibration"] = json.dumps(result.calibration)
        if result.pixel_calibration is not None:
            f.attrs["pixel_calibration"] = json.dumps(result.pixel_calibration)
        f.attrs["started_at"] = result.started_at
        f.attrs["finished_at"] = result.finished_at

    tifffile.imwrite(target / "stack.tif", frames, bigtiff=True)
    if result.corrected_frames is not None:
        tifffile.imwrite(target / "stack_corrected.tif", result.corrected_frames, bigtiff=True)

    np.savetxt(
        target / "positions.csv",
        result.positions,
        delimiter=",",
        header="x_um,y_um,z_um",
        comments="",
    )

    # MAT (Matlab) — Matlab 接收的 PSF 数据结构, 字段命名 snake_case 与 csv 一致
    mat_payload = {
        "frames": frames,
        "positions": result.positions,
        "timestamps": result.timestamps,
        "params": json.dumps(asdict(result.params)),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
    if result.corrected_frames is not None:
        mat_payload["frames_corrected"] = result.corrected_frames
    if result.pixel_calibration is not None:
        mat_payload["pixel_calibration"] = json.dumps(result.pixel_calibration)
    savemat(
        target / "stack.mat",
        mat_payload,
        do_compression=True,
        oned_as="row",
    )

    meta = {
        "params": asdict(result.params),
        "metadata": asdict(result.metadata or ScanMetadata()),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_s": result.finished_at - result.started_at,
        "n_frames": int(frames.shape[0]),
        "frame_shape": list(frames.shape[1:]),
        "frame_dtype": str(frames.dtype),
        "has_corrected": result.corrected_frames is not None,
        "calibration": result.calibration,
        "pixel_calibration": result.pixel_calibration,
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return target

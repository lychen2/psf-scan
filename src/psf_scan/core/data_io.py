"""扫描结果保存 — HDF5 + TIFF + CSV + meta.json。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import h5py
import numpy as np
import tifffile

from .scanner import ScanResult


def save_scan(out_dir: Path, result: ScanResult, name: str | None = None) -> Path:
    """落到 ``out_dir/<name>/`` 下，包含:

    - ``stack.h5`` — 完整数据 + 元信息 (主存档)
    - ``stack.tif`` — 多页 TIFF，方便 ImageJ 打开
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
        f.attrs["params"] = json.dumps(asdict(result.params))
        f.attrs["started_at"] = result.started_at
        f.attrs["finished_at"] = result.finished_at

    tifffile.imwrite(target / "stack.tif", frames, bigtiff=True)

    np.savetxt(
        target / "positions.csv",
        result.positions,
        delimiter=",",
        header="x_um,y_um,z_um",
        comments="",
    )

    meta = {
        "params": asdict(result.params),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_s": result.finished_at - result.started_at,
        "n_frames": int(frames.shape[0]),
        "frame_shape": list(frames.shape[1:]),
        "frame_dtype": str(frames.dtype),
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return target

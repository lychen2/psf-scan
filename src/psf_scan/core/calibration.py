"""Dark/flat calibration frames and correction logic."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .camera import CameraBase

CALIBRATION_VERSION = 1
DEFAULT_FRAME_COUNT = 50
FLAT_EPS = 1.0e-6
MAX_BAD_FLAT_RATIO = 0.001
MAX_SATURATED_FLAT_RATIO = 0.001
MIN_DISPLAY_WHITE_LEVEL = 1.0
SENSOR_SATURATION_FRACTION = 0.99


@dataclass(frozen=True)
class CalibrationFrame:
    kind: str
    data: np.ndarray
    metadata: dict[str, Any]
    sha256: str

    @property
    def path_metadata(self) -> dict[str, Any]:
        return {**self.metadata, "kind": self.kind, "sha256": self.sha256}


@dataclass(frozen=True)
class CalibrationConfig:
    dark_enabled: bool = False
    flat_enabled: bool = False
    dark_path: str = ""
    flat_path: str = ""
    flat_mode: str = "intensity"
    dark: CalibrationFrame | None = None
    flat: CalibrationFrame | None = None
    # 由 app 层在引擎握手后注入: 相机已通过 SDK 接管暗场补偿时,
    # 没有软件 dark 文件则零减法; 若用户加载 dark 文件, 视为残余暗场继续扣除.
    hardware_dark_active: bool = False
    hardware_dark_node: str | None = None

    @property
    def enabled(self) -> bool:
        return self.dark_enabled or self.flat_enabled

    def metadata(self) -> dict[str, Any]:
        return {
            "version": CALIBRATION_VERSION,
            "dark_enabled": self.dark_enabled,
            "flat_enabled": self.flat_enabled,
            "dark_path": self.dark_path,
            "flat_path": self.flat_path,
            "flat_mode": self.flat_mode,
            "dark": None if self.dark is None else self.dark.path_metadata,
            "flat": None if self.flat is None else self.flat.path_metadata,
            "hardware_dark_active": self.hardware_dark_active,
            "hardware_dark_node": self.hardware_dark_node,
        }


def camera_signature(camera: CameraBase) -> dict[str, Any]:
    return {
        "camera": camera.description,
        "exposure_us": int(camera.get_exposure_us()),
        "gain": float(camera.get_gain()),
        "pixel_format": camera.get_pixel_format() or "",
        "bit_depth": int(camera.bit_depth()),
    }


def capture_calibration_frame(
    camera: CameraBase,
    *,
    kind: str,
    frame_count: int = DEFAULT_FRAME_COUNT,
) -> CalibrationFrame:
    if frame_count < 1:
        raise ValueError("校正帧采集数量必须 >= 1")
    frames = [np.asarray(camera.grab_one(), dtype=np.float32) for _ in range(frame_count)]
    data = np.median(np.stack(frames, axis=0), axis=0).astype(np.float32, copy=False)
    metadata = {
        "version": CALIBRATION_VERSION,
        "created_at": float(time.time()),
        "frame_count": int(frame_count),
        "shape": list(data.shape),
        "dtype": str(data.dtype),
        **camera_signature(camera),
    }
    return CalibrationFrame(kind=kind, data=data, metadata=metadata, sha256=_sha256(data))


def save_calibration_frame(frame: CalibrationFrame, path: Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {**frame.metadata, "kind": frame.kind, "sha256": frame.sha256}
    np.savez_compressed(target, data=frame.data, metadata=json.dumps(metadata, ensure_ascii=False))
    return target


def load_calibration_frame(path: str | Path, *, expected_kind: str) -> CalibrationFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"校正文件不存在: {source}")
    with np.load(source, allow_pickle=False) as loaded:
        data = np.asarray(loaded["data"], dtype=np.float32)
        metadata = json.loads(str(loaded["metadata"].item()))
    kind = str(metadata.get("kind", ""))
    if kind != expected_kind:
        raise ValueError(f"校正文件类型不匹配: 需要 {expected_kind}, 实际 {kind or '未知'}")
    sha256 = _sha256(data)
    if sha256 != metadata.get("sha256"):
        raise ValueError(f"校正文件校验失败: {source}")
    return CalibrationFrame(kind=kind, data=data, metadata=metadata, sha256=sha256)


def config_from_settings(settings, camera: CameraBase) -> CalibrationConfig:
    raw = settings.calibration_config()
    dark = _load_optional_dark(raw["dark_enabled"], raw["dark_path"])
    flat = _load_enabled(raw["flat_enabled"], raw["flat_path"], "flat")
    return CalibrationConfig(**raw, dark=dark, flat=flat)


def validate_config(config: CalibrationConfig, camera: CameraBase) -> None:
    if config.flat_enabled and config.flat_mode != "intensity":
        raise ValueError("当前平场模式不是普通强度平场，拒绝做除法校正")
    if config.dark_enabled and not config.hardware_dark_active and config.dark is None:
        raise ValueError("已启用 dark, 但未选择校正文件")
    signature = camera_signature(camera)
    frames = [f for f in (config.dark, config.flat) if f is not None]
    for frame in frames:
        _validate_signature(frame, signature)
    if config.flat is not None:
        _validate_flat(config)


def apply_calibration(frame: np.ndarray, config: CalibrationConfig) -> np.ndarray:
    data = np.asarray(frame, dtype=np.float32)
    dark = _dark_array(config, data.shape)
    if config.flat_enabled:
        if config.flat is None:
            raise ValueError("已启用平场校正，但未加载平场文件")
        if tuple(config.flat.data.shape) != tuple(data.shape):
            raise ValueError("平场校正文件尺寸与当前帧不匹配")
        numerator = data - dark
        denominator = config.flat.data - dark
        corrected = numerator / np.maximum(denominator, FLAT_EPS)
        return corrected * float(np.mean(denominator))
    if config.dark_enabled:
        return data - dark
    return data


def calibrated_white_level(raw_white_level: int | float, config: CalibrationConfig | None) -> float:
    """Global display white after software residual dark subtraction."""
    white = float(raw_white_level)
    if config is None or not config.dark_enabled or config.dark is None:
        return white
    residual = float(np.nanmedian(config.dark.data))
    return max(MIN_DISPLAY_WHITE_LEVEL, white - residual)


def is_sensor_saturated(frame: np.ndarray, raw_white_level: int | float) -> bool:
    peak = float(np.nanmax(np.asarray(frame)))
    return peak >= float(raw_white_level) * SENSOR_SATURATION_FRACTION


def _load_enabled(enabled: bool, path: str, kind: str) -> CalibrationFrame | None:
    if not enabled:
        return None
    if not path:
        raise ValueError(f"已启用 {kind}, 但未选择校正文件")
    return load_calibration_frame(path, expected_kind=kind)


def _load_optional_dark(enabled: bool, path: str) -> CalibrationFrame | None:
    if not enabled or not path:
        return None
    return load_calibration_frame(path, expected_kind="dark")


def _validate_signature(frame: CalibrationFrame, signature: dict[str, Any]) -> None:
    for key in ("exposure_us", "gain", "pixel_format", "bit_depth"):
        if frame.metadata.get(key) != signature[key]:
            raise ValueError(f"{frame.kind} 校正文件与当前相机 {key} 不匹配")


def _validate_flat(config: CalibrationConfig) -> None:
    if config.flat is None:
        return
    denominator = _flat_denominator(config)
    bad_ratio = float(np.mean(denominator <= FLAT_EPS))
    if bad_ratio > MAX_BAD_FLAT_RATIO:
        raise ValueError(f"平场过暗或含无效像素过多: {bad_ratio:.3%}")
    max_value = _max_value(config.flat)
    saturated_ratio = float(np.mean(config.flat.data >= max_value))
    if saturated_ratio > MAX_SATURATED_FLAT_RATIO:
        raise ValueError(f"平场饱和像素过多: {saturated_ratio:.3%}")


def _dark_array(config: CalibrationConfig, shape: tuple[int, ...]) -> np.ndarray:
    if not config.dark_enabled:
        return np.zeros(shape, dtype=np.float32)
    if config.dark is None:
        if config.hardware_dark_active:
            return np.zeros(shape, dtype=np.float32)
        raise ValueError("已启用暗场校正，但未加载暗场文件")
    if tuple(config.dark.data.shape) != tuple(shape):
        raise ValueError("暗场校正文件尺寸与当前帧不匹配")
    return config.dark.data


def _flat_denominator(config: CalibrationConfig) -> np.ndarray:
    if config.flat is None:
        raise ValueError("已启用平场校正，但未加载平场文件")
    dark = _dark_array(config, config.flat.data.shape)
    return config.flat.data - dark


def _max_value(frame: CalibrationFrame) -> float:
    bit_depth = int(frame.metadata.get("bit_depth", 16) or 16)
    return float((1 << bit_depth) - 1)


def _sha256(data: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(data)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()

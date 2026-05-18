from __future__ import annotations

import numpy as np
import pytest

from psf_scan.core.calibration import (
    CalibrationConfig,
    apply_calibration,
    capture_calibration_frame,
    load_calibration_frame,
    save_calibration_frame,
    validate_config,
)


class DummyCamera:
    description = "dummy"

    def __init__(self, frames: list[np.ndarray], *, exposure_us: int = 1000) -> None:
        self._frames = list(frames)
        self._exposure_us = exposure_us

    def grab_one(self, timeout_ms: int = 1000) -> np.ndarray:
        if not self._frames:
            raise RuntimeError("no frames")
        return self._frames.pop(0)

    def get_exposure_us(self) -> int:
        return self._exposure_us

    def get_gain(self) -> float:
        return 1.0

    def get_pixel_format(self) -> str:
        return "Mono16"

    def bit_depth(self) -> int:
        return 16


def test_capture_save_load_roundtrip(tmp_path):
    frames = [
        np.array([[10, 20], [30, 40]], dtype=np.uint16),
        np.array([[12, 22], [32, 42]], dtype=np.uint16),
        np.array([[14, 24], [34, 44]], dtype=np.uint16),
    ]
    captured = capture_calibration_frame(DummyCamera(frames), kind="dark", frame_count=3)

    path = save_calibration_frame(captured, tmp_path / "dark.npz")
    loaded = load_calibration_frame(path, expected_kind="dark")

    np.testing.assert_array_equal(loaded.data, np.array([[12, 22], [32, 42]], dtype=np.float32))
    assert loaded.sha256 == captured.sha256


def test_apply_dark_flat_calibration():
    dark = _frame("dark", np.full((2, 2), 10, dtype=np.float32))
    flat = _frame("flat", np.full((2, 2), 110, dtype=np.float32))
    config = CalibrationConfig(
        dark_enabled=True,
        flat_enabled=True,
        flat_mode="intensity",
        dark=dark,
        flat=flat,
    )
    raw = np.full((2, 2), 60, dtype=np.uint16)

    corrected = apply_calibration(raw, config)

    np.testing.assert_allclose(corrected, np.full((2, 2), 50, dtype=np.float32))


def test_apply_skips_software_dark_when_hardware_active():
    """硬件接管后软件路径必须零减法 -- 即便 dark file 已加载."""
    dark = _frame("dark", np.full((2, 2), 10, dtype=np.float32))
    config = CalibrationConfig(
        dark_enabled=True,
        dark=dark,
        hardware_dark_active=True,
        hardware_dark_node="NUCEnable",
    )
    raw = np.full((2, 2), 60, dtype=np.float32)

    corrected = apply_calibration(raw, config)

    np.testing.assert_allclose(corrected, raw)


def test_apply_flat_without_software_dark_when_hardware_active():
    """硬件 dark + flat 时 denominator 不应再减 dark."""
    dark = _frame("dark", np.full((2, 2), 10, dtype=np.float32))
    flat = _frame("flat", np.full((2, 2), 100, dtype=np.float32))
    config = CalibrationConfig(
        dark_enabled=True,
        flat_enabled=True,
        flat_mode="intensity",
        dark=dark,
        flat=flat,
        hardware_dark_active=True,
        hardware_dark_node="NUCEnable",
    )
    raw = np.full((2, 2), 50, dtype=np.float32)

    corrected = apply_calibration(raw, config)

    # data / flat * mean(flat) = 50 / 100 * 100 = 50
    np.testing.assert_allclose(corrected, np.full((2, 2), 50, dtype=np.float32))


def test_validate_rejects_camera_mismatch():
    dark = _frame("dark", np.ones((2, 2), dtype=np.float32), exposure_us=2000)
    config = CalibrationConfig(dark_enabled=True, dark=dark)

    with pytest.raises(ValueError, match="exposure_us"):
        validate_config(config, DummyCamera([]))


def _frame(kind: str, data: np.ndarray, *, exposure_us: int = 1000):
    from psf_scan.core.calibration import CalibrationFrame

    metadata = {
        "version": 1,
        "created_at": 0.0,
        "frame_count": 1,
        "shape": list(data.shape),
        "dtype": str(data.dtype),
        "camera": "dummy",
        "exposure_us": exposure_us,
        "gain": 1.0,
        "pixel_format": "Mono16",
        "bit_depth": 16,
    }
    return CalibrationFrame(kind=kind, data=data, metadata=metadata, sha256=_sha(data))


def _sha(data: np.ndarray) -> str:
    import hashlib

    contiguous = np.ascontiguousarray(data)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()

from __future__ import annotations

import json

import h5py
import numpy as np
import pytest

from psf_scan.core.data_io import save_scan
from psf_scan.core.pixel_calibration import (
    METHOD_LINE,
    METHOD_SENSOR_OBJECTIVE,
    from_line,
    from_sensor_objective,
    from_settings,
)
from psf_scan.core.scanner import ScanParams, ScanResult


def test_sensor_objective_scale():
    calibration = from_sensor_objective(
        pixel_size_um=3.45,
        objective_magnification=100.0,
        created_at=1.0,
    )

    assert calibration.method == METHOD_SENSOR_OBJECTIVE
    assert calibration.microns_per_pixel == pytest.approx(0.0345)


def test_line_scale():
    calibration = from_line(line_length_px=250.0, line_length_um=50.0, created_at=2.0)

    assert calibration.method == METHOD_LINE
    assert calibration.microns_per_pixel == pytest.approx(0.2)


def test_from_settings_disabled():
    assert from_settings({"enabled": False}) is None


def test_save_scan_writes_pixel_calibration(tmp_path):
    pixel_calibration = from_line(
        line_length_px=100.0,
        line_length_um=25.0,
        created_at=3.0,
    ).metadata()
    result = ScanResult(
        params=ScanParams(),
        positions=np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
        frames=np.zeros((1, 2, 2), dtype=np.float32),
        timestamps=np.array([0.0], dtype=np.float64),
        started_at=10.0,
        finished_at=11.0,
        pixel_calibration=pixel_calibration,
    )

    target = save_scan(tmp_path, result, name="scan")

    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    assert meta["pixel_calibration"]["microns_per_pixel"] == pytest.approx(0.25)
    with h5py.File(target / "stack.h5", "r") as handle:
        stored = json.loads(handle.attrs["pixel_calibration"])
    assert stored["method"] == METHOD_LINE

from __future__ import annotations

import numpy as np

from psf_scan.drivers.camera_mock import MockCamera
from psf_scan.ui.camera_view import CameraView


def test_camera_view_auto_display_levels_are_throttled(qtbot, monkeypatch):
    view = CameraView()
    qtbot.addWidget(view)
    calls: list[tuple[float, float]] = []

    def fake_percentile(_frame, quantiles):
        calls.append(tuple(quantiles))
        return np.array([1.0, 10.0])

    monkeypatch.setattr("psf_scan.ui.camera_view.np.percentile", fake_percentile)
    frame = np.arange(100, dtype=np.uint8).reshape(10, 10)

    view._on_auto_levels_toggled(True)
    assert view._auto_display_levels(frame) == (1.0, 10.0)
    assert view._auto_display_levels(frame) == (1.0, 10.0)

    assert calls == [(0.1, 99.9)]


def test_mock_hardware_dark_removes_dark_background():
    camera = MockCamera(width=64, height=48, peak_counts=0.0, dark_counts=20.0)
    before = float(camera.grab_one().mean())

    assert camera.trigger_hardware_dark_calibration() == "mock_dark"
    assert camera.hardware_dark_active
    after = float(camera.grab_one().mean())

    assert camera.hardware_dark_node == "mock_dark"
    assert after < before * 0.5


def test_mock_disable_hardware_dark_restores_background():
    camera = MockCamera(width=64, height=48, peak_counts=0.0, dark_counts=20.0)
    camera.try_enable_hardware_dark()
    enabled = float(camera.grab_one().mean())

    camera.disable_hardware_dark()
    disabled = float(camera.grab_one().mean())

    assert not camera.hardware_dark_active
    assert disabled > enabled

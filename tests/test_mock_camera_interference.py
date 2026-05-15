from __future__ import annotations

import numpy as np

from psf_scan.core.camera import make_camera
from psf_scan.core.phase import PhaseReconstructionParams, reconstruct_off_axis_phase
from psf_scan.drivers.camera_mock import (
    MOCK_MODE_INTERFERENCE,
    MOCK_MODE_PSF,
    MOCK_MODE_REFERENCE,
    MOCK_MODE_SAMPLE,
    MockCamera,
)
from psf_scan.drivers.mock_interference import PHASE_SHIFT_MODES, sample_phase_span


def test_mock_camera_can_switch_to_interference_modes():
    camera = MockCamera(width=128, height=96)

    assert MOCK_MODE_INTERFERENCE in camera.pixel_formats()
    assert camera.get_pixel_format() == MOCK_MODE_PSF

    camera.set_pixel_format(MOCK_MODE_INTERFERENCE)
    sample = camera.grab_one()
    camera.set_pixel_format(MOCK_MODE_REFERENCE)
    reference = camera.grab_one()

    assert sample.shape == (96, 128)
    assert reference.shape == (96, 128)
    assert sample.std() > 5.0
    assert reference.std() > 5.0
    assert not np.array_equal(sample, reference)


def test_mock_sample_and_interference_sample_are_paired_modes():
    camera = MockCamera(width=128, height=96)

    assert MOCK_MODE_SAMPLE in camera.pixel_formats()

    camera.set_pixel_format(MOCK_MODE_SAMPLE)
    sample = camera.grab_one()
    camera.set_pixel_format(MOCK_MODE_INTERFERENCE)
    interference = camera.grab_one()

    assert sample.shape == interference.shape
    assert sample.mean() > 0.0
    assert interference.std() > 5.0
    assert not np.array_equal(sample, interference)


def test_mock_interference_driver_defaults_to_sample_mode():
    camera = make_camera("mock-interference", width=128, height=96)

    assert camera.get_pixel_format() == MOCK_MODE_INTERFERENCE
    assert "Interference" in camera.description


def test_mock_interference_frame_reconstructs_phase():
    camera = MockCamera(width=128, height=96, mode=MOCK_MODE_INTERFERENCE)
    frame = camera.grab_one()

    result = reconstruct_off_axis_phase(frame, PhaseReconstructionParams(source="mock"))

    assert result.wrapped_phase.shape == frame.shape
    assert result.fft_magnitude.shape == frame.shape


def test_mock_camera_provides_phase_shift_interferograms():
    camera = MockCamera(width=128, height=96)
    frames = []

    for mode in PHASE_SHIFT_MODES:
        camera.set_pixel_format(mode)
        frames.append(camera.grab_one().astype(np.float32))

    assert all(frame.shape == (96, 128) for frame in frames)
    assert max(float(frame.mean()) for frame in frames) > min(float(frame.mean()) for frame in frames)
    assert not np.array_equal(frames[0], frames[1])


def test_mock_sample_phase_has_metalens_scale_variation():
    assert sample_phase_span(128, 96) > 20.0

from __future__ import annotations

import json

import numpy as np

from psf_scan.core.phase import (
    PhaseReconstructionParams,
    PhaseSavePayload,
    Sideband,
    reconstruct_off_axis_phase,
    save_phase_payload,
    wrapped_phase_difference,
)


def test_reconstruct_off_axis_phase_from_synthetic_fringe():
    image, phase = _fringe_with_phase()
    result = reconstruct_off_axis_phase(image, _params())

    error = _phase_error(result.wrapped_phase, phase)

    assert error < 0.08
    assert result.sideband.x == 80.0


def test_reference_correction_removes_system_phase():
    system = _phase_ramp(64, 128, scale=0.35)
    sample_phase = 0.4 * _phase_ramp(64, 128, scale=1.0)
    sample = _fringe(system + sample_phase)
    reference = _fringe(system)

    sample_result = reconstruct_off_axis_phase(sample, _params())
    reference_result = reconstruct_off_axis_phase(reference, _params())
    corrected = wrapped_phase_difference(
        sample_result.wrapped_phase,
        reference_result.wrapped_phase,
    )

    assert _phase_error(corrected, sample_phase) < 0.08


def test_reference_smoothing_suppresses_noisy_reference():
    rng = np.random.default_rng(0)
    h, w = 128, 128
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    system = 0.8 * (yy / h + 0.7 * xx / w)
    feature = 0.5 * np.exp(-(((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / 10.0 ** 2))
    sample_phase = (system + feature).astype(np.float32)
    noisy_ref_phase = (system + 0.45 * rng.standard_normal((h, w))).astype(np.float32)

    raw = wrapped_phase_difference(sample_phase, noisy_ref_phase)
    smoothed = wrapped_phase_difference(
        sample_phase, noisy_ref_phase, reference_smoothing_sigma_px=3.0,
    )
    bg = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) > 30.0 ** 2
    assert smoothed[bg].std() < 0.4 * raw[bg].std()


def test_save_phase_payload_writes_arrays_and_meta(tmp_path):
    image, _phase = _fringe_with_phase()
    result = reconstruct_off_axis_phase(image, _params())

    target = save_phase_payload(tmp_path, PhaseSavePayload(result))

    assert (target / "phase_wrapped.npy").exists()
    assert (target / "phase_preview.png").exists()
    assert (target / "fft_preview.png").exists()
    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    assert meta["sideband"]["radius"] == 14.0


def _params() -> PhaseReconstructionParams:
    return PhaseReconstructionParams(
        sideband=Sideband(x=80.0, y=32.0, radius=14.0),
        auto_sideband=False,
        source="synthetic",
    )


def _fringe_with_phase() -> tuple[np.ndarray, np.ndarray]:
    phase = 0.35 * _phase_ramp(64, 128, scale=1.0)
    return _fringe(phase), phase


def _fringe(phase: np.ndarray) -> np.ndarray:
    h, w = phase.shape
    x = np.arange(w, dtype=np.float32)[None, :]
    carrier = 2.0 * np.pi * 16.0 * x / float(w)
    return (1.0 + np.cos(carrier + phase)).astype(np.float32)


def _phase_ramp(h: int, w: int, *, scale: float) -> np.ndarray:
    y, x = np.mgrid[:h, :w].astype(np.float32)
    return scale * (0.7 * x / float(w) + 0.3 * y / float(h)).astype(np.float32)


def _phase_error(actual: np.ndarray, expected: np.ndarray) -> float:
    delta = np.exp(1j * (actual - expected))
    offset = np.angle(np.mean(delta))
    return float(np.mean(np.abs(np.angle(delta * np.exp(-1j * offset)))))

from __future__ import annotations

import numpy as np

from psf_scan.core.autofocus import (
    _average_frames,
    _is_low_light,
    _is_saturated,
    _refine_targets,
)


def test_refine_targets_use_local_parabolic_peak() -> None:
    z_values = np.asarray([-5.0, 0.0, 5.0])
    scores = -(z_values - 1.0) ** 2 + 36.0

    targets = _refine_targets(z_values, scores)

    assert targets.size == 3
    assert np.isclose(targets[1], 1.0)
    assert np.all(targets >= -5.0)
    assert np.all(targets <= 5.0)


def test_refine_targets_respect_stage_min_step() -> None:
    z_values = np.asarray([-5.0, 0.0, 5.0])
    scores = -(z_values - 1.0) ** 2 + 36.0

    targets = _refine_targets(z_values, scores, min_step_um=2.0)

    assert np.isclose(targets[1] - targets[0], 2.0)
    assert np.isclose(targets[2] - targets[1], 2.0)


def test_average_frames_reduces_alternating_noise() -> None:
    low = np.zeros((4, 4), dtype=np.float32)
    high = np.full((4, 4), 10.0, dtype=np.float32)

    averaged = _average_frames([low, high])

    assert averaged.dtype == np.float32
    assert np.allclose(averaged, 5.0)


def test_low_light_uses_mean_and_high_percentile() -> None:
    assert _is_low_light([(0.01, 0.05, 0.05)])
    assert not _is_low_light([(0.01, 0.20, 0.20)])
    assert not _is_low_light([(0.01, 0.05, 1.0)])


def test_low_light_skipped_when_peak_signal_is_strong() -> None:
    # 稀疏 PSF: 背景几乎全黑,但单点信号足够亮 → 不应触发亮度不足
    assert not _is_low_light([(0.005, 0.01, 0.50)])
    assert not _is_low_light([(0.005, 0.01, 0.25)])
    # 三个指标全部贴近 0 才算真亮度不足
    assert _is_low_light([(0.005, 0.01, 0.10)])


def test_saturated_uses_peak_even_when_mean_is_low() -> None:
    assert _is_saturated([(0.01, 0.05, 1.0)])
    assert not _is_saturated([(0.50, 0.80, 0.98)])

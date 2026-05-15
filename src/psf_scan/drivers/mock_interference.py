"""Synthetic interferograms for mock camera phase workflows."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ._psf_optics import ZERNIKE

MODE_SAMPLE = "Sample"
MODE_REFERENCE = "Reference"
MODE_OFFAXIS_SAMPLE = "Interference sample"
MODE_OFFAXIS_REFERENCE = "Interference reference"
MODE_SHIFT_0 = "Phase shift 0"
MODE_SHIFT_90 = "Phase shift 90"
MODE_SHIFT_180 = "Phase shift 180"
MODE_SHIFT_270 = "Phase shift 270"
PHASE_SHIFT_MODES = (MODE_SHIFT_0, MODE_SHIFT_90, MODE_SHIFT_180, MODE_SHIFT_270)
INTERFERENCE_MODES = (
    MODE_OFFAXIS_SAMPLE,
    MODE_OFFAXIS_REFERENCE,
    *PHASE_SHIFT_MODES,
)
SAMPLE_ARM_MODES = (MODE_SAMPLE, MODE_REFERENCE)
PHASE_CAMERA_MODES = (
    *SAMPLE_ARM_MODES,
    *INTERFERENCE_MODES,
)

CARRIER_CYCLES = 32.0
DARK_NOISE = 2.0
REFERENCE_AMPLITUDE = 0.82
OBJECT_AMPLITUDE = 0.64
OUTPUT_PEAK_FRACTION = 0.74
EXPOSURE_REFERENCE_US = 10_000.0
APERTURE_RADIUS_NORM = 0.82
SAMPLE_RADIUS_UM = 80.0
SAMPLE_NA = 0.065
WAVELENGTH_UM = 0.55
SYSTEM_TILT_X_RAD = 0.7
SYSTEM_TILT_Y_RAD = 0.45
SYSTEM_ASTIG_X_RAD = 0.9
SYSTEM_ASTIG_Y_SCALE = 0.35
STAGE_SHIFT_SCALE_UM = 20.0
STAGE_SHIFT_NORM = 0.10
STAGE_DEFOCUS_SCALE_UM = 20.0
SAMPLE_RIPPLE_RAD = 0.35
SAMPLE_RIPPLE_X = 5.0
SAMPLE_RIPPLE_Y = 2.0
OBJECT_VIGNETTE = 0.14
REFERENCE_VIGNETTE = 0.18
FIXED_PATTERN_X = 0.035
FIXED_PATTERN_Y = 0.027
FIXED_PATTERN_SIN = 0.025
FIXED_PATTERN_COS = 0.018
OBJECT_MIN_ENVELOPE = 0.02
REFERENCE_MIN_ENVELOPE = 0.25
MAX_ENVELOPE = 1.0
HALF_SCALE = 0.5
MIN_HALF_AXIS = 1.0
APERTURE_EDGE_FRACTION = 0.08
BACKGROUND_FRACTION = 0.015
EPSILON = 1e-12
SAMPLE_ZERNIKE_RMS = {
    "astig0": 0.10,
    "coma_x": 0.06,
    "spherical": 0.08,
}
PHASE_SHIFT_RADIANS = {
    MODE_SHIFT_0: 0.0,
    MODE_SHIFT_90: 0.5 * np.pi,
    MODE_SHIFT_180: np.pi,
    MODE_SHIFT_270: 1.5 * np.pi,
}


@dataclass(frozen=True)
class InterferenceGrid:
    xx: np.ndarray
    yy: np.ndarray
    width: int
    height: int


def render_interferogram(
    *,
    mode: str,
    width: int,
    height: int,
    max_val: int,
    exposure_us: int,
    gain: float,
    black_level: int,
    gamma: float,
    rng: np.random.Generator,
    position: tuple[float, float, float],
    dtype,
) -> np.ndarray:
    grid = _make_grid(width, height)
    intensity = _render_intensity(mode, grid, position)
    signal = _scale_signal(intensity, max_val, exposure_us, gain)
    noisy = rng.normal(signal + black_level, DARK_NOISE).astype(np.float32)
    if gamma != 1.0:
        noisy = np.power(np.clip(noisy / max_val, 0.0, 1.0), 1.0 / gamma) * max_val
    return np.clip(noisy, 0, max_val).astype(dtype)


def _render_intensity(
    mode: str,
    grid: InterferenceGrid,
    position: tuple[float, float, float],
) -> np.ndarray:
    with_sample = mode not in {MODE_REFERENCE, MODE_OFFAXIS_REFERENCE}
    object_field = _object_field(grid, position, with_sample)
    if mode in SAMPLE_ARM_MODES:
        return np.abs(object_field) ** 2
    reference_field = _reference_field(mode, grid)
    return np.abs(object_field + reference_field) ** 2


def sample_phase_span(width: int, height: int) -> float:
    """Return the unwrapped mock sample phase span in radians."""
    phase = sample_phase_image(width=width, height=height)
    return float(np.nanmax(phase) - np.nanmin(phase))


def sample_phase_image(
    *,
    width: int,
    height: int,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Return the mock sample phase used by Interference sample."""
    return _sample_phase(_make_grid(width, height), position).astype(np.float32)


def _object_field(
    grid: InterferenceGrid,
    position: tuple[float, float, float],
    with_sample: bool,
) -> np.ndarray:
    amplitude = OBJECT_AMPLITUDE * np.sqrt(_object_envelope(grid))
    phase = _system_phase(grid)
    if with_sample:
        phase = phase + _sample_phase(grid, position)
    return amplitude * np.exp(1j * phase)


def _reference_field(mode: str, grid: InterferenceGrid) -> np.ndarray:
    phase = _reference_phase(mode, grid)
    amplitude = REFERENCE_AMPLITUDE * np.sqrt(_reference_envelope(grid))
    return amplitude * np.exp(1j * phase)


def _reference_phase(mode: str, grid: InterferenceGrid) -> np.ndarray | float:
    phase_shift = PHASE_SHIFT_RADIANS.get(mode)
    if phase_shift is None:
        return 2.0 * np.pi * CARRIER_CYCLES * grid.xx / float(grid.width)
    return phase_shift


def _scale_signal(
    intensity: np.ndarray,
    max_val: int,
    exposure_us: int,
    gain: float,
) -> np.ndarray:
    normalized = intensity / max(float(np.nanmax(intensity)), EPSILON)
    signal = max_val * np.clip(normalized, 0.0, 1.0) * OUTPUT_PEAK_FRACTION
    background = max_val * BACKGROUND_FRACTION
    exposure_scale = float(exposure_us) / EXPOSURE_REFERENCE_US
    return (signal + background) * exposure_scale * max(gain, 0.0)


def _system_phase(grid: InterferenceGrid) -> np.ndarray:
    xn, yn = _normalized_coords(grid)
    astig = xn * xn - SYSTEM_ASTIG_Y_SCALE * yn * yn
    return SYSTEM_TILT_X_RAD * xn + SYSTEM_TILT_Y_RAD * yn + SYSTEM_ASTIG_X_RAD * astig


def _sample_phase(
    grid: InterferenceGrid,
    position: tuple[float, float, float],
) -> np.ndarray:
    xn, yn = _sample_coords(grid, position)
    rho = np.sqrt(xn * xn + yn * yn)
    pupil_rho = np.clip(rho / APERTURE_RADIUS_NORM, 0.0, 1.0)
    theta = np.arctan2(yn, xn)
    phase = _metalens_phase(pupil_rho, position[2])
    phase = phase + _zernike_phase(pupil_rho, theta)
    return phase + SAMPLE_RIPPLE_RAD * np.sin(SAMPLE_RIPPLE_X * xn + SAMPLE_RIPPLE_Y * yn)


def _object_envelope(grid: InterferenceGrid) -> np.ndarray:
    xn, yn = _normalized_coords(grid)
    aperture = _soft_aperture(xn, yn)
    vignette = 1.0 - OBJECT_VIGNETTE * (xn * xn + yn * yn)
    return np.clip(aperture * vignette * _fixed_pattern(grid), OBJECT_MIN_ENVELOPE, MAX_ENVELOPE)


def _reference_envelope(grid: InterferenceGrid) -> np.ndarray:
    xn, yn = _normalized_coords(grid)
    vignette = 1.0 - REFERENCE_VIGNETTE * (xn * xn + yn * yn)
    return np.clip(vignette * _fixed_pattern(grid), REFERENCE_MIN_ENVELOPE, MAX_ENVELOPE)


def _sample_coords(
    grid: InterferenceGrid,
    position: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    x, y, _z = position
    xn, yn = _normalized_coords(grid)
    cx = STAGE_SHIFT_NORM * np.tanh(float(x) / STAGE_SHIFT_SCALE_UM)
    cy = STAGE_SHIFT_NORM * np.tanh(float(y) / STAGE_SHIFT_SCALE_UM)
    return xn - cx, yn - cy


def _metalens_phase(pupil_rho: np.ndarray, z_um: float) -> np.ndarray:
    rho_um = pupil_rho * SAMPLE_RADIUS_UM
    focus_um = SAMPLE_RADIUS_UM * np.sqrt(1.0 - SAMPLE_NA * SAMPLE_NA) / SAMPLE_NA
    base = -2.0 * np.pi * (np.sqrt(rho_um * rho_um + focus_um * focus_um) - focus_um)
    defocus = np.pi * float(z_um) * SAMPLE_NA * SAMPLE_NA * pupil_rho * pupil_rho
    focus_scale = 1.0 + np.tanh(float(z_um) / STAGE_DEFOCUS_SCALE_UM) * SAMPLE_NA
    return base * focus_scale / WAVELENGTH_UM + defocus / WAVELENGTH_UM


def _zernike_phase(rho: np.ndarray, theta: np.ndarray) -> np.ndarray:
    phase = np.zeros_like(rho, dtype=np.float32)
    for name, c_rms in SAMPLE_ZERNIKE_RMS.items():
        phase = phase + 2.0 * np.pi * float(c_rms) * ZERNIKE[name](rho, theta)
    return phase.astype(np.float32)


def _soft_aperture(xn: np.ndarray, yn: np.ndarray) -> np.ndarray:
    rho = np.sqrt(xn * xn + yn * yn)
    transition_width = APERTURE_RADIUS_NORM * APERTURE_EDGE_FRACTION
    transition = np.clip((APERTURE_RADIUS_NORM - rho) / transition_width, 0.0, 1.0)
    return OBJECT_MIN_ENVELOPE + (MAX_ENVELOPE - OBJECT_MIN_ENVELOPE) * transition


def _fixed_pattern(grid: InterferenceGrid) -> np.ndarray:
    sin_term = FIXED_PATTERN_SIN * np.sin(FIXED_PATTERN_X * grid.xx)
    cos_term = FIXED_PATTERN_COS * np.cos(FIXED_PATTERN_Y * grid.yy)
    return 1.0 + sin_term + cos_term


def _make_grid(width: int, height: int) -> InterferenceGrid:
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    return InterferenceGrid(xx=xx, yy=yy, width=width, height=height)


def _normalized_coords(grid: InterferenceGrid) -> tuple[np.ndarray, np.ndarray]:
    return (
        (grid.xx - grid.width * HALF_SCALE) / max(MIN_HALF_AXIS, grid.width * HALF_SCALE),
        (grid.yy - grid.height * HALF_SCALE) / max(MIN_HALF_AXIS, grid.height * HALF_SCALE),
    )

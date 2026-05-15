"""Off-axis interferogram phase reconstruction."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

PHASE_ALGORITHM_VERSION = 1
MIN_FILTER_RADIUS_PX = 2.0
DEFAULT_FILTER_RADIUS_PX = 32.0
DC_EXCLUSION_FRACTION = 0.08
EPS = 1e-12


@dataclass(frozen=True)
class Sideband:
    x: float
    y: float
    radius: float = DEFAULT_FILTER_RADIUS_PX


@dataclass(frozen=True)
class PhaseReconstructionParams:
    sideband: Sideband | None = None
    auto_sideband: bool = True
    unwrap_phase: bool = False
    source: str = ""


@dataclass(frozen=True)
class PhaseResult:
    wrapped_phase: np.ndarray
    unwrapped_phase: np.ndarray | None
    complex_field: np.ndarray
    fft_magnitude: np.ndarray
    sideband: Sideband
    source: str

    def metadata(self) -> dict[str, object]:
        return {
            "algorithm": "off_axis_fft",
            "version": PHASE_ALGORITHM_VERSION,
            "source": self.source,
            "shape": list(self.wrapped_phase.shape),
            "sideband": asdict(self.sideband),
            "has_unwrapped": self.unwrapped_phase is not None,
        }


@dataclass(frozen=True)
class PhaseSavePayload:
    result: PhaseResult
    corrected_phase: np.ndarray | None = None
    reference: PhaseResult | None = None


def reconstruct_off_axis_phase(
    image: np.ndarray,
    params: PhaseReconstructionParams,
) -> PhaseResult:
    gray = _to_gray(image)
    fft_shift = np.fft.fftshift(np.fft.fft2(gray))
    magnitude = np.log1p(np.abs(fft_shift)).astype(np.float32)
    sideband = params.sideband if params.sideband is not None else _auto_sideband(magnitude)
    _validate_sideband(sideband, gray.shape)
    centered = _center_sideband(fft_shift, sideband)
    field = np.fft.ifft2(np.fft.ifftshift(centered))
    wrapped = np.angle(field).astype(np.float32)
    unwrapped = unwrap_phase(wrapped) if params.unwrap_phase else None
    return PhaseResult(
        wrapped_phase=wrapped,
        unwrapped_phase=unwrapped,
        complex_field=field.astype(np.complex64, copy=False),
        fft_magnitude=magnitude,
        sideband=sideband,
        source=params.source,
    )


def wrapped_phase_difference(sample: np.ndarray, reference: np.ndarray) -> np.ndarray:
    if sample.shape != reference.shape:
        raise ValueError(f"参考图尺寸不匹配: {reference.shape} != {sample.shape}")
    delta = np.exp(1j * sample) / np.exp(1j * reference)
    return np.angle(delta).astype(np.float32)


def unwrap_phase(wrapped: np.ndarray) -> np.ndarray:
    return np.unwrap(np.unwrap(wrapped, axis=0), axis=1).astype(np.float32)


def load_phase_image(path: Path | str) -> np.ndarray:
    target = Path(path)
    if target.suffix.lower() in {".tif", ".tiff"}:
        return _to_gray(tifffile.imread(target))
    image = Image.open(target)
    return np.asarray(image.convert("F"), dtype=np.float32)


def save_phase_payload(base_dir: Path | str, payload: PhaseSavePayload) -> Path:
    target = Path(base_dir) / time.strftime("phase_%Y%m%d_%H%M%S", time.localtime())
    target.mkdir(parents=True, exist_ok=False)
    _write_arrays(target, payload)
    _write_previews(target, payload)
    _write_meta(target, payload)
    return target


def _to_gray(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 3:
        array = array[..., :3].mean(axis=2)
    if array.ndim != 2:
        raise ValueError(f"相位处理只支持 2D 图像, 当前 shape={array.shape}")
    return array.astype(np.float32, copy=False)


def _auto_sideband(magnitude: np.ndarray) -> Sideband:
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    masked = np.array(magnitude, copy=True)
    radius = max(4, int(min(h, w) * DC_EXCLUSION_FRACTION))
    yy, xx = np.ogrid[:h, :w]
    masked[(xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2] = -np.inf
    y, x = np.unravel_index(int(np.nanargmax(masked)), masked.shape)
    filt = max(MIN_FILTER_RADIUS_PX, min(float(np.hypot(x - cx, y - cy)) * 0.35, 80.0))
    return Sideband(x=float(x), y=float(y), radius=filt)


def _validate_sideband(sideband: Sideband, shape: tuple[int, int]) -> None:
    h, w = shape
    if not (0.0 <= sideband.x < w and 0.0 <= sideband.y < h):
        raise ValueError(f"旁瓣中心超出 FFT 图范围: ({sideband.x:.1f}, {sideband.y:.1f})")
    if sideband.radius < MIN_FILTER_RADIUS_PX:
        raise ValueError(f"滤波半径必须 >= {MIN_FILTER_RADIUS_PX:.1f} px")


def _center_sideband(fft_shift: np.ndarray, sideband: Sideband) -> np.ndarray:
    h, w = fft_shift.shape
    cy, cx = h // 2, w // 2
    yc, xc = int(round(sideband.y)), int(round(sideband.x))
    mask = _gaussian_mask((h, w), xc, yc, float(sideband.radius))
    selected = fft_shift * mask
    return np.roll(selected, shift=(cy - yc, cx - xc), axis=(0, 1))


def _gaussian_mask(shape: tuple[int, int], x: int, y: int, radius: float) -> np.ndarray:
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    sigma = max(radius / 2.0, EPS)
    dist2 = (xx - x) ** 2 + (yy - y) ** 2
    mask = np.exp(-0.5 * dist2 / (sigma * sigma))
    mask[dist2 > radius * radius] = 0.0
    return mask.astype(np.float32)


def _write_arrays(target: Path, payload: PhaseSavePayload) -> None:
    np.save(target / "phase_wrapped.npy", payload.result.wrapped_phase)
    if payload.result.unwrapped_phase is not None:
        np.save(target / "phase_unwrapped.npy", payload.result.unwrapped_phase)
    if payload.corrected_phase is not None:
        np.save(target / "phase_corrected.npy", payload.corrected_phase)


def _write_previews(target: Path, payload: PhaseSavePayload) -> None:
    _save_grayscale_png(target / "fft_preview.png", payload.result.fft_magnitude)
    phase = payload.corrected_phase if payload.corrected_phase is not None else payload.result.wrapped_phase
    _save_phase_png(target / "phase_preview.png", phase)


def _write_meta(target: Path, payload: PhaseSavePayload) -> None:
    meta = payload.result.metadata()
    meta["saved_at"] = time.time()
    meta["reference_correction"] = payload.reference is not None
    if payload.reference is not None:
        meta["reference"] = payload.reference.metadata()
    (target / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_phase_png(path: Path, phase: np.ndarray) -> None:
    normalized = np.clip((phase + np.pi) / (2.0 * np.pi), 0.0, 1.0)
    Image.fromarray((normalized * 255).astype(np.uint8)).save(path)


def _save_grayscale_png(path: Path, image: np.ndarray) -> None:
    arr = np.asarray(image, dtype=np.float32)
    span = max(float(np.nanmax(arr) - np.nanmin(arr)), EPS)
    normalized = np.clip((arr - float(np.nanmin(arr))) / span, 0.0, 1.0)
    Image.fromarray((normalized * 255).astype(np.uint8)).save(path)

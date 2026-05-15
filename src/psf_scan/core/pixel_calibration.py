"""Camera pixel-to-length calibration metadata."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass


METHOD_SENSOR_OBJECTIVE = "sensor_objective"
METHOD_LINE = "line"
MICRONS_PER_MM = 1000.0
MIN_POSITIVE_VALUE = 1e-12


@dataclass(frozen=True)
class PixelCalibration:
    """Physical size represented by one camera image pixel."""

    method: str
    microns_per_pixel: float
    created_at: float
    pixel_size_um: float | None = None
    objective_magnification: float | None = None
    line_length_px: float | None = None
    line_length_um: float | None = None

    def metadata(self) -> dict[str, object]:
        data = asdict(self)
        data["version"] = 1
        return data


def from_sensor_objective(
    *,
    pixel_size_um: float,
    objective_magnification: float,
    created_at: float | None = None,
) -> PixelCalibration:
    _require_positive(pixel_size_um, "pixel_size_um")
    _require_positive(objective_magnification, "objective_magnification")
    return PixelCalibration(
        method=METHOD_SENSOR_OBJECTIVE,
        microns_per_pixel=float(pixel_size_um) / float(objective_magnification),
        pixel_size_um=float(pixel_size_um),
        objective_magnification=float(objective_magnification),
        created_at=_timestamp(created_at),
    )


def from_line(
    *,
    line_length_px: float,
    line_length_um: float,
    created_at: float | None = None,
) -> PixelCalibration:
    _require_positive(line_length_px, "line_length_px")
    _require_positive(line_length_um, "line_length_um")
    return PixelCalibration(
        method=METHOD_LINE,
        microns_per_pixel=float(line_length_um) / float(line_length_px),
        line_length_px=float(line_length_px),
        line_length_um=float(line_length_um),
        created_at=_timestamp(created_at),
    )


def from_settings(config: dict[str, object]) -> PixelCalibration | None:
    if not _bool(config.get("enabled", False)):
        return None
    method = str(config.get("method", METHOD_SENSOR_OBJECTIVE))
    if method == METHOD_SENSOR_OBJECTIVE:
        return from_sensor_objective(
            pixel_size_um=float(config["pixel_size_um"]),
            objective_magnification=float(config["objective_magnification"]),
            created_at=_optional_float(config.get("created_at")),
        )
    if method == METHOD_LINE:
        return from_line(
            line_length_px=float(config["line_length_px"]),
            line_length_um=float(config["line_length_um"]),
            created_at=_optional_float(config.get("created_at")),
        )
    raise ValueError(f"未知像素标定方式: {method}")


def _require_positive(value: float, name: str) -> None:
    if float(value) <= MIN_POSITIVE_VALUE:
        raise ValueError(f"{name} 必须为正数")


def _timestamp(value: float | None) -> float:
    return float(time.time() if value is None else value)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)

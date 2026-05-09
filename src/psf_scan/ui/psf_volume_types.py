"""Shared data containers for PSF volume rendering."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PreparedVolume:
    data: np.ndarray
    source_shape: tuple[int, ...]
    scale_y: float = 1.0
    scale_x: float = 1.0


@dataclass(frozen=True)
class SurfaceLayer:
    vertices: np.ndarray
    faces: np.ndarray
    color: tuple[float, float, float, float]


@dataclass(frozen=True)
class SliceLayer:
    orientation: str
    origin: tuple[float, float, float]
    scale_u: float
    scale_v: float
    colors: np.ndarray


@dataclass(frozen=True)
class VoxelLayer:
    vertices: np.ndarray
    faces: np.ndarray
    face_colors: np.ndarray
    transmission_colors: np.ndarray
    z_um_per_display: float
    z_um_at_display_zero: float

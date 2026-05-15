"""Focus sharpness metrics used by live preview and autofocus helpers."""

from __future__ import annotations

import numpy as np


def brenner(frame: np.ndarray) -> float:
    """Brenner focus metric. Higher means sharper."""
    gray = _to_gray_float(frame)
    if gray.shape[0] < 3 and gray.shape[1] < 3:
        return 0.0
    dx = gray[:, 2:] - gray[:, :-2]
    dy = gray[2:, :] - gray[:-2, :]
    score = float(np.mean(dx * dx) + np.mean(dy * dy))
    return score


def tenengrad(frame: np.ndarray) -> float:
    """Tenengrad metric based on Sobel-like gradients."""
    gray = _to_gray_float(frame)
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    gx = (
        gray[:-2, 2:] + 2.0 * gray[1:-1, 2:] + gray[2:, 2:]
        - gray[:-2, :-2] - 2.0 * gray[1:-1, :-2] - gray[2:, :-2]
    )
    gy = (
        gray[2:, :-2] + 2.0 * gray[2:, 1:-1] + gray[2:, 2:]
        - gray[:-2, :-2] - 2.0 * gray[:-2, 1:-1] - gray[:-2, 2:]
    )
    score = float(np.mean(gx * gx + gy * gy))
    return score


def _to_gray_float(frame: np.ndarray) -> np.ndarray:
    data = np.asarray(frame, dtype=np.float32)
    if data.ndim == 2:
        return data
    if data.ndim == 3:
        return data[..., :3].mean(axis=2, dtype=np.float32)
    return np.squeeze(data).astype(np.float32, copy=False)

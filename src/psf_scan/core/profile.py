"""Line profile sampling + Gaussian FWHM fit — used by camera_view line tool (C.3)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit


def _to_gray(image: np.ndarray) -> np.ndarray:
    """RGB → gray; uint → float32. 输出 (H, W) float32."""
    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=2)
    return arr.astype(np.float32, copy=False)


def sample_along_line(
    image: np.ndarray,
    p0: tuple[float, float],
    p1: tuple[float, float],
    n_samples: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """沿 image[(y, x)] 的线段做双线性插值采样。

    p0/p1 单位为 image 像素坐标 (x, y) — 注意 image 第 0 维是 y。
    返回 (positions_px, values), positions 从 0 起按像素距离累计。

    采样点数默认 = ceil(线段长度) + 1, 保证每像素至少一个样本。
    """
    img = _to_gray(image)
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    length = float(np.hypot(x1 - x0, y1 - y0))
    if length < 1e-3:
        return np.zeros(1), np.zeros(1, dtype=np.float32)
    if n_samples is None:
        n_samples = max(2, int(np.ceil(length)) + 1)
    t = np.linspace(0.0, 1.0, n_samples)
    xs = x0 + (x1 - x0) * t
    ys = y0 + (y1 - y0) * t
    positions = t * length
    H, W = img.shape[:2]
    # 限制在图内, 越界点拿邻边值 (clamp)
    xs_c = np.clip(xs, 0, W - 1)
    ys_c = np.clip(ys, 0, H - 1)
    x_lo = np.floor(xs_c).astype(int)
    y_lo = np.floor(ys_c).astype(int)
    x_hi = np.clip(x_lo + 1, 0, W - 1)
    y_hi = np.clip(y_lo + 1, 0, H - 1)
    dx = xs_c - x_lo
    dy = ys_c - y_lo
    v00 = img[y_lo, x_lo]
    v01 = img[y_lo, x_hi]
    v10 = img[y_hi, x_lo]
    v11 = img[y_hi, x_hi]
    values = (
        v00 * (1 - dx) * (1 - dy)
        + v01 * dx * (1 - dy)
        + v10 * (1 - dx) * dy
        + v11 * dx * dy
    )
    return positions.astype(np.float32), values.astype(np.float32)


@dataclass
class GaussFit:
    center: float       # 拟合峰位 (与输入 x 同单位)
    fwhm: float         # 半高全宽
    amplitude: float    # 峰高 (扣基线)
    baseline: float     # 基线
    r2: float           # 拟合质量 0..1


def _gaussian(x, amp, mu, sigma, base):
    return base + amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def fwhm_gauss_fit(x: np.ndarray, y: np.ndarray) -> GaussFit | None:
    """单峰高斯拟合, 返回 FWHM = 2*sqrt(2*ln 2) * sigma。失败返回 None。"""
    if x is None or y is None or len(x) < 5 or len(y) < 5:
        return None
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    base0 = float(np.median(y_arr))
    amp0 = float(y_arr.max() - base0)
    if amp0 <= 0:
        return None
    mu0 = float(x_arr[int(np.argmax(y_arr))])
    span = float(x_arr[-1] - x_arr[0])
    sigma0 = max(span / 10.0, 1e-6)
    try:
        popt, _ = curve_fit(
            _gaussian, x_arr, y_arr,
            p0=[amp0, mu0, sigma0, base0],
            maxfev=2000,
        )
    except Exception:  # noqa: BLE001
        return None
    amp, mu, sigma, base = popt
    if sigma <= 0 or not np.isfinite([amp, mu, sigma, base]).all():
        return None
    y_fit = _gaussian(x_arr, *popt)
    ss_res = float(np.sum((y_arr - y_fit) ** 2))
    ss_tot = float(np.sum((y_arr - y_arr.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    fwhm = 2.0 * float(np.sqrt(2.0 * np.log(2.0))) * abs(float(sigma))
    return GaussFit(
        center=float(mu),
        fwhm=fwhm,
        amplitude=float(abs(amp)),
        baseline=float(base),
        r2=float(max(0.0, min(1.0, r2))),
    )

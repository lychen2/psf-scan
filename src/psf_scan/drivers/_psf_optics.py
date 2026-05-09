"""远场 PSF 计算 — |FFT(pupil)|²。

Pupil function::

    P(ρ, θ) = A(ρ) · exp[ i (φ_aberr(ρ,θ) + φ_defocus(ρ; z) + φ_tilt(ρ,θ; x,y) + m·θ) ]

- ``A(ρ)``: 振幅掩膜，full disk 或带中央遮挡 (Bessel-like 圆环).
- ``φ_aberr``: Zernike 多项式叠加 (RMS 单位 λ).
- ``φ_defocus``: 桨膜近似 ``π · z · NA² · ρ² / λ``.
- ``φ_tilt``: 把 stage XY 位移变成像面平移.
- ``m·θ``: 拓扑荷 m 的螺旋相位 → 中心相位奇点 → 空心 donut.

PSF = |FFT2(P)|². 在脚下零填充倍率 ``N / (2R) = 4`` 时焦面像元 ≈ ``λ / (8·NA)``。
"""

from __future__ import annotations

from typing import Optional

import numpy as np


# ── Zernike 基 (归一化 RMS=1) ────────────────────────────
ZERNIKE = {
    "astig0":     lambda r, t: np.sqrt(6) * r**2 * np.cos(2 * t),
    "astig45":    lambda r, t: np.sqrt(6) * r**2 * np.sin(2 * t),
    "coma_x":     lambda r, t: np.sqrt(8) * (3 * r**3 - 2 * r) * np.cos(t),
    "coma_y":     lambda r, t: np.sqrt(8) * (3 * r**3 - 2 * r) * np.sin(t),
    "trefoil0":   lambda r, t: np.sqrt(8) * r**3 * np.cos(3 * t),
    "trefoil30":  lambda r, t: np.sqrt(8) * r**3 * np.sin(3 * t),
    "spherical":  lambda r, t: np.sqrt(5) * (6 * r**4 - 6 * r**2 + 1),
    "spherical2": lambda r, t: np.sqrt(7) * (20 * r**6 - 30 * r**4 + 12 * r**2 - 1),
}


# ── 预设 — Mock 启动时随机抽一条 ─────────────────────────
# RMS 系数单位 λ。Marechal 准则: 0.07 λ RMS ≈ "衍射极限"。
# 这里取 0.06–0.12 (Strehl ≈ 0.6–0.85)，看得到形态但不毁掉成像。
PRESETS: dict[str, dict] = {
    "diffraction-limited": {},
    "astigmatism":      {"zernike": {"astig0": 0.10}},
    "coma":              {"zernike": {"coma_x": 0.09}},
    "trefoil":           {"zernike": {"trefoil0": 0.09}},
    "spherical":         {"zernike": {"spherical": 0.10}},
    "spherical-strong":  {"zernike": {"spherical": 0.18}},
    "mixed-mild":        {"zernike": {"astig45": 0.05, "spherical": 0.06}},
    "mixed-strong":      {"zernike": {"astig0": 0.07, "coma_y": 0.08, "spherical": 0.07}},
    "vortex-1":          {"vortex": 1},                       # 螺旋相位 m=1
    "vortex-2":          {"vortex": 2},                       # m=2 donut 更大
    "annular":           {"obscuration": 0.55},               # 环形光阑 (Bessel-like)
    "annular+spherical": {"obscuration": 0.45, "zernike": {"spherical": 0.08}},
    "vortex+coma":       {"vortex": 1, "zernike": {"coma_x": 0.08}},
}


class PsfModel:
    """物体平面上一个理想点源在像面上的强度分布，可注入像差 / vortex / 环形阑."""

    def __init__(
        self,
        n_grid: int,
        pupil_radius: int,
        na: float = 0.7,
        wavelength_um: float = 0.5,
        zernike: Optional[dict[str, float]] = None,
        vortex: int = 0,
        obscuration: float = 0.0,
    ) -> None:
        self.N = int(n_grid)
        self.R = int(pupil_radius)
        self.na = float(na)
        self.lam = float(wavelength_um)
        self.zernike = zernike or {}
        self.vortex = int(vortex)
        self.obscuration = float(obscuration)
        self._build()

    @property
    def pixel_um(self) -> float:
        """焦面像元尺寸 (µm)."""
        return self.lam / (2 * self.na) / (self.N / (2 * self.R))

    def _build(self) -> None:
        N, R = self.N, self.R
        c = N // 2
        y, x = np.indices((N, N), dtype=np.float32)
        x = (x - c) / R
        y = (y - c) / R
        rho = np.sqrt(x * x + y * y)
        theta = np.arctan2(y, x)
        # 振幅: 圆盘 (可选环形遮挡)
        mask = (rho <= 1.0).astype(np.float32)
        if self.obscuration > 0:
            mask *= (rho > self.obscuration).astype(np.float32)
        # 静态相位 (Zernike + vortex)
        phi = np.zeros((N, N), dtype=np.float32)
        for name, c_rms in self.zernike.items():
            f = ZERNIKE.get(name)
            if f is not None:
                phi += 2 * np.pi * float(c_rms) * f(rho, theta).astype(np.float32)
        if self.vortex:
            phi += float(self.vortex) * theta.astype(np.float32)
        self._mask = mask
        self._x = x
        self._y = y
        self._rho_sq = (rho * rho).astype(np.float32)
        self._phi_static = phi
        self._phi_buf = np.empty_like(phi)
        # 散焦 / 倾斜系数 (per µm)
        self._k_def = float(np.pi) * (self.na ** 2) / self.lam       # rad / (µm · ρ²)
        self._k_tilt = 2 * float(np.pi) * self.na / self.lam         # rad / (µm · x_norm)
        # 参考峰 (在焦无位移) — 用于稳定振幅归一
        self.ref_peak = float(self.render(0.0, 0.0, 0.0).max())

    def render(self, z_um: float = 0.0, x_um: float = 0.0, y_um: float = 0.0) -> np.ndarray:
        """计算 (z, x, y) 处的 PSF 强度图，shape (N, N)。"""
        np.copyto(self._phi_buf, self._phi_static)
        if z_um:
            self._phi_buf += self._k_def * float(z_um) * self._rho_sq
        if x_um or y_um:
            self._phi_buf += self._k_tilt * (
                float(x_um) * self._x + float(y_um) * self._y
            )
        E_pupil = self._mask * np.exp(1j * self._phi_buf)
        E_focal = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(E_pupil)))
        return (E_focal.real * E_focal.real + E_focal.imag * E_focal.imag)


def random_preset(rng: Optional[np.random.Generator] = None) -> tuple[str, dict]:
    rng = rng or np.random.default_rng()
    name = str(rng.choice(list(PRESETS.keys())))
    return name, PRESETS[name]

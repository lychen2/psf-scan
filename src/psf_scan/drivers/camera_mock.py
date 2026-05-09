"""Mock 相机 — 远场 PSF (FFT of pupil)，启动时随机抽一个相位预设。

- PSF = |FT{ A(ρ)·exp[i·(φ_aberr + φ_defocus(z) + φ_tilt(x,y) + m·θ)] }|²
- 预设见 :mod:`._psf_optics.PRESETS` (Zernike / vortex / 环形阑 / 混合)
- 当前 stage 位置由 ``stage.position`` 实时映射到 PSF (X/Y 位移、Z 散焦)
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QTimer, Slot

from ..core.camera import CameraBase
from ..core.stage import StageBase
from ._psf_optics import PRESETS, PsfModel, random_preset


class MockCamera(CameraBase):
    def __init__(
        self,
        width: int = 512,
        height: int = 512,
        fps: float = 30.0,
        stage: Optional[StageBase] = None,
        na: float = 0.7,
        wavelength_um: float = 0.5,
        peak_counts: Optional[float] = None,
        dark_counts: Optional[float] = None,
        bit_depth: int = 8,
        preset: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._w = int(width)
        self._h = int(height)
        self._fps = float(fps)
        self._stage = stage
        self._dtype = np.uint16 if bit_depth > 8 else np.uint8
        self._max_val = (1 << bit_depth) - 1
        # 默认在焦衍射极限峰 ≈ 70% 满量程，留给增益/aberration 调节空间
        self._peak = float(peak_counts) if peak_counts is not None else self._max_val * 0.7
        self._dark = float(dark_counts) if dark_counts is not None else self._max_val * 0.01
        self._exposure_us = 10_000
        self._gain = 1.0
        self._gamma = 1.0
        self._black_level = 0
        self._connected = False
        self._streaming = False
        self._rng = np.random.default_rng()

        N = max(self._w, self._h)
        R = max(8, N // 8)  # 4× 零填充 → 焦面像元 ≈ λ/(8·NA)
        if preset is None:
            self._preset_name, params = random_preset(self._rng)
        else:
            self._preset_name = preset
            params = PRESETS.get(preset, {})
        self._psf = PsfModel(
            n_grid=N, pupil_radius=R, na=na, wavelength_um=wavelength_um,
            zernike=params.get("zernike"),
            vortex=params.get("vortex", 0),
            obscuration=params.get("obscuration", 0.0),
        )

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._produce_frame)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def frame_size(self) -> tuple[int, int]:
        return (self._w, self._h)

    @property
    def description(self) -> str:
        return f"mock · pupil={self._preset_name}"

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self.stop_streaming()
        self._connected = False

    def start_streaming(self) -> None:
        if not self._connected:
            self.error.emit("相机未连接")
            return
        self._streaming = True
        self._timer.start(int(1000 / self._fps))

    def stop_streaming(self) -> None:
        self._timer.stop()
        self._streaming = False

    def grab_one(self, timeout_ms: int = 1000) -> np.ndarray:
        return self._render()

    def set_exposure_us(self, us: int) -> None:
        self._exposure_us = max(1, int(us))

    def set_gain(self, gain: float) -> None:
        self._gain = max(0.0, float(gain))

    def get_exposure_us(self) -> int:
        return self._exposure_us

    def get_gain(self) -> float:
        return self._gain

    def exposure_range(self) -> tuple[int, int]:
        return (10, 200_000)

    def gain_range(self) -> tuple[float, float]:
        return (0.0, 16.0)

    def bit_depth(self) -> int:
        return int(np.log2(self._max_val + 1))

    # ── advanced (mock 全部支持，实时影响渲染) ──────────────
    def set_gamma(self, gamma: float) -> None:
        self._gamma = max(0.1, float(gamma))

    def get_gamma(self) -> float | None:
        return self._gamma

    def gamma_range(self) -> tuple[float, float] | None:
        return (0.1, 4.0)

    def set_black_level(self, level: int) -> None:
        self._black_level = max(0, int(level))

    def get_black_level(self) -> int | None:
        return self._black_level

    def black_level_range(self) -> tuple[int, int] | None:
        return (0, int(self._max_val // 4))

    def set_frame_rate(self, fps: float) -> None:
        self._fps = max(1.0, float(fps))
        if self._streaming:
            self._timer.start(int(1000 / self._fps))

    def get_frame_rate(self) -> float | None:
        return self._fps

    def frame_rate_range(self) -> tuple[float, float] | None:
        return (1.0, 120.0)

    def pixel_formats(self) -> tuple[str, ...]:
        return ("Mono8",) if self.bit_depth() == 8 else ("Mono8", "Mono16")

    def get_pixel_format(self) -> str | None:
        return "Mono8" if self.bit_depth() == 8 else "Mono16"

    @Slot()
    def _produce_frame(self) -> None:
        self.frame_ready.emit(self._render(), time.time())

    def _render(self) -> np.ndarray:
        x, y, z = self._stage.position if self._stage else (0.0, 0.0, 0.0)
        psf = self._psf.render(z_um=z, x_um=x, y_um=y)
        # 裁到相机尺寸 (PSF FFT 网格 N×N，相机 H×W ≤ N)
        N = psf.shape[0]
        y0 = (N - self._h) // 2
        x0 = (N - self._w) // 2
        cropped = psf[y0:y0 + self._h, x0:x0 + self._w]
        # 振幅归一：在焦衍射极限峰 → peak_counts；其它情况按物理峰值缩放
        scale = self._peak / max(1e-12, self._psf.ref_peak)
        sig = cropped * scale * (self._exposure_us / 10_000.0 * self._gain)
        bg = self._dark * (self._exposure_us / 10_000.0) + self._black_level
        noisy = self._rng.poisson(np.clip(sig, 0, None) + bg).astype(np.float32)
        if self._gamma != 1.0:
            noisy = np.power(np.clip(noisy / self._max_val, 0.0, 1.0), 1.0 / self._gamma) * self._max_val
        return np.clip(noisy, 0, self._max_val).astype(self._dtype)

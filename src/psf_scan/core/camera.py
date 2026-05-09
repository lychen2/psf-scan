"""相机抽象 + 工厂。"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, Signal


class CameraBase(QObject):
    """相机基类。所有具体驱动继承此类。"""

    # 实时帧 (frame: np.ndarray HxW or HxWxC, timestamp_s: float)
    frame_ready = Signal(object, float)
    error = Signal(str)

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError

    @property
    def is_streaming(self) -> bool:
        raise NotImplementedError

    @property
    def frame_size(self) -> tuple[int, int]:
        """返回 (width, height)"""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """简短描述（如 ``mock · pupil=coma`` 或 ``mvs(SN=...)``），用于状态栏。"""
        return type(self).__name__.lower()

    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def start_streaming(self) -> None:
        raise NotImplementedError

    def stop_streaming(self) -> None:
        raise NotImplementedError

    def grab_one(self, timeout_ms: int = 1000) -> np.ndarray:
        """同步取一帧。扫描时使用，避免与流抢帧。"""
        raise NotImplementedError

    def set_exposure_us(self, us: int) -> None:
        raise NotImplementedError

    def set_gain(self, gain: float) -> None:
        raise NotImplementedError

    def get_exposure_us(self) -> int:
        """当前曝光时间 (µs)。子类应返回内部状态。"""
        return 10_000

    def get_gain(self) -> float:
        return 1.0

    def exposure_range(self) -> tuple[int, int]:
        """允许的曝光时间范围 (us_min, us_max)。"""
        return (10, 1_000_000)

    def gain_range(self) -> tuple[float, float]:
        return (0.0, 32.0)

    def bit_depth(self) -> int:
        return 8

    # ── advanced controls (optional, return None = feature unavailable) ──
    def set_gamma(self, gamma: float) -> None: pass
    def get_gamma(self) -> float | None: return None
    def gamma_range(self) -> tuple[float, float] | None: return None

    def set_black_level(self, level: int) -> None: pass
    def get_black_level(self) -> int | None: return None
    def black_level_range(self) -> tuple[int, int] | None: return None

    def set_frame_rate(self, fps: float) -> None: pass
    def get_frame_rate(self) -> float | None: return None
    def frame_rate_range(self) -> tuple[float, float] | None: return None

    def set_pixel_format(self, fmt: str) -> None: pass
    def get_pixel_format(self) -> str | None: return None
    def pixel_formats(self) -> tuple[str, ...]: return ()


AVAILABLE_CAMERAS = ["mock", "mvs"]


def make_camera(kind: str, **kwargs) -> CameraBase:
    """按字符串名实例化相机驱动。"""
    kind = kind.lower()
    if kind == "mock":
        from ..drivers.camera_mock import MockCamera

        return MockCamera(**kwargs)
    if kind == "mvs":
        from ..drivers.camera_mvs import MVSCamera

        return MVSCamera(**kwargs)
    raise ValueError(f"未知相机类型 {kind!r}（可用: {AVAILABLE_CAMERAS}）")

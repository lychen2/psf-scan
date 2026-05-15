"""位移台软限位 — app 层物理保护, 防止程序意外让 stage 撞到物镜/样品台.

实现:
- ``SafetyLimits`` 6 个上下限 + enabled 总开关.
- ``check_point`` 校验单点是否在限位内; 失败返回违规轴与值.
- ``check_path`` 批量校验扫描路径, 失败立即返回首违规.
- 默认 ±100 µm, enabled=True (新机起步保守).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class SafetyLimits:
    enabled: bool = True
    x_min: float = -100.0
    x_max: float = 100.0
    y_min: float = -100.0
    y_max: float = 100.0
    z_min: float = -100.0
    z_max: float = 100.0

    def check_point(self, x: float, y: float, z: float) -> Optional[tuple[str, float, float, float]]:
        """返回 (axis, value, lo, hi) 元组表示越界; None 表示通过."""
        if not self.enabled:
            return None
        checks = (
            ("x", x, self.x_min, self.x_max),
            ("y", y, self.y_min, self.y_max),
            ("z", z, self.z_min, self.z_max),
        )
        for axis, value, lo, hi in checks:
            if value < lo or value > hi:
                return (axis, float(value), float(lo), float(hi))
        return None

    def check_path(self, points: np.ndarray) -> Optional[tuple[str, float, float, float]]:
        """points: (N, 3). 返回首违规点或 None."""
        if not self.enabled:
            return None
        if points.size == 0:
            return None
        xs, ys, zs = points[:, 0], points[:, 1], points[:, 2]
        # x
        if xs.min() < self.x_min:
            return ("x", float(xs.min()), self.x_min, self.x_max)
        if xs.max() > self.x_max:
            return ("x", float(xs.max()), self.x_min, self.x_max)
        if ys.min() < self.y_min:
            return ("y", float(ys.min()), self.y_min, self.y_max)
        if ys.max() > self.y_max:
            return ("y", float(ys.max()), self.y_min, self.y_max)
        if zs.min() < self.z_min:
            return ("z", float(zs.min()), self.z_min, self.z_max)
        if zs.max() > self.z_max:
            return ("z", float(zs.max()), self.z_min, self.z_max)
        return None


DEFAULTS = SafetyLimits()

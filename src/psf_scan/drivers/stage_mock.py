"""模拟位移台。

60 Hz tick，按速度+加速度做梯形速度曲线收敛到目标。
跨线程读 ``is_moving`` / ``position`` 是安全的（GIL 原子）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QTimer, Slot

from ..core.stage import StageBase

_TICK_HZ = 60
_DT = 1.0 / _TICK_HZ
_EPS = 1e-3  # µm


class MockStage(StageBase):
    def __init__(
        self,
        velocity_um_s: float = 800.0,
        accel_um_s2: float = 4000.0,
        position_noise_nm: float = 5.0,
        travel_min_um: float = -100_000.0,
        travel_max_um: float = 100_000.0,
        invert_z: bool = False,
        safe_radius_um: float = 100.0,
        **_ignored,
    ) -> None:
        super().__init__()
        self._connected = False
        self._pos = [0.0, 0.0, 0.0]
        self._target = [0.0, 0.0, 0.0]
        self._cur_v = [0.0, 0.0, 0.0]
        self._velocity = float(velocity_um_s)
        self._accel = float(accel_um_s2)
        self._noise = float(position_noise_nm) * 1e-3  # → µm
        self._moving = False
        self._zero_offset_um = 0.0
        self._tmin_um = float(travel_min_um)
        self._tmax_um = float(travel_max_um)
        self._invert_z = bool(invert_z)
        self._safe_radius_um = float(safe_radius_um)
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / _TICK_HZ))
        self._timer.timeout.connect(self._tick)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def position(self) -> tuple[float, float, float]:
        """对外暴露用户视角 (扣 zero offset + invert_z)。"""
        z_user = self._pos[2] - self._zero_offset_um
        if self._invert_z:
            z_user = -z_user
        return (self._pos[0], self._pos[1], z_user)

    @property
    def raw_position(self) -> tuple[float, float, float]:
        """物理 ctrl 坐标 — mock camera 拍的是物理点位。"""
        return tuple(self._pos)

    @property
    def is_moving(self) -> bool:
        return self._moving

    @property
    def travel_limits_um(self) -> tuple[float, float]:
        lo = self._tmin_um - self._zero_offset_um
        hi = self._tmax_um - self._zero_offset_um
        if self._invert_z:
            lo, hi = -lo, -hi
        return (min(lo, hi), max(lo, hi))

    @property
    def hw_travel_z_um(self) -> tuple[float, float]:
        """硬件帧 z 行程 (ctrl 坐标系, 不受 set_zero/invert 影响)。"""
        return (float(self._tmin_um), float(self._tmax_um))

    def user_to_hw(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """逆变换: user 帧 → ctrl 帧 (与 move_to 里的换算一致)。"""
        z_in = -float(z) if self._invert_z else float(z)
        z_ctrl = z_in + self._zero_offset_um
        return (float(x), float(y), z_ctrl)

    def connect(self) -> None:
        self._connected = True
        # FRESH: 连接即把当前点设为 user 0, 行程锁到 ±safe_radius (跟 PI 一致)
        self._zero_offset_um = self._pos[2]
        self._tmin_um = self._pos[2] - self._safe_radius_um
        self._tmax_um = self._pos[2] + self._safe_radius_um
        self._timer.start()
        self.position_changed.emit(*self.position)

    def disconnect(self) -> None:
        self._timer.stop()
        self._connected = False

    def move_to(self, x: float, y: float, z: float) -> None:
        if not self._connected:
            self.error.emit("位移台未连接"); return
        z_in = -float(z) if self._invert_z else float(z)
        z_ctrl = z_in + self._zero_offset_um
        if not (self._tmin_um <= z_ctrl <= self._tmax_um):
            lo, hi = self.travel_limits_um
            self.error.emit(f"⛔ 越界: 目标超出 [{lo:.1f}, {hi:.1f}] µm (user 视角)")
            return
        self._target = [float(x), float(y), z_ctrl]
        self._moving = True

    def stop(self) -> None:
        """急停: 取消目标 + 速度归零。"""
        self._target = list(self._pos)
        self._cur_v = [0.0, 0.0, 0.0]
        self._moving = False

    def set_zero(self) -> None:
        # 重设坐标系前先停住任何 pending 运动 — set_zero 不能让 stage 物理移动
        self._target = list(self._pos)
        self._cur_v = [0.0, 0.0, 0.0]
        self._moving = False
        self._zero_offset_um = self._pos[2]
        self.position_changed.emit(*self.position)
        lo, hi = self.travel_limits_um
        self.error.emit(f"已置零 (ctrl={self._pos[2]:.1f}); 范围 [{lo:.0f}, {hi:.0f}] µm")

    def set_travel_limits_um(self, lo_user_um: float, hi_user_um: float) -> None:
        """从用户视角写软限位; 内部换算到 ctrl 系存。"""
        # 把 user lo/hi 转回 ctrl
        if self._invert_z:
            ctrl_a = -float(lo_user_um) + self._zero_offset_um
            ctrl_b = -float(hi_user_um) + self._zero_offset_um
        else:
            ctrl_a = float(lo_user_um) + self._zero_offset_um
            ctrl_b = float(hi_user_um) + self._zero_offset_um
        self._tmin_um, self._tmax_um = sorted((ctrl_a, ctrl_b))
        lo, hi = self.travel_limits_um
        self.error.emit(f"软限位已更新: 用户视角 [{lo:.1f}, {hi:.1f}] µm")

    def set_velocity(self, v_um_per_s: float) -> None:
        self._velocity = max(1.0, float(v_um_per_s))

    def set_invert_z(self, on: bool) -> None:
        """热切换 z 反转。stage 物理不动, 仅 user view 数字翻一边。"""
        self._invert_z = bool(on)
        self.position_changed.emit(*self.position)

    def reset_range(self, radius_um: float) -> None:
        """以当前位置为 user 0, 行程重设为 ctrl ± radius。stage 物理不动。"""
        if not self._connected: return
        self._target = list(self._pos)
        self._cur_v = [0.0, 0.0, 0.0]
        self._moving = False
        r = abs(float(radius_um))
        self._zero_offset_um = self._pos[2]
        self._tmin_um = self._pos[2] - r
        self._tmax_um = self._pos[2] + r
        self.position_changed.emit(*self.position)
        lo, hi = self.travel_limits_um
        self.error.emit(f"Range 重置: 当前=user 0; 范围 [{lo:.1f}, {hi:.1f}] µm")

    @Slot()
    def _tick(self) -> None:
        any_moving = False
        for i in range(3):
            if self._step_axis(i):
                any_moving = True
        was_moving = self._moving
        self._moving = any_moving
        # 加微小抖动让动画更"真实", 但仅在静止时不抖, 移动时基于 ctrl 位置抖再扣 offset
        n = self._noise
        x = self._pos[0] + ((random.random() - 0.5) * n if n > 0 else 0.0)
        y = self._pos[1] + ((random.random() - 0.5) * n if n > 0 else 0.0)
        z = self._pos[2] + ((random.random() - 0.5) * n if n > 0 else 0.0)
        z_user = z - self._zero_offset_um
        if self._invert_z:
            z_user = -z_user
        self.position_changed.emit(x, y, z_user)
        if was_moving and not any_moving:
            self.move_finished.emit()

    def _step_axis(self, i: int) -> bool:
        err = self._target[i] - self._pos[i]
        v = self._cur_v[i]
        if abs(err) < _EPS and abs(v) < _EPS:
            self._cur_v[i] = 0.0
            return False
        sign = 1.0 if err >= 0 else -1.0
        d_stop = (v * v) / (2 * self._accel)  # 距离能让当前速度刹停所需
        same_dir = sign * v >= 0
        # 决定加速 / 减速
        if same_dir and abs(err) <= d_stop:
            self._cur_v[i] -= sign * self._accel * _DT
        else:
            self._cur_v[i] += sign * self._accel * _DT
        # clamp speed
        if abs(self._cur_v[i]) > self._velocity:
            self._cur_v[i] = math.copysign(self._velocity, self._cur_v[i])
        # 推进位置
        new_pos = self._pos[i] + self._cur_v[i] * _DT
        # 防过冲
        if (sign > 0 and new_pos > self._target[i]) or (sign < 0 and new_pos < self._target[i]):
            new_pos = self._target[i]
            self._cur_v[i] = 0.0
        self._pos[i] = new_pos
        return True

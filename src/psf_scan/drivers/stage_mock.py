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
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / _TICK_HZ))
        self._timer.timeout.connect(self._tick)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def position(self) -> tuple[float, float, float]:
        return tuple(self._pos)

    @property
    def is_moving(self) -> bool:
        return self._moving

    def connect(self) -> None:
        self._connected = True
        self._timer.start()
        self.position_changed.emit(*self._pos)

    def disconnect(self) -> None:
        self._timer.stop()
        self._connected = False

    def move_to(self, x: float, y: float, z: float) -> None:
        if not self._connected:
            self.error.emit("位移台未连接")
            return
        self._target = [float(x), float(y), float(z)]
        self._moving = True

    def set_velocity(self, v_um_per_s: float) -> None:
        self._velocity = max(1.0, float(v_um_per_s))

    @Slot()
    def _tick(self) -> None:
        any_moving = False
        for i in range(3):
            if self._step_axis(i):
                any_moving = True
        was_moving = self._moving
        self._moving = any_moving
        # 加微小抖动让动画更"真实"
        n = self._noise
        if n > 0:
            disp = [self._pos[i] + (random.random() - 0.5) * n for i in range(3)]
        else:
            disp = list(self._pos)
        self.position_changed.emit(*disp)
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

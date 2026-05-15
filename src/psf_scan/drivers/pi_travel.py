"""PI 单轴 — 软限位 + 用户零点偏移 + 速度上限。

外部接口与项目其余部分一致使用 µm; 仅在与 PI 硬件 API 通讯时换算 mm。
controller 物理坐标系是 [tmin_um, tmax_um], 是绝对硬边界。
用户视角 = controller - zero_offset_um。move_to 永远先转 controller 坐标系
再校验, 物理上不可能越界。
"""

from __future__ import annotations


class TravelGuard:
    """物理硬限位 + 用户视角零点偏移 + 速度上限 + z 轴反转 (全部 µm)。"""

    def __init__(
        self,
        tmin_um: float = 0.0,
        tmax_um: float = 150_000.0,
        velocity_max_um_s: float = 2_000.0,
        invert_z: bool = False,
    ) -> None:
        self.tmin_um = float(tmin_um)
        self.tmax_um = float(tmax_um)
        self.zero_offset_um = 0.0
        self.velocity_max_um_s = float(velocity_max_um_s)
        self.invert_z = bool(invert_z)

    def set_zero(self, ctrl_pos_um: float) -> None:
        """把当前 ctrl 位置定义为用户视角的 0。"""
        self.zero_offset_um = float(ctrl_pos_um)

    def reset_zero(self) -> None:
        self.zero_offset_um = 0.0

    def to_user_um(self, ctrl_um: float) -> float:
        v = ctrl_um - self.zero_offset_um
        return -v if self.invert_z else v

    def to_ctrl_um(self, user_um: float) -> float:
        u = -user_um if self.invert_z else user_um
        return u + self.zero_offset_um

    def in_range_ctrl(self, ctrl_um: float) -> bool:
        return self.tmin_um <= ctrl_um <= self.tmax_um

    @property
    def user_travel_um(self) -> tuple[float, float]:
        lo = self.to_user_um(self.tmin_um)
        hi = self.to_user_um(self.tmax_um)
        return (min(lo, hi), max(lo, hi))

    def clamp_velocity(self, v_um_s: float) -> tuple[float, bool]:
        """clamp 速度到 [0.1, max]; 返回 (clamped_value, was_clamped)。"""
        v = max(0.1, float(v_um_s))
        if v > self.velocity_max_um_s:
            return self.velocity_max_um_s, True
        return v, False

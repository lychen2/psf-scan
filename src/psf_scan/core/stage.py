"""位移台抽象 + 工厂。新增驱动只要在 ``make_stage`` 加一行。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class StageBase(QObject):
    """位移台基类。子类继承此类并实现下面所有方法。

    位置单位 µm。所有移动是非阻塞的——状态通过信号回报。
    """

    # 实时位置 (x, y, z) µm
    position_changed = Signal(float, float, float)
    # 一次 ``move_to`` 完成
    move_finished = Signal()
    # 错误回报
    error = Signal(str)

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError

    @property
    def position(self) -> tuple[float, float, float]:
        raise NotImplementedError

    @property
    def raw_position(self) -> tuple[float, float, float]:
        """物理 controller 坐标 (不扣 zero offset)。供 mock camera 等内部组件用。
        默认与 position 一致; 实现了 set_zero 的子类应覆写返回真实 ctrl 坐标。"""
        return self.position

    def user_to_hw(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """把 (x, y, z) 从 user 帧逆向到 controller (hw) 帧。

        默认恒等; 子类若实现 set_zero/invert_z 必须覆写, 否则 app 层的硬件帧
        软限位检查会失真。
        """
        return (float(x), float(y), float(z))

    @property
    def hw_travel_z_um(self) -> tuple[float, float]:
        """Z 轴硬件帧行程 (lo, hi)。默认 (-inf, +inf); 子类按硬件覆写。

        app 层把当前 ctrl_z 与目标 ctrl_z 都对照这个范围检查 —
        与 SafetyLimits 一起构成"不太对劲就不动"的双层保护。
        """
        return (-float("inf"), float("inf"))

    @property
    def is_moving(self) -> bool:
        raise NotImplementedError

    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def move_to(self, x: float, y: float, z: float) -> None:
        raise NotImplementedError

    def home(self) -> None:
        self.move_to(0.0, 0.0, 0.0)

    def set_velocity(self, v_um_per_s: float) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        """急停 (可选实现)。默认: do-nothing — 急停不能因 driver 缺少而失败。"""
        return

    def set_zero(self) -> None:
        """把当前位置定义为用户视角的 0 (可选实现)。"""
        return

    def set_invert_z(self, on: bool) -> None:
        """热切换 z 轴反转 (可选实现; settings 改了后 app 调用)。"""
        return

    def reset_range(self, radius_um: float) -> None:
        """以当前位置为 user 0 + 重设行程到 ±radius_um (可选实现)。

        防"行程越缩越小": 用户在边缘卡住时, 主动调此 method 扩大范围。
        """
        return

    def reference(self, refmode: str = "FRF") -> bool:
        """手动寻参 (FRF/FNL/FPL)。可选实现; 返回是否成功对零。"""
        return False

    @property
    def travel_limits_um(self) -> tuple[float, float]:
        return (-float("inf"), float("inf"))


AVAILABLE_STAGES = ["pi-m531", "mock"]


def make_stage(kind: str, **kwargs) -> StageBase:
    """按字符串名实例化驱动。UI 下拉列表里直接选。"""
    kind = kind.lower()
    if kind == "mock":
        from ..drivers.stage_mock import MockStage

        return MockStage(**kwargs)
    if kind in {"pi-m531", "pi", "m531"}:
        from ..drivers.stage_pi import PIStage

        return PIStage(**kwargs)
    raise ValueError(f"未知位移台类型 {kind!r}（可用: {AVAILABLE_STAGES}）")

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


AVAILABLE_STAGES = ["mock"]


def make_stage(kind: str, **kwargs) -> StageBase:
    """按字符串名实例化驱动。UI 下拉列表里直接选。"""
    kind = kind.lower()
    if kind == "mock":
        from ..drivers.stage_mock import MockStage

        return MockStage(**kwargs)
    raise ValueError(f"未知位移台类型 {kind!r}（可用: {AVAILABLE_STAGES}）")

"""PI M-531 单轴位移台驱动 (基于 PIPython GCSDevice)。

约定:
- M-531 单轴 → 映射到 z 通道; x/y 始终为 0。
- StageBase 接口单位 µm; PI 内部以 mm 工作, 这里乘除 1000 换算。
- pipython 用 lazy import: 没装/没硬件时也能让 UI 用 mock 跑起来。
- I/O 由 QTimer 在 UI 线程轮询 (30Hz, 单次 qPOS 微秒级 USB IO)。
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QTimer, Slot

from ..core.stage import StageBase

MM_PER_UM = 1.0 / 1000.0
UM_PER_MM = 1000.0
POLL_HZ = 30
CONNECT_TIMEOUT_S = 8.0


class PIStage(StageBase):
    """PI 单轴位移台 (M-531 + C-863 控制器, USB)。"""

    def __init__(
        self,
        controller: str = "C-863",
        stage: str = "M-531.DG",
        refmode: str = "FRF",
        serialnum: Optional[str] = None,
        ip: Optional[str] = None,
        comport: Optional[int] = None,
        baudrate: int = 115200,
        velocity_um_s: Optional[float] = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._stage_name = stage
        self._refmode = refmode
        self._serialnum = serialnum
        self._ip = ip
        self._comport = comport
        self._baudrate = baudrate
        self._velocity_um_s = velocity_um_s

        self._dev = None  # GCSDevice; 在 connect() 里 lazy 构造
        self._axis_id: Optional[str] = None
        self._pos_um = [0.0, 0.0, 0.0]
        self._target_z_um = 0.0
        self._connected = False
        self._moving = False

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / POLL_HZ))
        self._timer.timeout.connect(self._poll)

    # ── StageBase API ─────────────────────────────────────
    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def position(self) -> tuple[float, float, float]:
        return (self._pos_um[0], self._pos_um[1], self._pos_um[2])

    @property
    def is_moving(self) -> bool:
        return self._moving

    def connect(self) -> None:
        try:
            from pipython import GCSDevice, pitools
        except ImportError as exc:
            self.error.emit(f"未安装 pipython: {exc}")
            return
        try:
            self._dev = GCSDevice(self._controller)
            self._open_link()
            pitools.startup(
                self._dev,
                stages=[self._stage_name],
                refmodes=[self._refmode],
            )
            self._axis_id = str(self._dev.axes[0])
            if self._velocity_um_s is not None and self._dev.HasVEL():
                self._dev.VEL(self._axis_id, self._velocity_um_s * MM_PER_UM)
            # 初始位置
            pos_mm = float(self._dev.qPOS(self._axis_id)[self._axis_id])
            self._pos_um[2] = pos_mm * UM_PER_MM
            self._target_z_um = self._pos_um[2]
            self._connected = True
            self._timer.start()
            self.position_changed.emit(*self._pos_um)
        except Exception as exc:  # noqa: BLE001
            self._cleanup_dev()
            self.error.emit(f"PI 连接失败: {exc}")

    def disconnect(self) -> None:
        self._timer.stop()
        try:
            if self._dev is not None and self._dev.IsConnected():
                # 停轴避免残留运动
                try:
                    self._dev.STP(noraise=True)
                except Exception:  # noqa: BLE001
                    pass
                self._dev.CloseConnection()
        except Exception:  # noqa: BLE001
            pass
        self._cleanup_dev()
        self._connected = False
        self._moving = False

    def move_to(self, x: float, y: float, z: float) -> None:
        if not self._connected or self._dev is None or self._axis_id is None:
            self.error.emit("位移台未连接")
            return
        # M-531 单轴, 只接收 z; xy 忽略 (mock 兼容)
        self._target_z_um = float(z)
        try:
            self._dev.MOV(self._axis_id, float(z) * MM_PER_UM)
            self._moving = True
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"MOV 失败: {exc}")

    def home(self) -> None:
        """单轴位移台 home = 移到 0 µm; xy 不动。"""
        self.move_to(0.0, 0.0, 0.0)

    def set_velocity(self, v_um_per_s: float) -> None:
        self._velocity_um_s = max(0.1, float(v_um_per_s))
        if self._dev is None or self._axis_id is None or not self._connected:
            return
        try:
            if self._dev.HasVEL():
                self._dev.VEL(self._axis_id, self._velocity_um_s * MM_PER_UM)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"VEL 失败: {exc}")

    # ── 内部 ───────────────────────────────────────────────
    def _open_link(self) -> None:
        if self._dev is None:
            raise RuntimeError("GCSDevice 未初始化")
        if self._ip:
            self._dev.ConnectTCPIP(ipaddress=self._ip)
            return
        if self._comport is not None:
            self._dev.ConnectRS232(comport=self._comport, baudrate=self._baudrate)
            return
        # USB: serialnum 给了就直连, 没给就枚举选第一个
        if self._serialnum:
            self._dev.ConnectUSB(serialnum=self._serialnum)
            return
        devices = self._dev.EnumerateUSB(mask=self._controller)
        if not devices:
            raise RuntimeError(f"未找到 {self._controller} USB 设备")
        self._dev.ConnectUSB(serialnum=devices[0])

    def _cleanup_dev(self) -> None:
        self._dev = None
        self._axis_id = None

    @Slot()
    def _poll(self) -> None:
        if self._dev is None or self._axis_id is None or not self._connected:
            return
        try:
            pos_mm = float(self._dev.qPOS(self._axis_id)[self._axis_id])
            self._pos_um[2] = pos_mm * UM_PER_MM
            was_moving = self._moving
            try:
                ont = bool(self._dev.qONT(self._axis_id)[self._axis_id])
            except Exception:  # noqa: BLE001
                # 控制器不支持 qONT 时回退到位置容差判断
                ont = abs(pos_mm - self._target_z_um * MM_PER_UM) < 5e-5
            self._moving = not ont
            self.position_changed.emit(*self._pos_um)
            if was_moving and not self._moving:
                self.move_finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"位移台读取失败: {exc}")
            self._timer.stop()

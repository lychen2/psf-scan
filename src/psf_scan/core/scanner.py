"""扫描调度器 — 在独立 QThread 里跑。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import ClassVar, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal

from .calibration import CalibrationConfig, apply_calibration, is_sensor_saturated
from .camera import CameraBase
from .stage import StageBase

MOVE_TIMEOUT_S = 30.0
POLL_SLEEP_S = 0.005
POSITION_TOLERANCE_UM = 0.02
SETTLE_S = 0.02
# 相机 streaming 一直开着，移动到位前已有上一个 z 的帧排在 SDK 队列里。
# 进入均匀化采样前先丢弃 N 帧，避免上一个 z 的值被均到当前 z 的平均帧里。
WARMUP_FRAMES = 2
WARMUP_TIMEOUT_MS = 50


@dataclass
class ScanParams:
    """扫描参数。Z 必填；XY 可选。"""

    DEFAULT_SAMPLE_COUNT: ClassVar[int] = 4

    z_start: float = -10.0
    z_stop: float = 10.0
    z_step: float = 0.5
    x_start: Optional[float] = None
    x_stop: Optional[float] = None
    x_step: Optional[float] = None
    y_start: Optional[float] = None
    y_stop: Optional[float] = None
    y_step: Optional[float] = None
    dwell_ms: int = 50
    sample_count: int = DEFAULT_SAMPLE_COUNT
    snake: bool = True

    def points(self) -> np.ndarray:
        """生成 (N, 3) 路径点。Z 内层、X 中层、Y 外层；XY 蛇形减少回程。"""
        zs = _linspace(self.z_start, self.z_stop, self.z_step)
        xs = _linspace(self.x_start, self.x_stop, self.x_step) if self.x_step else np.array([0.0])
        ys = _linspace(self.y_start, self.y_stop, self.y_step) if self.y_step else np.array([0.0])
        pts = []
        for iy, y in enumerate(ys):
            xs_iter = xs if (not self.snake or iy % 2 == 0) else xs[::-1]
            for x in xs_iter:
                for z in zs:
                    pts.append((float(x), float(y), float(z)))
        return np.array(pts, dtype=np.float64)


@dataclass
class ScanMetadata:
    """Optional user-provided metadata stored with scan artifacts."""

    sample_name: str = ""
    objective: str = ""
    na: float | None = None
    wavelength_nm: float | None = None
    note: str = ""


def _linspace(start, stop, step) -> np.ndarray:
    if start is None or stop is None or step is None or step == 0:
        return np.array([0.0])
    n = int(round(abs(stop - start) / abs(step))) + 1
    return np.linspace(start, stop, n)


@dataclass
class ScanResult:
    params: ScanParams
    positions: np.ndarray   # (N, 3)
    frames: np.ndarray      # (N, H, W) or (N, H, W, C)
    timestamps: np.ndarray  # (N,)
    started_at: float
    finished_at: float
    metadata: ScanMetadata | None = None
    corrected_frames: np.ndarray | None = None
    calibration: dict | None = None
    pixel_calibration: dict | None = None


class ScanCanceled(Exception):
    """扫描被用户取消 — 走静默退出而不是 error.emit。"""


class Scanner(QObject):
    """扫描 worker。``run`` 在自己的 QThread 里执行。"""

    progress = Signal(int, int, float, float, float)   # idx_1based, total, x, y, z
    frame_acquired = Signal(int, float, float, float, object, bool)
    finished = Signal(object)  # ScanResult
    canceled = Signal(int)     # 已采集帧数 (>=0)
    error = Signal(str)

    def __init__(self, stage: StageBase, camera: CameraBase) -> None:
        super().__init__()
        self._stage = stage
        self._camera = camera
        self._params: Optional[ScanParams] = None
        self._calibration: CalibrationConfig | None = None
        self._cancel = False
        self._writer = None  # StreamingScanWriter | None (duck-typed: 仅需 append/count)

    def configure(self, params: ScanParams, writer=None,
                  calibration: CalibrationConfig | None = None) -> None:
        self._params = params
        self._writer = writer
        self._calibration = calibration

    def cancel(self) -> None:
        """跨线程调用安全：bool 赋值原子。"""
        self._cancel = True

    def run(self) -> None:
        if self._params is None:
            self.error.emit("ScanParams 未设置")
            return
        try:
            self._cancel = False
            t0 = time.time()
            pts = self._params.points()
            frames: list[np.ndarray] = []
            corrected_frames: list[np.ndarray] = []
            ts: list[float] = []
            try:
                for idx, (x, y, z) in enumerate(pts):
                    if self._cancel:
                        break
                    position = (float(x), float(y), float(z))
                    if not self._move_and_wait(position):
                        if self._cancel:
                            break
                        self.error.emit("移动超时")
                        return
                    frame = self._acquire_average_frame()
                    corrected = self._correct_frame(frame)
                    t = time.time() - t0
                    frames.append(frame)
                    if corrected is not None:
                        corrected_frames.append(corrected)
                    ts.append(t)
                    # streaming: 边采边写 stack.h5, 中途崩溃已写帧保留 (C.4)
                    if self._writer is not None:
                        try:
                            self._writer.append(
                                idx, float(x), float(y), float(z), frame, t,
                                corrected=corrected,
                            )
                        except Exception as exc:  # noqa: BLE001
                            self.error.emit(f"流式写盘失败: {exc}")
                            return
                    self.progress.emit(idx + 1, len(pts), float(x), float(y), float(z))
                    self.frame_acquired.emit(
                        idx, float(x), float(y), float(z),
                        corrected if corrected is not None else frame,
                        self._is_sensor_saturated(frame),
                    )
            except ScanCanceled:
                pass

            if self._cancel and not frames:
                self.canceled.emit(0)
                return
            if not frames:
                self.error.emit("未采集到任何帧")
                return
            stack = np.stack(frames)
            corrected_stack = np.stack(corrected_frames) if corrected_frames else None
            result = ScanResult(
                params=self._params,
                positions=pts[: len(frames)],
                frames=stack,
                timestamps=np.array(ts),
                started_at=t0,
                finished_at=time.time(),
                corrected_frames=corrected_stack,
                calibration=None if self._calibration is None else self._calibration.metadata(),
            )
            if self._cancel:
                self.finished.emit(result)
                self.canceled.emit(len(frames))
            else:
                self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"扫描出错: {exc!r}")

    def _move_and_wait(
        self,
        position: tuple[float, float, float],
        *,
        timeout_s: float = MOVE_TIMEOUT_S,
    ) -> bool:
        x, y, z = position
        self._stage.move_to(x, y, z)
        deadline = time.time() + timeout_s
        time.sleep(POLL_SLEEP_S)
        while self._stage.is_moving:
            if self._cancel or time.time() > deadline:
                return False
            time.sleep(POLL_SLEEP_S)
        return self._wait_until_position(position, deadline)

    def _wait_until_position(
        self,
        target: tuple[float, float, float],
        deadline: float,
    ) -> bool:
        while not self._cancel and time.time() <= deadline:
            if _distance_um(self._stage.position, target) <= POSITION_TOLERANCE_UM:
                self._sleep_until(time.time() + SETTLE_S)
                return not self._cancel
            time.sleep(POLL_SLEEP_S)
        return False

    def _acquire_average_frame(self) -> np.ndarray:
        if self._params is None:
            raise RuntimeError("ScanParams 未设置")
        sample_count = int(self._params.sample_count)
        if sample_count < 1:
            raise ValueError("平均采样帧数必须 >= 1")
        self._drain_stale_frames()
        dwell_s = max(0.0, float(self._params.dwell_ms) / 1000.0)
        interval_s = dwell_s / max(1, sample_count - 1)
        t0 = time.time()
        accumulator: np.ndarray | None = None
        for sample_idx in range(sample_count):
            if self._cancel:
                raise ScanCanceled()
            frame = self._camera.grab_one()
            data = frame.astype(np.float32, copy=False)
            accumulator = data.copy() if accumulator is None else accumulator + data
            if sample_idx < sample_count - 1:
                self._sleep_until(t0 + interval_s * (sample_idx + 1))
        if accumulator is None:
            raise RuntimeError("未采集到平均帧样本")
        return accumulator / float(sample_count)

    def _correct_frame(self, frame: np.ndarray) -> np.ndarray | None:
        if self._calibration is None or not self._calibration.enabled:
            return None
        return apply_calibration(frame, self._calibration).astype(np.float32, copy=False)

    def _is_sensor_saturated(self, frame: np.ndarray) -> bool:
        return is_sensor_saturated(frame, (1 << int(self._camera.bit_depth())) - 1)

    def _sleep_until(self, deadline: float) -> None:
        while not self._cancel:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            time.sleep(min(POLL_SLEEP_S, remaining))

    def _drain_stale_frames(self) -> None:
        """丢弃移动过程中已排进 SDK 队列的旧 z 位置帧。"""
        for _ in range(WARMUP_FRAMES):
            if self._cancel:
                raise ScanCanceled()
            try:
                self._camera.grab_one(timeout_ms=WARMUP_TIMEOUT_MS)
            except Exception:  # noqa: BLE001
                # 队列已空 / 超时 / mock 不需要 — 都视为已 drain
                return


def _distance_um(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    delta = np.subtract(a, b)
    return float(np.linalg.norm(delta))

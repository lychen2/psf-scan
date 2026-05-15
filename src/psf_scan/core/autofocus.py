"""Autofocus worker — 沿 z 粗扫 + 局部抛物线细化 → 停在最锐 z (C.6)。

安全约束在 app 层组装 (autofocus_max_um × 软限位 × 行程范围 三者交集),
worker 仅接受最终 z 列表 (user 帧), 不再做范围决策。

工作流:
  1. 收到 z 列表 (user 帧) → 依次 move + 多帧平均 + Brenner score
  2. 若峰值不在边界, 用相邻三点拟合抛物线并追加细化采样
  3. 任何阶段可 cancel — 取消后 stage 停在当前位置
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Signal

from .camera import CameraBase
from .sharpness import brenner
from .stage import StageBase


MOVE_TIMEOUT_S = 20.0
POLL_SLEEP_S = 0.005
POSITION_TOLERANCE_UM = 0.05
SETTLE_S = 0.05
REFINE_FRACTION = 0.25
LOW_LIGHT_MEAN_FRACTION = 0.02
LOW_LIGHT_P99_FRACTION = 0.08
LOW_LIGHT_PEAK_FRACTION = 0.20
SATURATED_PEAK_FRACTION = 0.99
DEFAULT_SAMPLE_COUNT = 3


@dataclass
class AutofocusResult:
    z_values: np.ndarray         # 实际访问的 user-frame z (µm)
    scores: np.ndarray           # 对应 Brenner 分数
    best_z: float                # 最锐 z (user 帧)
    best_score: float
    started_at: float
    finished_at: float
    refined: bool
    low_light: bool
    saturated: bool


class AutofocusCanceled(Exception):
    pass


class AutofocusWorker(QObject):
    """单轴 z 粗扫 + 局部抛物线细化 worker。在自己的 QThread 里跑。"""

    # idx_1based, total, z (user), score
    progress = Signal(int, int, float, float)
    # AutofocusResult
    finished = Signal(object)
    canceled = Signal(int)        # 已访问点数
    error = Signal(str)

    def __init__(self, stage: StageBase, camera: CameraBase,
                 z_list: np.ndarray, *, dwell_ms: int = 50,
                 min_step_um: float = 0.4,
                 sample_count: int = DEFAULT_SAMPLE_COUNT) -> None:
        super().__init__()
        if min_step_um <= 0.0:
            raise ValueError("autofocus min_step_um must be > 0")
        if sample_count < 1:
            raise ValueError("autofocus sample_count must be >= 1")
        self._stage = stage
        self._camera = camera
        self._z_list = np.asarray(z_list, dtype=np.float64)
        self._dwell_s = max(0.0, float(dwell_ms) / 1000.0)
        self._min_step_um = float(min_step_um)
        self._sample_count = int(sample_count)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        if self._z_list.size == 0:
            self.error.emit("autofocus: empty z list")
            return
        t0 = time.time()
        z_values: list[float] = []
        scores: list[float] = []
        brightness: list[tuple[float, float, float]] = []
        try:
            self._measure_many(self._z_list, z_values, scores, brightness, total=self._z_list.size)
            refined = self._refine_peak(z_values, scores, brightness)
        except AutofocusCanceled:
            self.canceled.emit(len(z_values))
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"autofocus error: {exc!r}")
            return
        if not z_values:
            self.error.emit("autofocus: no points visited")
            return
        used_z = np.asarray(z_values, dtype=np.float64)
        used_scores = np.asarray(scores, dtype=np.float64)
        best_idx = int(np.argmax(used_scores))
        best_z = float(used_z[best_idx])
        # 最后移回最锐位置 (cancel 检查放在 move_z 内部)
        if not self._move_z(best_z):
            if self._cancel:
                self.canceled.emit(len(z_values))
                return
            self.error.emit("autofocus: failed to settle at peak z")
            return
        low_light = _is_low_light(brightness)
        saturated = _is_saturated(brightness)
        result = AutofocusResult(
            z_values=used_z, scores=used_scores,
            best_z=best_z, best_score=float(used_scores[best_idx]),
            started_at=t0, finished_at=time.time(),
            refined=refined, low_light=low_light, saturated=saturated,
        )
        self.finished.emit(result)

    def _measure_many(
        self,
        z_targets: np.ndarray,
        z_values: list[float],
        scores: list[float],
        brightness: list[tuple[float, float, float]],
        *,
        total: int,
    ) -> None:
        for z in z_targets:
            score, stat = self._measure_one(float(z))
            z_values.append(float(z))
            scores.append(score)
            brightness.append(stat)
            self.progress.emit(len(z_values), total, float(z), score)

    def _measure_one(self, z: float) -> tuple[float, tuple[float, float, float]]:
        if self._cancel:
            raise AutofocusCanceled()
        if not self._move_z(z):
            if self._cancel:
                raise AutofocusCanceled()
            raise RuntimeError(f"move to z={z:.2f} timeout")
        time.sleep(self._dwell_s)
        frame = self._grab_average_frame()
        score = float(brenner(frame))
        return score, _brightness_stats(frame, self._camera.bit_depth())

    def _grab_average_frame(self) -> np.ndarray:
        frames = [np.asarray(self._camera.grab_one(), dtype=np.float32) for _ in range(self._sample_count)]
        return _average_frames(frames)

    def _refine_peak(
        self,
        z_values: list[float],
        scores: list[float],
        brightness: list[tuple[float, float, float]],
    ) -> bool:
        targets = _refine_targets(
            np.asarray(z_values),
            np.asarray(scores),
            min_step_um=self._min_step_um,
        )
        if targets.size == 0:
            return False
        self._measure_many(targets, z_values, scores, brightness, total=len(z_values) + targets.size)
        return True

    def _move_z(self, z_user: float, *, timeout_s: float = MOVE_TIMEOUT_S) -> bool:
        """移到 user 帧 z (x=y=0); 等到位 + settle; cancel 时立即 False。"""
        self._stage.move_to(0.0, 0.0, float(z_user))
        deadline = time.time() + timeout_s
        time.sleep(POLL_SLEEP_S)
        while self._stage.is_moving:
            if self._cancel or time.time() > deadline:
                return False
            time.sleep(POLL_SLEEP_S)
        # tolerance 检查
        while time.time() <= deadline:
            if self._cancel:
                return False
            _x, _y, z_now = self._stage.position
            if abs(z_now - z_user) <= POSITION_TOLERANCE_UM:
                time.sleep(SETTLE_S)
                return not self._cancel
            time.sleep(POLL_SLEEP_S)
        return False


def _refine_targets(z_values: np.ndarray, scores: np.ndarray, *, min_step_um: float = 0.4) -> np.ndarray:
    if z_values.size < 3:
        return np.asarray([], dtype=np.float64)
    order = np.argsort(z_values)
    z_sorted = z_values[order]
    s_sorted = scores[order]
    peak = int(np.argmax(s_sorted))
    if peak == 0 or peak == z_sorted.size - 1:
        return np.asarray([], dtype=np.float64)
    left, center, right = z_sorted[peak - 1], z_sorted[peak], z_sorted[peak + 1]
    vertex = _parabolic_vertex(z_sorted[peak - 1:peak + 2], s_sorted[peak - 1:peak + 2])
    span = min(center - left, right - center)
    fine_step = max(float(min_step_um), span * REFINE_FRACTION)
    refined = np.asarray([vertex - fine_step, vertex, vertex + fine_step], dtype=np.float64)
    return np.clip(refined, left, right)


def _parabolic_vertex(z_values: np.ndarray, scores: np.ndarray) -> float:
    coeff = np.polyfit(z_values, scores, deg=2)
    a, b = float(coeff[0]), float(coeff[1])
    if a >= 0.0:
        return float(z_values[int(np.argmax(scores))])
    return float(np.clip(-b / (2.0 * a), z_values.min(), z_values.max()))


def _brightness_stats(frame: np.ndarray, bit_depth: int) -> tuple[float, float, float]:
    gray = _gray_float(frame)
    scale = float((1 << int(bit_depth)) - 1)
    mean_fraction = float(np.mean(gray) / scale)
    p99_fraction = float(np.percentile(gray, 99.0) / scale)
    peak_fraction = float(np.max(gray) / scale)
    return mean_fraction, p99_fraction, peak_fraction


def _average_frames(frames: list[np.ndarray]) -> np.ndarray:
    if not frames:
        raise ValueError("autofocus average requires at least one frame")
    if len(frames) == 1:
        return frames[0].astype(np.float32, copy=False)
    return np.mean(np.stack(frames, axis=0), axis=0, dtype=np.float32)


def _gray_float(frame: np.ndarray) -> np.ndarray:
    gray = np.asarray(frame, dtype=np.float32)
    if gray.ndim == 3:
        return gray[..., :3].mean(axis=2, dtype=np.float32)
    return np.squeeze(gray).astype(np.float32, copy=False)


def _is_low_light(stats: list[tuple[float, float, float]]) -> bool:
    if not stats:
        return False
    if _is_saturated(stats):
        return False
    means = np.asarray([item[0] for item in stats], dtype=np.float64)
    p99s = np.asarray([item[1] for item in stats], dtype=np.float64)
    peaks = np.asarray([item[2] for item in stats], dtype=np.float64)
    return bool(
        means.max() < LOW_LIGHT_MEAN_FRACTION
        and p99s.max() < LOW_LIGHT_P99_FRACTION
        and peaks.max() < LOW_LIGHT_PEAK_FRACTION
    )


def _is_saturated(stats: list[tuple[float, float, float]]) -> bool:
    if not stats:
        return False
    peaks = np.asarray([item[2] for item in stats], dtype=np.float64)
    return bool(peaks.max() >= SATURATED_PEAK_FRACTION)

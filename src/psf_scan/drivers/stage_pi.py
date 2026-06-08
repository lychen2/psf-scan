"""PI M-531 单轴位移台驱动 (基于 PIPython GCSDevice)。

约定:
- M-531 单轴 → 映射到 z 通道; x/y 始终为 0。
- 整个项目坐标全 µm; 只在调 dev.MOV/qPOS 这一行换算 mm (PI 硬件协议)。
- pipython 用 lazy import: 没装/没硬件时也能让 UI 用 mock 跑起来。
- 链路在 pi_link, 配置在 PIStageConfig, 限位/零点/限速在 TravelGuard。

防撞:
- referencing 默认 'skip'; 连接不机械移动。
- TravelGuard 在 move_to 下命令前 clamp 到 controller 物理边界, 越界拒绝下发。
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Q_ARG, QMetaObject, Qt, QThread, QTimer, Slot
from PySide6.QtWidgets import QApplication

from ..core.stage import StageBase
from . import pi_link
from .pi_link import PIStageConfig
from .pi_travel import TravelGuard

UM_PER_MM = 1000.0


class PIStage(StageBase):
    """PI 单轴位移台 (M-531 + C-863 系列)。"""

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self._cfg: PIStageConfig = PIStageConfig.from_kwargs(**kwargs)
        self._guard = TravelGuard(
            self._cfg.travel_min_um, self._cfg.travel_max_um,
            self._cfg.velocity_max_um_s, self._cfg.invert_z,
        )
        self._dev = None
        self._dcid: Optional[int] = None
        self._axis_id: Optional[str] = None
        self._ctrl_pos_um = 0.0
        self._pos_um = [0.0, 0.0, 0.0]
        self._target_z_um = 0.0
        self._connected = False
        self._moving = False
        self._was_referenced = False
        self._stop_requested = False  # FRF polling 中断用
        self._hw_travel_um: tuple[float, float] = (0.0, 0.0)  # qTMN/qTMX 硬件行程
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / max(1, self._cfg.poll_hz)))
        self._timer.timeout.connect(self._poll)
        self._poll_started_at = time.time()
        self._poll_count = 0
        self._poll_errors = 0
        self._poll_total_ms = 0.0
        self._poll_max_ms = 0.0
        self._poll_last_ms = 0.0

    # ── StageBase API ─────────────────────────────────────
    @property
    def is_connected(self) -> bool: return self._connected
    @property
    def position(self) -> tuple[float, float, float]: return tuple(self._pos_um)
    @property
    def raw_position(self) -> tuple[float, float, float]:
        """物理 controller 坐标 (qPOS 直接读数, 不扣 zero offset)。z=ctrl µm。"""
        return (self._pos_um[0], self._pos_um[1], self._ctrl_pos_um)
    @property
    def is_moving(self) -> bool: return self._moving
    @property
    def was_referenced(self) -> bool: return self._was_referenced
    @property
    def travel_limits_um(self) -> tuple[float, float]: return self._guard.user_travel_um
    @property
    def step_min_um(self) -> float: return self._cfg.step_min_um
    @property
    def hw_travel_um(self) -> tuple[float, float]: return self._hw_travel_um
    @property
    def hw_travel_z_um(self) -> tuple[float, float]:
        """硬件帧 z 行程 = guard 当前 ctrl 软限位 (用户标定写入的物理边界)。"""
        return (float(self._guard.tmin_um), float(self._guard.tmax_um))

    def user_to_hw(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """逆变换: user 帧 → ctrl 帧 (复用 TravelGuard)。"""
        return (float(x), float(y), self._guard.to_ctrl_um(float(z)))

    def connect(self) -> None:
        self._invoke_on_stage_thread("_connect_on_stage_thread")

    @Slot()
    def _connect_on_stage_thread(self) -> None:
        try: from pipython import GCSDevice
        except ImportError as exc:
            self.error.emit(f"未安装 pipython: {exc}"); return
        cfg = self._cfg
        try:
            self._dev = self._make_gcs_device(GCSDevice, cfg.controller)
            actual_iface = pi_link._choose_interface(cfg)
            self._dcid = pi_link.open_link(
                self._dev,
                interface=actual_iface, controller=cfg.controller,
                serialnum=cfg.serialnum, ip=cfg.ip, ipport=cfg.ipport,
                comport=cfg.comport, baudrate=cfg.baudrate, device_id=cfg.device_id,
                serialport=cfg.serialport,
            )
            # 手动初始化: C-863 菊花链模式下 SAI?/AddStage 不可用,
            # 单轴控制器轴固定为 "1"
            self._axis_id = "1"
            # 读硬件行程 (qTMN/qTMX 返回 mm) — 寻参距离估算用
            try:
                tmn = float(self._dev.qTMN(self._axis_id)[self._axis_id]) * UM_PER_MM
                tmx = float(self._dev.qTMX(self._axis_id)[self._axis_id]) * UM_PER_MM
                self._hw_travel_um = (tmn, tmx)
            except Exception: pass  # noqa: BLE001
            self._was_referenced = self._do_reference(cfg)
            if cfg.velocity_um_s and self._dev.HasVEL():
                self._dev.VEL(self._axis_id, cfg.velocity_um_s / UM_PER_MM)
            self._ctrl_pos_um = float(self._dev.qPOS(self._axis_id)[self._axis_id]) * UM_PER_MM
            if not self._was_referenced:
                # FRESH: 未参考时 qPOS 不可信, 当前点 = user 0 + 行程锁到 ±safe_radius
                safe = cfg.safe_radius_um
                self._guard.zero_offset_um = self._ctrl_pos_um
                self._guard.tmin_um, self._guard.tmax_um = self._ctrl_pos_um - safe, self._ctrl_pos_um + safe
            self._pos_um[2] = self._guard.to_user_um(self._ctrl_pos_um)
            self._target_z_um = self._pos_um[2]
            self._connected = True; self._timer.start()
            if not self._was_referenced:
                self.error.emit(f"⚠ 未参考: 当前点 = user 0; 行程 ±{cfg.safe_radius_um:.0f} µm (Reset 可扩大)")
            self.position_changed.emit(*self._pos_um)
        except Exception as exc:  # noqa: BLE001
            self._dev = self._dcid = self._axis_id = None
            self.error.emit(f"PI 连接失败: {self._format_connect_error(exc)}")

    def _format_connect_error(self, exc: Exception) -> str:
        message = str(exc)
        if "PI_GCS2_DLL_x64.dll" in message or "pi_gcs2_dll_x64.dll" in message.lower():
            return (
                f"{message}\n"
                "缺少 PI 官方 GCS2 运行时。请安装 PI Software Suite / GCSTranslator，"
                "或把 PI_GCS2_DLL_x64.dll 放到程序目录后重启。"
            )
        return message

    def _make_gcs_device(self, gcs_device_type, controller: str):
        return pi_link.make_gcs_device(gcs_device_type, controller)

    def disconnect(self) -> None:
        self._invoke_on_stage_thread("_disconnect_on_stage_thread")

    @Slot()
    def _disconnect_on_stage_thread(self) -> None:
        self._timer.stop()
        pi_link.close_link(self._dev, self._dcid)
        self._dev = None; self._dcid = None; self._axis_id = None
        self._connected = False; self._moving = False; self._was_referenced = False

    def move_to(self, x: float, y: float, z: float) -> None:
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_move_to_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(float, float(x)),
                Q_ARG(float, float(y)),
                Q_ARG(float, float(z)),
            )
            return
        self._move_to_on_stage_thread(float(x), float(y), float(z))

    @Slot(float, float, float)
    def _move_to_on_stage_thread(self, x: float, y: float, z: float) -> None:
        if not self._connected or self._dev is None or self._axis_id is None:
            self.error.emit("位移台未连接"); return
        z_ctrl_um = self._guard.to_ctrl_um(float(z))
        if not self._guard.in_range_ctrl(z_ctrl_um):
            self.error.emit(
                f"⛔ 越界: ctrl 目标 {z_ctrl_um:.1f} µm 超出 "
                f"[{self._guard.tmin_um:.0f}, {self._guard.tmax_um:.0f}]"
            ); return
        self._target_z_um = float(z)
        try:
            self._dev.MOV(self._axis_id, z_ctrl_um / UM_PER_MM); self._moving = True
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"MOV 失败: {exc}")

    def home(self) -> None:
        if not self._was_referenced:
            self.error.emit("未参考状态下禁止 home (绝对零点不可信)"); return
        self.move_to(0.0, 0.0, 0.0)

    def stop(self) -> None:
        """急停: 立即停止所有轴 (PI STP 命令)。不破坏连接。也中断 FRF polling。"""
        self._invoke_on_stage_thread("_stop_on_stage_thread")

    @Slot()
    def _stop_on_stage_thread(self) -> None:
        self._stop_requested = True
        if self._dev is None: return
        try: self._dev.STP(noraise=True)
        except Exception as exc: self.error.emit(f"STP 失败: {exc}")  # noqa: BLE001
        self._moving = False

    def set_velocity(self, v_um_per_s: float) -> None:
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_set_velocity_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(float, float(v_um_per_s)),
            )
            return
        self._set_velocity_on_stage_thread(float(v_um_per_s))

    @Slot(float)
    def _set_velocity_on_stage_thread(self, v_um_per_s: float) -> None:
        v, clamped = self._guard.clamp_velocity(v_um_per_s)
        if clamped:
            self.error.emit(f"⚠ 速度被限到 {self._guard.velocity_max_um_s:.0f} µm/s")
        self._cfg.velocity_um_s = v
        if self._dev is None or self._axis_id is None or not self._connected: return
        try:
            if self._dev.HasVEL(): self._dev.VEL(self._axis_id, v / UM_PER_MM)
        except Exception as exc: self.error.emit(f"VEL 失败: {exc}")  # noqa: BLE001

    def set_zero(self) -> None:
        """把当前位置定义为用户视角的 0; 软限位跟随平移 (物理硬限位不变)。"""
        self._invoke_on_stage_thread("_set_zero_on_stage_thread")

    @Slot()
    def _set_zero_on_stage_thread(self) -> None:
        if not self._connected:
            self.error.emit("未连接, 无法置零"); return
        lo, hi = self._zero_internal(None)
        self.error.emit(f"已置零 (ctrl={self._ctrl_pos_um:.1f} µm); 范围 [{lo:.0f}, {hi:.0f}] µm")

    def set_travel_limits_um(self, lo_user_um: float, hi_user_um: float) -> None:
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_set_travel_limits_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(float, float(lo_user_um)),
                Q_ARG(float, float(hi_user_um)),
            )
            return
        self._set_travel_limits_on_stage_thread(float(lo_user_um), float(hi_user_um))

    @Slot(float, float)
    def _set_travel_limits_on_stage_thread(self, lo_user_um: float, hi_user_um: float) -> None:
        """标定写入软限位。lo/hi 是用户视角, 内部换算到 ctrl 坐标系。"""
        lo, hi = sorted((float(lo_user_um), float(hi_user_um)))
        self._guard.tmin_um = self._guard.to_ctrl_um(lo)
        self._guard.tmax_um = self._guard.to_ctrl_um(hi)
        self.error.emit(f"软限位已更新: 用户视角 [{lo:.1f}, {hi:.1f}] µm")

    def set_invert_z(self, on: bool) -> None:
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_set_invert_z_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(bool, bool(on)),
            )
            return
        self._set_invert_z_on_stage_thread(bool(on))

    @Slot(bool)
    def _set_invert_z_on_stage_thread(self, on: bool) -> None:
        """热切换 z 反转。stage 物理不动, user view 数字翻一边 + 软限位 sort 跟随。"""
        self._guard.invert_z = bool(on)
        if self._connected:
            self._pos_um[2] = self._guard.to_user_um(self._ctrl_pos_um)
            self.position_changed.emit(*self._pos_um)

    def reset_range(self, radius_um: float) -> None:
        """以当前 ctrl 位置为 user 0, 行程重设为 ctrl ± radius。stage 物理不动。"""
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_reset_range_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(float, float(radius_um)),
            )
            return
        self._reset_range_on_stage_thread(float(radius_um))

    @Slot(float)
    def _reset_range_on_stage_thread(self, radius_um: float) -> None:
        if not self._connected:
            self.error.emit("未连接, 无法 reset range"); return
        lo, hi = self._zero_internal(abs(float(radius_um)))
        self.error.emit(f"Range 重置: 当前=user 0; 范围 [{lo:.1f}, {hi:.1f}] µm")

    def reference(self, refmode: str = "FRF") -> bool:
        """手动寻参 — 沿用 _do_reference 的限速 + polling, 可被 Esc/Space 中断。"""
        if QThread.currentThread() is not self.thread():
            QMetaObject.invokeMethod(
                self,
                "_reference_on_stage_thread",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, str(refmode)),
            )
            return self._was_referenced
        return self._reference_on_stage_thread(str(refmode))

    @Slot(str)
    def _reference_on_stage_thread(self, refmode: str = "FRF") -> bool:
        if not self._connected or self._dev is None:
            self.error.emit("未连接, 无法寻参"); return False
        from types import SimpleNamespace
        args = SimpleNamespace(
            refmode=str(refmode).upper(),
            referencing="force",
            velocity_max_um_s=self._cfg.velocity_max_um_s,
        )
        ok = self._do_reference(args)
        if ok:
            try:
                self._ctrl_pos_um = float(self._dev.qPOS(self._axis_id)[self._axis_id]) * UM_PER_MM
                self._pos_um[2] = self._guard.to_user_um(self._ctrl_pos_um)
                self.position_changed.emit(*self._pos_um)
                self.error.emit(f"✓ {args.refmode} 完成, ctrl 当前 {self._ctrl_pos_um:.1f} µm")
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"寻参后读位置失败: {exc}")
        self._was_referenced = ok
        return ok

    def _invoke_on_stage_thread(self, method_name: str) -> None:
        if QThread.currentThread() is self.thread():
            getattr(self, method_name)()
            return
        QMetaObject.invokeMethod(
            self,
            method_name,
            Qt.ConnectionType.BlockingQueuedConnection,
        )

    def _zero_internal(self, radius_um: Optional[float]) -> tuple[float, float]:
        """共享: STP + zero_offset 重设 + 可选重写行程; 返回 user_travel (lo, hi)。"""
        try: self._dev.STP(noraise=True)
        except Exception: pass  # noqa: BLE001
        self._moving = False
        self._guard.set_zero(self._ctrl_pos_um)
        if radius_um is not None:
            self._guard.tmin_um = self._ctrl_pos_um - radius_um
            self._guard.tmax_um = self._ctrl_pos_um + radius_um
        self._pos_um[2] = 0.0; self._target_z_um = 0.0
        self.position_changed.emit(*self._pos_um)
        return self._guard.user_travel_um

    def _do_reference(self, cfg) -> bool:
        """内联 reference 实现 — 限速 + polling (替代 pi_link.reference_if_needed 阻塞)。

        - referencing=skip: 仅 qFRF 报告状态, 不机械寻参
        - auto + 已对零: 跳过
        - 否则: 限速到 vmax → 调 FRF/FNL/FPL → polling qONT (processEvents 让 Esc 生效)
        """
        try: already = bool(self._dev.qFRF(self._axis_id)[self._axis_id])
        except Exception: already = False  # noqa: BLE001
        if cfg.referencing == "skip": return already
        if cfg.referencing == "auto" and already: return True
        if cfg.velocity_max_um_s and self._dev.HasVEL():
            try: self._dev.VEL(self._axis_id, cfg.velocity_max_um_s / UM_PER_MM)
            except Exception: pass  # noqa: BLE001
        mode = cfg.refmode.upper() if cfg.refmode.upper() in ("FRF", "FNL", "FPL") else "FRF"
        self._stop_requested = False
        try: getattr(self._dev, mode)(self._axis_id)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{mode} 启动失败: {exc}"); return False
        while True:
            if self._stop_requested:
                try: self._dev.STP(noraise=True)
                except Exception: pass  # noqa: BLE001
                self.error.emit(f"⛔ {mode} 被急停中断, stage 未对零")
                return False
            try: ont = bool(self._dev.qONT(self._axis_id)[self._axis_id])
            except Exception: ont = False  # noqa: BLE001
            if ont: return True
            QApplication.processEvents()
            time.sleep(0.05)

    @Slot()
    def _poll(self) -> None:
        if self._dev is None or self._axis_id is None or not self._connected: return
        started = time.perf_counter()
        ok = False
        try:
            ctrl_pos_um = float(self._dev.qPOS(self._axis_id)[self._axis_id]) * UM_PER_MM
            pos_z_um = self._guard.to_user_um(ctrl_pos_um)
            was_moving = self._moving
            if was_moving:
                try: ont = bool(self._dev.qONT(self._axis_id)[self._axis_id])
                except Exception:  # noqa: BLE001
                    target_ctrl_um = self._guard.to_ctrl_um(self._target_z_um)
                    ont = abs(ctrl_pos_um - target_ctrl_um) < self._cfg.position_tolerance_um
            else:
                ont = True
            changed = abs(pos_z_um - self._pos_um[2]) >= self._cfg.position_tolerance_um
            self._ctrl_pos_um = ctrl_pos_um
            self._pos_um[2] = pos_z_um
            self._moving = not ont
            if changed or was_moving != self._moving:
                self.position_changed.emit(*self._pos_um)
            if was_moving and not self._moving: self.move_finished.emit()
            ok = True
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"位移台读取失败: {exc}"); self._timer.stop()
        finally:
            self._record_poll((time.perf_counter() - started) * 1000.0, ok)

    def diagnostics(self) -> dict[str, object]:
        elapsed = max(1e-6, time.time() - self._poll_started_at)
        avg_ms = self._poll_total_ms / max(1, self._poll_count)
        return {
            "connected": self._connected,
            "moving": self._moving,
            "poll_hz_cfg": self._cfg.poll_hz,
            "poll_hz_actual": round(self._poll_count / elapsed, 2),
            "poll_count": self._poll_count,
            "poll_errors": self._poll_errors,
            "poll_last_ms": round(self._poll_last_ms, 2),
            "poll_avg_ms": round(avg_ms, 2),
            "poll_max_ms": round(self._poll_max_ms, 2),
            "timer_active": self._timer.isActive(),
        }

    def _record_poll(self, elapsed_ms: float, ok: bool) -> None:
        self._poll_count += 1
        self._poll_last_ms = elapsed_ms
        self._poll_total_ms += elapsed_ms
        self._poll_max_ms = max(self._poll_max_ms, elapsed_ms)
        if not ok:
            self._poll_errors += 1

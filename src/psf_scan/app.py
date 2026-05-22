"""主窗口 — 浅色科研绘图工作台版本。

布局：顶部 tab 栏（含标题）+ HSplitter(主视图 | stage 视图) + 控件面板 + 状态栏。
"""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Optional

from PySide6.QtCore import Qt, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QMainWindow, QMessageBox, QSplitter, QStatusBar,
    QTabWidget, QVBoxLayout, QWidget,
)

from .core.camera import AVAILABLE_CAMERAS, CameraBase, make_camera
from .core.calibration import (
    CalibrationConfig,
    apply_calibration,
    calibrated_white_level,
    config_from_settings,
    SENSOR_SATURATION_FRACTION,
    validate_config,
)
from .core.data_io import (
    StreamingScanWriter, finalize_streamed_scan, find_orphan_scans, save_scan,
)
from .core.diagnostics import format_kv, process_snapshot
from .core.i18n import set_language, tr
from .core.autofocus import AutofocusResult, AutofocusWorker
from .core.pixel_calibration import from_settings as pixel_calibration_from_settings
from .core.scanner import ScanMetadata, ScanParams, ScanResult, Scanner
from .core.snapshot import VideoRecorder, save_snapshot
from .core.stage import AVAILABLE_STAGES, StageBase, make_stage
from .ui import theme
from .ui.about_dialog import AboutDialog
from .ui.camera_view import CameraView
from .ui.control_panel import ControlPanel
from .ui.pi_connect_dialog import PIConnectDialog
from .ui.phase_view import PhaseView
from .ui.psf_view import PSFView
from .ui.settings import UserSettings
from .ui.settings_dialog import SettingsDialog
from .ui.stage_view import StageView
from .ui.stage_jog_panel import StageJogPanel
from .ui.status_strip import (
    STATE_ERROR, STATE_IDLE, STATE_ONLINE, STATE_SAVED, STATE_SCANNING, StatusStrip,
)

_log = logging.getLogger(__name__)


class _SaveWorker(QObject):
    """Off-main-thread finalize caller. UI fallback decisions stay on main thread."""

    done = Signal(object)      # Path
    failed = Signal(str)       # exception text

    def __init__(self, target_dir: Path, result: ScanResult,
                 name: str | None = None,
                 *, streamed: bool = False) -> None:
        super().__init__()
        self._target_dir = target_dir
        self._result = result
        self._name = name
        self._streamed = streamed

    @Slot()
    def run(self) -> None:
        try:
            if self._streamed:
                # streaming 模式: stack.h5 已经在 target_dir 里 (writer 写的), 这里只补 tif/mat/csv/meta
                target = finalize_streamed_scan(self._target_dir, self._result)
            else:
                target = save_scan(self._target_dir, self._result, name=self._name)
            self.done.emit(target)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("psf scan")
        self.setMinimumSize(1100, 720)

        self._stage: Optional[StageBase] = None
        self._camera: Optional[CameraBase] = None
        self._scanner: Optional[Scanner] = None
        self._scan_thread: Optional[QThread] = None
        self._save_thread: Optional[QThread] = None
        self._stage_thread: Optional[QThread] = None
        self._save_worker: Optional[_SaveWorker] = None
        self._af_thread: Optional[QThread] = None
        self._af_worker: Optional[AutofocusWorker] = None
        self._af_dialog = None  # AutofocusDialog (延迟构造)
        self._scan_writer: Optional[StreamingScanWriter] = None  # streaming HDF5 (C.4)
        self._calibration_config: CalibrationConfig | None = None
        self._scan_pixel_calibration: dict | None = None
        self._scan_metadata: ScanMetadata = ScanMetadata()
        self._settings = UserSettings()
        self._recorder = VideoRecorder()
        # 时间序列扫描状态机 (C.5)
        self._repeat_total: int = 0     # 0 表示当前没有时间序列在跑
        self._repeat_done: int = 0      # 已完成几次
        self._repeat_interval_s: float = 0.0
        self._repeat_base_name: str = ""
        self._repeat_params: Optional[ScanParams] = None
        self._diagnostic_timer = QTimer(self)
        self._diagnostic_timer.setInterval(5000)
        self._diagnostic_timer.timeout.connect(self._log_diagnostics)
        # 应用启动时确定语言
        set_language(self._settings.language())
        self._axis_signs = self._compute_axis_signs()

        self.cam_view = CameraView()
        self.stage_view = StageView()
        self.control = ControlPanel()
        self.stage_jog = self.control.stage_jog
        self.psf_view = PSFView()
        self.phase_view = PhaseView(live_frame_provider=self.cam_view.current_raw_frame)
        self.status_strip = StatusStrip(AVAILABLE_STAGES, AVAILABLE_CAMERAS)

        self._tabs = self._build_tabs()
        self.setCentralWidget(self._build_shell())

        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.hide()
        self._idle_status = "ready · connect devices"
        bar.showMessage(self._idle_status)
        self._build_menubar()
        self._bind_settings()
        self._wire_signals()
        self._diagnostic_timer.start()
        self.stage_view.set_safety_limits(self._settings.safety_limits())
        self._refresh_data_dir_label()
        # 启动时检测中途崩溃留下的未收尾 stack.h5 (C.4 恢复)
        QTimer.singleShot(0, self._check_orphan_scans)

    def _check_orphan_scans(self) -> None:
        """扫 data_dir 找有 stack.h5 但没 meta.json 的目录, 提示用户."""
        try:
            orphans = find_orphan_scans(self._settings.data_dir())
        except Exception:  # noqa: BLE001
            return
        if not orphans:
            return
        names = "\n  · ".join(o.name for o in orphans[:10])
        more = f"\n  · ... 还有 {len(orphans)-10} 个" if len(orphans) > 10 else ""
        QMessageBox.information(
            self, tr("recovery.title"),
            tr("recovery.found", n=len(orphans)) + f"\n\n  · {names}{more}\n\n" + tr("recovery.hint"),
        )

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()
        self._tabs.addTab(self.cam_view, "LIVE IMAGE")
        self._tabs.addTab(self.psf_view, "PSF STACK")
        self._tabs.addTab(self.phase_view, "PHASE")
        return self._tabs

    def _build_menubar(self) -> None:
        menu = self.menuBar()
        tools = menu.addMenu(tr("menu.tools"))
        act_settings = tools.addAction(tr("menu.settings"))
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self._on_settings)
        act_data = tools.addAction(tr("menu.open_data_dir"))
        act_data.triggered.connect(self._on_open_data_dir)
        help_menu = menu.addMenu(tr("about.help_menu"))
        act_about = help_menu.addAction(tr("about.menu"))
        act_about.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _build_shell(self) -> QWidget:
        main_content = QSplitter(Qt.Horizontal)
        main_content.addWidget(self._tabs)

        right_panel = QSplitter(Qt.Vertical)
        right_panel.addWidget(self.stage_view)
        right_panel.addWidget(self.control)
        right_panel.setSizes([100, 900])
        right_panel.setHandleWidth(1)

        # 右侧容器顶部留出与左侧 tab bar 等高的内边距, 让 stage_view 顶部对齐到
        # 第一个 tab 的内容顶。读取 sizeHint 而非硬编码,避免字号/QSS 改动后失准。
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        tab_bar_h = self._tabs.tabBar().sizeHint().height()
        right_layout.setContentsMargins(0, tab_bar_h, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(right_panel)

        main_content.addWidget(right_container)
        main_content.setSizes([800, 300])
        main_content.setHandleWidth(1)

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.status_strip)
        shell_layout.addWidget(main_content, stretch=1)
        return shell

    def _compute_axis_signs(self) -> tuple[int, int, int]:
        ix, iy, iz = self._settings.axis_inversion()
        return (-1 if ix else 1, -1 if iy else 1, -1 if iz else 1)

    def _device_summary(self, stage: StageBase, stage_kind: str, camera: CameraBase) -> str:
        """连接成功后给用户看的一行摘要 — PI 列出 ctrl@iface · stage · ref · range, 其余走 fallback。"""
        cfg = getattr(stage, "_cfg", None)
        if cfg is None:
            return f"{stage_kind} stage · {camera.description}"
        iface_lbl = self._pi_interface_label(cfg)
        ref_lbl = "referenced ✓" if getattr(stage, "was_referenced", False) else "fresh (no ref)"
        try:
            lo, hi = stage.travel_limits_um  # type: ignore[attr-defined]
            range_lbl = f"range [{lo:.0f}, {hi:.0f}] µm"
        except Exception:  # noqa: BLE001
            range_lbl = "range —"
        return (
            f"{cfg.controller} @ {iface_lbl} · {cfg.stage} · {ref_lbl} · {range_lbl}"
            f"  ·  {camera.description}"
        )

    @staticmethod
    def _pi_interface_label(cfg) -> str:
        iface = (cfg.interface or "usb").lower()
        if iface == "usb":
            sn = (cfg.serialnum or "").strip()
            return f"USB {sn}" if sn else "USB"
        if iface == "tcp":
            return f"TCP {cfg.ip}:{cfg.ipport}" if cfg.ip else "TCP"
        if iface == "rs232":
            return f"COM{cfg.comport}@{cfg.baudrate}" if cfg.comport else "RS232"
        if iface == "rs232-daisy":
            return f"COM{cfg.comport}@{cfg.baudrate} #{cfg.device_id}"
        if iface == "usb-daisy":
            return f"USB daisy #{cfg.device_id}"
        return iface

    def _wire_signals(self) -> None:
        self.status_strip.connect_requested.connect(self._on_connect)
        self.status_strip.disconnect_requested.connect(self._on_disconnect)
        self.status_strip.pi_settings_requested.connect(self._on_pi_settings)
        self.status_strip.stage_kind_changed.connect(self.control.set_single_axis)
        self.control.move_requested.connect(self._on_move)
        self.control.home_requested.connect(self._on_home)
        self.control.autofocus_requested.connect(self._on_autofocus_start)
        self.control.scan_started.connect(self._on_scan_start)
        self.control.scan_canceled.connect(self._on_scan_cancel)
        self.control.single_axis_changed.connect(self.stage_view.set_single_axis)
        self.stage_jog.stop_requested.connect(self._on_emergency_stop)
        self.stage_jog.set_zero_requested.connect(self._on_set_zero)
        self.stage_jog.jog_requested.connect(self._on_jog)
        self.stage_jog.apply_limits_requested.connect(self._on_apply_limits)
        self.stage_jog.reset_range_requested.connect(self._on_reset_range)
        self.cam_view.metrics_changed.connect(self.status_strip.set_camera)
        self.cam_view.exposure_changed.connect(self._on_exposure_changed)
        self.cam_view.gain_changed.connect(self._on_gain_changed)
        self.cam_view.gamma_changed.connect(self._on_gamma_changed)
        self.cam_view.black_level_changed.connect(self._on_black_level_changed)
        self.cam_view.frame_rate_changed.connect(self._on_frame_rate_changed)
        self.cam_view.pixel_format_changed.connect(self._on_pixel_format_changed)
        self.cam_view.snapshot_requested.connect(self._on_snapshot)
        self.cam_view.record_toggled.connect(self._on_record_toggled)
        self.psf_view.export_plot_requested.connect(self._on_export_plot)
        self.status_strip.settings_requested.connect(self._on_settings)

    def _bind_settings(self) -> None:
        self.control.bind_settings(self._settings)
        self.status_strip.bind_device_combos(self._settings)
        self.psf_view.bind_settings(self._settings)
        self.cam_view.bind_settings(self._settings)
        self.phase_view.bind_settings(self._settings)

    # ── connection ────────────────────────────────
    def _stage_kwargs(self, stage_kind: str) -> Optional[dict]:
        """连接永远 skip 寻参 (不动机械)。寻参改为 jog panel 上的手动按钮触发。"""
        if stage_kind.lower() not in {"pi-m531", "pi", "m531"}:
            return {}
        params = self._settings.pi_params()
        params["referencing"] = "skip"  # 强制 skip — 连接不寻参, fresh calibration
        return params

    @Slot()
    def _on_pi_settings(self) -> None:
        dlg = PIConnectDialog(self._settings.pi_params(), parent=self)
        if dlg.exec() == PIConnectDialog.DialogCode.Accepted:
            self._settings.set_pi_params(dlg.values())
            self.statusBar().showMessage("PI 连接参数已保存", 4000)

    @Slot()
    def _on_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self, camera=self._camera)
        dlg.reference_clicked.connect(self._on_reference)
        dlg.exec()
        self._axis_signs = self._compute_axis_signs()
        self.cam_view.set_gamma_enabled(self._settings.gamma_enabled())
        self.cam_view.refresh_pixel_calibration_status()
        self._refresh_calibration_config(show_errors=True)
        # 如果之前因为校正失败陷在 STATE_ERROR (例如帧尺寸不匹配),
        # 用户改完设置回来时若相机仍在连接, 把面板恢复回 ONLINE,
        # 否则连接 / 断开入口都会被错误面板挡掉。
        if self._camera is not None and self.status_strip.state() == STATE_ERROR:
            device_text = self._device_summary(self._stage, self._settings.value("devices/stage_driver", ""), self._camera)
            self.status_strip.set_state(STATE_ONLINE, tr("status.online"))
            self.status_strip.set_message(device_text)
        self.stage_view.set_safety_limits(self._settings.safety_limits())
        self.control.set_autofocus_allowed(self._settings.autofocus_enabled())
        # 热应用 invert_z 到当前 driver — 翻转后立即生效, 不必重连
        if self._stage is not None:
            _ix, _iy, iz = self._settings.axis_inversion()
            self._stage.set_invert_z(bool(iz))
            try:
                lo, hi = self._stage.travel_limits_um
                self.stage_jog.set_travel_range_um(lo, hi)
            except Exception:  # noqa: BLE001
                pass

    @Slot(str, str)
    def _on_connect(self, stage_kind: str, cam_kind: str) -> None:
        _log.info("connect requested stage=%s camera=%s", stage_kind, cam_kind)
        stage_kwargs = self._stage_kwargs(stage_kind)
        if stage_kwargs is None:
            return  # 用户取消 FRF 警告
        # 把 axis_inversion[2] (反转 Z) 注入 driver — invert 是 driver 内部职责
        _ix, _iy, iz = self._settings.axis_inversion()
        stage_kwargs["invert_z"] = bool(iz)
        try:
            stage = make_stage(stage_kind, **stage_kwargs)
            kw = {"stage": stage} if cam_kind == "mock" else {}
            camera = make_camera(cam_kind, **kw)
        except Exception as exc:  # noqa: BLE001
            _log.exception("make_stage/make_camera failed (stage=%s camera=%s)", stage_kind, cam_kind)
            QMessageBox.critical(self, "连接失败", str(exc))
            return
        self._start_stage_thread(stage_kind, stage)

        stage.position_changed.connect(self.stage_view.set_position)
        stage.position_changed.connect(self._on_position)
        stage.position_changed.connect(self.stage_jog.update_position)
        stage.error.connect(self._show_error)
        camera.frame_ready.connect(self._on_camera_frame)
        self._wire_preview_backpressure(camera)
        camera.error.connect(self._show_error)

        try:
            stage.connect()
        except Exception as exc:  # noqa: BLE001
            _log.exception("stage.connect failed")
            QMessageBox.critical(self, "启动失败", f"位移台连接失败:\n{exc}")
            self._stop_stage_thread()
            return
        if not stage.is_connected:
            QMessageBox.critical(self, "启动失败", "位移台连接失败。")
            self._stop_stage_thread()
            return
        try:
            camera.connect()
        except Exception as exc:  # noqa: BLE001
            _log.exception("camera.connect failed")
            QMessageBox.critical(self, "启动失败", f"相机连接失败:\n{exc}")
            try:
                stage.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._stop_stage_thread()
            return
        try:
            self._restore_camera_settings(camera)
        except Exception as exc:  # noqa: BLE001
            _log.warning("restore camera settings failed: %s", exc)
        # 校正配置失败不阻断连接: 跑无校正模式, 警告用户后续可改设置
        try:
            cfg = config_from_settings(self._settings, camera)
            cfg = self._engage_hardware_dark(cfg, camera=camera)
            validate_config(cfg, camera)
            self._calibration_config = cfg
        except Exception as exc:  # noqa: BLE001
            _log.warning("calibration config failed (running without correction): %s", exc)
            self._calibration_config = None
            QMessageBox.warning(
                self, tr("settings.title"),
                f"校正配置不可用,本次连接以无校正模式继续。\n\n{exc}\n\n"
                "可在 ⚙ 设置 → 校正 中修改或关闭校正后保留连接状态。",
            )
        try:
            camera.start_streaming()
        except Exception as exc:  # noqa: BLE001
            _log.exception("camera.start_streaming failed")
            QMessageBox.critical(self, "启动失败", f"相机出帧启动失败:\n{exc}")
            try:
                camera.disconnect()
            except Exception:  # noqa: BLE001
                pass
            try:
                stage.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._stop_stage_thread()
            return

        # jog panel 同步当前 stage 限位/速度/步长
        try:
            lo, hi = stage.travel_limits_um
            self.stage_jog.set_travel_range_um(lo, hi)
        except Exception:  # noqa: BLE001
            pass
        if hasattr(stage, "_cfg"):
            self.stage_jog.set_step_min(stage._cfg.step_min_um)
        self.stage_jog.set_enabled(True)

        # 同步曝光/增益到 UI 并接信号
        exp_range = camera.exposure_range()
        gain_range = camera.gain_range()
        self.cam_view.configure_camera(
            exposure_us=camera.get_exposure_us(),
            gain=camera.get_gain(),
            exp_range=exp_range,
            gain_range=gain_range,
            max_val=(1 << camera.bit_depth()) - 1,
        )
        self.cam_view.configure_advanced(camera)
        self.cam_view.set_gamma_enabled(self._settings.gamma_enabled())
        self._stage, self._camera = stage, camera
        self.control.set_connected(True)
        self.control.set_autofocus_allowed(self._settings.autofocus_enabled())
        device_text = self._device_summary(stage, stage_kind, camera)
        self.status_strip.set_state(STATE_ONLINE, tr("status.online"))
        self.status_strip.set_device_label(device_text)
        self.status_strip.set_message(device_text)
        self.statusBar().showMessage(f"connected · {device_text}", 5000)

    def _start_stage_thread(self, stage_kind: str, stage: StageBase) -> None:
        if stage_kind.lower() not in {"pi-m531", "pi", "m531"}:
            return
        self._stop_stage_thread()
        thread = QThread(self)
        thread.setObjectName("PIStageIO")
        stage.moveToThread(thread)
        thread.start()
        self._stage_thread = thread

    def _stop_stage_thread(self) -> None:
        thread = self._stage_thread
        if thread is None:
            return
        thread.quit()
        if not thread.wait(2000):
            _log.warning("PI stage IO thread did not stop within 2s")
        self._stage_thread = None

    def _restore_camera_settings(self, camera: CameraBase) -> None:
        exposure_us = self._settings.value_int("camera/exposure_us", camera.get_exposure_us())
        gain = self._settings.value_float("camera/gain", camera.get_gain())
        camera.set_exposure_us(exposure_us)
        camera.set_gain(gain)
        current_fps = camera.get_frame_rate()
        if current_fps is not None:
            fps = self._settings.value_float("camera/frame_rate_fps", current_fps)
            camera.set_frame_rate(fps)

    def _wire_preview_backpressure(self, camera: CameraBase) -> None:
        done = getattr(camera, "mark_preview_delivered", None)
        if done is not None:
            self.cam_view.frame_displayed.connect(done)

    def _unwire_preview_backpressure(self, camera: CameraBase) -> None:
        done = getattr(camera, "mark_preview_delivered", None)
        if done is None:
            return
        try:
            self.cam_view.frame_displayed.disconnect(done)
        except (RuntimeError, TypeError):
            pass

    @Slot(object, float)
    def _on_camera_frame(self, frame, ts: float) -> None:
        raw_peak = int(frame.max())
        shown = self._apply_calibration_for_preview(frame)
        self.cam_view.update_frame(
            shown,
            ts,
            saturated=self._is_peak_saturated(raw_peak),
            display_white_level=self._preview_white_level(),
            peak=raw_peak if shown is frame else None,
        )

    def _apply_calibration_for_preview(self, frame):
        config = self._calibration_config
        if config is None or not config.enabled:
            return frame
        try:
            return apply_calibration(frame, config)
        except Exception as exc:  # noqa: BLE001
            # 校正失败是软可恢复的 — 把软件配置自缴, 让相机继续出原始帧,
            # 不要切到 STATE_ERROR 面板 (会把 connect/disconnect 入口隐藏,
            # 用户改完设置后回不到 ONLINE)。只在 info_line 上闪一条提示。
            self._calibration_config = None
            try:
                self._camera.disable_hardware_dark() if self._camera else None
            except Exception:  # noqa: BLE001
                pass
            _log.warning("calibration disabled at runtime: %s", exc)
            self.status_strip.set_message(tr("calibration.failed", msg=str(exc)))
            self.statusBar().showMessage(f"calibration · {exc}", 6000)
            return frame

    def _is_peak_saturated(self, peak: int) -> bool:
        return float(peak) >= float(self.cam_view.max_value()) * SENSOR_SATURATION_FRACTION

    def _preview_white_level(self) -> float:
        return calibrated_white_level(
            self.cam_view.max_value(),
            self._calibration_config,
        )

    def _refresh_calibration_config(self, *, show_errors: bool) -> bool:
        if self._camera is None:
            self._calibration_config = None
            return True
        try:
            cfg = config_from_settings(self._settings, self._camera)
            cfg = self._engage_hardware_dark(cfg)
            validate_config(cfg, self._camera)
        except Exception as exc:  # noqa: BLE001
            self._calibration_config = None
            # 软件路径失败也要把硬件路径关掉, 避免相机被遗留在 NUCEnable=True
            try:
                self._camera.disable_hardware_dark()
            except Exception:  # noqa: BLE001
                pass
            if show_errors:
                QMessageBox.warning(self, tr("common.error"), tr("calibration.failed", msg=str(exc)))
            return False
        self._calibration_config = cfg
        return True

    def _engage_hardware_dark(
        self, cfg: CalibrationConfig, *, camera: CameraBase | None = None
    ) -> CalibrationConfig:
        """根据配置在相机端开/关硬件暗场, 把结果回填到 frozen 配置.

        camera 显式传入用于 ``_on_connect`` 流程中 ``self._camera`` 尚未赋值的场景."""
        from dataclasses import replace
        cam = camera if camera is not None else self._camera
        if cam is None:
            return cfg
        if not cfg.dark_enabled:
            try:
                cam.disable_hardware_dark()
            except Exception:  # noqa: BLE001
                pass
            return replace(cfg, hardware_dark_active=False, hardware_dark_node=None)
        try:
            active = bool(cam.try_enable_hardware_dark())
        except Exception:  # noqa: BLE001
            active = False
        node = cam.hardware_dark_node if active else None
        if active:
            _log.info("hardware dark-field engaged via SDK node %s", node)
        else:
            _log.info("hardware dark-field unavailable; software subtraction path active")
        return replace(cfg, hardware_dark_active=active, hardware_dark_node=node)

    @Slot(int)
    def _on_exposure_changed(self, exposure_us: int) -> None:
        if not self._camera:
            return  # 相机已断 (例如关窗口期间, spinbox 收尾触发) — 安全忽略
        self._camera.set_exposure_us(exposure_us)
        self._settings.set_value("camera/exposure_us", exposure_us)

    @Slot(float)
    def _on_gain_changed(self, gain: float) -> None:
        if not self._camera:
            return
        self._camera.set_gain(gain)
        self._settings.set_value("camera/gain", gain)

    @Slot(float)
    def _on_gamma_changed(self, gamma: float) -> None:
        if self._camera:
            self._camera.set_gamma(gamma)

    @Slot(int)
    def _on_black_level_changed(self, level: int) -> None:
        if self._camera:
            self._camera.set_black_level(level)

    @Slot(float)
    def _on_frame_rate_changed(self, fps: float) -> None:
        if not self._camera:
            return
        self._camera.set_frame_rate(fps)
        self._settings.set_value("camera/frame_rate_fps", fps)

    @Slot(str)
    def _on_pixel_format_changed(self, fmt: str) -> None:
        if self._camera:
            self._camera.set_pixel_format(fmt)

    @Slot()
    def _on_disconnect(self) -> None:
        if self._recorder.is_recording:
            self.cam_view.set_recording_state(False)
        if self._camera:
            try:
                self._camera.disable_hardware_dark()
            except Exception:  # noqa: BLE001
                pass
            self._unwire_preview_backpressure(self._camera)
            self._camera.disconnect()
            self._camera = None
        self._calibration_config = None
        if self._stage:
            try:
                self._stage.disconnect()
            finally:
                self._stage = None
                self._stop_stage_thread()
        self.stage_jog.set_enabled(False)
        self.control.set_connected(False)
        self.cam_view.reset(); self.stage_view.clear_path()
        self.status_strip.set_state(STATE_IDLE, tr("status.offline"))
        self.status_strip.set_progress_idle()
        self.status_strip.reset_camera()
        self.status_strip.set_message("connect devices")
        self.statusBar().showMessage(self._idle_status)

    # ── manual ────────────────────────────────────
    def _check_start_state(self) -> bool:
        """起始状态体检 — 当前 stage 是否落在软限位 + 行程范围里。
        核心原则: 不太对劲就不动。任何一项越界都拒绝接下来的移动。
        """
        stage = self._stage
        if stage is None:
            return False
        hw_now = stage.raw_position
        limits = self._settings.safety_limits()
        hit = limits.check_point(*hw_now)
        if hit:
            axis, value, lo, hi = hit
            QMessageBox.warning(self, tr("common.warning"),
                tr("safety.start_illegal_limits", axis=axis, value=value, lo=lo, hi=hi))
            return False
        lo_z, hi_z = stage.hw_travel_z_um
        if not (lo_z <= hw_now[2] <= hi_z):
            QMessageBox.warning(self, tr("common.warning"),
                tr("safety.start_illegal_range", value=hw_now[2], lo=lo_z, hi=hi_z))
            return False
        return True

    def _check_target(self, x: float, y: float, z: float) -> bool:
        """目标点体检 — user→hw 后过软限位 + 行程范围两道关。"""
        if not self._is_target_safe(x, y, z, show_msg=True):
            return False
        return True

    def _is_target_safe(self, x: float, y: float, z: float,
                        *, show_msg: bool = False) -> bool:
        """无弹窗变体 (autofocus 候选过滤用) — 返回 True 表示通过双道检查."""
        stage = self._stage
        if stage is None:
            return False
        hx, hy, hz = stage.user_to_hw(x, y, z)
        hit = self._settings.safety_limits().check_point(hx, hy, hz)
        if hit:
            if show_msg:
                axis, value, lo, hi = hit
                QMessageBox.warning(self, tr("common.warning"),
                    tr("safety.move_refused", axis=axis, value=value, lo=lo, hi=hi))
            return False
        lo_z, hi_z = stage.hw_travel_z_um
        if not (lo_z <= hz <= hi_z):
            if show_msg:
                QMessageBox.warning(self, tr("common.warning"),
                    tr("safety.range_refused", value=hz, lo=lo_z, hi=hi_z))
            return False
        return True

    def _check_path(self, path) -> bool:
        """扫描路径体检 — 整条 user 路径换 hw 后过软限位 + 行程范围。"""
        import numpy as _np
        stage = self._stage
        if stage is None:
            return False
        hw_pts = _np.array([stage.user_to_hw(*p) for p in path], dtype=float)
        hit = self._settings.safety_limits().check_path(hw_pts)
        if hit:
            axis, value, lo, hi = hit
            QMessageBox.warning(self, tr("common.warning"),
                tr("safety.scan_refused", axis=axis, value=value, lo=lo, hi=hi))
            return False
        lo_z, hi_z = stage.hw_travel_z_um
        zmin = float(hw_pts[:, 2].min())
        zmax = float(hw_pts[:, 2].max())
        if zmin < lo_z:
            QMessageBox.warning(self, tr("common.warning"),
                tr("safety.range_refused", value=zmin, lo=lo_z, hi=hi_z))
            return False
        if zmax > hi_z:
            QMessageBox.warning(self, tr("common.warning"),
                tr("safety.range_refused", value=zmax, lo=lo_z, hi=hi_z))
            return False
        return True

    @Slot(float, float, float)
    def _on_move(self, x, y, z):
        if not self._stage:
            return
        if not self._check_start_state():
            return
        if not self._check_target(x, y, z):
            return
        if not self._confirm_large_move(z):
            return
        # invert 是 driver/硬件层的职责, GUI 永远使用用户视角坐标
        self._stage.move_to(x, y, z)

    @Slot()
    def _on_home(self): self._stage and self._stage.home()

    @Slot(float)
    def _on_jog(self, delta_um: float) -> None:
        """相对移动: 当前 z + delta。受 driver TravelGuard clamp。"""
        if not self._stage:
            return
        if not self._check_start_state():
            return
        _x, _y, z = self._stage.position
        target = z + float(delta_um)
        if not self._check_target(0.0, 0.0, target):
            return
        if not self._confirm_large_move(target):
            return
        self._stage.move_to(0.0, 0.0, target)

    def _confirm_large_move(self, target_z_um: float) -> bool:
        """单次 z 移动 >= safety/large_move_um 时弹框确认。返回 True = 允许下发。

        防撞兜底: 默认 1mm, 用户在 设置→位移台→大幅移动阈值 调整。
        """
        if not self._stage:
            return True
        threshold = self._settings.large_move_um()
        _x, _y, z_now = self._stage.position
        delta = abs(float(target_z_um) - z_now)
        if delta < threshold:
            return True
        ret = QMessageBox.question(
            self, "⚠ 大幅移动确认",
            f"即将移动 {delta:.1f} µm (阈值 {threshold:.0f} µm)\n\n"
            f"当前 z = {z_now:+.2f} µm\n"
            f"目标 z = {target_z_um:+.2f} µm\n\n"
            "确认平台周围无样品架/镜筒/手指?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    @Slot()
    def _on_emergency_stop(self) -> None:
        """急停: 取消扫描 + autofocus → 停 stage。任何时候都安全 (即使未连接)。"""
        if self._scanner is not None:
            try: self._scanner.cancel()
            except Exception: pass  # noqa: BLE001
        if self._af_worker is not None:
            try: self._af_worker.cancel()
            except Exception: pass  # noqa: BLE001
        if self._stage is not None:
            try: self._stage.stop()
            except Exception: pass  # noqa: BLE001
        self.statusBar().showMessage("⛔ E-STOP", 3000)

    @Slot()
    def _on_set_zero(self) -> None:
        """Set Zero: 改坐标系 + 同步刷新 jog panel range 显示。不动 stage。"""
        if not self._stage: return
        self._stage.set_zero()
        try:
            lo, hi = self._stage.travel_limits_um
            self.stage_jog.set_travel_range_um(lo, hi)
        except Exception: pass  # noqa: BLE001

    @Slot(float)
    def _on_reset_range(self, radius_um: float) -> None:
        """以当前位置为 user 0, 行程扩展到 ±radius。stage 物理不动。"""
        if not self._stage: return
        self._stage.reset_range(radius_um)
        try:
            lo, hi = self._stage.travel_limits_um
            self.stage_jog.set_travel_range_um(lo, hi)
        except Exception: pass  # noqa: BLE001

    @Slot()
    def _on_reference(self) -> None:
        """手动寻参 — 距离估算仅用硬件物理行程, 跟软限位无关。"""
        if not self._stage:
            QMessageBox.warning(self, "寻参", "未连接位移台, 无法寻参。")
            return
        params = self._settings.pi_params()
        refmode = str(params.get("refmode", "FRF")).upper()
        vmax = float(params.get("velocity_max_um_s", 2_000.0))
        hw = getattr(self._stage, "hw_travel_um", (0.0, 0.0))
        if hw and hw[1] > hw[0]:
            range_mm = (hw[1] - hw[0]) / 1000.0
            if refmode == "FRF":
                est_str = f"≤ {range_mm/2:.1f} mm  (硬件 {range_mm:.1f} mm 的一半)"
                eta_max_s = (range_mm * 500.0) / max(1.0, vmax)
            else:
                est_str = f"≤ {range_mm:.1f} mm  (硬件全行程)"
                eta_max_s = (range_mm * 1000.0) / max(1.0, vmax)
            est_line = f"  • 最远移动 {est_str}  (实际取决于当前位置, 可能更短)"
            time_line = f"  • 限速 {vmax:.0f} µm/s, 最坏 {eta_max_s:.0f} 秒"
        else:
            est_line = "  • 最远移动: 未知 (qTMN/qTMX 读取失败), 请确保 stage 至少半行程余量"
            time_line = f"  • 限速 {vmax:.0f} µm/s"
        mark_hint = {
            "FRF": "参考标记位置 (一般在中点附近)",
            "FNL": "物理负向限位",
            "FPL": "物理正向限位",
        }.get(refmode, "参考点")
        msg = (
            f"将执行 {refmode} 寻参\n"
            f"\n"
            f"原理: PI 控制器把 stage 移动到{mark_hint}, 完成后绝对位置可信。\n"
            f"⚠ 寻参由控制器执行, 路径由控制器决定, 不受软限位约束。\n"
            f"\n"
            f"{est_line}\n"
            f"{time_line}\n"
            f"  • Esc / Space / 急停 可随时中断\n"
            f"\n"
            "确认平台周围无样品架/镜筒/手指?"
        )
        ret = QMessageBox.question(
            self, "寻参确认", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self._stage.reference(refmode)
        try:
            lo, hi = self._stage.travel_limits_um
            self.stage_jog.set_travel_range_um(lo, hi)
        except Exception: pass  # noqa: BLE001

    @Slot(float, float)
    def _on_apply_limits(self, lo: float, hi: float) -> None:
        """标定向导写软限位: 更新 driver guard + 持久化到 settings。"""
        if self._stage and hasattr(self._stage, "set_travel_limits_um"):
            self._stage.set_travel_limits_um(lo, hi)
            self.stage_jog.set_travel_range_um(*self._stage.travel_limits_um)
        # 持久化到 settings (用户视角坐标; driver 在下次连接时按 ctrl 重算)
        self._settings.set_value("pi/travel_min_um", lo)
        self._settings.set_value("pi/travel_max_um", hi)

    @Slot(float, float, float)
    def _on_position(self, x, y, z) -> None:
        self.status_strip.set_position(x, y, z)
        self.statusBar().showMessage(tr("scan.position_format", x=x, y=y, z=z))

    # ── autofocus (C.6) ───────────────────────────
    @Slot()
    def _on_autofocus_start(self) -> None:
        if not (self._stage and self._camera):
            return
        if self._af_thread is not None:
            return  # 已在跑
        if not self._settings.autofocus_enabled():
            QMessageBox.warning(self, tr("common.warning"), tr("autofocus.refused_disabled"))
            return
        if not self._check_start_state():
            return
        z_list = self._compute_autofocus_z_list()
        if z_list is None:
            return
        from .ui.autofocus_dialog import AutofocusDialog
        z_lo, z_hi = float(z_list.min()), float(z_list.max())
        z0 = float(self._stage.position[2])
        step = float(self._settings.autofocus_step_um())
        self.statusBar().showMessage(
            tr("autofocus.starting", z0=z0, lo=z_lo, hi=z_hi, step=step, n=len(z_list)), 5000,
        )
        dlg = AutofocusDialog(len(z_list), (z_lo, z_hi), parent=self)
        dlg.cancel_requested.connect(self._on_autofocus_cancel)
        dlg.show()
        self._af_dialog = dlg
        self._af_thread = QThread()
        min_step_um = float(self._settings.pi_params().get("step_min_um", 0.4))
        worker = AutofocusWorker(
            self._stage,
            self._camera,
            z_list,
            dwell_ms=self._settings.autofocus_dwell_ms(),
            min_step_um=min_step_um,
            sample_count=self._settings.autofocus_sample_count(),
        )
        worker.moveToThread(self._af_thread)
        self._af_thread.started.connect(worker.run)
        worker.progress.connect(self._on_autofocus_progress)
        worker.finished.connect(self._on_autofocus_done)
        worker.canceled.connect(self._on_autofocus_canceled)
        worker.error.connect(self._show_error)
        self._af_worker = worker
        # 扫描期间锁住按钮 (沿用 set_scanning 的视觉禁用; 但 scan worker 仍 None)
        self.control.set_scanning(True)
        self._af_thread.start()

    def _compute_autofocus_z_list(self):
        """组装 user 帧 z 列表 (autofocus_max ∩ 软限位 ∩ 行程 三者交集)。返回 None 表示拒绝."""
        import numpy as _np
        stage = self._stage
        if stage is None:
            return None
        z0 = float(stage.position[2])
        max_um = float(self._settings.autofocus_max_um())
        step = max(0.1, float(self._settings.autofocus_step_um()))
        # 先按 user 帧粗布点 (±max_um, 中心 z0)
        n_each_side = max(1, int(_np.floor(max_um / step)))
        offsets = _np.arange(-n_each_side, n_each_side + 1) * step
        candidates = z0 + offsets
        # 过滤: 每点必须通过 hw 帧安全检查 (_is_target_safe)
        valid = _np.array([
            z for z in candidates if self._is_target_safe(0.0, 0.0, float(z))
        ], dtype=_np.float64)
        if valid.size < 3:
            QMessageBox.warning(self, tr("common.warning"),
                tr("autofocus.refused_too_narrow", step=step))
            return None
        return valid

    @Slot(int, int, float, float)
    def _on_autofocus_progress(self, idx_1: int, total: int, z: float, score: float) -> None:
        if self._af_dialog is not None:
            self._af_dialog.add_point(idx_1, total, z, score)

    @Slot(object)
    def _on_autofocus_done(self, result: AutofocusResult) -> None:
        self._teardown_autofocus_thread()
        self.control.set_scanning(False)
        if self._af_dialog is not None:
            self._af_dialog.show_peak(
                result.best_z,
                result.best_score,
                low_light=result.low_light,
                saturated=result.saturated,
            )
        # 清除 autofocus 期间可能被 stage/camera 误触发的 ERROR 状态
        self.status_strip.set_state(STATE_ONLINE, tr("status.online"))
        self.statusBar().showMessage(tr("autofocus.done", z=result.best_z), 8000)
        self.status_strip.set_message(tr("autofocus.done", z=result.best_z))
        if result.saturated:
            QMessageBox.warning(self, tr("common.warning"), tr("autofocus.saturated_warning"))
            self.status_strip.set_message(tr("autofocus.saturated_status"))
        elif result.low_light:
            QMessageBox.warning(self, tr("common.warning"), tr("autofocus.low_light_warning"))
            self.status_strip.set_message(tr("autofocus.low_light_status"))

    @Slot(int)
    def _on_autofocus_canceled(self, _visited: int) -> None:
        self._teardown_autofocus_thread()
        self.control.set_scanning(False)
        if self._af_dialog is not None:
            self._af_dialog.close()
            self._af_dialog = None
        self.status_strip.set_state(STATE_ONLINE, tr("status.online"))
        self.statusBar().showMessage(tr("autofocus.canceled"), 5000)
        self.status_strip.set_message(tr("autofocus.canceled"))

    @Slot()
    def _on_autofocus_cancel(self) -> None:
        if self._af_worker is not None:
            self._af_worker.cancel()

    def _teardown_autofocus_thread(self) -> None:
        if self._af_thread is not None:
            self._af_thread.quit()
            self._af_thread.wait(3000)
            self._af_thread = None
        self._af_worker = None

    # ── scan ──────────────────────────────────────
    @Slot(object)
    def _on_scan_start(self, params: ScanParams) -> None:
        if not (self._stage and self._camera):
            return
        self._scan_metadata = self.control.scan_metadata()
        # 不再乘 axis_signs — invert 是 driver 内部职责, scan path 永远用 user 视角
        path = params.points()
        if len(path) == 0:
            QMessageBox.warning(self, "无效参数", "扫描路径为空，检查起止与步长。")
            return
        if not self._check_start_state():
            self._repeat_reset()
            return
        if not self._check_path(path):
            self._repeat_reset()
            return
        if not self._refresh_calibration_config(show_errors=True):
            self._repeat_reset()
            return
        try:
            pixel_calibration = pixel_calibration_from_settings(
                self._settings.pixel_calibration_config(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("common.error"), tr("pixel_calibration.failed", msg=str(exc)))
            self._repeat_reset()
            return
        self._scan_pixel_calibration = None if pixel_calibration is None else pixel_calibration.metadata()
        # 时间序列: 第一轮(_repeat_done==0)读 UI; 后续轮沿用初始参数
        if self._repeat_done == 0:
            self._repeat_total = max(1, self.control.repeat_count())
            self._repeat_interval_s = max(0.0, self.control.repeat_interval_min()) * 60.0
            self._repeat_base_name = time.strftime("psf_%Y%m%d_%H%M%S", time.localtime())
            self._repeat_params = params
        # streaming writer (C.4): 边采边写 stack.h5, 中途崩溃已写帧不丢
        scan_name = self._current_save_name()
        try:
            self._scan_writer = StreamingScanWriter.open(
                self._settings.data_dir(), params, name=scan_name,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("StreamingScanWriter.open failed")
            QMessageBox.critical(self, tr("common.error"), f"无法初始化流式写盘: {exc}")
            self._repeat_reset()
            return
        self.stage_view.set_scan_path(path)
        self.status_strip.set_scan_plan_ticks(len(path))
        self.psf_view.begin_scan(path)
        # 时间序列 2+ 轮不抢页签，留给用户当前正在看的视图
        if self._repeat_done == 0:
            self._tabs.setCurrentIndex(0)

        self._scan_thread = QThread()
        self._scanner = Scanner(self._stage, self._camera)
        self._scanner.configure(params, writer=self._scan_writer,
                                calibration=self._calibration_config)
        self._scanner.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scanner.run)

        self._scanner.progress.connect(self._on_progress)
        self._scanner.frame_acquired.connect(self._on_acquired)
        self._scanner.finished.connect(self._on_done)
        self._scanner.canceled.connect(self._on_canceled)
        self._scanner.error.connect(self._on_scan_error)

        self.control.set_scanning(True)
        self.status_strip.set_state(STATE_SCANNING, tr("status.scanning"))
        self.status_strip.set_progress_idle(f"0 / {len(path)}      0%")
        self.status_strip.set_message(f"scanning 0 / {len(path)} · avg {params.sample_count}")
        self._scan_thread.start()

    @Slot()
    def _on_scan_cancel(self) -> None:
        if self._scanner:
            self._scanner.cancel()
        self._repeat_reset()
        self.status_strip.set_message("canceling scan")

    @Slot(int, int, float, float, float)
    def _on_progress(self, idx_1: int, total: int, x: float, y: float, z: float) -> None:
        self.control.set_progress(
            idx_1, total,
            f"scanning  {idx_1} / {total}    z {z:+7.3f}",
        )
        self.status_strip.set_progress(idx_1, total, z)

    @Slot(int, float, float, float, object, bool)
    def _on_acquired(
        self,
        idx_0: int,
        x: float,
        y: float,
        z: float,
        frame,
        saturated: bool,
    ) -> None:
        self.stage_view.mark_done(idx_0)
        self.cam_view.update_frame(
            frame,
            0.0,
            saturated=saturated,
            display_white_level=self._preview_white_level(),
        )
        self.psf_view.add_frame(idx_0, frame)

    @Slot(object, str)
    def _on_snapshot(self, frame, cmap_name: str) -> None:
        try:
            paths = save_snapshot(self._settings.data_dir(), frame, cmap_name)
        except Exception as exc:  # noqa: BLE001
            _log.exception("snapshot save failed")
            QMessageBox.warning(self, "快照失败", str(exc))
            return
        self.statusBar().showMessage(
            f"snapshot · {paths.tiff.name} (+png+csv+json)", 5000,
        )
        self.status_strip.set_message(f"snapshot · {paths.tiff.name}")

    @Slot(bool)
    def _on_record_toggled(self, on: bool) -> None:
        if on:
            try:
                path = self._recorder.start(self._settings.data_dir())
            except Exception as exc:  # noqa: BLE001
                _log.exception("recorder.start failed")
                QMessageBox.warning(self, "录像失败", str(exc))
                self.cam_view.set_recording_state(False)
                return
            self.statusBar().showMessage(f"recording · {path.name}", 0)
            self.status_strip.set_message(f"recording · {path.name}")
            if self._camera is not None:
                self._camera.frame_ready.connect(self._on_record_frame)
            return
        if self._camera is not None:
            try:
                self._camera.frame_ready.disconnect(self._on_record_frame)
            except (RuntimeError, TypeError):
                pass
        try:
            path, n_frames, duration = self._recorder.stop()
        except Exception as exc:  # noqa: BLE001
            _log.exception("recorder.stop failed")
            QMessageBox.warning(self, "录像结束失败", str(exc))
            return
        msg = f"saved {n_frames} frames in {duration:.1f}s · {path.name}"
        self.statusBar().showMessage(msg, 8000)
        self.status_strip.set_message(msg)

    @Slot(object, float)
    def _on_record_frame(self, frame, ts: float) -> None:
        self._recorder.append(frame)

    @Slot(int)
    def _on_canceled(self, frames_collected: int) -> None:
        """扫描被用户停掉 — 不算 error，状态走 idle/saved，已采集帧保留。"""
        if frames_collected == 0:
            self._teardown_scan_thread()
            self.control.set_scanning(False)
            self.status_strip.set_state(STATE_IDLE, tr("status.canceled"))
            self.status_strip.set_message("scan canceled · no frames")
            self.statusBar().showMessage("scan canceled", 5000)
            self._close_writer_quiet()  # 空 h5 留作未收尾文件, 启动时自动检测
            self._repeat_reset()
        # 有帧的话，_on_done 会照常处理 finalize + 保存与切换视图

    @Slot(object)
    def _on_done(self, result: ScanResult) -> None:
        self._teardown_scan_thread()
        self.control.set_scanning(False)
        result.metadata = self._scan_metadata
        result.pixel_calibration = self._scan_pixel_calibration
        display_frames = result.corrected_frames if result.corrected_frames is not None else result.frames
        self.psf_view.set_data(display_frames, result.positions)
        # 单次扫描或时间序列末轮才自动跳到 PSF STACK，避免每轮闪页签
        if self._repeat_total <= 1 or self._repeat_done >= self._repeat_total - 1:
            self._tabs.setCurrentIndex(1)
        # streaming: stack.h5 已在扫描线程内写完, 这里收尾 attrs + 走 finalize 路径
        writer = self._scan_writer
        if writer is not None:
            try:
                writer.finalize_attrs(
                    metadata=result.metadata,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    calibration=result.calibration,
                    pixel_calibration=result.pixel_calibration,
                )
                writer.close()
            except Exception as exc:  # noqa: BLE001
                _log.exception("scan writer finalize failed: %s", exc)
            target_dir = writer.target_dir
            self._scan_writer = None
            self._start_save(result, target_dir, is_primary=True, streamed=True)
        else:
            # 兜底 (writer 没初始化成功): 走 legacy 一次性 save_scan
            name = self._current_save_name()
            self._start_save(result, self._settings.data_dir(),
                             is_primary=True, name=name)

    def _current_save_name(self) -> str | None:
        """时间序列模式 (_repeat_total>1) 下文件名加 _tNN 后缀; 单次扫描走 save_scan 默认。"""
        if self._repeat_total <= 1 or not self._repeat_base_name:
            return None
        return f"{self._repeat_base_name}_t{self._repeat_done:02d}"

    def _close_writer_quiet(self) -> None:
        """异常路径用 — 关闭 writer 但不抛，保留 stack.h5 留待启动恢复检测。"""
        if self._scan_writer is None:
            return
        try:
            self._scan_writer.close()
        except Exception:  # noqa: BLE001
            pass
        self._scan_writer = None

    def _start_save(self, result: ScanResult, target_dir: Path, *,
                    is_primary: bool, name: str | None = None,
                    streamed: bool = False) -> None:
        """Launch save/finalize on a worker thread; UI shows 'saving…' while it runs."""
        if self._save_thread is not None:
            return
        self.status_strip.set_state(STATE_SCANNING, tr("status.saving"))
        self.status_strip.set_message(f"saving · {target_dir.name}…")
        self._save_thread = QThread()
        self._save_worker = _SaveWorker(target_dir, result, name=name, streamed=streamed)
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.done.connect(self._on_save_done)
        self._save_worker.failed.connect(
            lambda msg, r=result, p=is_primary, n=name, s=streamed:
                self._on_save_failed(r, msg, is_primary=p, name=n, streamed=s)
        )
        self._save_thread.start()

    @Slot(object)
    def _on_save_done(self, target: Path) -> None:
        self._teardown_save_thread()
        self.status_strip.set_state(STATE_SAVED, tr("status.saved"))
        self.status_strip.set_message(f"saved · {target.name}")
        self.statusBar().showMessage(f"saved · {target}", 8000)
        # 时间序列: 派下一次或收尾
        self._repeat_done += 1
        if self._repeat_total > 1 and self._repeat_done < self._repeat_total:
            wait_s = self._repeat_interval_s
            self.status_strip.set_message(
                tr("status.timeseries_waiting",
                   done=self._repeat_done, total=self._repeat_total, wait_s=wait_s)
            )
            QTimer.singleShot(int(max(0.0, wait_s) * 1000), self._start_next_repeat)
        else:
            self._repeat_reset()

    def _start_next_repeat(self) -> None:
        if not (self._stage and self._camera and self._repeat_params is not None):
            self._repeat_reset()
            return
        if self._repeat_done >= self._repeat_total:
            self._repeat_reset()
            return
        # 直接进 _on_scan_start (沿用初始参数, 不重新读 UI)
        self._on_scan_start(self._repeat_params)

    def _repeat_reset(self) -> None:
        self._repeat_total = 0
        self._repeat_done = 0
        self._repeat_interval_s = 0.0
        self._repeat_base_name = ""
        self._repeat_params = None

    def _on_save_failed(self, result: ScanResult, msg: str, *, is_primary: bool,
                        name: str | None = None, streamed: bool = False) -> None:
        self._teardown_save_thread()
        _log.error("scan save failed (is_primary=%s streamed=%s): %s",
                   is_primary, streamed, msg)
        if not is_primary:
            QMessageBox.critical(self, "保存失败", msg)
            self.status_strip.set_state(STATE_ERROR, tr("status.error"))
            self.status_strip.set_message(f"save failed: {msg}")
            self._repeat_reset()
            return
        primary = self._settings.data_dir()
        QMessageBox.warning(
            self, "保存失败",
            f"默认目录 {primary} 不可写：\n{msg}\n\n请选一个新目录。",
        )
        chosen = QFileDialog.getExistingDirectory(
            self, "选择数据保存目录", str(Path.home()),
        )
        if not chosen:
            self.status_strip.set_state(STATE_ERROR, tr("status.not_saved"))
            self.status_strip.set_message("保存已取消，数据仍在内存里")
            self._repeat_reset()
            return
        self._settings.set_data_dir(chosen)
        self._refresh_data_dir_label()
        # streamed=True 时 stack.h5 已经在原 target_dir 内, fallback 改写到新 dir 必须走非 streamed 路径
        self._start_save(result, Path(chosen), is_primary=False, name=name, streamed=False)

    def _teardown_save_thread(self) -> None:
        if self._save_thread is not None:
            self._save_thread.quit()
            self._save_thread.wait(2000)
            self._save_thread = None
        self._save_worker = None

    @Slot()
    def _on_change_data_dir(self) -> None:
        current = self._settings.data_dir()
        chosen = QFileDialog.getExistingDirectory(
            self, "选择数据保存目录", str(current if current.exists() else Path.home()),
        )
        if chosen:
            self._settings.set_data_dir(chosen)
            self._refresh_data_dir_label()
            self.statusBar().showMessage(f"data folder · {chosen}", 4000)

    @Slot()
    def _on_open_data_dir(self) -> None:
        path = self._settings.data_dir()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.exception("data dir mkdir failed (%s)", path)
            QMessageBox.warning(self, "目录不可访问", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot()
    def _on_export_plot(self) -> None:
        if not self.psf_view.has_data():
            QMessageBox.information(self, "导出图像", "还没有 PSF 数据，先扫描或加载一份。")
            return
        base = self._settings.data_dir() / "plots"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path.home()
        default = base / time.strftime("psf_plot_%Y%m%d_%H%M%S.png", time.localtime())
        chosen, _ = QFileDialog.getSaveFileName(
            self, "导出 PSF 图像", str(default),
            "PNG image (*.png);;JPEG image (*.jpg);;TIFF image (*.tif)",
        )
        if not chosen:
            return
        try:
            self.psf_view.export_plot_to(chosen)
        except Exception as exc:  # noqa: BLE001
            _log.exception("export plot failed (target=%s)", chosen)
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.statusBar().showMessage(f"plot exported · {Path(chosen).name}", 5000)
        self.status_strip.set_message(f"plot · {Path(chosen).name}")

    def _refresh_data_dir_label(self) -> None:
        self.status_strip.set_data_dir(str(self._settings.data_dir()))

    def _teardown_scan_thread(self) -> None:
        if self._scan_thread:
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
            self._scan_thread = None
        self._scanner = None

    @Slot(str)
    def _on_scan_error(self, msg: str) -> None:
        """扫描期间的 error 信号 — 走通用 _show_error + 关流式 writer + 复位 UI。"""
        self._show_error(msg)
        self._close_writer_quiet()
        self.control.set_scanning(False)
        self._repeat_reset()

    @Slot(str)
    def _show_error(self, msg: str) -> None:
        _log.error("UI error: %s", msg)
        self.status_strip.set_state(STATE_ERROR, tr("status.error"))
        self.status_strip.set_message(msg)
        self.statusBar().showMessage(f"error · {msg}", 6000)

    @Slot()
    def _log_diagnostics(self) -> None:
        _log.info("diag process %s", format_kv(process_snapshot()))
        self._log_component_diagnostics("camera", self._camera)
        self._log_component_diagnostics("stage", self._stage)
        self._log_component_diagnostics("camera_view", self.cam_view)

    def _log_component_diagnostics(self, name: str, obj) -> None:
        if obj is None:
            _log.info("diag %s none", name)
            return
        diagnostics = getattr(obj, "diagnostics", None)
        if diagnostics is None:
            _log.info("diag %s unavailable type=%s", name, type(obj).__name__)
            return
        try:
            data = diagnostics()
        except Exception as exc:  # noqa: BLE001
            _log.exception("diag %s failed: %s", name, exc)
            return
        _log.info("diag %s type=%s %s", name, type(obj).__name__, format_kv(data))

    def closeEvent(self, ev) -> None:
        if not self._confirm_exit():
            ev.ignore()
            return
        self._shutdown_in_order()
        super().closeEvent(ev)

    def _confirm_exit(self) -> bool:
        """关窗前确认 — 扫描中 / 录像中 / 保存中 / 连着设备时都问一下。"""
        busy = []
        if self._scanner is not None:
            busy.append("扫描进行中")
        if self._save_thread is not None:
            busy.append("数据保存中 (退出会丢失未完成的写盘)")
        if self._recorder.is_recording:
            busy.append("录像进行中")
        if self._camera is not None or self._stage is not None:
            busy.append("设备已连接")
        if not busy:
            return True
        msg = "退出前要做:\n  · " + "\n  · ".join(busy) + "\n\n确定退出?"
        ret = QMessageBox.question(
            self, "退出 PSF Scan", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _shutdown_in_order(self) -> None:
        """严格顺序: 扫描 → autofocus → 录像 → 保存 → 相机 → 位移台. 每一步独立 try 防止后续阻塞."""
        # 1) 扫描器
        try:
            if self._scanner is not None:
                self._scanner.cancel()
                self._teardown_scan_thread()
        except Exception:  # noqa: BLE001
            pass
        # 1b) autofocus worker
        try:
            if self._af_worker is not None:
                self._af_worker.cancel()
            self._teardown_autofocus_thread()
        except Exception:  # noqa: BLE001
            pass
        # 1c) streaming writer (C.4) — 关闭未完成的 stack.h5，等待下次启动恢复
        try:
            self._close_writer_quiet()
        except Exception:  # noqa: BLE001
            pass
        # 2) 录像
        try:
            if self._recorder.is_recording:
                self.cam_view.set_recording_state(False)
        except Exception:  # noqa: BLE001
            pass
        # 3) 保存线程 (worker)
        try:
            if self._save_thread is not None:
                self._teardown_save_thread()
        except Exception:  # noqa: BLE001
            pass
        # 4) 断开相机信号, 让残留 spinbox/slider 事件不再触达硬件
        if self._camera is not None:
            try:
                self._camera.frame_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
        # 5) 走标准 disconnect 序列 (会同时停 streaming 与 stage timer)
        try:
            self._on_disconnect()
        except Exception:  # noqa: BLE001
            pass

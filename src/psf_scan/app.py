"""主窗口 — 浅色科研绘图工作台版本。

布局：顶部 tab 栏（含标题）+ HSplitter(主视图 | stage 视图) + 控件面板 + 状态栏。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QSplitter, QStatusBar, QTabWidget,
    QVBoxLayout, QWidget,
)

from .core.camera import AVAILABLE_CAMERAS, CameraBase, make_camera
from .core.data_io import save_scan
from .core.scanner import ScanParams, ScanResult, Scanner
from .core.stage import AVAILABLE_STAGES, StageBase, make_stage
from .ui import theme
from .ui.camera_view import CameraView
from .ui.control_panel import ControlPanel
from .ui.psf_view import PSFView
from .ui.settings import UserSettings
from .ui.stage_view import StageView
from .ui.status_strip import (
    STATE_ERROR, STATE_IDLE, STATE_ONLINE, STATE_SAVED, STATE_SCANNING, StatusStrip,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("psf scan")
        self.setMinimumSize(1100, 720)

        self._stage: Optional[StageBase] = None
        self._camera: Optional[CameraBase] = None
        self._scanner: Optional[Scanner] = None
        self._scan_thread: Optional[QThread] = None
        self._settings = UserSettings()

        self.cam_view = CameraView()
        self.stage_view = StageView()
        self.control = ControlPanel(AVAILABLE_STAGES, AVAILABLE_CAMERAS)
        self.psf_view = PSFView()
        self.status_strip = StatusStrip()

        self._tabs = self._build_tabs()
        self.setCentralWidget(self._build_shell())

        bar = QStatusBar()
        self.setStatusBar(bar)
        self._idle_status = "ready · connect devices"
        bar.showMessage(self._idle_status)
        self._bind_settings()
        self._wire_signals()
        self.status_strip.set_plan(self.control.plan_text())

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()
        self._tabs.addTab(self.cam_view, "LIVE IMAGE")
        self._tabs.addTab(self.psf_view, "PSF STACK")
        title = QLabel("PSF·SCAN")
        title.setFont(QFont(self.font().family(), 11, QFont.Bold))
        title.setStyleSheet(
            f"color:{theme.TEXT0};letter-spacing:3px;padding:0 16px 0 6px;"
        )
        self._tabs.setCornerWidget(title, Qt.TopLeftCorner)
        return self._tabs

    def _build_shell(self) -> QWidget:
        top = QSplitter(Qt.Horizontal)
        top.addWidget(self._tabs)
        top.addWidget(self.stage_view)
        top.setSizes([920, 320])
        top.setHandleWidth(1)

        main = QSplitter(Qt.Vertical)
        main.addWidget(top)
        main.addWidget(self.control)
        main.setSizes([560, 280])
        main.setHandleWidth(1)
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.status_strip)
        shell_layout.addWidget(main, stretch=1)
        return shell

    def _wire_signals(self) -> None:
        self.control.connect_requested.connect(self._on_connect)
        self.control.disconnect_requested.connect(self._on_disconnect)
        self.control.move_requested.connect(self._on_move)
        self.control.home_requested.connect(self._on_home)
        self.control.scan_started.connect(self._on_scan_start)
        self.control.scan_canceled.connect(self._on_scan_cancel)
        self.control.plan_changed.connect(self.status_strip.set_plan)
        self.cam_view.metrics_changed.connect(self.status_strip.set_camera)
        self.cam_view.exposure_changed.connect(self._on_exposure_changed)
        self.cam_view.gain_changed.connect(self._on_gain_changed)
        self.cam_view.gamma_changed.connect(self._on_gamma_changed)
        self.cam_view.black_level_changed.connect(self._on_black_level_changed)
        self.cam_view.frame_rate_changed.connect(self._on_frame_rate_changed)
        self.cam_view.pixel_format_changed.connect(self._on_pixel_format_changed)

    def _bind_settings(self) -> None:
        self.control.bind_settings(self._settings)
        self.psf_view.bind_settings(self._settings)
        self.cam_view.bind_settings(self._settings)

    # ── connection ────────────────────────────────
    @Slot(str, str)
    def _on_connect(self, stage_kind: str, cam_kind: str) -> None:
        try:
            stage = make_stage(stage_kind)
            kw = {"stage": stage} if cam_kind == "mock" else {}
            camera = make_camera(cam_kind, **kw)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "连接失败", str(exc))
            return

        stage.position_changed.connect(self.stage_view.set_position)
        stage.position_changed.connect(self._on_position)
        stage.error.connect(self._show_error)
        camera.frame_ready.connect(self.cam_view.update_frame)
        camera.error.connect(self._show_error)

        try:
            stage.connect()
            camera.connect()
            self._restore_camera_settings(camera)
            camera.start_streaming()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "启动失败", str(exc))
            return

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
        self._stage, self._camera = stage, camera
        self.control.set_connected(True)
        device_text = f"{stage_kind} stage · {camera.description}"
        self.status_strip.set_state(STATE_ONLINE, "online")
        self.status_strip.set_message(device_text)
        self.statusBar().showMessage(f"connected · {device_text}", 5000)

    def _restore_camera_settings(self, camera: CameraBase) -> None:
        exposure_us = self._settings.value_int("camera/exposure_us", camera.get_exposure_us())
        gain = self._settings.value_float("camera/gain", camera.get_gain())
        camera.set_exposure_us(exposure_us)
        camera.set_gain(gain)

    @Slot(int)
    def _on_exposure_changed(self, exposure_us: int) -> None:
        if not self._camera:
            raise RuntimeError("相机未连接，不能设置曝光")
        self._camera.set_exposure_us(exposure_us)
        self._settings.set_value("camera/exposure_us", exposure_us)

    @Slot(float)
    def _on_gain_changed(self, gain: float) -> None:
        if not self._camera:
            raise RuntimeError("相机未连接，不能设置增益")
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
        if self._camera:
            self._camera.set_frame_rate(fps)

    @Slot(str)
    def _on_pixel_format_changed(self, fmt: str) -> None:
        if self._camera:
            self._camera.set_pixel_format(fmt)

    @Slot()
    def _on_disconnect(self) -> None:
        if self._camera: self._camera.disconnect(); self._camera = None
        if self._stage: self._stage.disconnect(); self._stage = None
        self.control.set_connected(False)
        self.cam_view.reset(); self.stage_view.clear_path()
        self.status_strip.set_state(STATE_IDLE, "offline")
        self.status_strip.set_progress_idle()
        self.status_strip.reset_camera()
        self.status_strip.set_message("connect devices")
        self.statusBar().showMessage(self._idle_status)

    # ── manual ────────────────────────────────────
    @Slot(float, float, float)
    def _on_move(self, x, y, z): self._stage and self._stage.move_to(x, y, z)

    @Slot()
    def _on_home(self): self._stage and self._stage.home()

    @Slot(float, float, float)
    def _on_position(self, x, y, z) -> None:
        self.status_strip.set_position(x, y, z)
        self.statusBar().showMessage(f"x {x:+8.3f}    y {y:+8.3f}    z {z:+8.3f}    µm")

    # ── scan ──────────────────────────────────────
    @Slot(object)
    def _on_scan_start(self, params: ScanParams) -> None:
        if not (self._stage and self._camera):
            return
        path = params.points()
        if len(path) == 0:
            QMessageBox.warning(self, "无效参数", "扫描路径为空，检查起止与步长。")
            return
        self.stage_view.set_scan_path(path)
        self.psf_view.begin_scan(path)
        self._tabs.setCurrentIndex(0)

        self._scan_thread = QThread()
        self._scanner = Scanner(self._stage, self._camera)
        self._scanner.configure(params)
        self._scanner.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scanner.run)

        self._scanner.progress.connect(self._on_progress)
        self._scanner.frame_acquired.connect(self._on_acquired)
        self._scanner.finished.connect(self._on_done)
        self._scanner.error.connect(self._show_error)

        self.control.set_scanning(True)
        self.control.set_status(f"scanning  0 / {len(path)}    avg {params.sample_count}")
        self.status_strip.set_state(STATE_SCANNING, "scanning")
        self.status_strip.set_progress_idle(f"0 / {len(path)}      0%")
        self.status_strip.set_message("acquiring averaged frames")
        self._scan_thread.start()

    @Slot()
    def _on_scan_cancel(self) -> None:
        if self._scanner:
            self._scanner.cancel()
        self.control.set_status("canceling scan")
        self.status_strip.set_message("canceling scan")

    @Slot(int, int, float, float, float)
    def _on_progress(self, idx_1: int, total: int, x: float, y: float, z: float) -> None:
        self.control.set_progress(
            idx_1, total,
            f"scanning  {idx_1} / {total}    z {z:+7.3f}",
        )
        self.status_strip.set_progress(idx_1, total, z)

    @Slot(int, float, float, float, object)
    def _on_acquired(self, idx_0: int, x: float, y: float, z: float, frame) -> None:
        self.stage_view.mark_done(idx_0)
        self.cam_view.update_frame(frame, 0.0)
        self.psf_view.add_frame(idx_0, frame)

    @Slot(object)
    def _on_done(self, result: ScanResult) -> None:
        self._teardown_scan_thread()
        self.control.set_scanning(False)
        try:
            target = save_scan(Path("./psf_data"), result)
            self.control.set_status(f"saved · {target.name}")
            self.status_strip.set_state(STATE_SAVED, "saved")
            self.status_strip.set_message(target.name)
            self.statusBar().showMessage(f"saved · {target}", 8000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            self.control.set_status(f"save failed: {exc!r}")
            self.status_strip.set_state(STATE_ERROR, "error")
            self.status_strip.set_message(str(exc))
        self.psf_view.set_data(result.frames, result.positions)
        self._tabs.setCurrentIndex(1)

    def _teardown_scan_thread(self) -> None:
        if self._scan_thread:
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
            self._scan_thread = None
        self._scanner = None

    @Slot(str)
    def _show_error(self, msg: str) -> None:
        self.status_strip.set_state(STATE_ERROR, "error")
        self.status_strip.set_message(msg)
        self.statusBar().showMessage(f"error · {msg}", 6000)

    def closeEvent(self, ev) -> None:
        if self._scanner:
            self._scanner.cancel()
        self._teardown_scan_thread()
        self._on_disconnect()
        super().closeEvent(ev)

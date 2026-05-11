"""主窗口 — 浅色科研绘图工作台版本。

布局：顶部 tab 栏（含标题）+ HSplitter(主视图 | stage 视图) + 控件面板 + 状态栏。
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Optional

from PySide6.QtCore import Qt, QThread, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMainWindow, QMessageBox, QSplitter, QStatusBar,
    QTabWidget, QVBoxLayout, QWidget,
)

from .core.camera import AVAILABLE_CAMERAS, CameraBase, make_camera
from .core.data_io import save_scan
from .core.scanner import ScanParams, ScanResult, Scanner
from .core.snapshot import VideoRecorder, save_snapshot
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
        self._recorder = VideoRecorder()

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
        self._refresh_data_dir_label()

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
        self.cam_view.snapshot_requested.connect(self._on_snapshot)
        self.cam_view.record_toggled.connect(self._on_record_toggled)
        self.psf_view.export_plot_requested.connect(self._on_export_plot)
        self.status_strip.change_data_dir_requested.connect(self._on_change_data_dir)
        self.status_strip.open_data_dir_requested.connect(self._on_open_data_dir)

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
        if self._recorder.is_recording:
            self.cam_view.set_recording_state(False)
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
        self._scanner.canceled.connect(self._on_canceled)
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

    @Slot(object, str)
    def _on_snapshot(self, frame, cmap_name: str) -> None:
        try:
            tiff_path, png_path = save_snapshot(self._settings.data_dir(), frame, cmap_name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "快照失败", str(exc))
            return
        self.statusBar().showMessage(f"snapshot · {tiff_path.name} + .png", 5000)
        self.status_strip.set_message(f"snapshot · {tiff_path.name}")

    @Slot(bool)
    def _on_record_toggled(self, on: bool) -> None:
        if on:
            try:
                path = self._recorder.start(self._settings.data_dir())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "录像失败", str(exc))
                self.cam_view.set_recording_state(False)
                return
            self.statusBar().showMessage(f"recording · {path.name}", 0)
            self.status_strip.set_message(f"recording · {path.name}")
            self.cam_view.frame_rate_changed  # noop; 仅占位避免 lint
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
            self.control.set_status("scan canceled")
            self.status_strip.set_state(STATE_IDLE, "canceled")
            self.status_strip.set_message("scan canceled · no frames")
            self.statusBar().showMessage("scan canceled", 5000)
        # 有帧的话，_on_done 会照常处理保存与切换视图

    @Slot(object)
    def _on_done(self, result: ScanResult) -> None:
        self._teardown_scan_thread()
        self.control.set_scanning(False)
        target = self._save_with_fallback(result)
        if target is not None:
            self.control.set_status(f"saved · {target.name}")
            self.status_strip.set_state(STATE_SAVED, "saved")
            self.status_strip.set_message(target.name)
            self.statusBar().showMessage(f"saved · {target}", 8000)
        self.psf_view.set_data(result.frames, result.positions)
        self._tabs.setCurrentIndex(1)

    def _save_with_fallback(self, result: ScanResult) -> Optional[Path]:
        """先用配置的 data_dir 存；失败 (权限/不存在) 弹 dialog 让用户重选。"""
        primary = self._settings.data_dir()
        try:
            return save_scan(primary, result)
        except (PermissionError, OSError) as exc:
            QMessageBox.warning(
                self, "保存失败",
                f"默认目录 {primary} 不可写：\n{exc}\n\n请选一个新目录。",
            )
        chosen = QFileDialog.getExistingDirectory(
            self, "选择数据保存目录", str(Path.home()),
        )
        if not chosen:
            self.control.set_status("save canceled · data kept in memory")
            self.status_strip.set_state(STATE_ERROR, "not saved")
            self.status_strip.set_message("保存已取消，数据仍在内存里")
            return None
        try:
            target = save_scan(Path(chosen), result)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            self.control.set_status(f"save failed: {exc!r}")
            self.status_strip.set_state(STATE_ERROR, "error")
            self.status_strip.set_message(str(exc))
            return None
        self._settings.set_data_dir(chosen)
        self._refresh_data_dir_label()
        return target

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

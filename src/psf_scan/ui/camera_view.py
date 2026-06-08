"""实时相机画面 — 主题画布 + 曝光 / 增益 / 饱和指示。"""

from __future__ import annotations

import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QSpinBox, QStackedLayout,
    QMessageBox, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .camera_advanced import CameraAdvancedBar
from .colormap_resolver import resolve_colormap as _resolve_colormap
from .motion import flash
from .sparkline import Sparkline
from ..core.calibration import is_sensor_saturated
from ..core.pixel_calibration import from_settings as pixel_calibration_from_settings
from ..core.sharpness import brenner
from ..core.i18n import tr
from .widgets import HintLabel, MeterLabel


CAMERA_CMAPS = ("viridis", "gray", "hot", "rainbow", "magma", "inferno", "plasma")
DEFAULT_CMAP = "gray"


def _vrule() -> QFrame:
    rule = QFrame()
    rule.setFixedWidth(1)
    rule.setStyleSheet(f"background:{theme.BORDER0};")
    return rule


def _empty_html(main_key: str, hint_key: str) -> str:
    """两行空状态 (主标题 + 浅色提示) — RichText 渲染。"""
    return (
        f"<div>{tr(main_key)}</div>"
        f"<div style='color:{theme.TEXT3};font-size:{theme.SIZE_METER};"
        "margin-top:6px;font-weight:400;letter-spacing:0px;'>"
        f"{tr(hint_key)}</div>"
    )


class CameraView(QWidget):
    exposure_changed = Signal(int)        # us
    auto_exposure_requested = Signal()
    hardware_dark_requested = Signal()
    gain_changed = Signal(float)
    colormap_changed = Signal(str)
    gamma_changed = Signal(float)
    black_level_changed = Signal(int)
    frame_rate_changed = Signal(float)
    pixel_format_changed = Signal(str)
    metrics_changed = Signal(int, float, bool)
    frame_displayed = Signal()
    snapshot_requested = Signal(object, str)         # frame, cmap_name
    record_toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.BG0};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_exposure_bar())

        self._advanced = CameraAdvancedBar()
        self._advanced.gamma_changed.connect(self.gamma_changed.emit)
        self._advanced.black_level_changed.connect(self.black_level_changed.emit)
        self._advanced.frame_rate_changed.connect(self.frame_rate_changed.emit)
        self._advanced.pixel_format_changed.connect(self.pixel_format_changed.emit)
        self._advanced.setVisible(False)
        layout.addWidget(self._advanced)

        self._iv = pg.ImageView()
        self._iv.ui.histogram.hide()
        self._iv.ui.menuBtn.hide()
        self._iv.ui.roiBtn.hide()
        self._iv.view.setAspectLocked(True)
        self._iv.view.invertY(True)
        self._iv.view.setBackgroundColor(theme.BG0)
        # 框选缩放 (rubberband): 左键拖矩形 zoom; 右键拖平移; 双击重置
        self._iv.view.setMouseMode(pg.ViewBox.RectMode)
        self._cmap_name = DEFAULT_CMAP
        self._apply_colormap(DEFAULT_CMAP)
        self._empty = self._build_empty_state()
        self._image_host = QWidget()
        self._image_stack = QStackedLayout(self._image_host)
        self._image_stack.addWidget(self._empty)
        self._image_stack.addWidget(self._iv)
        self._sat_badge = QLabel("SATURATED", self._image_host)
        self._sat_badge.setProperty("role", "sat-badge")
        self._sat_badge.hide()
        _original_resize = self._image_host.resizeEvent
        def _resize_with_overlay(event):
            _original_resize(event)
            if self._sat_badge.isVisible():
                self._position_sat_badge()
        self._image_host.resizeEvent = _resize_with_overlay
        layout.addWidget(self._image_host, stretch=1)

        layout.addWidget(self._build_meter_bar())

        # F11 全屏切换, Esc 退出
        self._fs_parent: QWidget | None = None
        for seq, fn in ((Qt.Key_F11, self.toggle_fullscreen), (Qt.Key_Escape, self._exit_fullscreen)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)

        self._last_frame_t: float | None = None
        self._fps = 0.0
        self._fps_dirty = False
        self._metrics_dirty = False
        self._last_peak = 0
        self._last_saturated_status = False
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(100)
        self._fps_timer.timeout.connect(self._flush_fps)
        self._fps_timer.start()
        self._auto_levels = False
        self._auto_level_levels: tuple[float, float] | None = None
        self._auto_level_last_ts = 0.0
        self._levels_set = False
        self._max_val = 255
        self._saturated = False
        self._last_raw_frame: np.ndarray | None = None
        self._recording = False
        self._sharpness_window: deque[float] = deque(maxlen=100)
        self._displayed_frames = 0
        self._display_total_ms = 0.0
        self._display_max_ms = 0.0
        self._display_last_ms = 0.0
        # line profile (C.3)
        self._line_roi: pg.LineSegmentROI | None = None
        self._line_dialog = None  # 延迟构造 (避免无头测试时立刻弹窗)
        self._settings = None

    def _build_empty_state(self) -> QLabel:
        label = QLabel(_empty_html("camera.no_signal", "camera.no_signal_hint"))
        label.setAlignment(Qt.AlignCenter)
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet(
            f"color:{theme.TEXT3};background:{theme.BG0};"
            f"font-family:'Iosevka Term',monospace;font-size:{theme.SIZE_CONTROL};"
            "font-weight:500;letter-spacing:1px;"
        )
        return label

    def _build_exposure_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.BG1};border-bottom:1px solid {theme.BORDER0};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(10)

        h.addWidget(HintLabel(tr("camera.exposure")))
        self.sp_exp = QSpinBox()
        self.sp_exp.setRange(1, 1_000_000)
        self.sp_exp.setValue(10_000)
        self.sp_exp.setMinimumWidth(86)
        self.sp_exp.setSuffix(" µs")
        self.sp_exp.setButtonSymbols(QSpinBox.NoButtons)
        self.sp_exp.setEnabled(False)
        self.sp_exp.setToolTip(tr("tip.exposure"))
        self.sp_exp.editingFinished.connect(lambda: self.exposure_changed.emit(self.sp_exp.value()))
        h.addWidget(self.sp_exp)

        h.addSpacing(12)
        h.addWidget(HintLabel(tr("camera.gain")))
        self.sp_gain = QDoubleSpinBox()
        self.sp_gain.setRange(0.0, 64.0)
        self.sp_gain.setValue(1.0)
        self.sp_gain.setDecimals(2)
        self.sp_gain.setSingleStep(0.1)
        self.sp_gain.setMinimumWidth(70)
        self.sp_gain.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.sp_gain.setEnabled(False)
        self.sp_gain.setToolTip(tr("tip.gain"))
        self.sp_gain.editingFinished.connect(lambda: self.gain_changed.emit(self.sp_gain.value()))
        h.addWidget(self.sp_gain)

        h.addWidget(_vrule())
        h.addWidget(HintLabel(tr("camera.colormap")))
        self.cb_cmap = QComboBox()
        self.cb_cmap.addItems(CAMERA_CMAPS)
        self.cb_cmap.setCurrentText(DEFAULT_CMAP)
        self.cb_cmap.setMinimumWidth(92)
        self.cb_cmap.setToolTip(tr("tip.colormap"))
        self.cb_cmap.currentTextChanged.connect(self._on_cmap_changed)
        h.addWidget(self.cb_cmap)

        self.btn_auto_exposure = self._tool_button(tr("camera.auto_exposure"))
        self.btn_auto_exposure.setEnabled(False)
        self.btn_auto_exposure.setToolTip(tr("tip.auto_exposure"))
        self.btn_auto_exposure.clicked.connect(self.auto_exposure_requested.emit)
        h.addWidget(self.btn_auto_exposure)

        self.btn_auto_levels = self._tool_button(tr("camera.auto_levels"), checkable=True)
        self.btn_auto_levels.setToolTip(tr("tip.auto_levels"))
        self.btn_auto_levels.toggled.connect(self._on_auto_levels_toggled)
        h.addWidget(self.btn_auto_levels)

        self.btn_hardware_dark = self._tool_button(tr("camera.hardware_dark"))
        self.btn_hardware_dark.setEnabled(False)
        self.btn_hardware_dark.setToolTip(tr("tip.hardware_dark"))
        self.btn_hardware_dark.clicked.connect(self.hardware_dark_requested.emit)
        h.addWidget(self.btn_hardware_dark)

        h.addWidget(_vrule())

        self.btn_snapshot = self._action_button(tr("camera.snapshot"))
        self.btn_snapshot.setEnabled(False)
        self.btn_snapshot.setToolTip(tr("tip.snapshot"))
        self.btn_snapshot.clicked.connect(self._emit_snapshot)
        h.addWidget(self.btn_snapshot)

        self.btn_record = self._action_button(tr("camera.record"))
        self.btn_record.setCheckable(True)
        self.btn_record.setEnabled(False)
        self.btn_record.setToolTip(tr("tip.record"))
        self.btn_record.toggled.connect(self._on_record_toggled)
        h.addWidget(self.btn_record)

        self.btn_line_profile = QToolButton()
        self.btn_line_profile.setText(tr("camera.line_profile_tool"))
        self.btn_line_profile.setCheckable(True)
        self.btn_line_profile.setToolTip(tr("tip.line_profile_tool"))
        self.btn_line_profile.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT1};border:1px solid {theme.BORDER0};"
            f"background:{theme.HIGHLIGHT};padding:4px 12px;"
            f"font-family:'{theme.SANS}',sans-serif;font-size:{theme.SIZE_CONTROL};letter-spacing:1px;"
            "font-weight:600;min-height:28px;}"
            f"QToolButton:hover{{background:{theme.BG2};border-color:{theme.ACCENT};}}"
            f"QToolButton:checked{{color:{theme.ON_ACCENT};background:{theme.ACCENT};"
            f"border-color:{theme.ACCENT};}}"
        )
        self.btn_line_profile.toggled.connect(self._on_line_profile_toggled)
        h.addWidget(self.btn_line_profile)

        h.addWidget(_vrule())
        self.btn_advanced = QToolButton()
        self.btn_advanced.setText("▾ " + tr("camera.advanced"))
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setToolTip(tr("tip.advanced"))
        self.btn_advanced.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT1};border:1px solid {theme.BORDER0};"
            f"background:{theme.HIGHLIGHT};padding:4px 12px;"
            f"font-family:'{theme.SANS}',sans-serif;font-size:{theme.SIZE_CONTROL};letter-spacing:1px;"
            "font-weight:600;min-height:28px;}"
            f"QToolButton:hover{{background:{theme.BG2};border-color:{theme.ACCENT};}}"
            f"QToolButton:checked{{color:{theme.TEXT0};background:{theme.BG2};"
            f"border-color:{theme.ACCENT};}}"
        )
        self.btn_advanced.toggled.connect(self._on_advanced_toggled)
        h.addWidget(self.btn_advanced)

        h.addStretch()
        return bar

    def _build_meter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.BG1};border-top:1px solid {theme.BORDER0};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(20)
        self._size_lbl = MeterLabel("image ─×─")
        self._peak_lbl = MeterLabel(tr("camera.peak") + " ─")
        self._fps_lbl = MeterLabel("─.─ fps")
        self._sharpness_lbl = MeterLabel("sharp ─ / max ─")
        self._sharpness_lbl.hide()
        self._sharpness_spark = Sparkline(width=60, height=14, capacity=60)
        self._sharpness_spark.setToolTip(tr("tip.sharpness_trend"))
        self._pixel_calibration_lbl = MeterLabel(tr("pixel_calibration.meter_off"))
        self._pixel_calibration_lbl.hide()
        h.addWidget(self._size_lbl)
        h.addWidget(self._peak_lbl)
        h.addWidget(self._sharpness_spark)
        h.addWidget(self._sharpness_lbl)
        h.addWidget(self._pixel_calibration_lbl)
        h.addStretch()
        h.addWidget(self._fps_lbl)
        return bar

    def configure_camera(self, *, exposure_us: int, gain: float,
                         exp_range: tuple[int, int], gain_range: tuple[float, float],
                         max_val: int) -> None:
        """连接相机后调用，把当前曝光/增益值和上下限同步到 UI。"""
        self._max_val = int(max_val)
        self.sp_exp.blockSignals(True)
        self.sp_exp.setRange(int(exp_range[0]), int(exp_range[1]))
        self.sp_exp.setValue(int(exposure_us))
        self.sp_exp.setEnabled(True)
        self.btn_auto_exposure.setEnabled(True)
        self.btn_hardware_dark.setEnabled(True)
        self.sp_exp.blockSignals(False)
        self.sp_gain.blockSignals(True)
        self.sp_gain.setRange(float(gain_range[0]), float(gain_range[1]))
        self.sp_gain.setValue(float(gain))
        self.sp_gain.setEnabled(True)
        self.sp_gain.blockSignals(False)
        self._empty.setText(_empty_html("camera.waiting_frame", "camera.waiting_frame_hint"))
        self._image_stack.setCurrentWidget(self._empty)

    @Slot(object, float)
    def update_frame(
        self,
        frame: np.ndarray,
        ts: float,
        saturated: bool | None = None,
        display_white_level: float | None = None,
        peak: int | None = None,
    ) -> None:
        started = time.perf_counter()
        try:
            self._update_frame(
                frame,
                saturated=saturated,
                display_white_level=display_white_level,
                peak=peak,
            )
        finally:
            self._record_display_time((time.perf_counter() - started) * 1000.0)
            self.frame_displayed.emit()

    def diagnostics(self) -> dict[str, object]:
        avg = self._display_total_ms / max(1, self._displayed_frames)
        return {
            "displayed": self._displayed_frames,
            "display_last_ms": round(self._display_last_ms, 2),
            "display_avg_ms": round(avg, 2),
            "display_max_ms": round(self._display_max_ms, 2),
            "levels_set": self._levels_set,
            "recording": self._recording,
        }

    def current_raw_frame(self) -> np.ndarray | None:
        if self._last_raw_frame is None:
            return None
        return np.array(self._last_raw_frame, copy=True)

    def max_value(self) -> int:
        return int(self._max_val)

    def _record_display_time(self, elapsed_ms: float) -> None:
        self._displayed_frames += 1
        self._display_last_ms = elapsed_ms
        self._display_total_ms += elapsed_ms
        self._display_max_ms = max(self._display_max_ms, elapsed_ms)

    def _flush_fps(self) -> None:
        if not self._fps_dirty and not self._metrics_dirty:
            return
        self._fps_dirty = False
        self._metrics_dirty = False
        self._fps_lbl.setText(tr("camera.fps_val", fps=self._fps))
        self.metrics_changed.emit(self._last_peak, self._fps, self._last_saturated_status)

    def _update_frame(
        self,
        frame: np.ndarray,
        saturated: bool | None,
        display_white_level: float | None,
        peak: int | None,
    ) -> None:
        self._image_stack.setCurrentWidget(self._iv)
        self._last_raw_frame = frame
        self._enable_frame_actions()
        self._update_fps()
        self._show_frame(frame, display_white_level)

        if not self._levels_set:
            self._levels_set = True
        peak = int(frame.max()) if peak is None else int(peak)
        self._update_frame_metrics(frame, peak)
        sat = saturated if saturated is not None else is_sensor_saturated(frame, self._max_val)
        self._update_saturation_badge(sat)
        self._last_peak = peak
        self._last_saturated_status = bool(sat)
        self._metrics_dirty = True
        if self._line_roi is not None:
            self._refresh_line_profile()

    def _enable_frame_actions(self) -> None:
        if self.btn_snapshot.isEnabled():
            return
        self.btn_snapshot.setEnabled(True)
        self.btn_record.setEnabled(True)

    def _update_fps(self) -> None:
        now = time.perf_counter()
        if self._last_frame_t is not None:
            dt = now - self._last_frame_t
            if dt > 0:
                inst = 1.0 / dt
                self._fps = inst if self._fps <= 0 else 0.85 * self._fps + 0.15 * inst
        self._last_frame_t = now
        self._fps_dirty = True

    def _show_frame(self, frame: np.ndarray, display_white_level: float | None) -> None:
        if self._auto_levels:
            levels = self._auto_display_levels(frame)
        else:
            levels = (0, self._display_white_level(display_white_level))
        if self._levels_set:
            self._iv.imageItem.setImage(
                frame.T, autoLevels=False,
                levels=levels,
            )
            return
        self._iv.setImage(
            frame.T, autoLevels=False,
            levels=levels, autoHistogramRange=False,
        )

    def _auto_display_levels(self, frame: np.ndarray) -> tuple[float, float]:
        now = time.perf_counter()
        if self._auto_level_levels is not None and now - self._auto_level_last_ts < 0.25:
            return self._auto_level_levels
        lo, hi = np.percentile(frame, (0.1, 99.9))
        lo = float(lo)
        hi = float(hi)
        if hi <= lo:
            hi = lo + 1.0
        self._auto_level_levels = (lo, hi)
        self._auto_level_last_ts = now
        return self._auto_level_levels

    def _update_frame_metrics(self, frame: np.ndarray, peak: int) -> None:
        h, w = frame.shape[:2]
        self._size_lbl.setText(tr("camera.image_dims", w=w, h=h))
        self._peak_lbl.setText(tr("camera.peak_val", val=peak))
        if self._line_roi is not None:
            self._update_sharpness(frame)

    def _update_sharpness(self, frame: np.ndarray) -> None:
        score = brenner(frame)
        self._sharpness_window.append(score)
        self._sharpness_spark.push(score)
        best = max(self._sharpness_window) if self._sharpness_window else score
        self._sharpness_lbl.setText(f"sharp {score:.1f} / max {best:.1f}")

    def _update_saturation_badge(self, sat: bool) -> None:
        if sat != self._saturated:
            self._sat_badge.setVisible(sat)
            if sat:
                self._position_sat_badge()
                flash(self._sat_badge, low=0.2)
        self._saturated = sat

    def _display_white_level(self, value: float | None) -> float:
        if value is None:
            return float(self._max_val)
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"invalid display white level: {value!r}")
        return float(value)

    # ── colormap ─────────────────────────────────────────
    def _apply_colormap(self, name: str) -> None:
        cm = _resolve_colormap(name)
        if cm is None:
            return
        self._iv.setColorMap(cm)
        # ImageView.setColorMap 不一定会触发当前帧重绘，显式刷一次 LUT
        try:
            lut = cm.getLookupTable(0.0, 1.0, 256)
            self._iv.imageItem.setLookupTable(lut)
            self._iv.imageItem.update()
        except Exception:
            pass
        self._cmap_name = name

    def _on_cmap_changed(self, name: str) -> None:
        self._apply_colormap(name)
        self.colormap_changed.emit(self._cmap_name)

    def _on_auto_levels_toggled(self, on: bool) -> None:
        self._auto_levels = on
        self._auto_level_levels = None
        self._auto_level_last_ts = 0.0
        if self._settings is not None:
            self._settings.set_value("camera/auto_levels", on)
        if self._last_raw_frame is not None:
            self._levels_set = True
            self._show_frame(self._last_raw_frame, None)

    def set_exposure_value(self, exposure_us: int) -> None:
        self.sp_exp.blockSignals(True)
        self.sp_exp.setValue(int(exposure_us))
        self.sp_exp.blockSignals(False)

    def set_colormap(self, name: str) -> None:
        """外部按名字设 colormap（同步 UI 与图像）；未知名字静默忽略。"""
        if _resolve_colormap(name) is None:
            return
        self.cb_cmap.blockSignals(True)
        self.cb_cmap.setCurrentText(name)
        self.cb_cmap.blockSignals(False)
        self._apply_colormap(name)

    def configure_advanced(self, camera) -> None:
        """连接相机后调用：让 advanced bar 反映该相机的能力与当前值。"""
        self._advanced.configure(camera=camera)

    def set_gamma_enabled(self, enabled: bool) -> None:
        self._advanced.set_gamma_enabled(bool(enabled))

    # ── line profile (C.3) ────────────────────────────
    @Slot(bool)
    def _on_line_profile_toggled(self, on: bool) -> None:
        if on:
            self._enable_line_profile()
        else:
            self._disable_line_profile()

    def _enable_line_profile(self) -> None:
        if self._line_roi is not None:
            return
        from .line_profile_dialog import LineProfileDialog
        self._sharpness_lbl.show()
        # 默认线段放在图像中间偏右下, 端点离边 20%
        frame = self._last_raw_frame
        if frame is not None:
            h, w = frame.shape[:2]
            x0, y0 = w * 0.3, h * 0.5
            x1, y1 = w * 0.7, h * 0.5
        else:
            x0, y0, x1, y1 = 50.0, 100.0, 150.0, 100.0
        roi = pg.LineSegmentROI(
            positions=[(x0, y0), (x1, y1)],
            pen=pg.mkPen(theme.ACCENT, width=2),
            hoverPen=pg.mkPen(theme.DANGER, width=2),
            movable=True,
        )
        self._iv.view.addItem(roi)
        self._line_roi = roi
        if self._line_dialog is None:
            self._line_dialog = LineProfileDialog(self.window())
            self._line_dialog.pixel_calibration_requested.connect(
                self._on_pixel_calibration_requested,
            )
        self._line_dialog.show()
        self._line_dialog.raise_()
        roi.sigRegionChanged.connect(self._refresh_line_profile)
        self._refresh_line_profile()

    def _disable_line_profile(self) -> None:
        if self._line_roi is not None:
            try:
                self._iv.view.removeItem(self._line_roi)
            except Exception:  # noqa: BLE001
                pass
            try:
                self._line_roi.sigRegionChanged.disconnect(self._refresh_line_profile)
            except (RuntimeError, TypeError):
                pass
            self._line_roi = None
        if self._line_dialog is not None:
            self._line_dialog.hide()
        self._sharpness_lbl.hide()
        # 离开线轮廓模式时清掉趋势/历史，避免下次启用看到陈旧数据。
        self._sharpness_window.clear()
        self._sharpness_spark.clear()

    def _refresh_line_profile(self) -> None:
        if self._line_roi is None or self._line_dialog is None:
            return
        frame = self._last_raw_frame
        if frame is None:
            return
        # ROI 端点是 (x, y) — 而 ImageView 显示用了 frame.T, 视图坐标 = (col, row) = (x_img, y_img)
        pts = self._line_roi.getLocalHandlePositions()
        # 转 scene/world 坐标 (ROI 自身可能有平移/旋转)
        endpoints = []
        for _name, pt in pts:
            mapped = self._line_roi.mapToParent(pt)
            endpoints.append((float(mapped.x()), float(mapped.y())))
        if len(endpoints) < 2:
            return
        # 因为我们 setImage(frame.T), 视图 X = image cols, Y = image rows → 直接对原 frame 取样
        self._line_dialog.update_profile(frame, endpoints[0], endpoints[1])

    def _on_advanced_toggled(self, on: bool) -> None:
        self._advanced.setVisible(on)
        self.btn_advanced.setText(("▴ " if on else "▾ ") + tr("camera.advanced"))

    def _position_sat_badge(self) -> None:
        b = self._sat_badge
        b.adjustSize()
        b.move(self._image_host.width() - b.width() - 12, 12)
        b.raise_()

    def _tool_button(self, label: str, *, checkable: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setText(label)
        btn.setCheckable(checkable)
        btn.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT1};border:1px solid {theme.BORDER0};"
            f"background:{theme.HIGHLIGHT};padding:4px 8px;"
            f"font-family:'{theme.SANS}',sans-serif;font-size:{theme.SIZE_CONTROL};letter-spacing:1px;"
            "font-weight:600;min-height:28px;}"
            f"QToolButton:hover{{background:{theme.BG2};border-color:{theme.ACCENT};}}"
            f"QToolButton:disabled{{color:{theme.TEXT3};border-color:{theme.BORDER0};}}"
            f"QToolButton:checked{{color:{theme.ON_ACCENT};background:{theme.ACCENT};"
            f"border-color:{theme.ACCENT};}}"
        )
        return btn

    def _action_button(self, label: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(label)
        btn.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT1};border:1px solid {theme.BORDER0};"
            f"background:{theme.HIGHLIGHT};padding:4px 12px;"
            f"font-family:'{theme.SANS}',sans-serif;font-size:{theme.SIZE_CONTROL};letter-spacing:1px;"
            "font-weight:600;min-height:28px;}"
            f"QToolButton:hover{{background:{theme.BG2};border-color:{theme.ACCENT};}}"
            f"QToolButton:disabled{{color:{theme.TEXT3};border-color:{theme.BORDER0};}}"
            f"QToolButton:checked{{color:{theme.ON_ACCENT};background:{theme.DANGER};"
            f"border-color:{theme.DANGER};}}"
        )
        return btn

    @Slot()
    def _emit_snapshot(self) -> None:
        if self._last_raw_frame is None:
            return
        self.snapshot_requested.emit(np.array(self._last_raw_frame, copy=True), self._cmap_name)

    @Slot(bool)
    def _on_record_toggled(self, on: bool) -> None:
        self._recording = on
        self.btn_record.setText(tr("camera.recording") if on else tr("camera.record"))
        self.record_toggled.emit(on)

    def set_recording_state(self, recording: bool) -> None:
        """外部 (app.py) 因为 IO 失败回滚 toggle 用。"""
        self.btn_record.blockSignals(True)
        self.btn_record.setChecked(recording)
        self._on_record_toggled(recording)
        self.btn_record.blockSignals(False)

    def bind_settings(self, settings) -> None:
        """把 colormap 选择持久化到 QSettings。"""
        self._settings = settings
        settings.bind_combo("camera/colormap", self.cb_cmap)
        self._restore_auto_levels()
        self.refresh_pixel_calibration_status()

    def _restore_auto_levels(self) -> None:
        if self._settings is None:
            return
        val = self._settings._settings.value("camera/auto_levels", self._auto_levels)
        on = (
            bool(val) if isinstance(val, bool)
            else str(val).lower() in {"1", "true", "yes", "on"}
        )
        self._auto_levels = on
        self.btn_auto_levels.setChecked(on)

    def refresh_pixel_calibration_status(self) -> None:
        if self._settings is None:
            return
        try:
            calibration = pixel_calibration_from_settings(
                self._settings.pixel_calibration_config(),
            )
        except Exception as exc:  # noqa: BLE001
            self._pixel_calibration_lbl.setText(tr("pixel_calibration.meter_invalid", msg=str(exc)))
            self._pixel_calibration_lbl.show()
            return
        if calibration is None:
            self._pixel_calibration_lbl.hide()
            self._pixel_calibration_lbl.setText(tr("pixel_calibration.meter_off"))
            return
        self._pixel_calibration_lbl.setText(
            tr("pixel_calibration.meter_value", um=calibration.microns_per_pixel),
        )
        self._pixel_calibration_lbl.show()

    def _on_pixel_calibration_requested(self, line_length_px: float, line_length_um: float) -> None:
        if self._settings is None:
            QMessageBox.warning(self, tr("common.warning"), tr("pixel_calibration.no_settings"))
            return
        try:
            self._settings.set_line_pixel_calibration(
                line_length_px=line_length_px,
                line_length_um=line_length_um,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("common.warning"), str(exc))
            return
        self.refresh_pixel_calibration_status()
        QMessageBox.information(
            self,
            tr("settings.title"),
            tr("pixel_calibration.line_applied", px=line_length_px, um=line_length_um),
        )

    def reset(self) -> None:
        self._size_lbl.setText("image ─×─")
        self._peak_lbl.setText(tr("camera.peak") + " ─")
        self._fps_lbl.setText("─.─ fps")
        self._sharpness_lbl.setText("sharp ─ / max ─")
        self._sharpness_spark.clear()
        self._sat_badge.hide()
        self._saturated = False
        self._levels_set = False
        self._last_frame_t = None
        self._fps = 0.0
        self._fps_dirty = False
        self._metrics_dirty = False
        self._last_peak = 0
        self._last_saturated_status = False
        self._sharpness_window.clear()
        self._last_raw_frame = None
        self.sp_exp.setEnabled(False)
        self.btn_auto_exposure.setEnabled(False)
        self.sp_gain.setEnabled(False)
        self.btn_snapshot.setEnabled(False)
        if self._recording:
            self.set_recording_state(False)
        self.btn_record.setEnabled(False)
        self.btn_hardware_dark.setEnabled(False)
        self._advanced.reset()
        self._empty.setText(_empty_html("camera.no_signal", "camera.no_signal_hint"))
        self._image_stack.setCurrentWidget(self._empty)
        # 关闭 line profile (避免空图时点击端点崩)
        if self.btn_line_profile.isChecked():
            self.btn_line_profile.setChecked(False)

    def toggle_fullscreen(self) -> None:
        """F11 切换: 把整个 CameraView reparent 成 top-level 窗口 + showFullScreen。"""
        if self.isFullScreen():
            self._exit_fullscreen(); return
        self._fs_parent = self.parentWidget()
        self.setParent(None)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle("Camera — Fullscreen (Esc 退出)")
        self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if not self.isFullScreen(): return
        self.setWindowFlag(Qt.Window, False)
        if self._fs_parent is not None:
            self.setParent(self._fs_parent)
            layout = self._fs_parent.layout()
            if layout is not None: layout.addWidget(self)
            self.show()
        self.showNormal()

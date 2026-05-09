"""实时相机画面 — 浅色绘图画布 + 曝光 / 增益 / 饱和指示。"""

from __future__ import annotations

import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QStackedLayout,
    QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .camera_advanced import CameraAdvancedBar
from .colormap_resolver import resolve_colormap as _resolve_colormap
from .motion import flash
from .widgets import HintLabel, MeterLabel


EMPTY_DISCONNECTED_TEXT = "NO SIGNAL · connect camera"
EMPTY_WAITING_TEXT = "WAITING FOR FRAME"

CAMERA_CMAPS = ("viridis", "gray", "hot", "rainbow", "magma", "inferno", "plasma")
DEFAULT_CMAP = "gray"


class CameraView(QWidget):
    exposure_changed = Signal(int)        # us
    gain_changed = Signal(float)
    colormap_changed = Signal(str)
    gamma_changed = Signal(float)
    black_level_changed = Signal(int)
    frame_rate_changed = Signal(float)
    pixel_format_changed = Signal(str)
    metrics_changed = Signal(int, float, bool)

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
        self._cmap_name = DEFAULT_CMAP
        self._apply_colormap(DEFAULT_CMAP)
        self._empty = self._build_empty_state(EMPTY_DISCONNECTED_TEXT)
        self._image_stack = QStackedLayout()
        self._image_stack.addWidget(self._empty)
        self._image_stack.addWidget(self._iv)
        layout.addLayout(self._image_stack, stretch=1)

        layout.addWidget(self._build_meter_bar())

        self._frames = 0
        self._t0 = time.time()
        self._fps = 0.0
        self._levels_set = False
        self._max_val = 255
        self._saturated = False

    def _build_empty_state(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color:{theme.TEXT3};background:{theme.BG0};"
            "font-family:'Iosevka Term',monospace;font-size:12px;"
            "font-weight:500;letter-spacing:1px;"
        )
        return label

    def _build_exposure_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.BG0};border-bottom:1px solid {theme.BORDER0};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(10)

        h.addWidget(HintLabel("exposure time"))
        self.sp_exp = QSpinBox()
        self.sp_exp.setRange(1, 1_000_000)
        self.sp_exp.setValue(10_000)
        self.sp_exp.setMinimumWidth(86)
        self.sp_exp.setSuffix(" µs")
        self.sp_exp.setButtonSymbols(QSpinBox.NoButtons)
        self.sp_exp.setEnabled(False)
        self.sp_exp.editingFinished.connect(lambda: self.exposure_changed.emit(self.sp_exp.value()))
        h.addWidget(self.sp_exp)

        h.addSpacing(12)
        h.addWidget(HintLabel("gain"))
        self.sp_gain = QDoubleSpinBox()
        self.sp_gain.setRange(0.0, 64.0)
        self.sp_gain.setValue(1.0)
        self.sp_gain.setDecimals(2)
        self.sp_gain.setSingleStep(0.1)
        self.sp_gain.setMinimumWidth(70)
        self.sp_gain.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.sp_gain.setEnabled(False)
        self.sp_gain.editingFinished.connect(lambda: self.gain_changed.emit(self.sp_gain.value()))
        h.addWidget(self.sp_gain)

        h.addSpacing(12)
        h.addWidget(HintLabel("colormap"))
        self.cb_cmap = QComboBox()
        self.cb_cmap.addItems(CAMERA_CMAPS)
        self.cb_cmap.setCurrentText(DEFAULT_CMAP)
        self.cb_cmap.setMinimumWidth(92)
        self.cb_cmap.currentTextChanged.connect(self._on_cmap_changed)
        h.addWidget(self.cb_cmap)

        h.addSpacing(8)
        self.btn_advanced = QToolButton()
        self.btn_advanced.setText("▾ advanced")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT1};border:1px solid {theme.BORDER0};"
            f"background:{theme.BG0};padding:2px 10px;"
            "font-family:'Inter',sans-serif;font-size:10px;letter-spacing:1px;"
            "font-weight:600;}"
            f"QToolButton:hover{{background:{theme.BG1};border-color:{theme.TEXT2};}}"
            f"QToolButton:checked{{color:{theme.TEXT0};background:{theme.BG1};"
            f"border-color:{theme.TEXT2};}}"
        )
        self.btn_advanced.toggled.connect(self._on_advanced_toggled)
        h.addWidget(self.btn_advanced)

        h.addStretch()
        self._sat_lbl = QLabel("")
        self._sat_lbl.setStyleSheet(
            f"color:{theme.DANGER};font-family:'Iosevka Term',monospace;"
            "font-size:11px;font-weight:600;letter-spacing:1px;"
        )
        h.addWidget(self._sat_lbl)
        return bar

    def _build_meter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.BG0};border-top:1px solid {theme.BORDER0};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(20)
        self._size_lbl = MeterLabel("image ─×─")
        self._peak_lbl = MeterLabel("peak ─")
        self._fps_lbl = MeterLabel("─.─ fps")
        h.addWidget(self._size_lbl)
        h.addWidget(self._peak_lbl)
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
        self.sp_exp.blockSignals(False)
        self.sp_gain.blockSignals(True)
        self.sp_gain.setRange(float(gain_range[0]), float(gain_range[1]))
        self.sp_gain.setValue(float(gain))
        self.sp_gain.setEnabled(True)
        self.sp_gain.blockSignals(False)
        self._empty.setText(EMPTY_WAITING_TEXT)
        self._image_stack.setCurrentWidget(self._empty)

    @Slot(object, float)
    def update_frame(self, frame: np.ndarray, ts: float) -> None:
        self._image_stack.setCurrentWidget(self._iv)
        self._frames += 1
        elapsed = time.time() - self._t0
        if elapsed >= 0.5:
            self._fps = self._frames / elapsed
            self._frames = 0
            self._t0 = time.time()

        if not self._levels_set:
            self._iv.setImage(
                frame.T, autoLevels=False,
                levels=(0, self._max_val), autoHistogramRange=False,
            )
            self._levels_set = True
        else:
            self._iv.setImage(
                frame.T, autoLevels=False, autoRange=False,
                levels=(0, self._max_val), autoHistogramRange=False,
            )

        peak = int(frame.max())
        h, w = frame.shape[:2]
        self._size_lbl.setText(f"image {w}×{h}")
        self._peak_lbl.setText(f"peak {peak:>5d}")
        self._fps_lbl.setText(f"{self._fps:5.1f} fps")
        # 饱和：≥ 99% 满量程 视为饱和
        sat = peak >= int(self._max_val * 0.99)
        self._sat_lbl.setText("SATURATED" if sat else "")
        if sat and not self._saturated:
            flash(self._sat_lbl, low=0.2)
        self._saturated = sat
        self.metrics_changed.emit(peak, self._fps, sat)

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

    def _on_advanced_toggled(self, on: bool) -> None:
        self._advanced.setVisible(on)
        self.btn_advanced.setText("▴ advanced" if on else "▾ advanced")

    def bind_settings(self, settings) -> None:
        """把 colormap 选择持久化到 QSettings。"""
        settings.bind_combo("camera/colormap", self.cb_cmap)

    def reset(self) -> None:
        self._size_lbl.setText("image ─×─")
        self._peak_lbl.setText("peak ─")
        self._fps_lbl.setText("─.─ fps")
        self._sat_lbl.setText("")
        self._saturated = False
        self._levels_set = False
        self._frames = 0
        self._fps = 0.0
        self.sp_exp.setEnabled(False)
        self.sp_gain.setEnabled(False)
        self._advanced.reset()
        self._empty.setText(EMPTY_DISCONNECTED_TEXT)
        self._image_stack.setCurrentWidget(self._empty)

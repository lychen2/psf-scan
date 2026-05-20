"""Camera advanced controls bar.

折叠抽屉式：默认隐藏，点 chevron 展开。两行布局：
  Row 1: gamma + black level (曝光相关)
  Row 2: fps + pixel format (图像相关)

每个控件按相机能力（``camera.gamma_range`` 等返回 None 视为不支持）自动启停。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import HintLabel
from ..core.i18n import tr

ROW_HEIGHT = 26


class CameraAdvancedBar(QWidget):
    """gamma / black + fps / pixel 两行。"""

    gamma_changed = Signal(float)
    black_level_changed = Signal(int)
    frame_rate_changed = Signal(float)
    pixel_format_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{theme.BG0};border-bottom:1px solid {theme.BORDER0};"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.G_8, theme.G_4, theme.G_8, theme.G_4)
        outer.setSpacing(theme.G_4)

        # Row 1 — 曝光相关 (gamma + black level)
        row1 = QHBoxLayout()
        row1.setSpacing(theme.G_8)
        row1.addWidget(HintLabel("gamma"))
        self.sp_gamma = _dspin(0.10, 4.00, 1.00, 0.05, 2, width=64)
        self.sp_gamma.setToolTip(tr("tip.gamma"))
        self.sp_gamma.editingFinished.connect(
            lambda: self.gamma_changed.emit(self.sp_gamma.value())
        )
        row1.addWidget(self.sp_gamma)
        row1.addSpacing(theme.G_16)
        row1.addWidget(HintLabel("black"))
        self.sp_black = _ispin(0, 4095, 0, width=68)
        self.sp_black.setToolTip(tr("tip.black_level"))
        self.sp_black.editingFinished.connect(
            lambda: self.black_level_changed.emit(self.sp_black.value())
        )
        row1.addWidget(self.sp_black)
        row1.addStretch()
        outer.addLayout(row1)

        # Row 2 — 图像相关 (fps + pixel format)
        row2 = QHBoxLayout()
        row2.setSpacing(theme.G_8)
        row2.addWidget(HintLabel("fps"))
        self.sp_fps = _dspin(1.0, 240.0, 30.0, 1.0, 1, width=68)
        self.sp_fps.setToolTip(tr("tip.frame_rate"))
        self.sp_fps.editingFinished.connect(
            lambda: self.frame_rate_changed.emit(self.sp_fps.value())
        )
        row2.addWidget(self.sp_fps)
        row2.addSpacing(theme.G_16)
        row2.addWidget(HintLabel("pixel"))
        self.cb_pixel = QComboBox()
        self.cb_pixel.setMinimumWidth(96)
        self.cb_pixel.setToolTip(tr("tip.pixel_format"))
        self.cb_pixel.currentTextChanged.connect(
            lambda s: self.pixel_format_changed.emit(s)
        )
        row2.addWidget(self.cb_pixel)
        row2.addStretch()
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet(
            f"color:{theme.TEXT3};font-family:'Iosevka Term',monospace;font-size:{theme.SIZE_METER};"
        )
        row2.addWidget(self._lbl_status)
        outer.addLayout(row2)

        self.setMinimumHeight(ROW_HEIGHT * 2 + 8)

        self._gamma_supported = False
        self._black_supported = False
        self._fps_supported = False
        self._pixel_supported = False
        self._gamma_enabled_by_settings = True
        self._set_all_enabled(False)

    def configure(self, *, camera) -> None:
        """连接相机后调用，按相机能力填充控件可用性、范围与当前值。"""
        gamma_r = camera.gamma_range()
        gamma = camera.get_gamma()
        self._gamma_supported = gamma_r is not None and gamma is not None
        self._fill_dspin(self.sp_gamma, gamma_r, gamma)
        self._apply_gamma_enabled_state()

        black_r = camera.black_level_range()
        black = camera.get_black_level()
        self._black_supported = black_r is not None and black is not None
        self._fill_ispin(self.sp_black, black_r, black)

        fps_r = camera.frame_rate_range()
        fps = camera.get_frame_rate()
        self._fps_supported = fps_r is not None and fps is not None
        self._fill_dspin(self.sp_fps, fps_r, fps)

        formats = camera.pixel_formats()
        cur = camera.get_pixel_format()
        self.cb_pixel.blockSignals(True)
        self.cb_pixel.clear()
        if formats:
            self.cb_pixel.addItems(list(formats))
            if cur in formats:
                self.cb_pixel.setCurrentText(cur)
        self._pixel_supported = bool(formats)
        self.cb_pixel.setEnabled(self._pixel_supported)
        self.cb_pixel.blockSignals(False)

        self._update_status()

    def set_gamma_enabled(self, enabled: bool) -> None:
        self._gamma_enabled_by_settings = bool(enabled)
        self._apply_gamma_enabled_state()
        self._update_status()

    def reset(self) -> None:
        self._set_all_enabled(False)
        self.cb_pixel.blockSignals(True)
        self.cb_pixel.clear()
        self.cb_pixel.blockSignals(False)
        self._gamma_supported = False
        self._black_supported = False
        self._fps_supported = False
        self._pixel_supported = False
        self._lbl_status.setText("")

    def _fill_dspin(self, spin: QDoubleSpinBox, rng, value) -> None:
        if rng is None or value is None:
            spin.setEnabled(False)
            return
        spin.blockSignals(True)
        spin.setRange(float(rng[0]), float(rng[1]))
        spin.setValue(float(value))
        spin.setEnabled(True)
        spin.blockSignals(False)

    def _fill_ispin(self, spin: QSpinBox, rng, value) -> None:
        if rng is None or value is None:
            spin.setEnabled(False)
            return
        spin.blockSignals(True)
        spin.setRange(int(rng[0]), int(rng[1]))
        spin.setValue(int(value))
        spin.setEnabled(True)
        spin.blockSignals(False)

    def _set_all_enabled(self, on: bool) -> None:
        for w in (self.sp_gamma, self.sp_black, self.sp_fps, self.cb_pixel):
            w.setEnabled(on)

    def _apply_gamma_enabled_state(self) -> None:
        self.sp_gamma.setEnabled(self._gamma_supported and self._gamma_enabled_by_settings)

    def _update_status(self) -> None:
        unsupported = [
            name for name, supported in (
                ("γ", self._gamma_supported),
                ("black", self._black_supported),
                ("fps", self._fps_supported),
                ("pixel", self._pixel_supported),
            )
            if not supported
        ]
        if unsupported:
            self._lbl_status.setText("not supported: " + ", ".join(unsupported))
            return
        if self._gamma_supported and not self._gamma_enabled_by_settings:
            self._lbl_status.setText("gamma disabled in settings")
            return
        self._lbl_status.setText("")


def _dspin(lo: float, hi: float, value: float, step: float, decimals: int, *, width: int) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setMinimumWidth(width)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    return s


def _ispin(lo: int, hi: int, value: int, *, width: int) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    s.setMinimumWidth(width)
    s.setButtonSymbols(QSpinBox.NoButtons)
    return s

"""Camera advanced controls bar.

折叠抽屉式：默认隐藏，点 chevron 展开。包含 gamma / black level / frame rate /
pixel format 四类高级参数。每个控件按相机能力（``camera.gamma_range`` 等返回
None 视为不支持）自动启停。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import HintLabel

ROW_HEIGHT = 28


class CameraAdvancedBar(QWidget):
    """gamma / black / fps / pixel format 一行排开。"""

    gamma_changed = Signal(float)
    black_level_changed = Signal(int)
    frame_rate_changed = Signal(float)
    pixel_format_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{theme.BG0};border-bottom:1px solid {theme.BORDER0};"
        )
        self.setFixedHeight(ROW_HEIGHT)

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 2, 8, 2)
        h.setSpacing(10)

        h.addWidget(HintLabel("gamma"))
        self.sp_gamma = _dspin(0.10, 4.00, 1.00, 0.05, 2, width=64)
        self.sp_gamma.editingFinished.connect(
            lambda: self.gamma_changed.emit(self.sp_gamma.value())
        )
        h.addWidget(self.sp_gamma)

        h.addSpacing(12)
        h.addWidget(HintLabel("black"))
        self.sp_black = _ispin(0, 4095, 0, width=68)
        self.sp_black.editingFinished.connect(
            lambda: self.black_level_changed.emit(self.sp_black.value())
        )
        h.addWidget(self.sp_black)

        h.addSpacing(12)
        h.addWidget(HintLabel("fps"))
        self.sp_fps = _dspin(1.0, 240.0, 30.0, 1.0, 1, width=68)
        self.sp_fps.editingFinished.connect(
            lambda: self.frame_rate_changed.emit(self.sp_fps.value())
        )
        h.addWidget(self.sp_fps)

        h.addSpacing(12)
        h.addWidget(HintLabel("pixel"))
        self.cb_pixel = QComboBox()
        self.cb_pixel.setMinimumWidth(96)
        self.cb_pixel.currentTextChanged.connect(
            lambda s: self.pixel_format_changed.emit(s)
        )
        h.addWidget(self.cb_pixel)

        h.addStretch()
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet(
            f"color:{theme.TEXT3};font-family:'Iosevka Term',monospace;font-size:10px;"
        )
        h.addWidget(self._lbl_status)

        self._set_all_enabled(False)

    def configure(self, *, camera) -> None:
        """连接相机后调用，按相机能力填充控件可用性、范围与当前值。"""
        gamma_r = camera.gamma_range()
        gamma = camera.get_gamma()
        self._fill_dspin(self.sp_gamma, gamma_r, gamma)

        black_r = camera.black_level_range()
        black = camera.get_black_level()
        self._fill_ispin(self.sp_black, black_r, black)

        fps_r = camera.frame_rate_range()
        fps = camera.get_frame_rate()
        self._fill_dspin(self.sp_fps, fps_r, fps)

        formats = camera.pixel_formats()
        cur = camera.get_pixel_format()
        self.cb_pixel.blockSignals(True)
        self.cb_pixel.clear()
        if formats:
            self.cb_pixel.addItems(list(formats))
            if cur in formats:
                self.cb_pixel.setCurrentText(cur)
        self.cb_pixel.setEnabled(bool(formats))
        self.cb_pixel.blockSignals(False)

        self._update_status()

    def reset(self) -> None:
        self._set_all_enabled(False)
        self.cb_pixel.blockSignals(True)
        self.cb_pixel.clear()
        self.cb_pixel.blockSignals(False)
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

    def _update_status(self) -> None:
        unsupported = [
            name for name, w in (("γ", self.sp_gamma), ("black", self.sp_black),
                                  ("fps", self.sp_fps), ("pixel", self.cb_pixel))
            if not w.isEnabled()
        ]
        self._lbl_status.setText("not supported: " + ", ".join(unsupported) if unsupported else "")


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

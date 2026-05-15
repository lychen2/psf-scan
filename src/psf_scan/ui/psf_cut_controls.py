"""XYZ cut sliders for PSF volume rendering — slider + spinbox per axis."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSlider, QSpinBox, QWidget

from ..core.i18n import tr
from .widgets import HintLabel


def _link_pair(slider: QSlider, spin: QSpinBox, on_change: Callable[[], None]) -> None:
    """Bi-directional sync between a slider and a spin box. Each user edit fires ``on_change`` exactly once."""
    def from_slider(v: int) -> None:
        spin.blockSignals(True); spin.setValue(v); spin.blockSignals(False)
        on_change()

    def from_spin(v: int) -> None:
        slider.blockSignals(True); slider.setValue(v); slider.blockSignals(False)
        on_change()

    slider.valueChanged.connect(from_slider)
    spin.valueChanged.connect(from_spin)


class VolumeCutControls(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._x_slider = QSlider(Qt.Horizontal)
        self._x_spin = QSpinBox()
        self._y_slider = QSlider(Qt.Horizontal)
        self._y_spin = QSpinBox()
        self._z_slider = QSlider(Qt.Horizontal)
        self._z_spin = QSpinBox()
        for ss in (self._x_slider, self._y_slider, self._z_slider):
            ss.setEnabled(False)
        for sb in (self._x_spin, self._y_spin, self._z_spin):
            sb.setEnabled(False)
            sb.setButtonSymbols(QSpinBox.NoButtons)
            sb.setMaximumWidth(60)
        for slider, spin in self._pairs():
            _link_pair(slider, spin, self.changed.emit)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for label, slider, spin in (
            (tr("psf.x_cut"), self._x_slider, self._x_spin),
            (tr("psf.y_cut"), self._y_slider, self._y_spin),
            (tr("psf.z_cut"), self._z_slider, self._z_spin),
        ):
            layout.addWidget(HintLabel(label))
            layout.addWidget(slider, stretch=1)
            layout.addWidget(spin)

    def _pairs(self) -> tuple[tuple[QSlider, QSpinBox], ...]:
        return (
            (self._x_slider, self._x_spin),
            (self._y_slider, self._y_spin),
            (self._z_slider, self._z_spin),
        )

    def set_shape(self, shape: tuple[int, int, int]) -> None:
        depth, height, width = shape
        for slider, spin, maximum in (
            (self._x_slider, self._x_spin, width - 1),
            (self._y_slider, self._y_spin, height - 1),
            (self._z_slider, self._z_spin, depth - 1),
        ):
            for w in (slider, spin):
                w.blockSignals(True)
                w.setRange(0, maximum)
                w.setEnabled(maximum > 0)
                w.blockSignals(False)

    def set_values(self, x: int, y: int, z: int) -> None:
        for slider, spin, value in (
            (self._x_slider, self._x_spin, x),
            (self._y_slider, self._y_spin, y),
            (self._z_slider, self._z_spin, z),
        ):
            for w in (slider, spin):
                w.blockSignals(True)
                w.setValue(int(value))
                w.blockSignals(False)

    def maxima(self) -> tuple[int, int, int]:
        return (self._x_slider.maximum(), self._y_slider.maximum(), self._z_slider.maximum())

    def ratios(self) -> tuple[float, float, float]:
        return tuple(
            slider.value() / max(1, slider.maximum())
            for slider in (self._x_slider, self._y_slider, self._z_slider)
        )

    def x_value(self) -> int:
        return self._x_slider.value()

    def y_value(self) -> int:
        return self._y_slider.value()

    def z_value(self) -> int:
        return self._z_slider.value()

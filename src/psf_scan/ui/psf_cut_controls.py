"""XYZ cut sliders for PSF volume rendering."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSlider, QWidget

from .widgets import HintLabel


class VolumeCutControls(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._x = _slider()
        self._y = _slider()
        self._z = _slider()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for label, slider in (("x cut", self._x), ("y cut", self._y), ("z cut", self._z)):
            layout.addWidget(HintLabel(label))
            layout.addWidget(slider, stretch=1)
            slider.valueChanged.connect(self.changed)

    def set_shape(self, shape: tuple[int, int, int]) -> None:
        depth, height, width = shape
        for slider, maximum in ((self._x, width - 1), (self._y, height - 1), (self._z, depth - 1)):
            slider.blockSignals(True)
            slider.setRange(0, maximum)
            slider.setEnabled(maximum > 0)
            slider.blockSignals(False)

    def set_values(self, x: int, y: int, z: int) -> None:
        for slider, value in ((self._x, x), (self._y, y), (self._z, z)):
            slider.blockSignals(True)
            slider.setValue(int(value))
            slider.blockSignals(False)

    def maxima(self) -> tuple[int, int, int]:
        return (self._x.maximum(), self._y.maximum(), self._z.maximum())

    def ratios(self) -> tuple[float, float, float]:
        return tuple(
            slider.value() / max(1, slider.maximum())
            for slider in (self._x, self._y, self._z)
        )

    def x_value(self) -> int:
        return self._x.value()

    def y_value(self) -> int:
        return self._y.value()

    def z_value(self) -> int:
        return self._z.value()


def _slider() -> QSlider:
    slider = QSlider(Qt.Horizontal)
    slider.setEnabled(False)
    return slider

"""SpinSlider — spin box + 同步 slider 的复合控件.

设计:
- 上层 QSpinBox / QDoubleSpinBox 精确输入, 下层 QSlider 拖拽提速.
- 内部一对值, 双向同步; 信号仅暴露 ``valueChanged``, 复用 spin 的契约 (QSettings.bind_spin 仍可用).
- 整数版 SpinSliderInt 和浮点版 SpinSliderDouble 分别继承基类.
- ``setRange``, ``setValue``, ``value`` 直接代理到 spin; slider 端按需做整数化 (浮点 ×100).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QSlider, QSpinBox, QVBoxLayout, QWidget,
)


SCALE = 1000.0  # 浮点 → slider 整数的放大倍数


class SpinSliderInt(QWidget):
    """整数版."""

    valueChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spin = QSpinBox()
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMaximumHeight(12)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.spin)
        layout.addWidget(self.slider)
        self.spin.valueChanged.connect(self._on_spin)
        self.slider.valueChanged.connect(self._on_slider)

    def setRange(self, lo: int, hi: int) -> None:
        self.spin.setRange(lo, hi)
        self.slider.setRange(lo, hi)

    def setValue(self, v: int) -> None:
        self.spin.setValue(int(v))

    def value(self) -> int:
        return self.spin.value()

    def setSuffix(self, s: str) -> None:
        self.spin.setSuffix(s)

    def setSingleStep(self, n: int) -> None:
        self.spin.setSingleStep(int(n))
        self.slider.setSingleStep(int(n))

    def setEnabled(self, on: bool) -> None:  # type: ignore[override]
        super().setEnabled(on)
        self.spin.setEnabled(on)
        self.slider.setEnabled(on)

    def _on_spin(self, v: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_slider(self, v: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)


class SpinSliderDouble(QWidget):
    """浮点版 — slider 内部 ×1000 量化."""

    valueChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spin = QDoubleSpinBox()
        self.spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.spin.setDecimals(3)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMaximumHeight(12)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.spin)
        layout.addWidget(self.slider)
        self.spin.valueChanged.connect(self._on_spin)
        self.slider.valueChanged.connect(self._on_slider)

    def setRange(self, lo: float, hi: float) -> None:
        self.spin.setRange(lo, hi)
        self.slider.setRange(int(lo * SCALE), int(hi * SCALE))

    def setValue(self, v: float) -> None:
        self.spin.setValue(float(v))

    def value(self) -> float:
        return self.spin.value()

    def setDecimals(self, n: int) -> None:
        self.spin.setDecimals(n)

    def setSingleStep(self, s: float) -> None:
        self.spin.setSingleStep(float(s))

    def setSuffix(self, s: str) -> None:
        self.spin.setSuffix(s)

    def setEnabled(self, on: bool) -> None:  # type: ignore[override]
        super().setEnabled(on)
        self.spin.setEnabled(on)
        self.slider.setEnabled(on)

    def _on_spin(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(v * SCALE))
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_slider(self, v: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(v / SCALE)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v / SCALE)

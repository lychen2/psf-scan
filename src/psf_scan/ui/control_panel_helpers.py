"""Small widget factories for the scan control panel."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLayout, QPushButton, QSpinBox,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import HintLabel, SectionHeader


def section(title: str, items: list) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.G_8)
    layout.addWidget(SectionHeader(title))
    for item in items:
        layout.addLayout(item) if isinstance(item, QLayout) else layout.addWidget(item)
    return widget


def row(*items, _stretch: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(theme.G_8)
    for item in items:
        layout.addSpacing(item) if isinstance(item, int) else layout.addWidget(item)
    if _stretch:
        layout.addStretch()
    return layout


def row_widget(*items, _stretch: bool = False) -> QWidget:
    widget = QWidget()
    layout = row(*items, _stretch=_stretch)
    layout.setContentsMargins(0, 0, 0, 0)
    widget.setLayout(layout)
    return widget


def kv(label: str, widget: QWidget) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(theme.G_8)
    hint = HintLabel(label)
    hint.setMinimumWidth(78)
    layout.addWidget(hint)
    layout.addWidget(widget, stretch=1)
    return layout


def axis(name: str, control: QDoubleSpinBox) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.G_4)
    layout.addWidget(HintLabel(name))
    layout.addWidget(control)
    return widget


def dspin(lo, hi, val, *, enabled: bool = True) -> QDoubleSpinBox:
    control = QDoubleSpinBox()
    control.setRange(lo, hi)
    control.setValue(val)
    control.setDecimals(3)
    control.setSingleStep(0.1)
    control.setMinimumWidth(78)
    control.setEnabled(enabled)
    control.setButtonSymbols(QDoubleSpinBox.NoButtons)
    return control


def ispin(lo, hi, val, *, width: int = 80) -> QSpinBox:
    control = QSpinBox()
    control.setRange(lo, hi)
    control.setValue(val)
    control.setMinimumWidth(width)
    control.setButtonSymbols(QSpinBox.NoButtons)
    return control


def combo(items: list[str]) -> QComboBox:
    control = QComboBox()
    control.addItems(items)
    control.setMinimumWidth(110)
    control.setItemDelegate(QStyledItemDelegate(control))
    return control


def button(
    text: str,
    *,
    primary: bool = False,
    danger: bool = False,
    estop: bool = False,
    enabled: bool = True,
) -> QPushButton:
    control = QPushButton(text)
    if primary:
        control.setProperty("role", "primary")
    elif danger:
        control.setProperty("role", "danger")
    elif estop:
        control.setProperty("role", "estop")
    control.setEnabled(enabled)
    return control

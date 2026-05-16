"""PSF view compact control factories."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QStyledItemDelegate, QWidget,
)

from .motion import set_motion_visible


LEVEL_MIN = -1_000_000_000.0
LEVEL_MAX = 1_000_000_000.0


def combo(items: tuple[str, ...], width: int) -> QComboBox:
    control = QComboBox()
    control.addItems(items)
    control.setMinimumWidth(width)
    control.setItemDelegate(QStyledItemDelegate(control))
    return control


def check(text: str, checked: bool) -> QCheckBox:
    control = QCheckBox(text)
    control.setChecked(checked)
    return control


def dspin(
    value: float,
    *,
    lo: float = LEVEL_MIN,
    hi: float = LEVEL_MAX,
    step: float = 1.0,
    decimals: int = 1,
    width: int = 86,
) -> QDoubleSpinBox:
    control = QDoubleSpinBox()
    control.setRange(lo, hi)
    control.setDecimals(decimals)
    control.setSingleStep(step)
    control.setValue(value)
    control.setMinimumWidth(width)
    control.setButtonSymbols(QDoubleSpinBox.NoButtons)
    return control


def dspin2(
    value: float,
    *,
    lo: float = LEVEL_MIN,
    hi: float = LEVEL_MAX,
    step: float = 1.0,
    decimals: int = 2,
    width: int = 64,
) -> QDoubleSpinBox:
    return dspin(value, lo=lo, hi=hi, step=step, decimals=decimals, width=width)


def ispin(lo: int, hi: int, value: int, *, width: int = 54) -> QSpinBox:
    control = QSpinBox()
    control.setRange(lo, hi)
    control.setValue(value)
    control.setMinimumWidth(width)
    control.setButtonSymbols(QSpinBox.NoButtons)
    return control


def set_visible(widgets: tuple[QWidget, ...], visible: bool) -> None:
    for widget in widgets:
        set_motion_visible(widget, visible)

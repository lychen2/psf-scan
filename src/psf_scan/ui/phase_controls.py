"""Control strip for the PHASE workbench."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from ..core.phase import DEFAULT_FILTER_RADIUS_PX
from . import theme
from .control_panel_helpers import button
from .widgets import HintLabel, MeterLabel

VIEW_INTERFEROGRAM = "INTERFEROGRAM"
VIEW_FFT = "FFT"
VIEW_PHASE = "PHASE"
VIEW_CORRECTED = "CORRECTED"


class PhaseControls(QWidget):
    load_sample_requested = Signal()
    load_reference_requested = Signal()
    live_sample_requested = Signal()
    live_reference_requested = Signal()
    process_requested = Signal()
    save_requested = Signal()
    view_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PhaseControls")
        self.setStyleSheet(
            f"QWidget#PhaseControls{{background:{theme.BG0};"
            f"border-top:1px solid {theme.BORDER0};}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)
        root.addLayout(self._source_row())
        root.addLayout(self._process_row())
        root.addLayout(self._status_row())

    def _source_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        for widget in self._source_buttons():
            row.addWidget(widget)
        row.addSpacing(10)
        row.addWidget(HintLabel(tr("phase.view")))
        self.view_mode = QComboBox()
        self.view_mode.addItems((VIEW_INTERFEROGRAM, VIEW_FFT, VIEW_PHASE, VIEW_CORRECTED))
        self.view_mode.currentTextChanged.connect(lambda _text: self.view_changed.emit())
        row.addWidget(self.view_mode)
        row.addStretch()
        return row

    def _source_buttons(self) -> tuple[QPushButton, ...]:
        self.btn_load_sample = button(tr("phase.load_sample"), primary=True)
        self.btn_load_reference = button(tr("phase.load_reference"))
        self.btn_live_sample = button(tr("phase.live_sample"))
        self.btn_live_reference = button(tr("phase.live_reference"))
        self.btn_load_sample.clicked.connect(self.load_sample_requested.emit)
        self.btn_load_reference.clicked.connect(self.load_reference_requested.emit)
        self.btn_live_sample.clicked.connect(self.live_sample_requested.emit)
        self.btn_live_reference.clicked.connect(self.live_reference_requested.emit)
        return (
            self.btn_load_sample, self.btn_load_reference,
            self.btn_live_sample, self.btn_live_reference,
        )

    def _process_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.chk_reference = QCheckBox(tr("phase.reference_correction"))
        self.chk_auto = QCheckBox(tr("phase.auto_sideband"))
        self.chk_auto.setChecked(True)
        self.chk_unwrap = QCheckBox(tr("phase.unwrap"))
        for widget in (self.chk_reference, self.chk_auto, self.chk_unwrap):
            row.addWidget(widget)
        self._add_sideband_controls(row)
        self.btn_process = button(tr("phase.process"), primary=True)
        self.btn_save = button(tr("phase.save_result"))
        self.btn_process.clicked.connect(self.process_requested.emit)
        self.btn_save.clicked.connect(self.save_requested.emit)
        row.addWidget(self.btn_process)
        row.addWidget(self.btn_save)
        row.addStretch()
        return row

    def _add_sideband_controls(self, row: QHBoxLayout) -> None:
        self.sp_x = _spin(0.0, 100000.0, 0.0, "")
        self.sp_y = _spin(0.0, 100000.0, 0.0, "")
        self.sp_radius = _spin(2.0, 10000.0, DEFAULT_FILTER_RADIUS_PX, " px")
        self.sp_ref_sigma = _spin(0.0, 64.0, 0.0, " px")
        self.sp_ref_sigma.setToolTip(tr("phase.ref_sigma_tip"))
        for label, spin in ((tr("phase.sideband_x"), self.sp_x),
                            (tr("phase.sideband_y"), self.sp_y),
                            (tr("phase.radius"), self.sp_radius),
                            (tr("phase.ref_sigma"), self.sp_ref_sigma)):
            row.addWidget(HintLabel(label))
            row.addWidget(spin)

    def _status_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        self.lbl_status = MeterLabel(tr("phase.status_empty"))
        self.lbl_sample = MeterLabel(tr("phase.sample_empty"))
        self.lbl_reference = MeterLabel(tr("phase.reference_empty"))
        for widget in (self.lbl_status, self.lbl_sample, self.lbl_reference):
            row.addWidget(widget)
        row.addStretch()
        return row


def source_text(label: str, image: np.ndarray | None, source: str) -> str:
    if image is None:
        return f"{label} ─"
    h, w = image.shape[:2]
    return f"{label} {w}×{h} · {Path(source).name if source else 'live'}"


def _spin(lo: float, hi: float, value: float, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(lo, hi)
    spin.setDecimals(2)
    spin.setValue(value)
    spin.setSuffix(suffix)
    spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
    spin.setMinimumWidth(78)
    return spin

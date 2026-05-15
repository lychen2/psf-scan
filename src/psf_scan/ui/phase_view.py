"""Interactive off-axis interferogram phase workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from ..core.i18n import tr
from ..core.phase import (
    PhaseReconstructionParams, PhaseResult, PhaseSavePayload, Sideband,
    load_phase_image, reconstruct_off_axis_phase, save_phase_payload,
    wrapped_phase_difference,
)
from . import theme
from .phase_controls import (
    VIEW_CORRECTED, VIEW_FFT, VIEW_INTERFEROGRAM, VIEW_PHASE, PhaseControls,
    source_text,
)
from .phase_display import PhaseDisplay
from .settings import UserSettings

PHASE_LEVELS = (-np.pi, np.pi)


class PhaseView(QWidget):
    def __init__(self, *, live_frame_provider: Callable[[], np.ndarray | None] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.BG0};")
        self._live_frame_provider = live_frame_provider
        self._settings: UserSettings | None = None
        self._sample: np.ndarray | None = None
        self._reference: np.ndarray | None = None
        self._sample_source = ""
        self._reference_source = ""
        self._result: PhaseResult | None = None
        self._reference_result: PhaseResult | None = None
        self._corrected: np.ndarray | None = None
        self._build()

    def bind_settings(self, settings: UserSettings) -> None:
        self._settings = settings

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._display = PhaseDisplay()
        self._display.point_clicked.connect(self._on_display_clicked)
        self._controls_widget = PhaseControls()
        self._wire_controls()
        layout.addWidget(self._display, stretch=1)
        layout.addWidget(self._controls_widget)
        self._display.clear_display(tr("phase.empty"))

    def _wire_controls(self) -> None:
        c = self._controls_widget
        c.load_sample_requested.connect(lambda: self._load_file(sample=True))
        c.load_reference_requested.connect(lambda: self._load_file(sample=False))
        c.live_sample_requested.connect(lambda: self._load_live(sample=True))
        c.live_reference_requested.connect(lambda: self._load_live(sample=False))
        c.process_requested.connect(self._process)
        c.save_requested.connect(self._save)
        c.view_changed.connect(self._refresh_display)

    def _load_file(self, *, sample: bool) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("phase.open_title"), "", "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp)",
        )
        if not path:
            return
        self._set_image(load_phase_image(path), source=str(Path(path)), sample=sample)

    def _load_live(self, *, sample: bool) -> None:
        if self._live_frame_provider is None:
            self._warn(tr("phase.no_live_provider"))
            return
        frame = self._live_frame_provider()
        if frame is None:
            self._warn(tr("phase.no_live_frame"))
            return
        self._set_image(np.array(frame, copy=True), source=tr("phase.source_live"), sample=sample)

    def _set_image(self, image: np.ndarray, *, source: str, sample: bool) -> None:
        if sample:
            self._sample, self._sample_source = image, source
            self._result = None
            self._corrected = None
        else:
            self._reference, self._reference_source = image, source
            self._reference_result = None
            self._corrected = None
        self._update_source_labels()
        self._controls_widget.view_mode.setCurrentText(VIEW_INTERFEROGRAM)
        self._refresh_display()

    @Slot()
    def _process(self) -> None:
        if self._sample is None:
            self._warn(tr("phase.need_sample"))
            return
        if self._controls_widget.chk_reference.isChecked() and self._reference is None:
            self._warn(tr("phase.need_reference"))
            return
        try:
            self._process_images()
        except Exception as exc:  # noqa: BLE001
            self._warn(tr("phase.process_failed", msg=str(exc)))

    def _process_images(self) -> None:
        params = self._params(source=self._sample_source)
        self._result = reconstruct_off_axis_phase(self._sample, params)
        self._sync_sideband(self._result.sideband)
        self._reference_result = self._process_reference()
        self._corrected = self._correct_phase()
        self._controls_widget.lbl_status.setText(self._result_status())
        self._controls_widget.view_mode.setCurrentText(
            VIEW_CORRECTED if self._corrected is not None else VIEW_PHASE,
        )
        self._refresh_display()

    def _process_reference(self) -> PhaseResult | None:
        if not self._controls_widget.chk_reference.isChecked() or self._reference is None or self._result is None:
            return None
        params = PhaseReconstructionParams(
            sideband=self._result.sideband,
            auto_sideband=False,
            unwrap_phase=False,
            source=self._reference_source,
        )
        return reconstruct_off_axis_phase(self._reference, params)

    def _correct_phase(self) -> np.ndarray | None:
        if self._result is None or self._reference_result is None:
            return None
        return wrapped_phase_difference(
            self._result.wrapped_phase,
            self._reference_result.wrapped_phase,
            reference_smoothing_sigma_px=float(self._controls_widget.sp_ref_sigma.value()),
        )

    def _params(self, *, source: str) -> PhaseReconstructionParams:
        controls = self._controls_widget
        sideband = None if controls.chk_auto.isChecked() else self._sideband_from_controls()
        return PhaseReconstructionParams(
            sideband=sideband,
            auto_sideband=controls.chk_auto.isChecked(),
            unwrap_phase=controls.chk_unwrap.isChecked(),
            source=source,
        )

    def _sideband_from_controls(self) -> Sideband:
        c = self._controls_widget
        return Sideband(c.sp_x.value(), c.sp_y.value(), c.sp_radius.value())

    def _sync_sideband(self, sideband: Sideband) -> None:
        controls = self._controls_widget
        for spin, value in ((controls.sp_x, sideband.x), (controls.sp_y, sideband.y),
                            (controls.sp_radius, sideband.radius)):
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    def _refresh_display(self) -> None:
        mode = self._controls_widget.view_mode.currentText()
        if mode == VIEW_INTERFEROGRAM:
            self._show_interferogram()
        elif mode == VIEW_FFT:
            self._show_fft()
        elif mode == VIEW_PHASE:
            self._show_phase()
        else:
            self._show_corrected()

    def _show_interferogram(self) -> None:
        image = self._reference if (
            self._controls_widget.chk_reference.isChecked() and self._reference is not None
        ) else self._sample
        if image is None:
            self._display.clear_display(tr("phase.empty"))
            return
        self._display.set_image(image, title=tr("phase.interferogram_title"))

    def _show_fft(self) -> None:
        if self._result is None:
            self._display.clear_display(tr("phase.fft_empty"))
            return
        self._display.set_image(
            self._result.fft_magnitude,
            title=tr("phase.fft_title"),
            sideband=self._sideband_from_controls(),
        )

    def _show_phase(self) -> None:
        if self._result is None:
            self._display.clear_display(tr("phase.phase_empty"))
            return
        self._display.set_image(
            self._result.wrapped_phase,
            title=tr("phase.phase_title"),
            cmap_name="CET-L4",
            levels=PHASE_LEVELS,
        )

    def _show_corrected(self) -> None:
        if self._corrected is None:
            self._show_phase()
            return
        self._display.set_image(
            self._corrected,
            title=tr("phase.corrected_title"),
            cmap_name="CET-L4",
            levels=PHASE_LEVELS,
        )

    def _save(self) -> None:
        if self._settings is None or self._result is None:
            self._warn(tr("phase.nothing_to_save"))
            return
        payload = PhaseSavePayload(self._result, self._corrected, self._reference_result)
        try:
            target = save_phase_payload(self._settings.data_dir(), payload)
        except Exception as exc:  # noqa: BLE001
            self._warn(tr("phase.save_failed", msg=str(exc)))
            return
        self._controls_widget.lbl_status.setText(tr("phase.saved", name=target.name))

    def _update_source_labels(self) -> None:
        controls = self._controls_widget
        controls.lbl_sample.setText(source_text(tr("phase.sample"), self._sample, self._sample_source))
        controls.lbl_reference.setText(source_text(tr("phase.reference"), self._reference, self._reference_source))

    def _result_status(self) -> str:
        if self._result is None:
            return tr("phase.status_empty")
        sb = self._result.sideband
        return tr("phase.status_result", x=sb.x, y=sb.y, r=sb.radius)

    def _on_display_clicked(self, x: float, y: float) -> None:
        controls = self._controls_widget
        if controls.view_mode.currentText() != VIEW_FFT:
            return
        controls.chk_auto.setChecked(False)
        controls.sp_x.setValue(max(0.0, x))
        controls.sp_y.setValue(max(0.0, y))
        self._refresh_display()

    def _warn(self, message: str) -> None:
        self._controls_widget.lbl_status.setText(message)
        QMessageBox.warning(self, tr("phase.title"), message)

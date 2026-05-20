"""PSF view controls and readouts."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..core.i18n import tr
from . import theme
from .control_panel_helpers import button as _btn
from . import psf_preset
from .psf_cut_controls import VolumeCutControls
from .psf_render import (
    DEFAULT_THRESHOLD, DEFAULT_VOLUME_ALPHA, DEFAULT_VOLUME_BRIGHTNESS,
    MIN_THRESHOLD, MODE_MIP, MODE_ORTHO, MODE_VOLUME, RenderOptions,
    VOLUME_STYLE_SLICES, VOLUME_STYLE_SURFACE,
)
from .psf_view_controls import check, combo, dspin, ispin, set_visible
from .settings import UserSettings
from .spin_slider import SpinSliderDouble, SpinSliderInt
from .widgets import HintLabel, MeterLabel, SectionHeader, ValueLabel

CMAPS = ("viridis", "gray", "hot", "rainbow", "magma", "inferno", "plasma", "CET-L4")
VOLUME_LAYER_MAX = 12
DEFAULT_VOLUME_LAYERS = 3


def _empty_html(text: str, hint: str | None) -> str:
    """主行 + 浅色提示行 (None 时退化为单行)。"""
    if not hint:
        return text
    return (
        f"<div>{text}</div>"
        f"<div style='color:{theme.TEXT3};font-size:{theme.SIZE_METER};"
        "margin-top:6px;font-weight:400;letter-spacing:0px;'>"
        f"{hint}</div>"
    )


def _ss_double(value: float, lo: float, hi: float, *, step: float, decimals: int, width: int) -> SpinSliderDouble:
    ss = SpinSliderDouble()
    ss.setRange(lo, hi)
    ss.setDecimals(decimals)
    ss.setSingleStep(step)
    ss.setValue(value)
    ss.setMinimumWidth(width)
    ss.spin.setMinimumWidth(max(54, width // 2 + 8))
    return ss


def _ss_int(value: int, lo: int, hi: int, *, width: int) -> SpinSliderInt:
    ss = SpinSliderInt()
    ss.setRange(lo, hi)
    ss.setValue(value)
    ss.setMinimumWidth(width)
    ss.spin.setMinimumWidth(max(48, width // 2 + 8))
    return ss
VOLUME_ALPHA_MIN = 0.05
VOLUME_ALPHA_MAX = 1.0
VOLUME_BRIGHTNESS_MIN = 0.0
VOLUME_BRIGHTNESS_MAX = 2.0
FINE_INTERP_MIN = 1.0
FINE_INTERP_MAX = 4.0
DETAIL_ROW_INDENT = 88


class PsfControlPanel(QWidget):
    render_requested = Signal()
    auto_toggled = Signal(bool)
    rect_zoom_changed = Signal(bool)
    reset_view_requested = Signal()
    export_plot_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PsfControlPanel")
        self.setStyleSheet(
            f"QWidget#PsfControlPanel{{background:{theme.BG1};"
            f"border-top:1px solid {theme.BORDER0};}}"
        )
        self._has_volume_shape = False
        self._cut_ratios_cached: tuple[float, float, float] = (1.0, 1.0, 1.0)
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.G_16, theme.G_8, theme.G_16, theme.G_8)
        root.setSpacing(theme.G_8)
        root.addLayout(self._mode_row())
        root.addLayout(self._detail_row())
        root.addWidget(self.cuts)
        root.addLayout(self._info_row())
        self._wire()
        self.sync_visibility()
        self._on_auto_toggled(True)

    def selected_options(self) -> RenderOptions:
        return RenderOptions(
            mode=self.mode.currentText(),
            slice_index=self.cuts.z_value(),
            auto_levels=self.auto.isChecked(),
            level_min=self.level_min.value(),
            level_max=self.level_max.value(),
            show_colorbar=self.colorbar.isChecked(),
            show_labels=self.labels.isChecked(),
            show_locator=self.locator.isChecked(),
            volume_threshold=self.threshold.value(),
            volume_step=self.layers.value(),
            volume_detail=self._detail_value(),
            volume_style=self.volume_style.currentText(),
            volume_alpha=self.alpha.value(),
            volume_brightness=self.brightness.value(),
            volume_cmap=self.cmap.currentText(),
            volume_cut_x=self.cuts.x_value(),
            volume_cut_y=self.cuts.y_value(),
            fine_interp_z=self.fine_z.value(),
            fine_interp_xy=self.fine_xy.value(),
        )

    def cmap_name(self) -> str:
        return self.cmap.currentText()

    def current_slice_index(self) -> int:
        return self.cuts.z_value()

    def set_levels(self, low: float, high: float) -> None:
        for spin, value in ((self.level_min, low), (self.level_max, high)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def set_volume_shape(self, shape: tuple[int, int, int]) -> None:
        self.cuts.set_shape(shape)
        self._has_volume_shape = True
        self._apply_cuts_defaults()

    def set_info(self, idx: int, total: int, peak: float, position: str, status: str) -> None:
        self.idx_label.setText(f"{idx + 1:>4d} / {total:<4d}")
        self.peak_label.setText(f"peak {peak:>8.1f}")
        self.pos_label.setText(position)
        self.status_label.setText(status)

    def set_empty(self, text: str, hint: str | None = None) -> None:
        self.idx_label.setText("─ / ─")
        self.pos_label.setText("")
        self.peak_label.setText("")
        self.status_label.setText(_empty_html(text, hint))

    def bind_settings(self, settings: UserSettings) -> None:
        """PSF 视图不再自动持久化任何参数；改用 save/load preset 按钮。
        保留方法签名以兼容 :meth:`PSFView.bind_settings` 调用链。"""
        self.sync_visibility()
        self._on_auto_toggled(self.auto.isChecked())
        if self._has_volume_shape:
            self._apply_cuts_defaults()

    def sync_visibility(self) -> None:
        style = self.volume_style.currentText()
        mode = self.mode.currentText()
        volume = mode == MODE_VOLUME
        ortho = mode == MODE_ORTHO
        self.cuts.setVisible(ortho or (volume and style == VOLUME_STYLE_SLICES))
        set_visible(self._volume_controls(), volume)
        set_visible(self._fine_controls(), volume and self.detail.currentIndex() == 1)
        set_visible((self.threshold_lbl, self.threshold), volume and style == VOLUME_STYLE_SURFACE)
        set_visible((self.layers_lbl, self.layers), volume and style == VOLUME_STYLE_SURFACE)
        set_visible(self._brightness_controls(), volume and style == VOLUME_STYLE_SLICES)
        set_visible(self._image_controls(), not volume)

    def _mode_row(self) -> QHBoxLayout:
        self.mode = combo((MODE_ORTHO, MODE_MIP, MODE_VOLUME), 92)
        self.cmap = combo(CMAPS, 92)
        self.cuts = VolumeCutControls()
        self._make_controls()
        row = QHBoxLayout()
        row.setSpacing(theme.G_8)
        for widget in self._row_widgets():
            row.addWidget(widget)
        row.addStretch()
        return row

    def _detail_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.G_8)
        row.addSpacing(DETAIL_ROW_INDENT)
        for widget in self._detail_widgets():
            row.addWidget(widget)
        row.addStretch()
        return row

    def _make_controls(self) -> None:
        self.colorbar = check(tr("psf.colorbar"), True)
        self.auto = check(tr("psf.auto_levels"), True)
        self.labels = check(tr("psf.axes"), True)
        self.locator = check(tr("psf.z_marker"), True)
        self.rect_zoom = check(tr("psf.rect_zoom"), False)
        self.btn_reset = _btn(tr("psf.reset_view"), enabled=True)
        self.btn_reset.clicked.connect(self.reset_view_requested.emit)
        self.rect_zoom.toggled.connect(self.rect_zoom_changed.emit)
        self.level_min = dspin(0.0)
        self.level_max = dspin(1.0)
        self.threshold = _ss_double(
            DEFAULT_THRESHOLD, MIN_THRESHOLD, 1.0, step=0.01, decimals=3, width=96,
        )
        self.layers = _ss_int(DEFAULT_VOLUME_LAYERS, 1, VOLUME_LAYER_MAX, width=80)
        self.detail = combo((tr("psf.fast"), tr("psf.fine")), 72)
        self.fine_z = _ss_double(2.0, FINE_INTERP_MIN, FINE_INTERP_MAX, step=0.25, decimals=2, width=96)
        self.fine_xy = _ss_double(2.0, FINE_INTERP_MIN, FINE_INTERP_MAX, step=0.25, decimals=2, width=96)
        self.volume_style = combo((VOLUME_STYLE_SURFACE, VOLUME_STYLE_SLICES), 104)
        self.alpha = _ss_double(
            DEFAULT_VOLUME_ALPHA, VOLUME_ALPHA_MIN, VOLUME_ALPHA_MAX,
            step=0.05, decimals=2, width=96,
        )
        self.brightness = SpinSliderDouble()
        self.brightness.setRange(VOLUME_BRIGHTNESS_MIN, VOLUME_BRIGHTNESS_MAX)
        self.brightness.setDecimals(2)
        self.brightness.setSingleStep(0.05)
        self.brightness.setValue(DEFAULT_VOLUME_BRIGHTNESS)
        self.brightness.setMinimumWidth(112)
        self.brightness.spin.setMinimumWidth(62)
        self._wire_tooltips()

    def _wire_tooltips(self) -> None:
        self.threshold.setToolTip(tr("tip.psf_threshold"))
        self.layers.setToolTip(tr("tip.psf_layers"))
        self.fine_z.setToolTip(tr("tip.psf_fine_z"))
        self.fine_xy.setToolTip(tr("tip.psf_fine_xy"))
        self.alpha.setToolTip(tr("tip.psf_alpha"))
        self.brightness.setToolTip(tr("tip.psf_brightness"))
        self.level_min.setToolTip(tr("tip.psf_level_min"))
        self.level_max.setToolTip(tr("tip.psf_level_max"))
        self.detail.setToolTip(tr("tip.psf_detail"))
        self.volume_style.setToolTip(tr("tip.psf_volume_style"))
        self.auto.setToolTip(tr("tip.psf_auto_levels"))
        self.colorbar.setToolTip(tr("tip.psf_colorbar"))
        self.labels.setToolTip(tr("tip.psf_axes"))
        self.locator.setToolTip(tr("tip.psf_z_marker"))
        self.rect_zoom.setToolTip(tr("tip.psf_rect_zoom"))
        self.btn_reset.setToolTip(tr("tip.psf_reset_view"))

    def _row_widgets(self) -> tuple[QWidget, ...]:
        self.render_lbl = HintLabel(tr("psf.render"))
        self.cmap_lbl = HintLabel(tr("psf.colormap"))
        self.min_lbl = HintLabel(tr("psf.min"))
        self.max_lbl = HintLabel(tr("psf.max"))
        self.threshold_lbl = HintLabel(tr("psf.threshold"))
        self.layers_lbl = HintLabel(tr("psf.layers"))
        self.detail_lbl = HintLabel(tr("psf.detail"))
        self.fine_z_lbl = HintLabel(tr("psf.z_interp"))
        self.fine_xy_lbl = HintLabel(tr("psf.xy_interp"))
        self.volume_lbl = HintLabel(tr("psf.volume"))
        self.alpha_lbl = HintLabel(tr("psf.alpha"))
        self.brightness_lbl = HintLabel(tr("psf.brightness"))
        return (
            SectionHeader(tr("psf.view_section")), self.render_lbl, self.mode,
            self.cmap_lbl, self.cmap, self.colorbar, self.auto,
            self.min_lbl, self.level_min, self.max_lbl, self.level_max,
            self.labels, self.locator,
            self.rect_zoom, self.btn_reset,
        )

    def _detail_widgets(self) -> tuple[QWidget, ...]:
        return (
            self.threshold_lbl, self.threshold, self.layers_lbl, self.layers,
            self.detail_lbl, self.detail, self.fine_z_lbl, self.fine_z,
            self.fine_xy_lbl, self.fine_xy, self.volume_lbl,
            self.volume_style, self.alpha_lbl, self.alpha,
            self.brightness_lbl, self.brightness,
        )

    def _info_row(self) -> QHBoxLayout:
        self.idx_label = MeterLabel("─ / ─")
        self.pos_label = ValueLabel("")
        self.peak_label = MeterLabel("")
        self.status_label = HintLabel(_empty_html(tr("psf.empty_state"), tr("psf.empty_state_hint")))
        self.btn_save_preset = _btn(tr("psf.save_preset"), enabled=True)
        self.btn_load_preset = _btn(tr("psf.load_preset"), enabled=True)
        self.btn_export_plot = _btn(tr("psf.export_plot"), enabled=True)
        self.btn_save_preset.setToolTip(tr("tip.psf_save_preset"))
        self.btn_load_preset.setToolTip(tr("tip.psf_load_preset"))
        self.btn_export_plot.setToolTip(tr("tip.psf_export_plot"))
        self.btn_save_preset.clicked.connect(lambda: psf_preset.prompt_save(self))
        self.btn_load_preset.clicked.connect(lambda: psf_preset.prompt_load(self))
        self.btn_export_plot.clicked.connect(self.export_plot_requested.emit)
        info = QHBoxLayout()
        info.setSpacing(theme.G_24)
        for widget in (self.idx_label, self.pos_label, self.peak_label):
            info.addWidget(widget)
        info.addWidget(self.status_label, stretch=1)
        info.addWidget(self.btn_export_plot)
        info.addWidget(self.btn_save_preset)
        info.addWidget(self.btn_load_preset)
        return info

    def _wire(self) -> None:
        for control in self._render_controls():
            control.currentTextChanged.connect(self._on_mode_changed)
        for control in self._value_controls():
            control.valueChanged.connect(self._emit_render)
        for control in (self.colorbar, self.labels, self.locator):
            control.toggled.connect(self._emit_render)
        self.auto.toggled.connect(self._on_auto_toggled)
        self.cuts.changed.connect(self._on_cuts_changed)
        self.cmap.currentTextChanged.connect(self._emit_render)

    def _on_mode_changed(self, *_: object) -> None:
        self.sync_visibility()
        if self._has_volume_shape:
            self._apply_cuts_defaults()
        self.render_requested.emit()

    def _on_cuts_changed(self, *_: object) -> None:
        if self.mode.currentText() == MODE_VOLUME:
            self._cut_ratios_cached = self.cuts.ratios()
        self.render_requested.emit()

    def _apply_cuts_defaults(self) -> None:
        max_x, max_y, max_z = self.cuts.maxima()
        if self.mode.currentText() == MODE_VOLUME:
            rx, ry, rz = self._cut_ratios_cached
        else:
            rx = ry = rz = 0.5
        x = int(round(rx * max_x))
        y = int(round(ry * max_y))
        z = int(round(rz * max_z))
        self.cuts.set_values(x, y, z)

    def _on_auto_toggled(self, on: bool) -> None:
        for spin in (self.level_min, self.level_max):
            spin.setEnabled(not on)
        self.auto_toggled.emit(on)

    def _emit_render(self, *_: object) -> None:
        self.render_requested.emit()

    def _detail_value(self) -> str:
        return "fine" if self.detail.currentIndex() == 1 else "fast"

    def _render_controls(self) -> tuple:
        return (self.mode, self.detail, self.volume_style)

    def _value_controls(self) -> tuple:
        return (
            self.threshold, self.layers, self.fine_z,
            self.fine_xy, self.alpha, self.brightness,
            self.level_min, self.level_max,
        )

    def _volume_controls(self) -> tuple[QWidget, ...]:
        return (
            self.detail_lbl, self.detail, self.fine_z_lbl, self.fine_z,
            self.fine_xy_lbl, self.fine_xy, self.volume_lbl,
            self.volume_style, self.alpha_lbl, self.alpha,
            self.brightness_lbl, self.brightness,
        )

    def _fine_controls(self) -> tuple[QWidget, ...]:
        return (self.fine_z_lbl, self.fine_z, self.fine_xy_lbl, self.fine_xy)

    def _brightness_controls(self) -> tuple[QWidget, ...]:
        return (self.brightness_lbl, self.brightness)

    def _image_controls(self) -> tuple[QWidget, ...]:
        return (
            self.colorbar, self.auto, self.min_lbl, self.level_min,
            self.max_lbl, self.level_max, self.locator,
        )

    def _persistent_combos(self) -> dict[str, QWidget]:
        return {
            "mode": self.mode,
            "cmap": self.cmap,
            "detail": self.detail,
            "volume_style": self.volume_style,
        }

    def _persistent_checks(self) -> dict[str, QWidget]:
        return {
            "show_colorbar": self.colorbar,
            "auto_levels": self.auto,
            "show_axes": self.labels,
            "show_z_marker": self.locator,
        }

    def _persistent_spins(self) -> dict[str, QWidget]:
        return {
            "level_min": self.level_min,
            "level_max": self.level_max,
            "threshold": self.threshold,
            "layers": self.layers,
            "fine_z": self.fine_z,
            "fine_xy": self.fine_xy,
            "alpha": self.alpha,
            "brightness": self.brightness,
        }


def _clip_ratio(value: float) -> float:
    return min(1.0, max(0.0, float(value)))

"""控制面板 — 二列工作流:位移台 · 扫描计划。

Devices 已移到 StatusStrip;metadata 在 SCAN PLAN 列底部默认折叠;
repeat / interval 在 ⚙ 设置 → 时间序列扫描。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QScrollArea, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from ..core.scanner import ScanMetadata, ScanParams
from . import theme
from .control_panel_helpers import (
    button as _btn, dspin as _dspin, kv as _kv, row as _row,
    row_widget as _row_widget, section as _section,
)
from .metadata_dialog import MetadataDialog
from .progress_bar import ScanProgressBar
from .settings import UserSettings
from .spin_slider import SpinSliderDouble, SpinSliderInt
from .stage_jog_panel import StageJogPanel
from .widgets import HintLabel, SectionHeader
from .workflow import ScanBrief

AVG_SAMPLE_MAX = 512
MS_PER_SECOND = 1000.0


def _sspin_double(lo, hi, val, *, step=0.1, enabled=True):
    ss = SpinSliderDouble()
    ss.setRange(lo, hi)
    ss.setValue(val)
    ss.setSingleStep(step)
    ss.setEnabled(enabled)
    return ss


def _sspin_int(lo, hi, val, *, step=1, enabled=True):
    ss = SpinSliderInt()
    ss.setRange(lo, hi)
    ss.setValue(val)
    ss.setSingleStep(step)
    ss.setEnabled(enabled)
    return ss


def _axis_ss(name, ss):
    """Wrap a SpinSlider with a HintLabel above it."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(HintLabel(name))
    layout.addWidget(ss)
    return widget


class ControlPanel(QWidget):
    move_requested = Signal(float, float, float)
    home_requested = Signal()
    autofocus_requested = Signal()
    scan_started = Signal(object)
    scan_canceled = Signal()
    single_axis_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._autofocus_allowed = True
        self._scanning = False
        self._settings: UserSettings | None = None
        self.setObjectName("ControlPanel")
        self.setStyleSheet(f"QWidget#ControlPanel {{ background: {theme.BG1}; }}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")

        content = QWidget()
        content.setObjectName("ControlPanelContent")
        content.setStyleSheet(f"QWidget#ControlPanelContent {{ background: {theme.BG1}; }}")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(theme.PANEL_GUTTER, theme.PANEL_GUTTER, theme.PANEL_GUTTER, theme.PANEL_GUTTER)
        outer.setSpacing(theme.G_24)

        outer.addWidget(self._stage())
        
        rule1 = QFrame()
        rule1.setProperty("role", "rule")
        outer.addWidget(rule1)
        
        outer.addWidget(self._scan_params())

        rule2 = QFrame()
        rule2.setProperty("role", "rule")
        outer.addWidget(rule2)
        
        outer.addLayout(self._scan_run())
        outer.addStretch(1)
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        self._parameter_controls = {
            "target_x": self.sp_x,
            "target_y": self.sp_y,
            "target_z": self.sp_z,
            "z_start": self.sp_zs,
            "z_stop": self.sp_ze,
            "z_step": self.sp_zd,
            "dwell_ms": self.sp_dwell,
            "sample_count": self.sp_avg,
        }

    def _stage(self) -> QWidget:
        self.sp_x = _sspin_double(-1e6, 1e6, 0.0, step=0.1)
        self.sp_y = _sspin_double(-1e6, 1e6, 0.0, step=0.1)
        self.sp_z = _sspin_double(-1e6, 1e6, 65050.0, step=0.1)
        self.sp_z.setSuffix(" µm")
        self.sp_x.setVisible(False)
        self.sp_y.setVisible(False)

        for s in (self.sp_x, self.sp_y, self.sp_z):
            s.setToolTip(tr("tip.target_xyz"))
        self.btn_move = _btn(tr("panel.move_stage"), enabled=False)
        self.btn_move.setToolTip(tr("tip.move"))
        self.btn_home = _btn(tr("panel.home"), enabled=False)
        self.btn_home.setToolTip(tr("tip.home"))
        self.btn_autofocus = _btn(tr("panel.auto_focus"), enabled=False)
        self.btn_autofocus.setToolTip(tr("tip.auto_focus"))
        self.btn_move.clicked.connect(lambda: self.move_requested.emit(
            self.sp_x.value(), self.sp_y.value(), self.sp_z.value()))
        self.btn_home.clicked.connect(self.home_requested.emit)
        self.btn_autofocus.clicked.connect(self.autofocus_requested.emit)
        self.stage_jog = StageJogPanel()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.G_8)

        layout.addWidget(SectionHeader(tr("panel.stage")))

        # 单行 Z 控制带:标签 + spinslider(µm suffix) + 三按钮共行
        z_row = QHBoxLayout()
        z_row.setSpacing(theme.G_8)
        z_label = HintLabel("Z")
        z_label.setMinimumWidth(16)
        z_row.addWidget(z_label)
        z_row.addWidget(self.sp_z, stretch=1)
        z_row.addWidget(self.btn_move)
        z_row.addWidget(self.btn_home)
        z_row.addWidget(self.btn_autofocus)
        layout.addLayout(z_row)

        layout.addWidget(self.stage_jog)
        return container

    def _scan_params(self) -> QWidget:
        self.sp_zs = _sspin_double(-1e6, 1e6, -10.0)
        self.sp_zs.setToolTip(tr("tip.z_start"))
        self.sp_ze = _sspin_double(-1e6, 1e6, 10.0)
        self.sp_ze.setToolTip(tr("tip.z_stop"))
        self.sp_zd = _sspin_double(0.01, 100, 0.5)
        self.sp_zd.setToolTip(tr("tip.z_step"))
        self.sp_dwell = _sspin_int(0, 5000, 50)
        self.sp_dwell.setToolTip(tr("tip.dwell"))
        self.sp_avg = _sspin_int(1, AVG_SAMPLE_MAX, ScanParams.DEFAULT_SAMPLE_COUNT)
        self.sp_avg.setToolTip(tr("tip.avg"))
        self.scan_brief = ScanBrief()
        self._scan_inputs = (
            self.sp_zs, self.sp_ze, self.sp_zd, self.sp_dwell, self.sp_avg
        )
        self._wire_scan_summary()
        
        self.btn_metadata = _btn(tr("panel.metadata") + "…")
        self.btn_metadata.clicked.connect(self._show_metadata_dialog)
        
        # 扫描范围:Z Start / Z Stop 直接并排,无装饰
        range_row = _row(
            _axis_ss(tr("panel.z_start"), self.sp_zs),
            _axis_ss(tr("panel.z_stop"), self.sp_ze),
            _stretch=True,
        )

        # Precision & Timing row
        params_row = _row(
            _axis_ss(tr("panel.z_step"), self.sp_zd),
            theme.G_24,
            _axis_ss(tr("panel.dwell"), self.sp_dwell),
            _axis_ss(tr("panel.avg"), self.sp_avg),
            _stretch=True
        )
        
        return _section(tr("panel.scan_plan"), [
            range_row,
            params_row,
            self.scan_brief,
            self.btn_metadata,
        ])

    def _show_metadata_dialog(self) -> None:
        if self._settings:
            dlg = MetadataDialog(self._settings, self)
            dlg.exec()

    def _scan_run(self) -> QHBoxLayout:
        self.btn_start = _btn(tr("panel.start_scan"), primary=True, enabled=False)
        self.btn_start.setToolTip(tr("tip.start_scan"))
        self.btn_stop = _btn(tr("panel.stop"), danger=True, enabled=False)
        self.btn_stop.setToolTip(tr("tip.stop_scan"))
        self.btn_start.clicked.connect(self._emit_start)
        self.btn_stop.clicked.connect(self.scan_canceled.emit)
        self.pb = ScanProgressBar()
        self.pb.setRange(0, 100)
        self.pb.setFormat("0%")
        h = QHBoxLayout()
        h.setSpacing(theme.G_16)
        h.setContentsMargins(0, theme.G_8, 0, 0)
        for w in (self.btn_start, self.btn_stop):
            h.addWidget(w)
        h.addSpacing(theme.G_8)
        h.addWidget(self.pb, stretch=1)
        return h

    def _wire_scan_summary(self) -> None:
        for widget in self._scan_inputs:
            widget.valueChanged.connect(self._update_scan_summary)
        self._update_scan_summary()

    @Slot()
    def _emit_start(self) -> None:
        self.scan_started.emit(self._scan_params_from_controls())

    @Slot()
    def _update_scan_summary(self, *_: object) -> None:
        params = self._scan_params_from_controls()
        point_count = len(params.points())
        frame_count = point_count * params.sample_count
        seconds = point_count * params.dwell_ms / MS_PER_SECOND
        self.scan_brief.set_values(
            points=point_count,
            frames=frame_count,
            seconds=seconds,
        )

    def _scan_params_from_controls(self) -> ScanParams:
        params = {
            "z_start": self.sp_zs.value(),
            "z_stop": self.sp_ze.value(),
            "z_step": self.sp_zd.value(),
            "dwell_ms": self.sp_dwell.value(),
            "sample_count": self.sp_avg.value(),
        }
        return ScanParams(**params)

    def set_connected(self, on: bool) -> None:
        self._connected = on
        for w in (self.btn_move, self.btn_home, self.btn_start):
            w.setEnabled(on)
        self.btn_autofocus.setEnabled(on and self._autofocus_allowed)

    def set_single_axis(self, is_single: bool) -> None:
        for n in ("sp_x", "sp_y"):
            getattr(self, n).setEnabled(not is_single)
        if is_single:
            self.sp_x.setValue(0.0)
            self.sp_y.setValue(0.0)
        self.single_axis_changed.emit(is_single)

    def set_autofocus_allowed(self, allowed: bool) -> None:
        self._autofocus_allowed = bool(allowed)
        self.btn_autofocus.setEnabled(self._connected and self._autofocus_allowed)

    def set_scanning(self, on: bool) -> None:
        self.btn_start.setEnabled(not on)
        self.btn_stop.setEnabled(on)
        self.btn_move.setEnabled(not on)
        self.btn_home.setEnabled(not on)
        self.btn_autofocus.setEnabled(not on and self._connected and self._autofocus_allowed)
        self._set_scan_inputs_enabled(not on)
        self.pb.set_running(on)
        if on:
            self.pb.setValue(0)
            self.pb.setFormat("0%")
        self._scanning = bool(on)

    def set_progress(self, idx: int, total: int, text: str = "") -> None:
        pct = int(idx / total * 100) if total else 0
        self.pb.setValue(pct)
        self.pb.setFormat(f"{idx} / {total}   {pct}%")

    def repeat_count(self) -> int:
        if self._settings is None:
            return 1
        return int(self._settings.value_int("scan/repeat_count", 1))

    def repeat_interval_min(self) -> float:
        if self._settings is None:
            return 0.0
        return float(self._settings.value_float("scan/repeat_interval_min", 0.0))

    def scan_metadata(self) -> ScanMetadata:
        if self._settings:
            s = self._settings._settings
            return ScanMetadata(
                sample_name=str(s.value("meta/sample_name", "")),
                objective=str(s.value("meta/objective", "")),
                na=float(s.value("meta/na", 1.40) or 1.40),
                wavelength_nm=float(s.value("meta/wavelength_nm", 532.0) or 532.0),
                note=str(s.value("meta/note", "")),
            )
        return ScanMetadata()

    def bind_settings(self, settings: UserSettings) -> None:
        self._settings = settings
        for key, control in self._parameter_controls.items():
            settings.bind_spin(f"scan/{key}", control)
        self._update_scan_summary()

    def _set_scan_inputs_enabled(self, enabled: bool) -> None:
        for widget in self._scan_inputs:
            widget.setEnabled(enabled)

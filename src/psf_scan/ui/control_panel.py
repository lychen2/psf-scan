"""控制面板 — 三步工作流：设备、位移台、扫描计划。"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLineEdit, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from ..core.scanner import ScanMetadata, ScanParams
from . import theme
from .control_panel_helpers import (
    axis as _axis, button as _btn, combo as _combo, dspin as _dspin,
    ispin as _ispin, kv as _kv, row as _row, row_widget as _row_widget,
    section as _section,
)
from .progress_bar import ScanProgressBar
from .settings import UserSettings
from .spin_slider import SpinSliderDouble, SpinSliderInt
from .stage_jog_panel import StageJogPanel
from .widgets import HintLabel, ValueLabel
from .workflow import ScanBrief, WorkflowGuide, duration_text

AVG_SAMPLE_MAX = 512
MS_PER_SECOND = 1000.0
PANEL_MAX_HEIGHT = 480


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
    """Wrap a SpinSlider with a HintLabel above it, same pattern as _axis()."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(HintLabel(name))
    layout.addWidget(ss)
    return widget


class ControlPanel(QWidget):
    connect_requested = Signal(str, str)
    disconnect_requested = Signal()
    move_requested = Signal(float, float, float)
    home_requested = Signal()
    autofocus_requested = Signal()
    scan_started = Signal(object)
    scan_canceled = Signal()
    plan_changed = Signal(str)
    pi_settings_requested = Signal()
    single_axis_changed = Signal(bool)

    def __init__(self, stages: list[str], cameras: list[str], parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._autofocus_allowed = True
        self._has_results = False
        self._scanning = False
        self.setStyleSheet(f"background:{theme.BG1};")
        self.setMaximumHeight(PANEL_MAX_HEIGHT)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 4, 20, 8)
        outer.setSpacing(0)

        self.workflow = WorkflowGuide()
        outer.addWidget(self.workflow)

        cols = QHBoxLayout()
        cols.setSpacing(28)
        cols.addWidget(self._devices(stages, cameras), stretch=2)
        cols.addWidget(self._stage(), stretch=2)
        cols.addWidget(self._scan_params(), stretch=3)
        cols.addWidget(self._metadata(), stretch=2)
        outer.addLayout(cols)

        rule = QFrame()
        rule.setProperty("role", "rule")
        outer.addWidget(rule)
        outer.addLayout(self._scan_run())
        self._parameter_controls = {
            "target_x": self.sp_x,
            "target_y": self.sp_y,
            "target_z": self.sp_z,
            "z_start": self.sp_zs,
            "z_stop": self.sp_ze,
            "z_step": self.sp_zd,
            "dwell_ms": self.sp_dwell,
            "sample_count": self.sp_avg,
            "x_start": self.sp_xs,
            "x_stop": self.sp_xe,
            "x_step": self.sp_xd,
            "y_start": self.sp_ys,
            "y_stop": self.sp_ye,
            "y_step": self.sp_yd,
            "repeat_count": self.sp_repeat,
            "repeat_interval_min": self.sp_interval,
        }

    def _devices(self, stages, cameras) -> QWidget:
        self.cb_stage = _combo(stages)
        self.cb_cam = _combo(cameras)
        self.btn_pi_settings = _btn("PI…", enabled=False)
        self.btn_pi_settings.setToolTip(tr("tip.pi_settings"))
        self.btn_conn = _btn(tr("panel.connect"), primary=True)
        self.btn_conn.setToolTip(tr("tip.connect"))
        self.btn_disc = _btn(tr("panel.disconnect"), danger=True, enabled=False)
        self.btn_disc.setToolTip(tr("tip.disconnect"))
        self.lbl_device_state = ValueLabel(tr("panel.offline"))
        self.btn_conn.clicked.connect(lambda: self.connect_requested.emit(
            self.cb_stage.currentText(), self.cb_cam.currentText()))
        self.btn_disc.clicked.connect(self.disconnect_requested.emit)
        self.btn_pi_settings.clicked.connect(self.pi_settings_requested.emit)
        self.cb_stage.currentTextChanged.connect(self._on_stage_kind_changed)
        return _section(tr("panel.devices"), [
            _kv(tr("panel.stage_driver"), _row_widget(self.cb_stage, self.btn_pi_settings, _stretch=True)),
            _kv(tr("panel.camera_driver"), self.cb_cam),
            _row(self.btn_conn, self.btn_disc, _stretch=True),
            _kv(tr("panel.device_state"), self.lbl_device_state),
        ])

    @Slot(str)
    def _on_stage_kind_changed(self, kind: str) -> None:
        is_pi = self._is_single_axis(kind)
        self.btn_pi_settings.setEnabled(is_pi)
        # 单轴 stage → xy 灰掉 + 取消勾选
        if not hasattr(self, "cb_xy"):
            self.single_axis_changed.emit(is_pi)
            return
        if is_pi:
            self.cb_xy.blockSignals(True)
            self.cb_xy.setChecked(False)
            self.cb_xy.blockSignals(False)
            self._toggle_xy(False)
            self._update_scan_summary()
        self.cb_xy.setEnabled(not is_pi)
        for n in ("sp_x", "sp_y"):
            getattr(self, n).setEnabled(not is_pi)
        if is_pi:
            self.sp_x.setValue(0.0)
            self.sp_y.setValue(0.0)
        self.single_axis_changed.emit(is_pi)

    @staticmethod
    def _is_single_axis(kind: str) -> bool:
        return kind.lower() in {"pi-m531", "pi", "m531"}

    def _stage(self) -> QWidget:
        self.sp_x = _sspin_double(-1e6, 1e6, 0.0, step=0.1)
        self.sp_y = _sspin_double(-1e6, 1e6, 0.0, step=0.1)
        self.sp_z = _sspin_double(-1e6, 1e6, 65050.0, step=0.1)
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
        return _section(tr("panel.stage"), [
            _row(_axis_ss(tr("panel.target_x"), self.sp_x), _axis_ss(tr("panel.target_y"), self.sp_y),
                 _axis_ss(tr("panel.target_z"), self.sp_z), 8, HintLabel(tr("panel.unit_um")), _stretch=True),
            _row(self.btn_move, self.btn_home, self.btn_autofocus, _stretch=True),
            self.stage_jog,
        ])

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
        self.lbl_plan = ValueLabel("")
        self.cb_xy = QCheckBox(tr("panel.include_xy_grid"))
        self.cb_xy.setToolTip(tr("tip.xy_grid"))
        self.sp_xs = _sspin_double(-500, 500, -5.0, enabled=False)
        self.sp_xe = _sspin_double(-500, 500, 5.0, enabled=False)
        self.sp_xd = _sspin_double(0.01, 100, 1.0, enabled=False)
        self.sp_ys = _sspin_double(-500, 500, -5.0, enabled=False)
        self.sp_ye = _sspin_double(-500, 500, 5.0, enabled=False)
        self.sp_yd = _sspin_double(0.01, 100, 1.0, enabled=False)
        for sp, key in (
            (self.sp_xs, "tip.x_start"), (self.sp_xe, "tip.x_stop"), (self.sp_xd, "tip.x_step"),
            (self.sp_ys, "tip.y_start"), (self.sp_ye, "tip.y_stop"), (self.sp_yd, "tip.y_step"),
        ):
            sp.setToolTip(tr(key))
        self.sp_repeat = _sspin_int(1, 1000, 1)
        self.sp_repeat.setToolTip(tr("tip.repeat_count"))
        self.sp_interval = _sspin_double(0.0, 1440.0, 0.0, step=0.5)
        self.sp_interval.setToolTip(tr("tip.repeat_interval"))
        self.scan_brief = ScanBrief()
        self._scan_inputs = (
            self.cb_xy, self.sp_zs, self.sp_ze, self.sp_zd, self.sp_dwell,
            self.sp_avg, self.sp_xs, self.sp_xe, self.sp_xd,
            self.sp_ys, self.sp_ye, self.sp_yd,
        )
        self._xy_rows = (
            _row_widget(_axis_ss(tr("panel.x_start"), self.sp_xs), 6, _axis_ss(tr("panel.z_stop"), self.sp_xe),
                        6, _axis_ss(tr("panel.z_step"), self.sp_xd), _stretch=True),
            _row_widget(_axis_ss(tr("panel.y_start"), self.sp_ys), 6, _axis_ss(tr("panel.z_stop"), self.sp_ye),
                        6, _axis_ss(tr("panel.z_step"), self.sp_yd), _stretch=True),
        )
        self._wire_scan_summary()
        self._toggle_xy(False)
        return _section(tr("panel.scan_plan"), [
            _row(_axis_ss(tr("panel.z_start"), self.sp_zs), 6, _axis_ss(tr("panel.z_stop"), self.sp_ze),
                 6, _axis_ss(tr("panel.z_step"), self.sp_zd), _stretch=True),
            _row(_axis_ss(tr("panel.dwell"), self.sp_dwell), HintLabel(tr("panel.unit_ms")),
                 12, _axis_ss(tr("panel.avg"), self.sp_avg), _stretch=True),
            _row(_axis_ss(tr("panel.repeat_count"), self.sp_repeat),
                 12, _axis_ss(tr("panel.repeat_interval_min"), self.sp_interval), _stretch=True),
            _row(self.cb_xy, _stretch=True),
            self.scan_brief,
            *self._xy_rows,
        ])

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
        self.lbl_status = ValueLabel(tr("panel.ready_connect"))
        h = QHBoxLayout()
        h.setSpacing(14)
        h.setContentsMargins(0, 6, 0, 0)
        for w in (self.btn_start, self.btn_stop):
            h.addWidget(w)
        h.addSpacing(8)
        h.addWidget(self.pb, stretch=1)
        h.addSpacing(8)
        h.addWidget(self.lbl_status)
        return h

    def _metadata(self) -> QWidget:
        self.le_sample = QLineEdit()
        self.le_sample.setToolTip(tr("tip.meta_sample"))
        self.le_objective = QLineEdit()
        self.le_objective.setToolTip(tr("tip.meta_objective"))
        self.sp_na = _dspin(0.0, 2.0, 1.40)
        self.sp_na.setToolTip(tr("tip.meta_na"))
        self.sp_lambda = _dspin(200.0, 2000.0, 532.0)
        self.sp_lambda.setToolTip(tr("tip.meta_lambda"))
        self.te_note = QTextEdit()
        self.te_note.setFixedHeight(54)
        self.te_note.setPlaceholderText("note")
        self.te_note.setToolTip(tr("tip.meta_note"))
        return _section(tr("panel.metadata"), [
            _kv(tr("panel.meta_sample"), self.le_sample),
            _kv(tr("panel.meta_objective"), self.le_objective),
            _kv(tr("panel.meta_na"), self.sp_na),
            _kv(tr("panel.meta_lambda"), self.sp_lambda),
            _kv(tr("panel.meta_note"), self.te_note),
        ])

    def _wire_scan_summary(self) -> None:
        self.cb_xy.toggled.connect(self._toggle_xy)
        self.cb_xy.toggled.connect(self._update_scan_summary)
        for widget in self._scan_inputs[1:]:
            widget.valueChanged.connect(self._update_scan_summary)
        self._update_scan_summary()

    @Slot(bool)
    def _toggle_xy(self, on: bool) -> None:
        for n in ("sp_xs", "sp_xe", "sp_xd", "sp_ys", "sp_ye", "sp_yd"):
            getattr(self, n).setEnabled(on)
        for row in getattr(self, "_xy_rows", ()):
            row.setVisible(on)

    @Slot()
    def _emit_start(self) -> None:
        self.scan_started.emit(self._scan_params_from_controls())

    @Slot()
    def _update_scan_summary(self, *_: object) -> None:
        params = self._scan_params_from_controls()
        point_count = len(params.points())
        frame_count = point_count * params.sample_count
        seconds = point_count * params.dwell_ms / MS_PER_SECOND
        self.lbl_plan.setText(
            f"{point_count:,} pts · {frame_count:,} frames · {duration_text(seconds)}"
        )
        self.scan_brief.set_values(
            points=point_count,
            frames=frame_count,
            seconds=seconds,
            xy_enabled=self.cb_xy.isChecked(),
        )
        self.plan_changed.emit(self.lbl_plan.text())

    def _scan_params_from_controls(self) -> ScanParams:
        params = {
            "z_start": self.sp_zs.value(),
            "z_stop": self.sp_ze.value(),
            "z_step": self.sp_zd.value(),
            "dwell_ms": self.sp_dwell.value(),
            "sample_count": self.sp_avg.value(),
        }
        if self.cb_xy.isChecked():
            params.update({
                "x_start": self.sp_xs.value(),
                "x_stop": self.sp_xe.value(),
                "x_step": self.sp_xd.value(),
                "y_start": self.sp_ys.value(),
                "y_stop": self.sp_ye.value(),
                "y_step": self.sp_yd.value(),
            })
        return ScanParams(**params)

    def set_connected(self, on: bool) -> None:
        self._connected = on
        self.btn_conn.setEnabled(not on); self.btn_disc.setEnabled(on)
        for w in (self.btn_move, self.btn_home, self.btn_start): w.setEnabled(on)
        # autofocus 同时受连接状态 + 设置开关约束 (默认 True; app 层调 set_autofocus_allowed 同步)
        self.btn_autofocus.setEnabled(on and self._autofocus_allowed)
        self.cb_stage.setEnabled(not on); self.cb_cam.setEnabled(not on)
        self.lbl_device_state.setText(tr("panel.online") if on else tr("panel.offline"))
        self.lbl_status.setText(tr("panel.ready_plan") if on else tr("panel.ready_connect"))
        if not on:
            self._has_results = False
        self._refresh_workflow_phase()

    def set_autofocus_allowed(self, allowed: bool) -> None:
        """设置里禁用自动对焦时主界面按钮置灰 (并自动取消已勾)。"""
        self._autofocus_allowed = bool(allowed)
        self.btn_autofocus.setEnabled(self._connected and self._autofocus_allowed)

    def set_scanning(self, on: bool) -> None:
        self.btn_start.setEnabled(not on); self.btn_stop.setEnabled(on)
        self.btn_disc.setEnabled(not on)
        self.btn_move.setEnabled(not on); self.btn_home.setEnabled(not on)
        self.btn_autofocus.setEnabled(not on and self._connected and self._autofocus_allowed)
        self._set_scan_inputs_enabled(not on)
        self.pb.set_running(on)
        if on:
            self.pb.setValue(0); self.pb.setFormat("0%")
            self._has_results = False
        self._scanning = bool(on)
        self._refresh_workflow_phase()

    def set_results_loaded(self, has_results: bool) -> None:
        """扫描完成 / stack 载入后调用; 把工作流推进到第 4 步 (导出)。"""
        self._has_results = bool(has_results)
        self._refresh_workflow_phase()

    def _refresh_workflow_phase(self) -> None:
        if self._scanning:
            phase = 3
        elif self._has_results:
            phase = 4
        elif self._connected:
            phase = 2
        else:
            phase = 1
        self.workflow.set_phase(phase)

    def set_progress(self, idx: int, total: int, text: str = "") -> None:
        pct = int(idx / total * 100) if total else 0
        self.pb.setValue(pct)
        self.pb.setFormat(f"{idx} / {total}   {pct}%")
        self.lbl_status.setText(text or f"{idx} / {total}")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def plan_text(self) -> str:
        return self.lbl_plan.text()

    def repeat_count(self) -> int:
        return int(self.sp_repeat.value())

    def repeat_interval_min(self) -> float:
        return float(self.sp_interval.value())

    def scan_metadata(self) -> ScanMetadata:
        sample_name = self.le_sample.text().strip()
        objective = self.le_objective.text().strip()
        note = self.te_note.toPlainText().strip()
        na = float(self.sp_na.value())
        wavelength_nm = float(self.sp_lambda.value())
        return ScanMetadata(
            sample_name=sample_name,
            objective=objective,
            na=na,
            wavelength_nm=wavelength_nm,
            note=note,
        )

    def bind_settings(self, settings: UserSettings) -> None:
        settings.bind_combo("devices/stage_driver", self.cb_stage)
        settings.bind_combo("devices/camera_driver", self.cb_cam)
        settings.bind_check("scan/include_xy_grid", self.cb_xy)
        for key, control in self._parameter_controls.items():
            settings.bind_spin(f"scan/{key}", control)
        self.le_sample.setText(str(settings._settings.value("meta/sample_name", "")))
        self.le_objective.setText(str(settings._settings.value("meta/objective", "")))
        self.sp_na.setValue(float(settings._settings.value("meta/na", 1.40) or 1.40))
        self.sp_lambda.setValue(float(settings._settings.value("meta/wavelength_nm", 532.0) or 532.0))
        self.te_note.setPlainText(str(settings._settings.value("meta/note", "")))
        self.le_sample.textChanged.connect(lambda v: settings.set_value("meta/sample_name", v))
        self.le_objective.textChanged.connect(lambda v: settings.set_value("meta/objective", v))
        self.sp_na.valueChanged.connect(lambda v: settings.set_value("meta/na", float(v)))
        self.sp_lambda.valueChanged.connect(lambda v: settings.set_value("meta/wavelength_nm", float(v)))
        self.te_note.textChanged.connect(lambda: settings.set_value("meta/note", self.te_note.toPlainText()))
        self._toggle_xy(self.cb_xy.isChecked())
        self._on_stage_kind_changed(self.cb_stage.currentText())
        self._update_scan_summary()

    def _set_scan_inputs_enabled(self, enabled: bool) -> None:
        for widget in self._scan_inputs:
            widget.setEnabled(enabled)
        self._toggle_xy(enabled and self.cb_xy.isChecked())

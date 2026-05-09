"""控制面板 — 三步工作流：设备、位移台、扫描计划。"""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QVBoxLayout, QWidget,
)

from ..core.scanner import ScanParams
from . import theme
from .control_panel_helpers import (
    axis as _axis, button as _btn, combo as _combo, dspin as _dspin,
    ispin as _ispin, kv as _kv, row as _row, row_widget as _row_widget,
    section as _section,
)
from .progress_bar import ScanProgressBar
from .settings import UserSettings
from .widgets import HintLabel, ValueLabel
from .workflow import ScanBrief, WorkflowGuide, duration_text

AVG_SAMPLE_MAX = 512
MS_PER_SECOND = 1000.0
PANEL_MAX_HEIGHT = 286


class ControlPanel(QWidget):
    connect_requested = Signal(str, str)
    disconnect_requested = Signal()
    move_requested = Signal(float, float, float)
    home_requested = Signal()
    scan_started = Signal(object)
    scan_canceled = Signal()
    plan_changed = Signal(str)

    def __init__(self, stages: list[str], cameras: list[str], parent=None) -> None:
        super().__init__(parent)
        self._connected = False
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
        }

    def _devices(self, stages, cameras) -> QWidget:
        self.cb_stage = _combo(stages)
        self.cb_cam = _combo(cameras)
        self.btn_conn = _btn("connect", primary=True)
        self.btn_disc = _btn("disconnect", danger=True, enabled=False)
        self.lbl_device_state = ValueLabel("offline")
        self.btn_conn.clicked.connect(lambda: self.connect_requested.emit(
            self.cb_stage.currentText(), self.cb_cam.currentText()))
        self.btn_disc.clicked.connect(self.disconnect_requested.emit)
        return _section("1 Devices", [
            _kv("stage driver", self.cb_stage),
            _kv("camera driver", self.cb_cam),
            _row(self.btn_conn, self.btn_disc, _stretch=True),
            _kv("state", self.lbl_device_state),
        ])

    def _stage(self) -> QWidget:
        self.sp_x, self.sp_y, self.sp_z = (_dspin(-1000, 1000, 0.0) for _ in range(3))
        self.btn_move = _btn("move stage", enabled=False)
        self.btn_home = _btn("home", enabled=False)
        self.btn_move.clicked.connect(lambda: self.move_requested.emit(
            self.sp_x.value(), self.sp_y.value(), self.sp_z.value()))
        self.btn_home.clicked.connect(self.home_requested.emit)
        return _section("2 Stage", [
            _row(_axis("target x", self.sp_x), _axis("target y", self.sp_y),
                 _axis("target z", self.sp_z), 8, HintLabel("µm"), _stretch=True),
            _row(self.btn_move, self.btn_home, _stretch=True),
        ])

    def _scan_params(self) -> QWidget:
        self.sp_zs = _dspin(-500, 500, -10.0)
        self.sp_ze = _dspin(-500, 500, 10.0)
        self.sp_zd = _dspin(0.01, 100, 0.5)
        self.sp_dwell = _ispin(0, 5000, 50, width=72)
        self.sp_avg = _ispin(1, AVG_SAMPLE_MAX, ScanParams.DEFAULT_SAMPLE_COUNT, width=62)
        self.lbl_plan = ValueLabel("")
        self.cb_xy = QCheckBox("include xy grid")
        self.sp_xs = _dspin(-500, 500, -5.0, enabled=False)
        self.sp_xe = _dspin(-500, 500, 5.0, enabled=False)
        self.sp_xd = _dspin(0.01, 100, 1.0, enabled=False)
        self.sp_ys = _dspin(-500, 500, -5.0, enabled=False)
        self.sp_ye = _dspin(-500, 500, 5.0, enabled=False)
        self.sp_yd = _dspin(0.01, 100, 1.0, enabled=False)
        self.scan_brief = ScanBrief()
        self._scan_inputs = (
            self.cb_xy, self.sp_zs, self.sp_ze, self.sp_zd, self.sp_dwell,
            self.sp_avg, self.sp_xs, self.sp_xe, self.sp_xd,
            self.sp_ys, self.sp_ye, self.sp_yd,
        )
        self._xy_rows = (
            _row_widget(HintLabel("x start"), self.sp_xs, HintLabel("stop"), self.sp_xe,
                        8, HintLabel("step"), self.sp_xd, _stretch=True),
            _row_widget(HintLabel("y start"), self.sp_ys, HintLabel("stop"), self.sp_ye,
                        8, HintLabel("step"), self.sp_yd, _stretch=True),
        )
        self._wire_scan_summary()
        self._toggle_xy(False)
        return _section("3 Scan plan", [
            _row(HintLabel("z start"), self.sp_zs, HintLabel("stop"), self.sp_ze,
                 12, HintLabel("step"), self.sp_zd, _stretch=True),
            _row(HintLabel("dwell"), self.sp_dwell, HintLabel("ms"),
                 18, HintLabel("avg"), self.sp_avg, _stretch=True),
            _row(self.cb_xy, _stretch=True),
            self.scan_brief,
            *self._xy_rows,
        ])

    def _scan_run(self) -> QHBoxLayout:
        self.btn_start = _btn("START SCAN", primary=True, enabled=False)
        self.btn_stop = _btn("stop", danger=True, enabled=False)
        self.btn_start.clicked.connect(self._emit_start)
        self.btn_stop.clicked.connect(self.scan_canceled.emit)
        self.pb = ScanProgressBar()
        self.pb.setRange(0, 100)
        self.pb.setFormat("0%")
        self.lbl_status = ValueLabel("ready · connect devices")
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
        self.cb_stage.setEnabled(not on); self.cb_cam.setEnabled(not on)
        self.lbl_device_state.setText("online" if on else "offline")
        self.lbl_status.setText("ready · set scan plan" if on else "ready · connect devices")
        self.workflow.set_phase(2 if on else 1)

    def set_scanning(self, on: bool) -> None:
        self.btn_start.setEnabled(not on); self.btn_stop.setEnabled(on)
        self.btn_disc.setEnabled(not on)
        self.btn_move.setEnabled(not on); self.btn_home.setEnabled(not on)
        self._set_scan_inputs_enabled(not on)
        self.pb.set_running(on)
        if on:
            self.pb.setValue(0); self.pb.setFormat("0%")
        self.workflow.set_phase(3 if on else (2 if self._connected else 1))

    def set_progress(self, idx: int, total: int, text: str = "") -> None:
        pct = int(idx / total * 100) if total else 0
        self.pb.setValue(pct)
        self.pb.setFormat(f"{idx} / {total}   {pct}%")
        self.lbl_status.setText(text or f"{idx} / {total}")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def plan_text(self) -> str:
        return self.lbl_plan.text()

    def bind_settings(self, settings: UserSettings) -> None:
        settings.bind_combo("devices/stage_driver", self.cb_stage)
        settings.bind_combo("devices/camera_driver", self.cb_cam)
        settings.bind_check("scan/include_xy_grid", self.cb_xy)
        for key, control in self._parameter_controls.items():
            settings.bind_spin(f"scan/{key}", control)
        self._toggle_xy(self.cb_xy.isChecked())
        self._update_scan_summary()

    def _set_scan_inputs_enabled(self, enabled: bool) -> None:
        for widget in self._scan_inputs:
            widget.setEnabled(enabled)
        self._toggle_xy(enabled and self.cb_xy.isChecked())

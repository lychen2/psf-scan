"""位移台 jog + 急停 — 嵌入 control_panel 的 stage section。

精简后 4 行布局:
  Row 1: ◀  [step]  ▶  [Zero]
  Row 2: [Calibrate range…]
  Row 3: [E-STOP — Esc/Space]
  Row 4: pos: X.X µm    range: [lo, hi]

3 步标定 (Rec- / Rec+ / Apply / Reset) 走 CalibrationDialog (modeless),
打开后用户仍能用 ◀▶ 移动位移台。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from ..core.i18n import tr
from .calibration_dialog import CalibrationDialog
from .control_panel_helpers import button as _btn, dspin as _dspin


class StageJogPanel(QWidget):
    """位移台 jog/标定/急停 控件 — 嵌入 control_panel.stage section。"""

    stop_requested = Signal()
    set_zero_requested = Signal()
    jog_requested = Signal(float)
    apply_limits_requested = Signal(float, float)
    reset_range_requested = Signal(float)  # radius_um — dialog 内 prompt 半径

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_z_um = 0.0
        self._travel_lo: float | None = None
        self._travel_hi: float | None = None
        self._calib_dialog: CalibrationDialog | None = None
        self._build()
        self._register_shortcuts()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(4)

        # Row 1: ◀  [step]  ▶  [Zero]
        row_jog = QHBoxLayout(); row_jog.setSpacing(6)
        self.btn_left = _btn("◀")
        self.btn_left.setToolTip(tr("tip.jog_left"))
        self.btn_right = _btn("▶")
        self.btn_right.setToolTip(tr("tip.jog_right"))
        self.sp_step = _dspin(0.01, 100_000.0, 100.0)
        self.sp_step.setSuffix(" µm")
        self.sp_step.setToolTip(tr("tip.jog_step"))
        self.btn_zero = _btn(tr("jog.zero"))
        self.btn_zero.setToolTip(tr("tip.zero"))
        self.btn_left.clicked.connect(lambda: self.jog_requested.emit(-self.sp_step.value()))
        self.btn_right.clicked.connect(lambda: self.jog_requested.emit(self.sp_step.value()))
        self.btn_zero.clicked.connect(self.set_zero_requested.emit)
        for w in (self.btn_left, self.sp_step, self.btn_right, self.btn_zero):
            row_jog.addWidget(w, stretch=1)
        outer.addLayout(row_jog)

        # Row 2: [Calibrate range…]
        self.btn_calib = _btn(tr("calib.open"))
        self.btn_calib.setToolTip(tr("tip.reset_range"))
        self.btn_calib.clicked.connect(self._open_calib_dialog)
        outer.addWidget(self.btn_calib)

        # Row 3: E-STOP (永久红色 — QSS [role="estop"])
        self.btn_estop = _btn(tr("jog.estop"), estop=True)
        self.btn_estop.setToolTip(tr("tip.estop"))
        self.btn_estop.clicked.connect(self.stop_requested.emit)
        outer.addWidget(self.btn_estop)

        # Row 4: pos / range
        self.lbl_range = QLabel(tr("jog.pos_range_empty"))
        self.lbl_range.setAlignment(Qt.AlignCenter)
        self.lbl_range.setStyleSheet(
            f"color:{theme.ACCENT};font-family:'Iosevka Term',monospace;"
            f"font-size:{theme.SIZE_BODY};font-weight:700;padding:2px;"
        )
        outer.addWidget(self.lbl_range)

        self.set_enabled(False)

    def _register_shortcuts(self) -> None:
        for seq in (QKeySequence(Qt.Key_Escape), QKeySequence(Qt.Key_Space)):
            sc = QShortcut(seq, self); sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(self.stop_requested.emit)

    @Slot(bool)
    def set_enabled(self, on: bool) -> None:
        for w in (self.btn_left, self.btn_right, self.sp_step, self.btn_zero, self.btn_calib):
            w.setEnabled(on)
        self.btn_estop.setEnabled(True)

    def _open_calib_dialog(self) -> None:
        """打开 modeless 标定对话框;已开就 raise。"""
        if self._calib_dialog is not None:
            self._calib_dialog.raise_(); self._calib_dialog.activateWindow()
            return
        dlg = CalibrationDialog(self._current_z_um, parent=self)
        dlg.apply_limits.connect(self.apply_limits_requested)
        dlg.reset_range.connect(self.reset_range_requested)
        dlg.finished.connect(self._on_calib_closed)
        self._calib_dialog = dlg
        dlg.show()

    def _on_calib_closed(self, *_: object) -> None:
        self._calib_dialog = None

    @Slot(float, float, float)
    def update_position(self, _x: float, _y: float, z: float) -> None:
        z = float(z)
        if abs(z) < 0.005: z = 0.0
        if abs(z - self._current_z_um) < 0.005: return
        self._current_z_um = z
        self._refresh_range()
        if self._calib_dialog is not None:
            self._calib_dialog.set_current_z(z)

    def _refresh_range(self) -> None:
        if self._travel_lo is None:
            self.lbl_range.setText(tr("jog.pos_range_norange", pos=self._current_z_um))
        else:
            self.lbl_range.setText(tr(
                "jog.pos_range_full",
                pos=self._current_z_um, lo=self._travel_lo, hi=self._travel_hi,
            ))

    @Slot(float, float)
    def set_travel_range_um(self, lo: float, hi: float) -> None:
        self._travel_lo = float(lo); self._travel_hi = float(hi)
        self._refresh_range()

    @Slot(float)
    def set_step_min(self, step_min: float) -> None:
        self.sp_step.setSingleStep(float(step_min))
        self.sp_step.setMinimum(float(step_min))
        if self.sp_step.value() < step_min: self.sp_step.setValue(step_min)

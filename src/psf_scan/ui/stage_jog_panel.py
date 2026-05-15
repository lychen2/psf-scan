"""位移台 jog 控件 — 急停 / 置零 / 相对移动 / 标定。

嵌入 control_panel 的 stage section, 风格使用 control_panel_helpers 的 button/dspin,
和上方 [Move]/[Home] 同尺度同样式。

Layout (4 紧凑行):
  Row 1: ◀  [step]  ▶  [Zero]
  Row 2: [Rec-] [Rec+] [Apply]
  Row 3: [E-STOP — Esc/Space]
  Row 4: pos: X.X µm    range: [lo, hi]
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QVBoxLayout, QWidget

from . import theme
from ..core.i18n import tr
from .control_panel_helpers import button as _btn, dspin as _dspin


class StageJogPanel(QWidget):
    """位移台 jog/calib/急停 控件 — 嵌入 control_panel.stage section。"""

    stop_requested = Signal()
    set_zero_requested = Signal()
    jog_requested = Signal(float)
    apply_limits_requested = Signal(float, float)
    reset_range_requested = Signal(float)  # radius_um — 用户在 prompt 输入半径

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_z_um = 0.0
        self._calib_min: float | None = None
        self._calib_max: float | None = None
        self._travel_lo: float | None = None
        self._travel_hi: float | None = None
        self._last_reset_radius_um = 1000.0  # 1 mm 默认
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

        # Row 2: Rec- / Rec+ / Apply / Reset
        row_cal = QHBoxLayout(); row_cal.setSpacing(6)
        self.btn_rec_min = _btn(tr("jog.rec_min"))
        self.btn_rec_min.setToolTip(tr("tip.rec_min"))
        self.btn_rec_max = _btn(tr("jog.rec_max"))
        self.btn_rec_max.setToolTip(tr("tip.rec_max"))
        self.btn_apply = _btn(tr("jog.apply"))
        self.btn_apply.setToolTip(tr("tip.apply"))
        self.btn_reset = _btn(tr("jog.reset"))
        self.btn_reset.setToolTip(tr("tip.reset_range"))
        self.btn_rec_min.clicked.connect(lambda: self._record(False))
        self.btn_rec_max.clicked.connect(lambda: self._record(True))
        self.btn_apply.clicked.connect(self._apply_calib)
        self.btn_reset.clicked.connect(self._prompt_reset_range)
        for w in (self.btn_rec_min, self.btn_rec_max, self.btn_apply, self.btn_reset):
            row_cal.addWidget(w, stretch=1)
        outer.addLayout(row_cal)

        # Row 3: E-STOP (永久红色, 不仅是 hover)
        self.btn_estop = _btn(tr("jog.estop"), danger=True)
        self.btn_estop.setToolTip(tr("tip.estop"))
        self.btn_estop.setStyleSheet(
            "QPushButton{background:#e63939;color:#fff;border:0;border-radius:3px;"
            "padding:8px;font-weight:700;letter-spacing:2px;font-size:11px;}"
            "QPushButton:hover{background:#ff4c4c;}"
            "QPushButton:pressed{background:#cc0000;}"
        )
        self.btn_estop.clicked.connect(self.stop_requested.emit)
        outer.addWidget(self.btn_estop)

        # Row 4: pos / range  +  calib status
        self.lbl_range = QLabel(tr("jog.pos_range_empty"))
        self.lbl_range.setAlignment(Qt.AlignCenter)
        self.lbl_range.setStyleSheet(
            f"color:{theme.ACCENT};font-family:'Iosevka Term',monospace;"
            "font-size:11px;font-weight:700;padding:2px;"
        )
        outer.addWidget(self.lbl_range)
        self.lbl_calib = QLabel(tr("jog.calib_hint"))
        self.lbl_calib.setStyleSheet(
            f"color:{theme.TEXT3};font-family:'Iosevka Term',monospace;font-size:9px;"
        )
        self.lbl_calib.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.lbl_calib)

        self.set_enabled(False)

    def _register_shortcuts(self) -> None:
        for seq in (QKeySequence(Qt.Key_Escape), QKeySequence(Qt.Key_Space)):
            sc = QShortcut(seq, self); sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(self.stop_requested.emit)

    @Slot(bool)
    def set_enabled(self, on: bool) -> None:
        for w in (self.btn_left, self.btn_right, self.sp_step, self.btn_zero,
                  self.btn_rec_min, self.btn_rec_max, self.btn_apply, self.btn_reset):
            w.setEnabled(on)
        self.btn_estop.setEnabled(True)

    def _prompt_reset_range(self) -> None:
        """弹框输入新行程半径 → emit reset_range_requested。"""
        radius, ok = QInputDialog.getDouble(
            self, tr("jog.reset_title"), tr("jog.reset_prompt"),
            self._last_reset_radius_um, 1.0, 1e7, 1,
        )
        if not ok:
            return
        self._last_reset_radius_um = float(radius)
        self.reset_range_requested.emit(float(radius))

    @Slot(float, float, float)
    def update_position(self, _x: float, _y: float, z: float) -> None:
        z = float(z)
        if abs(z) < 0.005: z = 0.0
        if abs(z - self._current_z_um) < 0.005: return
        self._current_z_um = z
        self._refresh_range()

    def _refresh_range(self) -> None:
        if self._travel_lo is None:
            self.lbl_range.setText(tr("jog.pos_range_norange", pos=self._current_z_um))
        else:
            self.lbl_range.setText(tr(
                "jog.pos_range_full",
                pos=self._current_z_um, lo=self._travel_lo, hi=self._travel_hi,
            ))

    def _record(self, is_max: bool) -> None:
        if is_max: self._calib_max = self._current_z_um
        else: self._calib_min = self._current_z_um
        lo = "—" if self._calib_min is None else f"{self._calib_min:.1f}"
        hi = "—" if self._calib_max is None else f"{self._calib_max:.1f}"
        self.lbl_calib.setText(tr("jog.calib_status", lo=lo, hi=hi))

    def _apply_calib(self) -> None:
        if self._calib_min is None or self._calib_max is None:
            self.lbl_calib.setText(tr("jog.calib_need_rec")); return
        lo, hi = sorted((self._calib_min, self._calib_max))
        self.apply_limits_requested.emit(lo, hi)
        self._calib_min = self._calib_max = None
        self.lbl_calib.setText(tr("jog.calib_applied", lo=lo, hi=hi))

    @Slot(float, float)
    def set_travel_range_um(self, lo: float, hi: float) -> None:
        self._travel_lo = float(lo); self._travel_hi = float(hi)
        self._refresh_range()

    @Slot(float)
    def set_step_min(self, step_min: float) -> None:
        self.sp_step.setSingleStep(float(step_min))
        self.sp_step.setMinimum(float(step_min))
        if self.sp_step.value() < step_min: self.sp_step.setValue(step_min)

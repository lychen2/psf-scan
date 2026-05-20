"""标定行程范围对话框 — 把 Rec/Apply/Reset 工作流从主面板移出。

主面板只剩一个 [Calibrate range…] 按钮;真正的 3 步工作流(到下限按
Rec-、到上限按 Rec+、点 Apply)在这个 modeless dialog 里展开,这样
用户仍可同时操作主面板上的 jog ◀▶ 移动 stage。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QVBoxLayout,
)

from ..core.i18n import tr
from . import theme
from .control_panel_helpers import button as _btn


class CalibrationDialog(QDialog):
    """3-step calibration: Rec- → Rec+ → Apply, plus Reset range."""

    apply_limits = Signal(float, float)
    reset_range = Signal(float)

    def __init__(self, current_z: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("calib.title"))
        self.setModal(False)
        self._current_z = float(current_z)
        self._calib_min: float | None = None
        self._calib_max: float | None = None
        self._last_reset_radius_um = 1000.0
        self._build()
        self._refresh_status()
        self._refresh_pos()

    @Slot(float)
    def set_current_z(self, z: float) -> None:
        self._current_z = float(z)
        self._refresh_pos()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.G_16, theme.G_16, theme.G_16, theme.G_16)
        layout.setSpacing(theme.G_8)

        intro = QLabel(tr("calib.intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{theme.TEXT2};font-size:{theme.SIZE_BODY};")
        layout.addWidget(intro)

        self.lbl_pos = QLabel()
        self.lbl_pos.setAlignment(Qt.AlignCenter)
        self.lbl_pos.setStyleSheet(
            f"color:{theme.ACCENT_LO};font-family:'{theme.MONO}',monospace;"
            f"font-size:{theme.SIZE_VALUE};font-weight:700;padding:6px;"
        )
        layout.addWidget(self.lbl_pos)

        rec_row = QHBoxLayout()
        rec_row.setSpacing(theme.G_8)
        self.btn_rec_min = _btn(tr("jog.rec_min"))
        self.btn_rec_max = _btn(tr("jog.rec_max"))
        self.btn_rec_min.clicked.connect(lambda: self._record(False))
        self.btn_rec_max.clicked.connect(lambda: self._record(True))
        rec_row.addWidget(self.btn_rec_min, stretch=1)
        rec_row.addWidget(self.btn_rec_max, stretch=1)
        layout.addLayout(rec_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"color:{theme.TEXT3};font-family:'{theme.MONO}',monospace;"
            f"font-size:{theme.SIZE_METER};padding:4px;"
        )
        layout.addWidget(self.lbl_status)

        action_row = QHBoxLayout()
        action_row.setSpacing(theme.G_8)
        self.btn_apply = _btn(tr("jog.apply"), primary=True)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_reset = _btn(tr("jog.reset"))
        self.btn_reset.clicked.connect(self._prompt_reset_range)
        btn_close = _btn(tr("calib.close"))
        btn_close.clicked.connect(self.close)
        action_row.addWidget(self.btn_reset)
        action_row.addStretch(1)
        action_row.addWidget(btn_close)
        action_row.addWidget(self.btn_apply)
        layout.addLayout(action_row)

    def _refresh_pos(self) -> None:
        self.lbl_pos.setText(tr("calib.current_pos", z=self._current_z))

    def _record(self, is_max: bool) -> None:
        if is_max:
            self._calib_max = self._current_z
        else:
            self._calib_min = self._current_z
        self._refresh_status()

    def _refresh_status(self) -> None:
        lo = "—" if self._calib_min is None else f"{self._calib_min:.1f}"
        hi = "—" if self._calib_max is None else f"{self._calib_max:.1f}"
        self.lbl_status.setText(tr("jog.calib_status", lo=lo, hi=hi))

    def _apply(self) -> None:
        if self._calib_min is None or self._calib_max is None:
            self.lbl_status.setText(tr("jog.calib_need_rec"))
            return
        lo, hi = sorted((self._calib_min, self._calib_max))
        self.apply_limits.emit(lo, hi)
        self.accept()

    def _prompt_reset_range(self) -> None:
        radius, ok = QInputDialog.getDouble(
            self, tr("jog.reset_title"), tr("jog.reset_prompt"),
            self._last_reset_radius_um, 1.0, 1e7, 1,
        )
        if not ok:
            return
        self._last_reset_radius_um = float(radius)
        self.reset_range.emit(float(radius))
        self.accept()

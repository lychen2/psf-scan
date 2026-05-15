"""Autofocus 进度对话框 — 显示 z 扫描与细化阶段的 Brenner 锐度曲线。"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from ..core.i18n import tr
from . import theme


class AutofocusDialog(QDialog):
    """非阻塞: 显示 z vs Brenner 实时曲线 + 进度条 + 取消按钮。"""

    cancel_requested = Signal()

    def __init__(self, total_points: int, z_range: tuple[float, float],
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("autofocus.title"))
        self.setModal(False)
        self.resize(480, 320)
        self.setStyleSheet(f"background:{theme.BG1};")
        self._total = max(1, int(total_points))
        self._finished = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._lbl_range = QLabel(
            tr("autofocus.range_label", lo=z_range[0], hi=z_range[1], n=total_points)
        )
        self._lbl_range.setStyleSheet(f"color:{theme.TEXT1};font-size:10px;")
        layout.addWidget(self._lbl_range)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG0)
        self._plot.setLabel("bottom", tr("autofocus.z_label"))
        self._plot.setLabel("left", tr("autofocus.score_label"))
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._curve = self._plot.plot(
            pen=None,
            symbol="o", symbolSize=6, symbolBrush=theme.ACCENT, symbolPen=None,
        )
        self._peak_line = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.DANGER, width=1.2, style=Qt.DashLine))
        self._peak_line.hide()
        self._plot.addItem(self._peak_line)
        layout.addWidget(self._plot, stretch=1)

        self._pb = QProgressBar()
        self._pb.setRange(0, self._total)
        self._pb.setValue(0)
        layout.addWidget(self._pb)

        row = QHBoxLayout()
        self._lbl_status = QLabel(tr("autofocus.status_running", done=0, total=self._total))
        self._lbl_status.setStyleSheet(f"color:{theme.TEXT0};font-family:'Iosevka Term',monospace;font-size:10px;")
        row.addWidget(self._lbl_status)
        row.addStretch()
        self.btn_cancel = QPushButton(tr("common.cancel"))
        self.btn_cancel.clicked.connect(self._on_button_clicked)
        row.addWidget(self.btn_cancel)
        layout.addLayout(row)

        self._zs: list[float] = []
        self._ss: list[float] = []

    def add_point(self, idx_1: int, total: int, z: float, score: float) -> None:
        self._total = max(int(total), int(idx_1), 1)
        self._pb.setRange(0, self._total)
        self._zs.append(float(z))
        self._ss.append(float(score))
        order = np.argsort(self._zs)
        self._curve.setData(
            np.asarray(self._zs)[order], np.asarray(self._ss)[order],
        )
        self._pb.setValue(idx_1)
        self._lbl_status.setText(tr("autofocus.status_running", done=idx_1, total=self._total))

    def show_peak(self, z: float, score: float, *, low_light: bool = False,
                  saturated: bool = False) -> None:
        self._finished = True
        self._peak_line.setPos(float(z))
        self._peak_line.show()
        key = _done_status_key(low_light=low_light, saturated=saturated)
        self._lbl_status.setText(tr(key, z=z, score=score))
        self.btn_cancel.setText(tr("common.close"))

    def _on_button_clicked(self) -> None:
        if self._finished:
            self.close()
            return
        self.cancel_requested.emit()


def _done_status_key(*, low_light: bool, saturated: bool) -> str:
    if saturated:
        return "autofocus.status_saturated"
    if low_light:
        return "autofocus.status_low_light"
    return "autofocus.status_done"

"""Line profile 弹窗 — pyqtgraph LineSegmentROI 数据 + 高斯 FWHM 拟合 + CSV 导出。

调用方:
- CameraView (C.3): live frame 上画一条线, 看一维 intensity + 拟合 FWHM。
- 后续可被 PSFView 复用 (同样的 image + LineSegmentROI 接入即可)。
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from ..core.profile import fwhm_gauss_fit, sample_along_line
from . import theme

MIN_CALIBRATION_LINE_PX = 1e-6


class LineProfileDialog(QDialog):
    """非模态弹窗 — owner 调 ``update_profile(image, p0, p1)`` 推数据进来。"""

    pixel_calibration_requested = Signal(float, float)  # line_length_px, line_length_um

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("line_profile.title"))
        self.setModal(False)
        self.resize(560, 360)
        self.setStyleSheet(f"background:{theme.BG1};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG0)
        self._plot.setLabel("bottom", tr("line_profile.x_label"))
        self._plot.setLabel("left", tr("line_profile.y_label"))
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._curve = self._plot.plot(pen=pg.mkPen(theme.ACCENT, width=2))
        self._fit_curve = self._plot.plot(pen=pg.mkPen(theme.DANGER, width=1.5, style=Qt.DashLine))
        layout.addWidget(self._plot, stretch=1)

        # 控件行: FWHM 显示 + 拟合开关 + CSV 导出
        row = QHBoxLayout()
        row.setSpacing(12)
        self._fwhm_lbl = QLabel(tr("line_profile.fwhm_placeholder"))
        self._fwhm_lbl.setStyleSheet(
            f"color:{theme.TEXT0};font-family:'Iosevka Term',monospace;"
            "font-size:11px;font-weight:600;"
        )
        row.addWidget(self._fwhm_lbl)
        row.addStretch()

        self.cb_fit = QCheckBox(tr("line_profile.fit"))
        self.cb_fit.setChecked(True)
        self.cb_fit.toggled.connect(self._refresh)
        row.addWidget(self.cb_fit)

        self.btn_csv = QPushButton(tr("line_profile.export_csv"))
        self.btn_csv.clicked.connect(self._export_csv)
        self.btn_csv.setEnabled(False)
        row.addWidget(self.btn_csv)

        layout.addLayout(row)
        layout.addLayout(self._build_calibration_row())

        self._last_positions: np.ndarray | None = None
        self._last_values: np.ndarray | None = None
        self._last_fit = None
        self._unit: str = "px"

    def _build_calibration_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(tr("line_profile.known_length")))
        self.sp_known_length = QDoubleSpinBox()
        self.sp_known_length.setRange(0.001, 1_000_000.0)
        self.sp_known_length.setDecimals(3)
        self.sp_known_length.setSuffix(" µm")
        self.sp_known_length.setButtonSymbols(QDoubleSpinBox.NoButtons)
        row.addWidget(self.sp_known_length)
        self.btn_set_pixel_calibration = QPushButton(tr("line_profile.set_pixel_calibration"))
        self.btn_set_pixel_calibration.setEnabled(False)
        self.btn_set_pixel_calibration.clicked.connect(self._emit_pixel_calibration)
        row.addWidget(self.btn_set_pixel_calibration)
        row.addStretch()
        return row

    def set_unit(self, unit: str) -> None:
        """让外部声明位置坐标单位 (默认 px); 出 CSV 与轴标签会用这个。"""
        self._unit = str(unit) or "px"
        self._plot.setLabel("bottom", f"{tr('line_profile.x_label')} ({self._unit})")

    def clear(self) -> None:
        self._curve.clear()
        self._fit_curve.clear()
        self._fwhm_lbl.setText(tr("line_profile.fwhm_placeholder"))
        self._last_positions = None
        self._last_values = None
        self._last_fit = None
        self.btn_csv.setEnabled(False)
        self.btn_set_pixel_calibration.setEnabled(False)

    def update_profile(self, image: np.ndarray,
                       p0: tuple[float, float], p1: tuple[float, float]) -> None:
        """image: (H,W) 或 (H,W,3); p0/p1 是 image 坐标系 (x, y) px。"""
        positions, values = sample_along_line(image, p0, p1)
        self._last_positions = positions
        self._last_values = values
        self._last_fit = fwhm_gauss_fit(positions, values) if self.cb_fit.isChecked() else None
        self._refresh()

    def _refresh(self) -> None:
        if self._last_positions is None or self._last_values is None:
            return
        self._curve.setData(self._last_positions, self._last_values)
        if self.cb_fit.isChecked():
            self._last_fit = fwhm_gauss_fit(self._last_positions, self._last_values)
        else:
            self._last_fit = None
        fit = self._last_fit
        if fit is not None:
            from ..core.profile import _gaussian  # 已存在
            xfit = np.linspace(self._last_positions[0], self._last_positions[-1], 200)
            yfit = _gaussian(xfit, fit.amplitude, fit.center, fit.fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0))), fit.baseline)
            self._fit_curve.setData(xfit, yfit)
            self._fwhm_lbl.setText(
                tr("line_profile.fwhm_value",
                   fwhm=fit.fwhm, unit=self._unit, center=fit.center, r2=fit.r2)
            )
        else:
            self._fit_curve.clear()
            self._fwhm_lbl.setText(tr("line_profile.fwhm_no_fit"))
        self.btn_csv.setEnabled(True)
        self.btn_set_pixel_calibration.setEnabled(True)

    def _emit_pixel_calibration(self) -> None:
        length_px = self._current_line_length_px()
        if length_px <= MIN_CALIBRATION_LINE_PX:
            QMessageBox.warning(self, tr("common.warning"), tr("pixel_calibration.line_too_short"))
            return
        self.pixel_calibration_requested.emit(length_px, self.sp_known_length.value())

    def _current_line_length_px(self) -> float:
        if self._last_positions is None or len(self._last_positions) == 0:
            return 0.0
        return float(self._last_positions[-1])

    def _export_csv(self) -> None:
        if self._last_positions is None or self._last_values is None:
            return
        default = Path.home() / time.strftime("line_profile_%Y%m%d_%H%M%S.csv", time.localtime())
        chosen, _ = QFileDialog.getSaveFileName(
            self, tr("line_profile.export_csv"), str(default), "CSV (*.csv)",
        )
        if not chosen:
            return
        try:
            header = f"position_{self._unit},intensity"
            data = np.column_stack([self._last_positions, self._last_values])
            np.savetxt(chosen, data, delimiter=",", header=header, comments="")
            fit = self._last_fit
            if fit is not None:
                with open(chosen, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n# gauss fit: center={fit.center:.4f} {self._unit}, "
                        f"fwhm={fit.fwhm:.4f} {self._unit}, "
                        f"amplitude={fit.amplitude:.2f}, baseline={fit.baseline:.2f}, r2={fit.r2:.3f}\n"
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("common.warning"), str(exc))

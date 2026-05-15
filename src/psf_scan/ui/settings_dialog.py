"""统一设置 dialog — 通用 / 位移台 / 相机 / 校正 / 数据 五个标签页.

承担:
- 语言切换 (zh/en) — 重启生效
- 软限位 (撞镜防护) — 6 个上下限 + 总开关 + 关闭警告
- PI 连接参数入口 (复用 PIConnectDialog)
- 相机伽马使能
- Dark/flat 校正
- 数据目录
"""

from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.i18n import SUPPORTED, tr
from ..core.calibration import capture_calibration_frame, save_calibration_frame
from ..core.camera import CameraBase
from ..core.pixel_calibration import METHOD_LINE, METHOD_SENSOR_OBJECTIVE, from_settings as pixel_calibration_from_settings
from ..core.safety import SafetyLimits
from . import theme
from .pi_connect_dialog import PIConnectDialog
from .settings import UserSettings


AUTOFOCUS_SAMPLE_MIN = 1
AUTOFOCUS_SAMPLE_MAX = 50


class SettingsDialog(QDialog):
    reference_clicked = Signal()  # 寻参按钮 — app 接管弹框 + 调 stage.reference

    def __init__(self, settings: UserSettings, parent=None,
                 camera: CameraBase | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._camera = camera
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumSize(540, 420)
        self.resize(640, 560)
        self.setStyleSheet(f"background:{theme.BG0};color:{theme.TEXT0};")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll_tab(self._tab_general()), tr("settings.tab_general"))
        self.tabs.addTab(_scroll_tab(self._tab_stage()), tr("settings.tab_stage"))
        self.tabs.addTab(_scroll_tab(self._tab_camera()), tr("settings.tab_camera"))
        self.tabs.addTab(_scroll_tab(self._tab_calibration()), tr("settings.tab_calibration"))
        self.tabs.addTab(_scroll_tab(self._tab_data()), tr("settings.tab_data"))
        layout.addWidget(self.tabs, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr("common.save"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── 通用 ────────────────────────────────────────────
    def _tab_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)
        self.cb_lang = QComboBox()
        self.cb_lang.setToolTip(tr("tip.settings_lang"))
        for code, label in SUPPORTED.items():
            self.cb_lang.addItem(label, code)
        cur = self._settings.language()
        ix = self.cb_lang.findData(cur)
        if ix >= 0:
            self.cb_lang.setCurrentIndex(ix)
        form.addRow(tr("settings.language"), self.cb_lang)
        hint = QLabel(tr("settings.language_hint"))
        hint.setStyleSheet(f"color:{theme.TEXT3};font-size:10px;")
        form.addRow("", hint)
        return w

    # ── 位移台 ──────────────────────────────────────────
    def _tab_stage(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        # 软限位
        limits = self._settings.safety_limits()
        gb = QGroupBox(tr("settings.safety_section"))
        gbl = QVBoxLayout(gb)
        self.chk_safety = QCheckBox(tr("settings.safety_enable"))
        self.chk_safety.setChecked(limits.enabled)
        self.chk_safety.setToolTip(tr("tip.settings_safety_enable"))
        self.chk_safety.toggled.connect(self._on_safety_toggled)
        gbl.addWidget(self.chk_safety)

        self.lbl_safety_warn = QLabel(tr("settings.safety_disable_warning"))
        self.lbl_safety_warn.setWordWrap(True)
        self.lbl_safety_warn.setStyleSheet(
            f"color:{theme.DANGER};background:{theme.BG1};border:1px solid {theme.DANGER};"
            "padding:6px;font-size:10px;"
        )
        self.lbl_safety_warn.setVisible(not limits.enabled)
        gbl.addWidget(self.lbl_safety_warn)

        self.lbl_safety_hint = QLabel(tr("safety.hw_frame_hint"))
        self.lbl_safety_hint.setWordWrap(True)
        self.lbl_safety_hint.setStyleSheet(
            f"color:{theme.TEXT1};background:{theme.BG1};border:1px solid {theme.BORDER1};"
            "padding:6px;font-size:10px;"
        )
        gbl.addWidget(self.lbl_safety_hint)

        form = QFormLayout()
        self.sp_xmin = _dspin(-1e5, 1e5, limits.x_min)
        self.sp_xmin.setToolTip(tr("tip.settings_axis_min"))
        self.sp_xmax = _dspin(-1e5, 1e5, limits.x_max)
        self.sp_xmax.setToolTip(tr("tip.settings_axis_max"))
        self.sp_ymin = _dspin(-1e5, 1e5, limits.y_min)
        self.sp_ymin.setToolTip(tr("tip.settings_axis_min"))
        self.sp_ymax = _dspin(-1e5, 1e5, limits.y_max)
        self.sp_ymax.setToolTip(tr("tip.settings_axis_max"))
        self.sp_zmin = _dspin(-1e5, 1e5, limits.z_min)
        self.sp_zmin.setToolTip(tr("tip.settings_axis_min"))
        self.sp_zmax = _dspin(-1e5, 1e5, limits.z_max)
        self.sp_zmax.setToolTip(tr("tip.settings_axis_max"))
        form.addRow(tr("settings.z_min"), self.sp_zmin)
        form.addRow(tr("settings.z_max"), self.sp_zmax)
        form.addRow(tr("settings.x_min"), self.sp_xmin)
        form.addRow(tr("settings.x_max"), self.sp_xmax)
        form.addRow(tr("settings.y_min"), self.sp_ymin)
        form.addRow(tr("settings.y_max"), self.sp_ymax)
        # 大幅移动确认阈值 — 任何单次 z 移动 >= 此值会弹框
        self.sp_large_move = _dspin(0.1, 1e6, self._settings.large_move_um())
        self.sp_large_move.setToolTip(tr("tip.settings_large_move"))
        form.addRow(tr("settings.large_move_threshold"), self.sp_large_move)
        gbl.addLayout(form)
        layout.addWidget(gb)

        # Autofocus (C.6)
        gb_af = QGroupBox(tr("settings.autofocus_section"))
        afl = QVBoxLayout(gb_af)
        self.chk_af = QCheckBox(tr("settings.autofocus_enable"))
        self.chk_af.setChecked(self._settings.autofocus_enabled())
        self.chk_af.setToolTip(tr("tip.settings_autofocus_enable"))
        afl.addWidget(self.chk_af)
        af_form = QFormLayout()
        self.sp_af_max = _dspin(10.0, 1e6, self._settings.autofocus_max_um())
        self.sp_af_max.setToolTip(tr("tip.settings_autofocus_max"))
        af_form.addRow(tr("settings.autofocus_max"), self.sp_af_max)
        self.sp_af_step = _dspin(0.1, 1000.0, self._settings.autofocus_step_um())
        self.sp_af_step.setToolTip(tr("tip.settings_autofocus_step"))
        af_form.addRow(tr("settings.autofocus_step"), self.sp_af_step)
        self.sp_af_dwell = _dspin(0.0, 5000.0, float(self._settings.autofocus_dwell_ms()),
                                  suffix=" ms")
        self.sp_af_dwell.setToolTip(tr("tip.settings_autofocus_dwell"))
        af_form.addRow(tr("settings.autofocus_dwell"), self.sp_af_dwell)
        self.sp_af_samples = QSpinBox()
        self.sp_af_samples.setRange(AUTOFOCUS_SAMPLE_MIN, AUTOFOCUS_SAMPLE_MAX)
        self.sp_af_samples.setValue(self._settings.autofocus_sample_count())
        self.sp_af_samples.setToolTip(tr("tip.settings_autofocus_samples"))
        af_form.addRow(tr("settings.autofocus_samples"), self.sp_af_samples)
        afl.addLayout(af_form)
        layout.addWidget(gb_af)

        # PI 连接
        gb_pi = QGroupBox(tr("settings.pi_section"))
        pl = QHBoxLayout(gb_pi)
        self.btn_pi = QPushButton(tr("settings.pi_open"))
        self.btn_pi.setToolTip(tr("tip.settings_pi_open"))
        self.btn_pi.clicked.connect(self._open_pi_dialog)
        pl.addWidget(self.btn_pi)
        pl.addStretch()
        layout.addWidget(gb_pi)

        # 寻参 (危险, 藏在 settings 防止误触)
        gb_ref = QGroupBox(tr("settings.reference_section"))
        rfl = QVBoxLayout(gb_ref)
        ref_warn = QLabel(tr("settings.reference_warning"))
        ref_warn.setWordWrap(True)
        ref_warn.setStyleSheet(
            f"color:{theme.DANGER};background:{theme.BG1};border:1px solid {theme.DANGER};"
            "padding:6px;font-size:10px;"
        )
        rfl.addWidget(ref_warn)
        self.btn_ref = QPushButton(tr("settings.reference_button"))
        self.btn_ref.setToolTip(tr("tip.settings_ref"))
        self.btn_ref.setProperty("role", "danger")
        self.btn_ref.clicked.connect(self.reference_clicked.emit)
        rfl.addWidget(self.btn_ref)
        layout.addWidget(gb_ref)

        # 轴反转
        invert = self._settings.axis_inversion()
        gb_axes = QGroupBox(tr("settings.axes_section"))
        avl = QVBoxLayout(gb_axes)
        row_inv = QHBoxLayout()
        self.chk_inv_x = QCheckBox(tr("settings.invert_x"))
        self.chk_inv_x.setChecked(invert[0])
        self.chk_inv_x.setToolTip(tr("tip.settings_invert"))
        self.chk_inv_y = QCheckBox(tr("settings.invert_y"))
        self.chk_inv_y.setChecked(invert[1])
        self.chk_inv_y.setToolTip(tr("tip.settings_invert"))
        self.chk_inv_z = QCheckBox(tr("settings.invert_z"))
        self.chk_inv_z.setChecked(invert[2])
        self.chk_inv_z.setToolTip(tr("tip.settings_invert"))
        for c in (self.chk_inv_x, self.chk_inv_y, self.chk_inv_z):
            row_inv.addWidget(c)
        row_inv.addStretch()
        avl.addLayout(row_inv)
        hint = QLabel(tr("settings.axes_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.TEXT3};font-size:10px;")
        avl.addWidget(hint)
        layout.addWidget(gb_axes)
        layout.addStretch()
        return w

    def _on_safety_toggled(self, on: bool) -> None:
        self.lbl_safety_warn.setVisible(not on)

    def _open_pi_dialog(self) -> None:
        dlg = PIConnectDialog(self._settings.pi_params(), parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._settings.set_pi_params(dlg.values())
            QMessageBox.information(self, tr("settings.title"), tr("settings.applied"))

    # ── 相机 ────────────────────────────────────────────
    def _tab_camera(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.chk_gamma = QCheckBox(tr("camera.gamma_enable"))
        self.chk_gamma.setChecked(self._settings.gamma_enabled())
        self.chk_gamma.setToolTip(tr("tip.settings_gamma_enable"))
        form.addRow(tr("camera.gamma"), self.chk_gamma)
        layout.addLayout(form)
        layout.addWidget(self._pixel_calibration_group())
        layout.addStretch()
        return w

    def _pixel_calibration_group(self) -> QGroupBox:
        cfg = self._settings.pixel_calibration_config()
        group = QGroupBox(tr("pixel_calibration.section"))
        layout = QVBoxLayout(group)
        self.chk_pixel_calibration = QCheckBox(tr("pixel_calibration.enable"))
        self.chk_pixel_calibration.setChecked(bool(cfg["enabled"]))
        self.chk_pixel_calibration.setToolTip(tr("tip.pixel_calibration_enable"))
        layout.addWidget(self.chk_pixel_calibration)

        form = QFormLayout()
        self.cb_pixel_calibration_method = QComboBox()
        self.cb_pixel_calibration_method.addItem(
            tr("pixel_calibration.method_sensor_objective"),
            METHOD_SENSOR_OBJECTIVE,
        )
        self.cb_pixel_calibration_method.addItem(tr("pixel_calibration.method_line"), METHOD_LINE)
        index = self.cb_pixel_calibration_method.findData(cfg["method"])
        self.cb_pixel_calibration_method.setCurrentIndex(max(0, index))
        form.addRow(tr("pixel_calibration.method"), self.cb_pixel_calibration_method)
        self.sp_pixel_size = _dspin(0.01, 100.0, float(cfg["pixel_size_um"]), suffix=" µm")
        self.sp_pixel_size.setToolTip(tr("tip.pixel_size_um"))
        form.addRow(tr("pixel_calibration.pixel_size"), self.sp_pixel_size)
        self.sp_objective_mag = _dspin(0.1, 1000.0, float(cfg["objective_magnification"]), suffix="×")
        self.sp_objective_mag.setToolTip(tr("tip.objective_magnification"))
        form.addRow(tr("pixel_calibration.objective_mag"), self.sp_objective_mag)
        layout.addLayout(form)

        self.lbl_pixel_calibration_status = QLabel(_pixel_calibration_status(cfg))
        self.lbl_pixel_calibration_status.setWordWrap(True)
        self.lbl_pixel_calibration_status.setStyleSheet(f"color:{theme.TEXT3};font-size:10px;")
        layout.addWidget(self.lbl_pixel_calibration_status)
        self.cb_pixel_calibration_method.currentIndexChanged.connect(
            self._refresh_pixel_calibration_hint,
        )
        return group

    def _refresh_pixel_calibration_hint(self) -> None:
        cfg = dict(self._settings.pixel_calibration_config())
        cfg["enabled"] = self.chk_pixel_calibration.isChecked()
        cfg["method"] = self.cb_pixel_calibration_method.currentData()
        cfg["pixel_size_um"] = self.sp_pixel_size.value()
        cfg["objective_magnification"] = self.sp_objective_mag.value()
        self.lbl_pixel_calibration_status.setText(_pixel_calibration_status(cfg))

    # ── 校正 ────────────────────────────────────────────
    def _tab_calibration(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        cfg = self._settings.calibration_config()

        self.chk_dark = QCheckBox(tr("calibration.dark_enable"))
        self.chk_dark.setChecked(bool(cfg["dark_enabled"]))
        self.chk_dark.setToolTip(tr("tip.calibration_dark_enable"))
        layout.addWidget(self.chk_dark)
        self.le_dark = self._calibration_path_row(
            layout=layout,
            label=tr("calibration.dark_path"),
            value=cfg["dark_path"],
            capture_cb=self._capture_dark,
            kind="dark",
        )

        self.chk_flat = QCheckBox(tr("calibration.flat_enable"))
        self.chk_flat.setChecked(bool(cfg["flat_enabled"]))
        self.chk_flat.setToolTip(tr("tip.calibration_flat_enable"))
        layout.addWidget(self.chk_flat)
        self.le_flat = self._calibration_path_row(
            layout=layout,
            label=tr("calibration.flat_path"),
            value=cfg["flat_path"],
            capture_cb=self._capture_flat,
            kind="flat",
        )

        form = QFormLayout()
        self.cb_flat_mode = QComboBox()
        self.cb_flat_mode.setToolTip(tr("tip.calibration_flat_mode"))
        self.cb_flat_mode.addItem(tr("calibration.mode_intensity"), "intensity")
        self.cb_flat_mode.addItem(tr("calibration.mode_coherent"), "flat_coherent")
        ix = self.cb_flat_mode.findData(cfg["flat_mode"])
        self.cb_flat_mode.setCurrentIndex(max(0, ix))
        form.addRow(tr("calibration.flat_mode"), self.cb_flat_mode)
        layout.addLayout(form)

        hint = QLabel(tr("calibration.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.TEXT3};font-size:10px;")
        layout.addWidget(hint)
        layout.addStretch()
        return w

    def _calibration_path_row(
        self,
        *,
        layout: QVBoxLayout,
        label: str,
        value: str,
        capture_cb,
        kind: str,
    ) -> QLineEdit:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit(value)
        edit.setToolTip(tr("tip.calibration_path"))
        row.addWidget(edit, stretch=1)
        choose = QPushButton(tr("calibration.choose"))
        choose.setToolTip(tr("tip.calibration_choose"))
        choose.clicked.connect(lambda: self._pick_calibration_file(edit))
        row.addWidget(choose)
        capture_key = "calibration.capture_dark" if kind == "dark" else "calibration.capture_flat"
        capture = QPushButton(tr(capture_key))
        capture.setToolTip(tr("tip.calibration_capture"))
        capture.clicked.connect(lambda: capture_cb(edit))
        row.addWidget(capture)
        layout.addLayout(row)
        return edit

    def _pick_calibration_file(self, edit: QLineEdit) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, tr("settings.title"), str(self._settings.data_dir()), "Calibration (*.npz)",
        )
        if chosen:
            edit.setText(chosen)

    def _capture_dark(self, edit: QLineEdit) -> None:
        self._capture_calibration(edit, kind="dark", prompt=tr("calibration.dark_prompt"))

    def _capture_flat(self, edit: QLineEdit) -> None:
        self._capture_calibration(edit, kind="flat", prompt=tr("calibration.flat_prompt"))

    def _capture_calibration(self, edit: QLineEdit, *, kind: str, prompt: str) -> None:
        if self._camera is None:
            QMessageBox.warning(self, tr("settings.title"), tr("calibration.no_camera"))
            return
        if QMessageBox.question(self, tr("settings.title"), prompt) != QMessageBox.Yes:
            return
        try:
            frame = capture_calibration_frame(self._camera, kind=kind)
            target = self._settings.data_dir() / "calibration" / f"{kind}_{time.strftime('%Y%m%d_%H%M%S')}.npz"
            save_calibration_frame(frame, target)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("settings.title"), tr("calibration.failed", msg=str(exc)))
            return
        edit.setText(str(target))
        QMessageBox.information(self, tr("settings.title"), tr("calibration.saved", path=target.name))

    # ── 数据 ────────────────────────────────────────────
    def _tab_data(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("settings.data_dir")))
        self.le_data = QLineEdit(str(self._settings.data_dir()))
        self.le_data.setReadOnly(True)
        self.le_data.setToolTip(tr("tip.settings_data_dir"))
        row.addWidget(self.le_data, stretch=1)
        btn_pick = QPushButton(tr("settings.data_dir_choose"))
        btn_pick.setToolTip(tr("tip.settings_data_choose"))
        btn_pick.clicked.connect(self._pick_data_dir)
        row.addWidget(btn_pick)
        btn_open = QPushButton(tr("settings.data_dir_open"))
        btn_open.setToolTip(tr("tip.settings_data_open"))
        btn_open.clicked.connect(self._open_data_dir)
        row.addWidget(btn_open)
        layout.addLayout(row)
        layout.addStretch()
        return w

    def _pick_data_dir(self) -> None:
        cur = Path(self.le_data.text() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, tr("settings.data_dir"), str(cur if cur.exists() else Path.home()),
        )
        if chosen:
            self.le_data.setText(chosen)

    def _open_data_dir(self) -> None:
        path = Path(self.le_data.text() or "")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, tr("common.error"), str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ── 保存 ────────────────────────────────────────────
    def _on_save(self) -> None:
        # 语言
        new_lang = self.cb_lang.currentData()
        old_lang = self._settings.language()
        self._settings.set_language(new_lang)
        # 软限位
        self._settings.set_safety_limits(SafetyLimits(
            enabled=self.chk_safety.isChecked(),
            x_min=self.sp_xmin.value(),
            x_max=self.sp_xmax.value(),
            y_min=self.sp_ymin.value(),
            y_max=self.sp_ymax.value(),
            z_min=self.sp_zmin.value(),
            z_max=self.sp_zmax.value(),
        ))
        # 相机
        self._settings.set_gamma_enabled(self.chk_gamma.isChecked())
        pixel_cfg = self._settings.pixel_calibration_config()
        self._settings.set_pixel_calibration_config({
            "enabled": self.chk_pixel_calibration.isChecked(),
            "method": self.cb_pixel_calibration_method.currentData(),
            "pixel_size_um": self.sp_pixel_size.value(),
            "objective_magnification": self.sp_objective_mag.value(),
            "line_length_px": pixel_cfg["line_length_px"],
            "line_length_um": pixel_cfg["line_length_um"],
        })
        self._settings.set_calibration_config({
            "dark_enabled": self.chk_dark.isChecked(),
            "flat_enabled": self.chk_flat.isChecked(),
            "dark_path": self.le_dark.text().strip(),
            "flat_path": self.le_flat.text().strip(),
            "flat_mode": self.cb_flat_mode.currentData(),
        })
        # 轴反转
        self._settings.set_axis_inversion((
            self.chk_inv_x.isChecked(),
            self.chk_inv_y.isChecked(),
            self.chk_inv_z.isChecked(),
        ))
        # 数据目录
        new_dir = self.le_data.text().strip()
        if new_dir:
            self._settings.set_data_dir(new_dir)
        # 大幅移动阈值
        self._settings.set_large_move_um(self.sp_large_move.value())
        # 自动对焦 (C.6)
        self._settings.set_autofocus_enabled(self.chk_af.isChecked())
        self._settings.set_autofocus_max_um(self.sp_af_max.value())
        self._settings.set_autofocus_step_um(self.sp_af_step.value())
        self._settings.set_autofocus_dwell_ms(int(self.sp_af_dwell.value()))
        self._settings.set_autofocus_sample_count(int(self.sp_af_samples.value()))
        # 语言变更提示重启
        if new_lang != old_lang:
            QMessageBox.information(self, tr("settings.title"), tr("settings.language_hint"))
        self.accept()


def _pixel_calibration_status(config: dict[str, object]) -> str:
    detail = _pixel_calibration_detail(config)
    if not bool(config["enabled"]):
        return tr("pixel_calibration.status_off", detail=detail)
    return detail


def _pixel_calibration_detail(config: dict[str, object]) -> str:
    if str(config["method"]) == METHOD_SENSOR_OBJECTIVE:
        return _sensor_objective_detail(config)
    return _line_calibration_detail(config)


def _sensor_objective_detail(config: dict[str, object]) -> str:
    try:
        enabled_config = dict(config)
        enabled_config["enabled"] = True
        calibration = pixel_calibration_from_settings(enabled_config)
    except (KeyError, ValueError) as exc:
        return tr("pixel_calibration.status_invalid", msg=str(exc))
    return tr(
        "pixel_calibration.sensor_value",
        pixel=float(config["pixel_size_um"]),
        mag=float(config["objective_magnification"]),
        um=calibration.microns_per_pixel,
    )


def _line_calibration_detail(config: dict[str, object]) -> str:
    line_px = float(config["line_length_px"])
    line_um = float(config["line_length_um"])
    if line_px <= 0.0 or line_um <= 0.0:
        return tr("pixel_calibration.status_empty")
    try:
        enabled_config = dict(config)
        enabled_config["enabled"] = True
        calibration = pixel_calibration_from_settings(enabled_config)
    except (KeyError, ValueError) as exc:
        return tr("pixel_calibration.status_invalid", msg=str(exc))
    return tr(
        "pixel_calibration.line_saved",
        px=line_px,
        um=line_um,
        scale=calibration.microns_per_pixel,
    )


def _dspin(lo: float, hi: float, value: float, *, suffix: str = " µm") -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi)
    sp.setDecimals(2)
    sp.setSuffix(suffix)
    sp.setValue(float(value))
    return sp


def _scroll_tab(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(content)
    return area

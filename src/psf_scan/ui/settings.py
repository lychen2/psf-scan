"""Persistent user-adjustable UI parameters."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

from ..core.i18n import DEFAULT_LANGUAGE, LANGUAGE_KEY, SUPPORTED
from ..core.pixel_calibration import METHOD_LINE, METHOD_SENSOR_OBJECTIVE
from ..core.safety import SafetyLimits

ORG_NAME = "PSF Scan"
APP_NAME = "PSF Scan"

DATA_DIR_KEY = "save/base_dir"
DEFAULT_SENSOR_PIXEL_SIZE_UM = 2.4
DEFAULT_OBJECTIVE_MAGNIFICATION = 10.0


def default_data_dir() -> Path:
    """跨平台默认数据目录 — 写得到的位置 (Win: 我的文档/PSF Scan)。"""
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    base = Path(docs) if docs else Path.home()
    return base / "PSF Scan"


class UserSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(ORG_NAME, APP_NAME)

    def value_int(self, key: str, default: int) -> int:
        return int(self._settings.value(key, default))

    def value_float(self, key: str, default: float) -> float:
        return float(self._settings.value(key, default))

    def set_value(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise RuntimeError(f"保存设置失败: {key}")

    def data_dir(self) -> Path:
        raw = self._settings.value(DATA_DIR_KEY, "")
        path = Path(str(raw)) if raw else default_data_dir()
        return path

    def set_data_dir(self, path: Path | str) -> None:
        self.set_value(DATA_DIR_KEY, str(Path(path)))

    def large_move_um(self) -> float:
        """单次移动 >= 此阈值时弹框确认 (防撞)。默认 1000 µm = 1 mm。"""
        return float(self._settings.value("safety/large_move_um", 5000.0) or 5000.0)

    def set_large_move_um(self, v: float) -> None:
        self.set_value("safety/large_move_um", float(v))

    def autofocus_max_um(self) -> float:
        """自动对焦单次搜索 z 总位移上限 (µm). 默认 2000 = ±2 mm.

        实际范围还需与软限位和位移台行程取交集 (app 层做)。
        """
        return float(self._settings.value("autofocus/max_um", 2000.0) or 2000.0)

    def set_autofocus_max_um(self, v: float) -> None:
        self.set_value("autofocus/max_um", float(v))

    def autofocus_enabled(self) -> bool:
        """是否允许在主界面用 auto focus 按钮 (默认 True). 关掉则按钮灰掉。"""
        raw = self._settings.value("autofocus/enabled", True)
        if isinstance(raw, str):
            return raw.lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    def set_autofocus_enabled(self, v: bool) -> None:
        self.set_value("autofocus/enabled", bool(v))

    def autofocus_step_um(self) -> float:
        """自动对焦粗扫 step (µm). 默认 5 µm."""
        return float(self._settings.value("autofocus/step_um", 5.0) or 5.0)

    def set_autofocus_step_um(self, v: float) -> None:
        self.set_value("autofocus/step_um", float(v))

    def autofocus_dwell_ms(self) -> int:
        """每个 z 点稳定 + 取帧前的 dwell (ms). 默认 50."""
        return int(self._settings.value("autofocus/dwell_ms", 50) or 50)

    def set_autofocus_dwell_ms(self, v: int) -> None:
        self.set_value("autofocus/dwell_ms", int(v))

    def autofocus_sample_count(self) -> int:
        """自动对焦每个 z 点取帧数。多帧平均可降低低光照噪声。"""
        return int(self._settings.value("autofocus/sample_count", 3) or 3)

    def set_autofocus_sample_count(self, v: int) -> None:
        self.set_value("autofocus/sample_count", int(v))

    def pi_params(self) -> dict:
        """读 PI 连接参数 (供 PIStage 构造)。所有距离单位 µm, 速度 µm/s。"""
        s = self._settings
        return {
            "controller": str(s.value("pi/controller", "C-863")),
            "stage": str(s.value("pi/stage", "M-531.DG")),
            "interface": str(s.value("pi/interface", "usb")),
            "serialnum": str(s.value("pi/serialnum", "")),
            "ip": str(s.value("pi/ip", "")),
            "ipport": int(s.value("pi/ipport", 50000) or 50000),
            "comport": int(s.value("pi/comport", 0) or 0),
            "baudrate": int(s.value("pi/baudrate", 115200) or 115200),
            "device_id": int(s.value("pi/device_id", 0) or 0),
            "refmode": str(s.value("pi/refmode", "FRF")),
            "referencing": str(s.value("pi/referencing", "skip")),
            "travel_min_um": float(s.value("pi/travel_min_um", 0.0) or 0.0),
            "travel_max_um": float(s.value("pi/travel_max_um", 150_000.0) or 150_000.0),
            "velocity_um_s": float(s.value("pi/velocity_um_s", 0.0) or 0.0),
            "velocity_max_um_s": float(s.value("pi/velocity_max_um_s", 2_000.0) or 2_000.0),
            "step_min_um": float(s.value("pi/step_min_um", 0.4) or 0.4),
            "poll_hz": int(s.value("pi/poll_hz", 30) or 30),
            "position_tolerance_um": float(s.value("pi/position_tolerance_um", 0.05) or 0.05),
        }

    def set_pi_params(self, params: dict) -> None:
        for key, value in params.items():
            self.set_value(f"pi/{key}", value)

    def ui_scale_pref(self) -> float:
        """UI 缩放偏好。0.0 = 自动(按屏幕 DPI 推荐),其余值 = 显式倍率。"""
        raw = self._settings.value("ui/scale_factor", 0.0)
        try:
            return float(raw or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def set_ui_scale_pref(self, v: float) -> None:
        self.set_value("ui/scale_factor", float(v))

    def language(self) -> str:
        raw = str(self._settings.value(LANGUAGE_KEY, DEFAULT_LANGUAGE))
        return raw if raw in SUPPORTED else DEFAULT_LANGUAGE

    def set_language(self, code: str) -> None:
        if code in SUPPORTED:
            self.set_value(LANGUAGE_KEY, code)

    def safety_limits(self) -> SafetyLimits:
        s = self._settings
        return SafetyLimits(
            enabled=_bool_value(s.value("safety/enabled", True)),
            x_min=float(s.value("safety/x_min", -100.0)),
            x_max=float(s.value("safety/x_max", 100.0)),
            y_min=float(s.value("safety/y_min", -100.0)),
            y_max=float(s.value("safety/y_max", 100.0)),
            z_min=float(s.value("safety/z_min", -100.0)),
            z_max=float(s.value("safety/z_max", 100.0)),
        )

    def set_safety_limits(self, limits: SafetyLimits) -> None:
        self.set_value("safety/enabled", limits.enabled)
        self.set_value("safety/x_min", float(limits.x_min))
        self.set_value("safety/x_max", float(limits.x_max))
        self.set_value("safety/y_min", float(limits.y_min))
        self.set_value("safety/y_max", float(limits.y_max))
        self.set_value("safety/z_min", float(limits.z_min))
        self.set_value("safety/z_max", float(limits.z_max))

    def gamma_enabled(self) -> bool:
        return _bool_value(self._settings.value("camera/gamma_enabled", False))

    def set_gamma_enabled(self, on: bool) -> None:
        self.set_value("camera/gamma_enabled", bool(on))

    def calibration_config(self) -> dict:
        s = self._settings
        return {
            "dark_enabled": _bool_value(s.value("calibration/dark_enabled", False)),
            "flat_enabled": _bool_value(s.value("calibration/flat_enabled", False)),
            "dark_path": str(s.value("calibration/dark_path", "") or ""),
            "flat_path": str(s.value("calibration/flat_path", "") or ""),
            "flat_mode": str(s.value("calibration/flat_mode", "intensity") or "intensity"),
        }

    def set_calibration_config(self, config: dict) -> None:
        self.set_value("calibration/dark_enabled", bool(config["dark_enabled"]))
        self.set_value("calibration/flat_enabled", bool(config["flat_enabled"]))
        self.set_value("calibration/dark_path", str(config["dark_path"]))
        self.set_value("calibration/flat_path", str(config["flat_path"]))
        self.set_value("calibration/flat_mode", str(config["flat_mode"]))

    def pixel_calibration_config(self) -> dict[str, object]:
        s = self._settings
        return {
            "enabled": _bool_value(s.value("pixel_calibration/enabled", False)),
            "method": str(s.value("pixel_calibration/method", METHOD_SENSOR_OBJECTIVE)),
            "pixel_size_um": float(
                s.value("pixel_calibration/pixel_size_um", DEFAULT_SENSOR_PIXEL_SIZE_UM)
                or DEFAULT_SENSOR_PIXEL_SIZE_UM,
            ),
            "objective_magnification": float(
                s.value("pixel_calibration/objective_magnification", DEFAULT_OBJECTIVE_MAGNIFICATION)
                or DEFAULT_OBJECTIVE_MAGNIFICATION,
            ),
            "line_length_px": float(s.value("pixel_calibration/line_length_px", 0.0) or 0.0),
            "line_length_um": float(s.value("pixel_calibration/line_length_um", 0.0) or 0.0),
            "created_at": float(s.value("pixel_calibration/created_at", 0.0) or 0.0),
        }

    def set_pixel_calibration_config(self, config: dict[str, object]) -> None:
        self.set_value("pixel_calibration/enabled", bool(config["enabled"]))
        self.set_value("pixel_calibration/method", str(config["method"]))
        self.set_value("pixel_calibration/pixel_size_um", float(config["pixel_size_um"]))
        self.set_value(
            "pixel_calibration/objective_magnification",
            float(config["objective_magnification"]),
        )
        self.set_value("pixel_calibration/created_at", float(time.time()))

    def set_line_pixel_calibration(self, *, line_length_px: float, line_length_um: float) -> None:
        self.set_value("pixel_calibration/method", METHOD_LINE)
        self.set_value("pixel_calibration/enabled", True)
        self.set_value("pixel_calibration/line_length_px", float(line_length_px))
        self.set_value("pixel_calibration/line_length_um", float(line_length_um))
        self.set_value("pixel_calibration/created_at", float(time.time()))

    def axis_inversion(self) -> tuple[bool, bool, bool]:
        s = self._settings
        return (
            _bool_value(s.value("axes/invert_x", False)),
            _bool_value(s.value("axes/invert_y", False)),
            _bool_value(s.value("axes/invert_z", False)),
        )

    def set_axis_inversion(self, invert: tuple[bool, bool, bool]) -> None:
        ix, iy, iz = invert
        self.set_value("axes/invert_x", bool(ix))
        self.set_value("axes/invert_y", bool(iy))
        self.set_value("axes/invert_z", bool(iz))

    def bind_combo(self, key: str, control: QComboBox) -> None:
        text = str(self._settings.value(key, control.currentText()))
        index = control.findText(text)
        if index >= 0:
            control.setCurrentIndex(index)
        control.currentTextChanged.connect(lambda value: self.set_value(key, value))

    def bind_check(self, key: str, control: QCheckBox) -> None:
        control.setChecked(_bool_value(self._settings.value(key, control.isChecked())))
        control.toggled.connect(lambda value: self.set_value(key, value))

    def bind_spin(self, key: str, control) -> None:
        if hasattr(control, 'spin'):
            inner = control.spin
        else:
            inner = control
        value = self._settings.value(key, inner.value())
        inner.setValue(float(value) if isinstance(inner, QDoubleSpinBox) else int(value))
        control.valueChanged.connect(lambda value: self.set_value(key, value))


def _bool_value(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)

"""Persistent user-adjustable UI parameters."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

ORG_NAME = "PSF Scan"
APP_NAME = "PSF Scan"

DATA_DIR_KEY = "save/base_dir"


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

    def bind_combo(self, key: str, control: QComboBox) -> None:
        text = str(self._settings.value(key, control.currentText()))
        index = control.findText(text)
        if index >= 0:
            control.setCurrentIndex(index)
        control.currentTextChanged.connect(lambda value: self.set_value(key, value))

    def bind_check(self, key: str, control: QCheckBox) -> None:
        control.setChecked(_bool_value(self._settings.value(key, control.isChecked())))
        control.toggled.connect(lambda value: self.set_value(key, value))

    def bind_spin(self, key: str, control: QSpinBox | QDoubleSpinBox) -> None:
        value = self._settings.value(key, control.value())
        control.setValue(float(value) if isinstance(control, QDoubleSpinBox) else int(value))
        control.valueChanged.connect(lambda value: self.set_value(key, value))


def _bool_value(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)

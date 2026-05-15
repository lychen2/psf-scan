"""PSF 预设：控件状态 ↔ dict 转换，加上 save/load 对话框。

把 PsfControlPanel 的 combo/check/spin 与 cuts ratio 抽到一个 dict，可写入
JSON 或从 JSON 还原。控件不存在 / key 缺失时静默跳过，便于以后扩展。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QInputDialog, QMessageBox, QWidget,
)

from . import preset_io


def panel_state(panel) -> dict[str, Any]:
    """从 PsfControlPanel 抓出全部可还原参数。"""
    state: dict[str, Any] = {}
    for key, control in panel._persistent_combos().items():  # noqa: SLF001
        state[key] = control.currentText()
    for key, control in panel._persistent_checks().items():  # noqa: SLF001
        state[key] = bool(control.isChecked())
    for key, control in panel._persistent_spins().items():  # noqa: SLF001
        state[key] = _spin_value(control)
    rx, ry, rz = panel.cuts.ratios()
    state["cut_x_ratio"] = float(rx)
    state["cut_y_ratio"] = float(ry)
    state["cut_z_ratio"] = float(rz)
    return state


def apply_state(panel, state: dict[str, Any]) -> None:
    """把 dict 写回控件；同时为 cuts ratio 设缓存供下次 _apply_cuts_defaults 用。"""
    for key, control in panel._persistent_combos().items():  # noqa: SLF001
        if key in state:
            _set_combo(control, str(state[key]))
    for key, control in panel._persistent_checks().items():  # noqa: SLF001
        if key in state:
            control.setChecked(bool(state[key]))
    for key, control in panel._persistent_spins().items():  # noqa: SLF001
        if key in state:
            _set_spin_value(control, state[key])
    panel._cut_ratios_cached = (  # noqa: SLF001
        _ratio(state.get("cut_x_ratio", 1.0)),
        _ratio(state.get("cut_y_ratio", 1.0)),
        _ratio(state.get("cut_z_ratio", 1.0)),
    )
    panel.sync_visibility()
    if getattr(panel, "_has_volume_shape", False):
        panel._apply_cuts_defaults()  # noqa: SLF001
    panel.render_requested.emit()


def _set_combo(combo: QComboBox, value: str) -> None:
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _spin_value(control: Any) -> int | float:
    value = control.value()
    return float(value) if _is_float_spin(control) else int(value)


def _set_spin_value(control: Any, value: Any) -> None:
    control.setValue(float(value) if _is_float_spin(control) else int(value))


def _is_float_spin(control: Any) -> bool:
    if isinstance(control, QDoubleSpinBox):
        return True
    return isinstance(getattr(control, "spin", None), QDoubleSpinBox)


def _ratio(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


# ── dialog flows ────────────────────────────────────────────

def prompt_save(panel: QWidget) -> None:
    name, ok = QInputDialog.getText(panel, "save preset", "preset name:")
    if not ok or not name.strip():
        return
    try:
        path = preset_io.save_preset(name, panel_state(panel))
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(panel, "save failed", str(exc))
        return
    QMessageBox.information(panel, "saved", f"preset → {path}")


def prompt_load(panel: QWidget) -> None:
    presets = preset_io.list_presets()
    if not presets:
        QMessageBox.information(panel, "no presets", f"先 save 一个；位置：{preset_io.PRESET_DIR}")
        return
    name, ok = QInputDialog.getItem(
        panel, "load preset", "preset:", presets, 0, editable=False,
    )
    if not ok or not name:
        return
    try:
        data = preset_io.load_preset(name)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(panel, "load failed", str(exc))
        return
    apply_state(panel, data)

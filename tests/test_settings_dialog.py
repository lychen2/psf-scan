from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from psf_scan.ui.settings_dialog import SettingsDialog


def test_capture_dark_uses_hardware_active_property(monkeypatch):
    calls: list[tuple[str, str] | str] = []

    class Camera:
        @property
        def hardware_dark_active(self) -> bool:
            return True

        def trigger_hardware_dark_calibration(self) -> str | None:
            raise AssertionError("hardware trigger should not run")

        def try_enable_hardware_dark(self) -> bool:
            raise AssertionError("hardware enable should not run")

    def capture_calibration(_edit, *, kind: str, prompt: str) -> None:
        calls.append((kind, prompt))

    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Yes)
    dialog = SimpleNamespace(
        _camera=Camera(),
        _capture_calibration=capture_calibration,
        _refresh_dark_status=lambda: calls.append("refresh"),
    )

    SettingsDialog._capture_dark(dialog, SimpleNamespace())

    assert calls[-1] == "refresh"
    assert calls[0][0] == "dark"

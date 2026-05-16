"""Compact scan plan summary widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from .widgets import HintLabel, ValueLabel


class ScanBrief(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self._points = ValueLabel("pts ─")
        self._frames = ValueLabel("frames ─")
        self._runtime = ValueLabel("time ─")
        for label, value in self._items():
            row.addWidget(HintLabel(label))
            row.addWidget(value)
        row.addStretch()

    def set_values(
        self,
        *,
        points: int,
        frames: int,
        seconds: float,
    ) -> None:
        self._points.setText(f"{points:,}")
        self._frames.setText(f"{frames:,}")
        self._runtime.setText(duration_text(seconds))

    def _items(self) -> tuple[tuple[str, ValueLabel], ...]:
        return (
            ("points", self._points),
            ("frames", self._frames),
            ("time", self._runtime),
        )


def duration_text(seconds: float) -> str:
    minutes = int(seconds // 60)
    whole_seconds = int(round(seconds % 60))
    if minutes:
        return f"{minutes}m {whole_seconds:02d}s"
    return f"{whole_seconds}s"

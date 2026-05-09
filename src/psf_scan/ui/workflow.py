"""Compact workflow and scan plan readouts."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import theme
from .motion import flash
from .widgets import HintLabel, ValueLabel


class WorkflowGuide(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._phase = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 4)
        row.setSpacing(8)
        self._steps = []
        for index, text in enumerate(("01 DEVICES", "02 POSITION", "03 SCAN"), start=1):
            label = QLabel(text)
            label.setProperty("role", "workflow")
            self._steps.append(label)
            row.addWidget(label)
            if index < 3:
                row.addWidget(HintLabel("/"))
        row.addStretch()
        self.set_phase(1)

    def set_phase(self, phase: int) -> None:
        changed = phase != self._phase
        self._phase = phase
        for index, label in enumerate(self._steps, start=1):
            color = theme.TEXT0 if index == phase else theme.TEXT3
            weight = 700 if index == phase else 500
            label.setStyleSheet(
                f"color:{color};font-size:10px;font-weight:{weight};"
                "letter-spacing:1px;padding:0 0 2px 0;"
            )
            if changed and index == phase:
                flash(label, low=0.45, duration_ms=160)


class ScanBrief(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self._points = ValueLabel("pts ─")
        self._frames = ValueLabel("frames ─")
        self._runtime = ValueLabel("time ─")
        self._grid = ValueLabel("z only")
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
        xy_enabled: bool,
    ) -> None:
        self._points.setText(f"{points:,}")
        self._frames.setText(f"{frames:,}")
        self._runtime.setText(duration_text(seconds))
        self._grid.setText("xy grid" if xy_enabled else "z only")

    def _items(self) -> tuple[tuple[str, ValueLabel], ...]:
        return (
            ("points", self._points),
            ("frames", self._frames),
            ("time", self._runtime),
            ("mode", self._grid),
        )


def duration_text(seconds: float) -> str:
    minutes = int(seconds // 60)
    whole_seconds = int(round(seconds % 60))
    if minutes:
        return f"{minutes}m {whole_seconds:02d}s"
    return f"{whole_seconds}s"

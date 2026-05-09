"""Global readout strip for the scan workflow."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from . import theme
from .motion import StatusDot
from .widgets import HintLabel, ValueLabel

STATE_IDLE = "idle"
STATE_ONLINE = "online"
STATE_SCANNING = "scanning"
STATE_ERROR = "error"
STATE_SAVED = "saved"

STATE_COLORS = {
    STATE_IDLE: theme.BORDER1,
    STATE_ONLINE: theme.ACCENT,
    STATE_SCANNING: theme.ACCENT_LO,
    STATE_ERROR: theme.DANGER,
    STATE_SAVED: theme.DONE,
}
POSITION_READOUT_MIN_WIDTH = 250
PROGRESS_READOUT_MIN_WIDTH = 150
CAMERA_READOUT_MIN_WIDTH = 132
STATUS_ROW_GAP = 8


class StatusStrip(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusStrip")
        self.setStyleSheet(
            f"QWidget#StatusStrip{{background:{theme.BG0};"
            f"border-bottom:1px solid {theme.BORDER0};}}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(STATUS_ROW_GAP)
        self._dot = StatusDot(theme.BORDER1)
        self._state = ValueLabel("offline")
        self._position = ValueLabel("x      ─       y      ─       z      ─     µm")
        self._plan = ValueLabel("plan ─")
        self._progress = ValueLabel("progress ─")
        self._camera = ValueLabel("peak ─       fps ─")
        self._message = "connect devices"
        self._set_readout_widths()
        for label, widget in self._items():
            row.addWidget(HintLabel(label))
            row.addWidget(widget)
            row.addWidget(_vrule())
        row.addStretch()
        self.set_state(STATE_IDLE, "offline")

    def set_state(self, state: str, text: str) -> None:
        color = STATE_COLORS.get(state, theme.BORDER1)
        self._dot.set_dot_color(color)
        self._state.setText(text)

    def set_position(self, x: float, y: float, z: float) -> None:
        self._position.setText(f"x {x:+8.3f}   y {y:+8.3f}   z {z:+8.3f}  µm")

    def set_plan(self, text: str) -> None:
        self._plan.setText(text or "plan ─")

    def set_progress(self, idx: int, total: int, z: float) -> None:
        pct = int(idx / total * 100) if total else 0
        self._progress.setText(f"{idx:>4d} / {total:<4d}   {pct:>3d}%   z {z:+7.3f}")

    def set_progress_idle(self, text: str = "progress ─") -> None:
        self._progress.setText(text)

    def set_camera(self, peak: int, fps: float, saturated: bool) -> None:
        suffix = "  SAT" if saturated else ""
        self._camera.setText(f"peak {peak:>5d}   {fps:>5.1f} fps{suffix}")

    def reset_camera(self) -> None:
        self._camera.setText("peak ─       fps ─")

    def set_message(self, text: str) -> None:
        self._message = text

    def _set_readout_widths(self) -> None:
        for widget, width in (
            (self._position, POSITION_READOUT_MIN_WIDTH),
            (self._progress, PROGRESS_READOUT_MIN_WIDTH),
            (self._camera, CAMERA_READOUT_MIN_WIDTH),
        ):
            widget.setMinimumWidth(width)

    def _items(self) -> tuple[tuple[str, QWidget], ...]:
        state = _with_dot(self._dot, self._state)
        return (
            ("state", state),
            ("pos", self._position),
            ("run", self._progress),
            ("cam", self._camera),
        )


def _with_dot(dot: QWidget, label: QLabel) -> QWidget:
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(dot)
    row.addWidget(label)
    return widget


def _vrule() -> QFrame:
    rule = QFrame()
    rule.setProperty("role", "vrule")
    rule.setFrameShape(QFrame.NoFrame)
    return rule

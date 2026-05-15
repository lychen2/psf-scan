"""Global readout strip for the scan workflow."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from ..core.i18n import tr
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
DATA_DIR_READOUT_MAX_WIDTH = 360
STATUS_ROW_GAP = 8


class StatusStrip(QWidget):
    change_data_dir_requested = Signal()
    open_data_dir_requested = Signal()
    settings_requested = Signal()

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
        self._data_dir = ValueLabel("")
        self._data_dir.setMaximumWidth(DATA_DIR_READOUT_MAX_WIDTH)
        self._data_dir.setToolTip("数据保存目录")
        self._data_dir_full = ""
        self._message = "connect devices"
        self._set_readout_widths()
        for label, widget in self._items():
            row.addWidget(HintLabel(label))
            row.addWidget(widget)
            row.addWidget(_vrule())
        row.addStretch()
        row.addWidget(HintLabel(tr("status.data")))
        row.addWidget(self._data_dir)
        self._btn_open = _link_button(tr("status.open"))
        self._btn_open.setToolTip(tr("tip.data_dir_open"))
        self._btn_open.clicked.connect(self.open_data_dir_requested.emit)
        self._btn_change = _link_button(tr("status.change"))
        self._btn_change.setToolTip(tr("tip.data_dir_change"))
        self._btn_change.clicked.connect(self.change_data_dir_requested.emit)
        row.addWidget(self._btn_open)
        row.addWidget(self._btn_change)
        # 齿轮按钮 — 打开统一设置
        self._btn_settings = QToolButton()
        self._btn_settings.setText("⚙")
        self._btn_settings.setToolTip(tr("tip.settings"))
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.setStyleSheet(
            f"QToolButton{{color:{theme.TEXT2};border:none;background:transparent;"
            "padding:0 6px;font-size:16px;}"
            f"QToolButton:hover{{color:{theme.ACCENT};}}"
        )
        self._btn_settings.clicked.connect(self.settings_requested.emit)
        row.addWidget(self._btn_settings)
        self.set_state(STATE_IDLE, tr("status.offline"))

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

    def set_data_dir(self, path: str) -> None:
        """显示当前数据目录 (右端) — 过长尾部截断。"""
        self._data_dir_full = path
        self._data_dir.setToolTip(path)
        self._data_dir.setText(_shorten_path(path, 40))

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
            (tr("status.state"), state),
            (tr("status.position"), self._position),
            (tr("status.run"), self._progress),
            (tr("status.camera"), self._camera),
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


def _link_button(text: str) -> QToolButton:
    btn = QToolButton()
    btn.setText(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(
        f"QToolButton{{color:{theme.TEXT2};border:none;background:transparent;"
        "padding:0 4px;font-family:'Inter',sans-serif;font-size:10px;"
        "letter-spacing:1px;font-weight:600;text-decoration:underline;}"
        f"QToolButton:hover{{color:{theme.ACCENT};}}"
    )
    return btn


def _shorten_path(path: str, max_chars: int) -> str:
    if len(path) <= max_chars:
        return path
    # 头部保留盘符 / 第一级，尾部保留 max_chars-头部 个字符
    head = path[: max(4, max_chars // 6)]
    keep = max_chars - len(head) - 1
    return head + "…" + path[-keep:]

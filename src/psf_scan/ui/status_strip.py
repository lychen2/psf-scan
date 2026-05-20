"""全局状态栏 — 同时承担 device 选择与运行进度。

布局是两行:上行根据 mode 切换四种 panel,下行是跨 panel 的 info-line。

上行 panel:
- OFFLINE  — 设备选择(stage / camera combo) + Connect 按钮
- ONLINE   — 设备身份徽章 + 位置 + fps + disconnect link
- SCANNING — 进度条 + 当前点 + z + remaining + fps
- ERROR    — 占位空 panel(详情由下行 info-line 用 DANGER 色显示)

下行 info-line:任意 mode 都能显示一行短文字(autofocus done、保存路径等),颜色随 state 自动切换,ERROR 时变红加粗。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from . import theme
from .motion import StatusDot
from .progress_with_ticks import ProgressWithTicks
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

# 把 IDLE 也视作 OFFLINE,共用同一个 stack panel
_STATE_TO_PANEL = {
    STATE_IDLE: 0,        # OFFLINE  — devices
    STATE_ONLINE: 1,      # ONLINE   — identity + pos + fps
    STATE_SAVED: 1,
    STATE_SCANNING: 2,    # SCANNING — progress + z + eta + fps
    STATE_ERROR: 3,       # ERROR    — message
}


class StatusStrip(QWidget):
    connect_requested = Signal(str, str)
    disconnect_requested = Signal()
    pi_settings_requested = Signal()
    settings_requested = Signal()
    stage_kind_changed = Signal(str)

    def __init__(self, stages: list[str], cameras: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusStrip")
        self.setStyleSheet(
            f"QWidget#StatusStrip{{background:{theme.BG0};"
            f"border-bottom:1px solid {theme.BORDER0};}}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.G_16, theme.G_8, theme.G_16, theme.G_8)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.G_16)

        self._dot = StatusDot(theme.BORDER1)
        self._mode = QLabel("OFFLINE")
        self._mode.setProperty("role", "status-mode")

        row.addWidget(self._dot)
        row.addWidget(self._mode)
        row.addWidget(_vrule())

        # 中间:四 mode 切换面板
        self._stack = QStackedWidget()
        self._stack.addWidget(self._offline_panel(stages, cameras))
        self._stack.addWidget(self._online_panel())
        self._stack.addWidget(self._scanning_panel())
        self._stack.addWidget(self._error_panel())
        row.addWidget(self._stack, stretch=1)

        # 右侧:disconnect link + ⚙
        self._btn_disconnect = QPushButton(tr("status.disconnect_link"))
        self._btn_disconnect.setProperty("role", "disconnect-link")
        self._btn_disconnect.setCursor(Qt.PointingHandCursor)
        self._btn_disconnect.setToolTip(tr("tip.disconnect"))
        self._btn_disconnect.clicked.connect(self.disconnect_requested.emit)
        self._btn_disconnect.setVisible(False)
        row.addWidget(self._btn_disconnect)

        self._btn_settings = QToolButton()
        self._btn_settings.setText("⚙")
        self._btn_settings.setProperty("role", "settings")
        self._btn_settings.setToolTip(tr("tip.settings"))
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.clicked.connect(self.settings_requested.emit)
        row.addWidget(self._btn_settings)

        outer.addLayout(row)

        # 跨 panel 信息行 — 任何 mode 都能显示一行短文字(autofocus 完成、扫描阶段、保存路径等)
        self._info_line = QLabel("")
        self._info_line.setMinimumHeight(14)
        self._info_line.setMaximumHeight(16)
        self._info_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self._info_line)

        # 60 Hz 合并: 高速 stage poll 不会让 position 文本 setText 飙起来。
        self._pending_pos: tuple[float, float, float] | None = None
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(16)
        self._pos_timer.timeout.connect(self._flush_position)
        self._pos_timer.start()

        self.set_state(STATE_IDLE, tr("status.offline"))

    # ── panels ─────────────────────────────────────────────────────────
    def _offline_panel(self, stages: list[str], cameras: list[str]) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.G_8)
        row.addWidget(HintLabel(tr("panel.stage_driver")))
        self.cb_stage = QComboBox()
        self.cb_stage.addItems(stages)
        self.cb_stage.setMinimumWidth(120)
        row.addWidget(self.cb_stage)
        self.btn_pi = QPushButton("PI…")
        self.btn_pi.setEnabled(False)
        self.btn_pi.setToolTip(tr("tip.pi_settings"))
        self.btn_pi.clicked.connect(self.pi_settings_requested.emit)
        row.addWidget(self.btn_pi)
        row.addSpacing(8)
        row.addWidget(HintLabel(tr("panel.camera_driver")))
        self.cb_cam = QComboBox()
        self.cb_cam.addItems(cameras)
        self.cb_cam.setMinimumWidth(120)
        row.addWidget(self.cb_cam)
        row.addStretch()
        self.btn_connect = QPushButton("⏵ " + tr("panel.connect"))
        self.btn_connect.setProperty("role", "connect")
        self.btn_connect.setToolTip(tr("tip.connect"))
        self.btn_connect.clicked.connect(self._emit_connect)
        row.addWidget(self.btn_connect)
        self.cb_stage.currentTextChanged.connect(self._on_stage_kind_changed)
        return w

    def _online_panel(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.G_16)
        self._device_label = QLabel("")
        self._device_label.setProperty("role", "status-detail")
        row.addWidget(self._device_label)
        row.addWidget(_vrule())
        self._position = QLabel("x ─    y ─    z ─    µm")
        self._position.setProperty("role", "status-detail")
        self._position.setMinimumWidth(240)
        row.addWidget(self._position)
        row.addStretch()
        self._fps_idle = QLabel("─.─ fps")
        self._fps_idle.setProperty("role", "status-detail")
        row.addWidget(self._fps_idle)
        return w

    def _scanning_panel(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.G_16)
        self._scan_count = QLabel("0 / 0")
        self._scan_count.setProperty("role", "status-progress")
        row.addWidget(self._scan_count)
        self._progress_bar = ProgressWithTicks()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_finished = False
        self._progress_bar.setStyleSheet(_progress_qss(False))
        row.addWidget(self._progress_bar, stretch=1)
        self._scan_z = QLabel("z ─")
        self._scan_z.setProperty("role", "status-detail")
        self._scan_z.setMinimumWidth(90)
        row.addWidget(self._scan_z)
        self._scan_eta = QLabel("─")
        self._scan_eta.setProperty("role", "status-detail")
        self._scan_eta.setMinimumWidth(60)
        row.addWidget(self._scan_eta)
        self._fps_scan = QLabel("─.─ fps")
        self._fps_scan.setProperty("role", "status-detail")
        row.addWidget(self._fps_scan)
        return w

    def _error_panel(self) -> QWidget:
        # ERROR mode 的详细文字由跨 panel 的 info-line 显示(用 DANGER 色);
        # 这个 panel 留作占位,保持 stack index 与 STATE_ERROR 的对应关系。
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        return w

    # ── API ────────────────────────────────────────────────────────────
    def set_state(self, state: str, text: str) -> None:
        color = STATE_COLORS.get(state, theme.BORDER1)
        self._dot.set_dot_color(color)
        self._mode.setText(text.upper() if text else state.upper())
        panel = _STATE_TO_PANEL.get(state, 0)
        self._stack.setCurrentIndex(panel)
        # disconnect link 仅在 ONLINE / SCANNING / ERROR 显示
        self._btn_disconnect.setVisible(panel != 0)
        self._apply_info_style(state)
        self._state = state

    def state(self) -> str:
        return getattr(self, "_state", STATE_IDLE)

    def set_position(self, x: float, y: float, z: float) -> None:
        self._pending_pos = (float(x), float(y), float(z))

    def _flush_position(self) -> None:
        if self._pending_pos is None:
            return
        x, y, z = self._pending_pos
        self._pending_pos = None
        self._position.setText(f"x {x:+8.3f}   y {y:+8.3f}   z {z:+8.3f}  µm")

    def set_device_label(self, text: str) -> None:
        self._device_label.setText(text)

    def set_progress(self, idx: int, total: int, z: float, eta_s: float = 0.0) -> None:
        pct = int(idx / total * 100) if total else 0
        self._scan_count.setText(f"{idx} / {total}")
        self._progress_bar.setValue(pct)
        self._set_progress_finished(total > 0 and idx >= total)
        self._scan_z.setText(f"z {z:+7.3f}")
        if eta_s > 0:
            self._scan_eta.setText(_eta_text(eta_s))
        else:
            self._scan_eta.setText("─")

    def set_progress_idle(self, _text: str = "") -> None:
        self._scan_count.setText("0 / 0")
        self._progress_bar.setValue(0)
        self._set_progress_finished(False)
        self._progress_bar.clear_ticks()
        self._scan_z.setText("z ─")
        self._scan_eta.setText("─")

    def _set_progress_finished(self, finished: bool) -> None:
        """只在 finished 翻转时重设 stylesheet——避免每个 scan tick 都重解析 QSS。"""
        if finished == self._progress_finished:
            return
        self._progress_finished = finished
        self._progress_bar.setStyleSheet(_progress_qss(finished))

    def set_scan_plan_ticks(self, n_points: int) -> None:
        """刻度按等距 10 段铺在进度条上;≤4 点的扫描不画刻度。"""
        if n_points < 5:
            self._progress_bar.clear_ticks()
            return
        self._progress_bar.set_tick_positions([i / 10.0 for i in range(1, 10)])

    def set_camera(self, peak: int, fps: float, saturated: bool) -> None:
        text = f"{fps:>5.1f} fps"
        if saturated:
            text = f"SAT · {text}"
        self._fps_idle.setText(text)
        self._fps_scan.setText(text)

    def reset_camera(self) -> None:
        self._fps_idle.setText("─.─ fps")
        self._fps_scan.setText("─.─ fps")

    def set_message(self, text: str) -> None:
        # 跨 panel 的信息行,任意 mode 下都能展示;颜色由 set_state 控制(ERROR 时 DANGER 红)。
        self._info_line.setText(text or "")

    def _apply_info_style(self, state: str) -> None:
        color = theme.DANGER if state == STATE_ERROR else theme.TEXT3
        weight = 500 if state == STATE_ERROR else 400
        self._info_line.setStyleSheet(
            f"color:{color};font-family:'{theme.MONO}',monospace;"
            f"font-size:{theme.SIZE_METER};font-weight:{weight};letter-spacing:0.4px;"
        )

    def set_data_dir(self, _path: str) -> None:  # API 兼容,数据目录入口已移到 ⚙
        pass

    # ── device combos ─────────────────────────────────────────────────
    def stage_kind(self) -> str:
        return self.cb_stage.currentText()

    def camera_kind(self) -> str:
        return self.cb_cam.currentText()

    def set_pi_settings_enabled(self, on: bool) -> None:
        self.btn_pi.setEnabled(on)

    def bind_device_combos(self, settings) -> None:
        settings.bind_combo("devices/stage_driver", self.cb_stage)
        settings.bind_combo("devices/camera_driver", self.cb_cam)
        self._on_stage_kind_changed(self.cb_stage.currentText())

    def set_connect_enabled(self, on: bool) -> None:
        self.btn_connect.setEnabled(on)
        self.cb_stage.setEnabled(on)
        self.cb_cam.setEnabled(on)

    def _on_stage_kind_changed(self, kind: str) -> None:
        is_pi = kind.lower() in {"pi-m531", "pi", "m531"}
        self.btn_pi.setEnabled(is_pi)
        self.stage_kind_changed.emit(kind)

    def _emit_connect(self) -> None:
        self.connect_requested.emit(self.cb_stage.currentText(), self.cb_cam.currentText())


def _vrule() -> QWidget:
    rule = QWidget()
    rule.setFixedWidth(1)
    rule.setStyleSheet(f"background:{theme.BORDER0};")
    return rule


def _progress_qss(finished: bool) -> str:
    """完成时把 chunk 翻成 DONE 绿,与 StageView 的已采样点对齐。"""
    chunk = theme.DONE if finished else theme.ACCENT
    return (
        f"QProgressBar{{background:{theme.BG0};border:1px solid {theme.BORDER0};"
        "border-radius:0;}}"
        f"QProgressBar::chunk{{background:{chunk};}}"
    )


def _eta_text(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s left"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"

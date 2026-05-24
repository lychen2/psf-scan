"""扫描中和扫描完成后的 PSF 3D 浏览。"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..core.i18n import tr
from . import theme
from .psf_control_panel import PsfControlPanel
from .psf_plot import PsfPlotWidget
from .psf_render import (
    MODE_VOLUME, RenderOptions, make_volume, render_images, resolve_levels,
)
from .settings import UserSettings

# Live 扫描下的 2D 渲染合并间隔——避免每收一帧就完整 nanmin/nanmax + MIP
# 三次 reduce。150ms ≈ 6 Hz,人眼足够流畅,CPU 占用与原来差一个量级。
_LIVE_RENDER_DEBOUNCE_MS = 150


class PSFView(QWidget):
    export_plot_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PSFView")
        self.setStyleSheet(f"QWidget#PSFView{{background:{theme.BG0};}}")
        self._stack: np.ndarray | None = None
        self._frame_count = 0
        self._positions: np.ndarray | None = None
        self._path_positions: np.ndarray | None = None
        self._volume: np.ndarray | None = None
        self._live = False
        self._render_pending = False
        self._running_levels: tuple[float, float] | None = None
        self._volume_revision = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot = PsfPlotWidget()
        self._controls = PsfControlPanel()
        self._controls.render_requested.connect(self._render)
        self._controls.auto_toggled.connect(self._on_auto_toggled)
        self._controls.rect_zoom_changed.connect(self._plot.set_rect_zoom_mode)
        self._controls.reset_view_requested.connect(self._plot.reset_views)
        self._controls.export_plot_requested.connect(self.export_plot_requested.emit)
        layout.addWidget(self._plot, stretch=1)
        layout.addWidget(self._controls)

        self._live_refresh = QTimer(self)
        self._live_refresh.setSingleShot(True)
        self._live_refresh.setInterval(_LIVE_RENDER_DEBOUNCE_MS)
        self._live_refresh.timeout.connect(self._refresh_render)

    def export_plot_to(self, path: str) -> None:
        """由 app.py 在弹出 QFileDialog 选好路径后调用。"""
        self._plot.export_to(path)

    def has_data(self) -> bool:
        return self._volume is not None

    def bind_settings(self, settings: UserSettings) -> None:
        self._controls.bind_settings(settings)

    def begin_scan(self, positions: np.ndarray) -> None:
        self._stack = None
        self._frame_count = 0
        self._positions = np.array(positions, copy=True)
        self._path_positions = np.array(positions, copy=True)
        self._volume = None
        self._render_pending = False
        self._running_levels = None
        self._bump_volume_revision()
        self._live_refresh.stop()
        self._plot.clear()
        self._set_empty(tr("scan.scanning_status"))

    def add_frame(self, idx: int, frame: np.ndarray) -> None:
        if idx != self._frame_count:
            raise ValueError(f"PSF frame index out of order: {idx} != {self._frame_count}")
        self._ensure_stack(frame)
        self._stack[idx] = frame
        self._frame_count += 1
        self._bump_volume_revision()
        # 用单帧的 min/max 增量更新整套 levels，避免对增长中的 stack 做全量扫。
        f_lo = float(np.nanmin(frame))
        f_hi = float(np.nanmax(frame))
        if self._running_levels is None:
            self._running_levels = (f_lo, f_hi)
        else:
            lo, hi = self._running_levels
            self._running_levels = (min(lo, f_lo), max(hi, f_hi))
        self._set_stack(self._stack[: self._frame_count], self._positions[: idx + 1], live=True)

    def set_data(self, frames: np.ndarray, positions: np.ndarray) -> None:
        self._stack = np.array(frames, dtype=np.float32, copy=True)
        self._frame_count = len(self._stack)
        self._positions = np.array(positions, copy=True)
        self._path_positions = np.array(positions, copy=True)
        self._bump_volume_revision()
        # 扫描结束态: 一次性算出准确 levels,后续 _render 直接用 hint 不再扫体。
        self._running_levels = (
            float(np.nanmin(self._stack)),
            float(np.nanmax(self._stack)),
        )
        self._set_stack(self._stack, self._positions, live=False)

    def _set_stack(self, frames: np.ndarray, positions: np.ndarray, *, live: bool = False) -> None:
        self._volume = make_volume(frames)
        self._positions = np.array(positions, copy=True)
        self._live = live
        self._controls.set_volume_shape(self._volume.shape)
        if live and not self.isVisible():
            self._render_pending = True
            return
        if live:
            # Live 帧合并: 不要每帧都重渲染,等 _LIVE_RENDER_DEBOUNCE_MS 静默窗口。
            self._live_refresh.start()
            return
        self._live_refresh.stop()
        if not self.isVisible():
            self._render_pending = True
            return
        self._refresh_render()

    def _ensure_stack(self, frame: np.ndarray) -> None:
        if self._stack is not None:
            return
        if self._positions is None:
            raise RuntimeError("PSF scan positions missing")
        shape = (len(self._positions),) + frame.shape
        self._stack = np.empty(shape, dtype=np.float32)

    def _sync_auto_levels(self) -> None:
        if self._volume is None or not self._controls.auto.isChecked():
            return
        if self._running_levels is not None:
            lo, hi = self._running_levels
        else:
            lo, hi = float(np.nanmin(self._volume)), float(np.nanmax(self._volume))
        self._controls.set_levels(lo, hi)

    def _refresh_render(self) -> None:
        self._sync_auto_levels()
        self._render()
        self._render_pending = False

    def _render(self) -> None:
        if self._volume is None:
            return
        try:
            options = self._options()
            levels = resolve_levels(self._volume, options, hint=self._running_levels)
            self._render_plot(levels, options)
            self._update_info()
        except Exception as exc:  # noqa: BLE001
            self._controls.set_empty(tr("psf.plot_error", exc=exc))

    def _options(self) -> RenderOptions:
        return self._controls.selected_options()

    def _render_plot(self, levels: tuple[float, float], options: RenderOptions) -> None:
        if self._volume is None:
            return
        if options.mode == MODE_VOLUME:
            self._plot.set_volume(
                self._volume,
                levels=levels,
                options=options,
                z_positions=self._z_positions(),
                live=self._live,
                data_revision=self._volume_revision,
            )
            return
        images = render_images(self._volume, options, self._z_positions())
        self._plot.set_images(
            images,
            cmap_name=self._controls.cmap_name(),
            levels=levels,
            options=options,
        )

    def _z_positions(self) -> np.ndarray | None:
        source = self._path_positions if self._path_positions is not None else self._positions
        return None if source is None else source[:, 2]

    def _update_info(self) -> None:
        if self._volume is None:
            return
        idx = self._controls.current_slice_index()
        peak = float(np.nanmax(self._volume[idx]))
        status = f"{self._controls.mode.currentText().lower()} · averaged stack"
        self._controls.set_info(idx, self._volume.shape[0], peak, self._position_text(idx), status)

    def _position_text(self, idx: int) -> str:
        if self._positions is None or idx >= len(self._positions):
            return "x      ─       y      ─       z      ─     µm"
        x, y, z = self._positions[idx]
        return f"x {x:+8.3f}   y {y:+8.3f}   z {z:+8.3f}  µm"

    def _on_auto_toggled(self, on: bool) -> None:
        self._refresh_render()

    def _bump_volume_revision(self) -> None:
        self._volume_revision += 1

    def _set_empty(self, text: str) -> None:
        self._controls.set_empty(text)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._render_pending:
            self._refresh_render()

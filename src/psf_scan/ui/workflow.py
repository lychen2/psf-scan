"""Compact workflow and scan plan readouts."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..core.i18n import tr
from . import theme
from .motion import flash
from .widgets import HintLabel, ValueLabel


WORKFLOW_STEPS = ("workflow.step1", "workflow.step2", "workflow.step3", "workflow.step4")


class WorkflowGuide(QWidget):
    """四步工作流: 连接 → 计划 → 扫描 → 导出. 当前步高亮, 下一步用浅箭头标记."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._phase = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 4)
        row.setSpacing(8)
        self._steps: list[QLabel] = []
        self._arrows: list[QLabel] = []
        for index, key in enumerate(WORKFLOW_STEPS, start=1):
            label = QLabel(tr(key))
            label.setProperty("role", "workflow")
            self._steps.append(label)
            row.addWidget(label)
            if index < len(WORKFLOW_STEPS):
                arrow = HintLabel("›")
                self._arrows.append(arrow)
                row.addWidget(arrow)
        row.addStretch()
        self.set_phase(1)

    def set_phase(self, phase: int) -> None:
        phase = max(1, min(len(self._steps), int(phase)))
        changed = phase != self._phase
        self._phase = phase
        for index, label in enumerate(self._steps, start=1):
            color, weight = self._style_for(index, phase)
            label.setStyleSheet(
                f"color:{color};font-size:10px;font-weight:{weight};"
                "letter-spacing:1px;padding:0 0 2px 0;"
            )
            if changed and index == phase:
                flash(label, low=0.45, duration_ms=160)
        for arrow_index, arrow in enumerate(self._arrows, start=1):
            # arrow_index 是它左边那一步的序号; 下一步是 arrow_index+1.
            # 当前步刚好指向下一步时, 让箭头亮一点提示走向.
            is_active_pointer = arrow_index == phase
            arrow.setStyleSheet(
                f"color:{theme.TEXT2 if is_active_pointer else theme.TEXT3};"
                "font-size:11px;padding:0 0 2px 0;"
            )

    @staticmethod
    def _style_for(index: int, phase: int) -> tuple[str, int]:
        if index == phase:
            return theme.TEXT0, 700
        if index == phase + 1:
            return theme.TEXT2, 600
        return theme.TEXT3, 500


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

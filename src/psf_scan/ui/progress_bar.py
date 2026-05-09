"""Animated scan progress bar for the control panel."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .motion import reduced_motion_enabled

TRACK_HEIGHT = 14
MIN_WIDTH = 200
ANIMATION_MS = 160
SWEEP_MS = 45
SWEEP_STEP = 0.035
TEXT_SIZE = 10
TEXT_Y_OFFSET = 1
BORDER_WIDTH = 1
HEAD_WIDTH = 2
MIN_FILL_WIDTH = 1
QUARTER_TICKS = (0.25, 0.5, 0.75)


class ScanProgressBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._value = 0
        self._display_value = 0.0
        self._format = "0%"
        self._running = False
        self._sweep = 0.0
        self._animation: QPropertyAnimation | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(SWEEP_MS)
        self._timer.timeout.connect(self._advance_sweep)
        self.setMinimumWidth(MIN_WIDTH)
        self.setFixedHeight(TRACK_HEIGHT)

    def setRange(self, minimum: int, maximum: int) -> None:
        if maximum < minimum:
            raise ValueError(f"invalid progress range: {minimum}..{maximum}")
        self._minimum = minimum
        self._maximum = maximum
        self.setValue(self._value)

    def setValue(self, value: int) -> None:
        self._value = max(self._minimum, min(value, self._maximum))
        target = float(self._value)
        if reduced_motion_enabled():
            self._set_display_value(target)
            return
        self._animate_to(target)

    def setFormat(self, text: str) -> None:
        self._format = text
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running and not reduced_motion_enabled():
            self._timer.start()
        else:
            self._timer.stop()
            self._sweep = 0.0
        self.update()

    def display_value(self) -> float:
        return self._display_value

    def _set_display_value(self, value: float) -> None:
        self._display_value = value
        self.update()

    displayValue = Property(float, display_value, _set_display_value)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(rect, QColor(theme.BG0))
        fill_width = self._fill_width(rect.width())
        if fill_width:
            fill = rect.adjusted(BORDER_WIDTH, BORDER_WIDTH, 0, -BORDER_WIDTH)
            fill.setWidth(fill_width)
            painter.fillRect(fill, QColor(theme.ACCENT))
            self._paint_head(painter, fill)
        self._paint_ticks(painter, rect)
        painter.setPen(QPen(QColor(theme.BORDER0), BORDER_WIDTH))
        painter.drawRect(rect)
        painter.setPen(QColor(theme.TEXT2))
        painter.setFont(QFont("Iosevka Term", TEXT_SIZE))
        text_rect = rect.adjusted(0, TEXT_Y_OFFSET, 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._format)

    def _paint_head(self, painter: QPainter, fill) -> None:
        x = fill.right() - HEAD_WIDTH + 1
        painter.fillRect(x, fill.top(), HEAD_WIDTH, fill.height(), QColor(theme.ACCENT_LO))
        if not self._running:
            return
        sweep_x = fill.left() + int(fill.width() * self._sweep)
        painter.fillRect(sweep_x, fill.top(), HEAD_WIDTH, fill.height(), QColor(theme.ACCENT_HI))

    def _paint_ticks(self, painter: QPainter, rect) -> None:
        painter.setPen(QPen(QColor(theme.BORDER0), BORDER_WIDTH))
        for tick in QUARTER_TICKS:
            x = rect.left() + int(rect.width() * tick)
            painter.drawLine(x, rect.top() + 1, x, rect.bottom() - 1)

    def _fill_width(self, width: int) -> int:
        span = self._maximum - self._minimum
        if span <= 0:
            return 0
        pct = (self._display_value - self._minimum) / span
        return max(0, int((width - BORDER_WIDTH) * pct) - BORDER_WIDTH)

    def _animate_to(self, target: float) -> None:
        if self._animation is not None:
            self._animation.stop()
        animation = QPropertyAnimation(self, b"displayValue", self)
        self._animation = animation
        animation.setDuration(ANIMATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        animation.setStartValue(self._display_value)
        animation.setEndValue(target)
        animation.finished.connect(lambda: self._clear_animation(animation))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _advance_sweep(self) -> None:
        self._sweep = (self._sweep + SWEEP_STEP) % 1.0
        self.update()

    def _clear_animation(self, animation: QPropertyAnimation | None) -> None:
        if self._animation is animation:
            self._animation = None

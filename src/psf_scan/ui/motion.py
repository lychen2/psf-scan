"""Small Qt motion helpers for state feedback.

Set ``PSF_SCAN_REDUCED_MOTION=1`` to replace UI animations with instant changes.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


MOTION_MS = 160
FLASH_MS = 180
EASE_OUT_QUART = QEasingCurve.Type.OutQuart
_REDUCED_MOTION_VALUES = {"1", "true", "yes", "on"}


def reduced_motion_enabled() -> bool:
    value = os.getenv("PSF_SCAN_REDUCED_MOTION", "")
    return value.strip().lower() in _REDUCED_MOTION_VALUES


def fade_in(widget: QWidget, *, duration_ms: int = MOTION_MS) -> None:
    if reduced_motion_enabled():
        return
    effect = _opacity_effect(widget, 0.0)
    animation = _opacity_animation(effect, duration_ms=duration_ms)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    _start_animation(widget, animation)


def flash(widget: QWidget, *, low: float = 0.25, duration_ms: int = FLASH_MS) -> None:
    if reduced_motion_enabled():
        return
    effect = _opacity_effect(widget, low)
    animation = _opacity_animation(effect, duration_ms=duration_ms)
    animation.setStartValue(low)
    animation.setEndValue(1.0)
    _start_animation(widget, animation)


def set_motion_visible(widget: QWidget, visible: bool) -> None:
    if reduced_motion_enabled() or widget.isVisible() == visible:
        widget.setVisible(visible)
        return
    if visible:
        widget.setVisible(True)
        fade_in(widget)
        return
    widget.setVisible(False)


class StatusDot(QWidget):
    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(8, 8)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor | str) -> None:
        self._color = QColor(color)
        self.update()

    dotColor = Property(QColor, color, set_color)

    def set_dot_color(self, color: str) -> None:
        if reduced_motion_enabled():
            self.set_color(color)
            return
        animation = QPropertyAnimation(self, b"dotColor", self)
        animation.setDuration(MOTION_MS)
        animation.setEasingCurve(EASE_OUT_QUART)
        animation.setStartValue(self.color())
        animation.setEndValue(QColor(color))
        _start_animation(self, animation)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.fillRect(self.rect(), self._color)
        finally:
            painter.end()


def _opacity_effect(widget: QWidget, opacity: float) -> QGraphicsOpacityEffect:
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(opacity)
    return effect


def _opacity_animation(
    effect: QGraphicsOpacityEffect,
    *,
    duration_ms: int,
) -> QPropertyAnimation:
    animation = QPropertyAnimation(effect, b"opacity", effect)
    animation.setDuration(duration_ms)
    animation.setEasingCurve(EASE_OUT_QUART)
    return animation


def _start_animation(widget: QWidget, animation: QPropertyAnimation) -> None:
    current = getattr(widget, "_motion_animation", None)
    if current is not None:
        current.stop()
    widget._motion_animation = animation
    animation.finished.connect(lambda: _clear_animation(widget, animation))
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def _clear_animation(widget: QWidget, animation: QPropertyAnimation) -> None:
    if getattr(widget, "_motion_animation", None) is animation:
        widget._motion_animation = None

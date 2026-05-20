"""UI 缩放推荐与解析 — 4K 屏自适应字体。

`apply_theme(app, scale)` 接收一个浮点 scale,这里负责:
- `recommend_scale`:根据主屏 logical DPI 给出推荐值(96 dpi → 1.0,4K 144 → 1.25,2.7K 168 → 1.5,…)
- `effective_scale`:把用户偏好(0 = 自动)和推荐值合成一个最终 scale

Linux/X11 上 DE 已做全局缩放时,Qt 看到的 logical DPI 就已经是被放大过的值;
自动档因此始终给得稍保守(每级 +25% 而非 +50%)。
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

SCALE_MIN = 0.75
SCALE_MAX = 2.5

AUTO = 0.0
"""存进 QSettings 的"自动"哨值 —— 区别于显式 1.0。"""


def recommend_scale(app: QApplication) -> float:
    """按主屏 logical DPI 推荐 scale。Qt 6 默认 96 dpi = 1.0。"""
    screen = app.primaryScreen()
    if screen is None:
        return 1.0
    dpi = float(screen.logicalDotsPerInch())
    if dpi <= 110.0:
        return 1.0
    if dpi <= 130.0:
        return 1.1
    if dpi <= 150.0:
        return 1.25
    if dpi <= 170.0:
        return 1.5
    if dpi <= 190.0:
        return 1.75
    return 2.0


def clamp_scale(value: float) -> float:
    if value <= 0.0:
        return AUTO
    return max(SCALE_MIN, min(SCALE_MAX, float(value)))


def effective_scale(pref: float, app: QApplication) -> float:
    """pref == 0 → 推荐;否则 clamp 后返回。"""
    pref = float(pref)
    if pref <= 0.0:
        return recommend_scale(app)
    return clamp_scale(pref)

"""Colormap 名字解析。pyqtgraph 内置只有 CET-* 和 viridis 系，
gray/hot/rainbow 等需要落到 matplotlib source；rainbow 优先用感知均匀的 CET-R2。"""
from __future__ import annotations

import pyqtgraph as pg

_SOURCES = (None, "matplotlib")
_RAINBOW_FALLBACKS = ("CET-R2", "rainbow", "turbo")


def resolve_colormap(name: str):
    """按名字找 pyqtgraph ColorMap；查不到返回 None。"""
    candidates = _RAINBOW_FALLBACKS if name == "rainbow" else (name,)
    for cand in candidates:
        for source in _SOURCES:
            try:
                cm = pg.colormap.get(cand) if source is None else pg.colormap.get(cand, source=source)
            except Exception:
                cm = None
            if cm is not None:
                return cm
    return None


def resolve_or_default(name: str, default: str = "viridis"):
    """同 resolve_colormap，但找不到时回退到 default。"""
    cm = resolve_colormap(name)
    if cm is not None:
        return cm
    return resolve_colormap(default)

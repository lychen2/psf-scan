"""浅色科研绘图工作台主题 — 调色板、字体、应用入口。

QSS 模板见 ``_qss.py``。浅色中性画布避免纯白刺眼，保留绘图可读性。
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ._qss import QSS_TEMPLATE


# ── 调色板 (OKLCH 推导) ──────────────────────────────
BG0 = "#f7f5ef"
BG1 = "#ebe8df"
BG2 = "#ddd8cd"
BORDER0 = "#d4cfc3"
BORDER1 = "#b8b1a3"

TEXT0 = "#171a1c"
TEXT1 = "#2a2f32"
TEXT2 = "#626a6c"
TEXT3 = "#6f7470"

ACCENT = "#9fc6dc"
ACCENT_HI = "#b8d7e8"
ACCENT_LO = "#7aa9c5"

DONE = "#5f8f83"
DANGER = "#b55345"


def _font_family(*candidates: str, default: str) -> str:
    available = set(QFontDatabase.families())
    for c in candidates:
        if c in available:
            return c
    return default


def apply_theme(app: QApplication) -> None:
    sans = _font_family(
        "Inter", "SF Pro Text", "Segoe UI", "Noto Sans CJK SC", "Noto Sans",
        default="sans-serif",
    )
    mono = _font_family(
        "Iosevka Term", "JetBrains Mono", "Cascadia Mono", "Fira Code",
        "DejaVu Sans Mono", "Menlo", "Consolas", default="monospace",
    )
    app.setFont(QFont(sans, 10))
    pg.setConfigOptions(background=BG0, foreground=TEXT2, antialias=True)
    qss = QSS_TEMPLATE.format(
        BG0=BG0, BG1=BG1, BG2=BG2,
        BORDER0=BORDER0, BORDER1=BORDER1,
        TEXT0=TEXT0, TEXT1=TEXT1, TEXT2=TEXT2, TEXT3=TEXT3,
        ACCENT=ACCENT, ACCENT_HI=ACCENT_HI, ACCENT_LO=ACCENT_LO,
        DONE=DONE, DANGER=DANGER,
        SANS=sans, MONO=mono,
    )
    app.setStyleSheet(qss)

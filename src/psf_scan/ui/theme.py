"""主题 — 浅色 / 深色双调色板,应用入口。

QSS 模板见 ``_qss.py``。
- 浅色 (light): 默认,符合 PRODUCT.md 的"暖中性浅画布"原则。
- 深色 (dark): 暖深底 UI chrome (面板 / 按钮 / 文本),给夜间或长时间观看用。
  PSF / stage 等后续绘图画布区保持浅色,colormap 由 viridis 等表达;
  相机预览画布跟随主题,便于暗场观察。
  深色只切 chrome,不污染数据可读性。
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QStyleFactory, QStyledItemDelegate,
)

from ._qss import QSS_TEMPLATE


class _ComboBoxQssEnforcer(QObject):
    """给每个 QComboBox 装 QStyledItemDelegate,保证 popup item 走 QSS / palette。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Polish and isinstance(obj, QComboBox):
            if type(obj.itemDelegate()) is not QStyledItemDelegate:
                obj.setItemDelegate(QStyledItemDelegate(obj))
        return False


_combo_enforcer: _ComboBoxQssEnforcer | None = None


# ── Light palette (OKLCH 推导,warm tinted neutral) ──────────
_LIGHT = {
    "BG0": "#f7f5ef",
    "BG1": "#ebe8df",
    "BG2": "#ddd8cd",
    "BORDER0": "#d4cfc3",
    "BORDER1": "#b8b1a3",
    "TEXT0": "#171a1c",
    "TEXT1": "#2a2f32",
    "TEXT2": "#626a6c",
    "TEXT3": "#6f7470",
    "ACCENT": "#9fc6dc",
    "ACCENT_HI": "#b8d7e8",
    "ACCENT_LO": "#7aa9c5",
    "DONE": "#5f8f83",
    "DANGER": "#b55345",
    "DANGER_HI": "#c86b5d",
    "DANGER_LO": "#984438",
    "WARN": "#d6892b",
    "SHADOW": "#d4cfc3",
    "HIGHLIGHT": "#fefdf7",
}

# ── Dark palette (warm-tinted, 不冷蓝灰也不纯黑) ──────────
# 设计原则:基础 hue 同 light 保持暖偏(~75 度),把 lightness 推到 0.18-0.32 区间;
# accent / danger / warn 在深底上略提亮以保持对比;bevel 反过来用深 shadow + 暖深 highlight。
_DARK = {
    "BG0": "#1a1714",   # paper (inputs, tooltip, status bar bg)
    "BG1": "#241f1a",   # panel (main window, control panel)
    "BG2": "#2e2823",   # surface (hover, disabled)
    "BORDER0": "#3a3329",
    "BORDER1": "#4e463a",
    "TEXT0": "#ede8df",   # strong
    "TEXT1": "#d4cec3",
    "TEXT2": "#9c9789",
    "TEXT3": "#82806f",
    "ACCENT": "#9fc6dc",   # signal blue: 同 hue, 深底上仍醒目
    "ACCENT_HI": "#b8d7e8",
    "ACCENT_LO": "#7aa9c5",
    "DONE": "#7eb0a3",     # sampled green: 略提亮
    "DANGER": "#d6766c",   # terracotta: 提亮版
    "DANGER_HI": "#e08879",
    "DANGER_LO": "#b85a51",
    "WARN": "#e3a14b",
    "SHADOW": "#13110e",   # 更深 shadow
    "HIGHLIGHT": "#332d27",  # 暖深 highlight
}

# ── Canvas-locked tokens (永远浅色, 不随 mode 切) ──────────
# PSF / 相机 / stage / autofocus / line profile / 火花线 等所有 plot canvas 使用。
# 这些区域承载科学数据 (viridis / hot / volume shell 等 colormap),
# 浅画布最利于颜色还原,所以无论 UI mode 如何都不切。
CANVAS_BG = _LIGHT["BG0"]
CANVAS_FG = _LIGHT["TEXT0"]
CANVAS_TEXT_MUTED = _LIGHT["TEXT2"]
CANVAS_BORDER = _LIGHT["BORDER0"]


# ── 当前生效调色板 (module-level, apply_theme 时重赋) ──────
BG0 = _LIGHT["BG0"]
BG1 = _LIGHT["BG1"]
BG2 = _LIGHT["BG2"]
BORDER0 = _LIGHT["BORDER0"]
BORDER1 = _LIGHT["BORDER1"]
TEXT0 = _LIGHT["TEXT0"]
TEXT1 = _LIGHT["TEXT1"]
TEXT2 = _LIGHT["TEXT2"]
TEXT3 = _LIGHT["TEXT3"]
ACCENT = _LIGHT["ACCENT"]
ACCENT_HI = _LIGHT["ACCENT_HI"]
ACCENT_LO = _LIGHT["ACCENT_LO"]
DONE = _LIGHT["DONE"]
DANGER = _LIGHT["DANGER"]
DANGER_HI = _LIGHT["DANGER_HI"]
DANGER_LO = _LIGHT["DANGER_LO"]
WARN = _LIGHT["WARN"]
SHADOW = _LIGHT["SHADOW"]
HIGHLIGHT = _LIGHT["HIGHLIGHT"]
MODE = "light"


# ── 间距 (Geometric Scale) ──────────────────────
G_4 = 4
G_8 = 8
G_16 = 16
G_24 = 24
G_32 = 32
G_48 = 48
PANEL_GUTTER = 24


# ── 字体 (Tokens) ──────────────────────────────
_BASE_SIZE_PX = {
    "SIZE_SECTION": 13,
    "SIZE_VALUE": 14,
    "SIZE_BODY": 11,
    "SIZE_METER": 10,
    "SIZE_CONTROL": 12,
}
_BASE_FONT_PT = 11

SIZE_SECTION = f"{_BASE_SIZE_PX['SIZE_SECTION']}px"
SIZE_VALUE = f"{_BASE_SIZE_PX['SIZE_VALUE']}px"
SIZE_BODY = f"{_BASE_SIZE_PX['SIZE_BODY']}px"
SIZE_METER = f"{_BASE_SIZE_PX['SIZE_METER']}px"
SIZE_CONTROL = f"{_BASE_SIZE_PX['SIZE_CONTROL']}px"
BASE_FONT_PT = _BASE_FONT_PT
UI_SCALE = 1.0

SANS = "sans-serif"
MONO = "monospace"


def _scaled_px(base_px: int, scale: float) -> int:
    return max(8, int(round(base_px * scale)))


def _font_family(*candidates: str, default: str) -> str:
    available = set(QFontDatabase.families())
    for c in candidates:
        if c in available:
            return c
    return default


def _apply_palette(mode: str) -> None:
    """Switch the module-level palette globals to the chosen mode."""
    global BG0, BG1, BG2, BORDER0, BORDER1
    global TEXT0, TEXT1, TEXT2, TEXT3
    global ACCENT, ACCENT_HI, ACCENT_LO, DONE
    global DANGER, DANGER_HI, DANGER_LO, WARN
    global SHADOW, HIGHLIGHT, MODE
    palette = _DARK if mode == "dark" else _LIGHT
    MODE = "dark" if mode == "dark" else "light"
    BG0 = palette["BG0"]
    BG1 = palette["BG1"]
    BG2 = palette["BG2"]
    BORDER0 = palette["BORDER0"]
    BORDER1 = palette["BORDER1"]
    TEXT0 = palette["TEXT0"]
    TEXT1 = palette["TEXT1"]
    TEXT2 = palette["TEXT2"]
    TEXT3 = palette["TEXT3"]
    ACCENT = palette["ACCENT"]
    ACCENT_HI = palette["ACCENT_HI"]
    ACCENT_LO = palette["ACCENT_LO"]
    DONE = palette["DONE"]
    DANGER = palette["DANGER"]
    DANGER_HI = palette["DANGER_HI"]
    DANGER_LO = palette["DANGER_LO"]
    WARN = palette["WARN"]
    SHADOW = palette["SHADOW"]
    HIGHLIGHT = palette["HIGHLIGHT"]


def apply_theme(app: QApplication, scale: float = 1.0, mode: str = "light") -> None:
    """Apply theme to the app, choosing palette (light|dark) and UI scale.

    Must be called before any widget creation (theme tokens are module-level globals
    consumed at widget __init__ time).
    """
    global SANS, MONO, _combo_enforcer
    global SIZE_SECTION, SIZE_VALUE, SIZE_BODY, SIZE_METER, SIZE_CONTROL
    global BASE_FONT_PT, UI_SCALE
    _apply_palette(mode)
    UI_SCALE = float(scale)
    SIZE_SECTION = f"{_scaled_px(_BASE_SIZE_PX['SIZE_SECTION'], UI_SCALE)}px"
    SIZE_VALUE = f"{_scaled_px(_BASE_SIZE_PX['SIZE_VALUE'], UI_SCALE)}px"
    SIZE_BODY = f"{_scaled_px(_BASE_SIZE_PX['SIZE_BODY'], UI_SCALE)}px"
    SIZE_METER = f"{_scaled_px(_BASE_SIZE_PX['SIZE_METER'], UI_SCALE)}px"
    SIZE_CONTROL = f"{_scaled_px(_BASE_SIZE_PX['SIZE_CONTROL'], UI_SCALE)}px"
    BASE_FONT_PT = max(8, int(round(_BASE_FONT_PT * UI_SCALE)))
    if "Fusion" in QStyleFactory.keys():
        app.setStyle(QStyleFactory.create("Fusion"))
    if _combo_enforcer is None:
        _combo_enforcer = _ComboBoxQssEnforcer()
        app.installEventFilter(_combo_enforcer)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG1))
    pal.setColor(QPalette.WindowText, QColor(TEXT1))
    pal.setColor(QPalette.Base, QColor(BG0))
    pal.setColor(QPalette.AlternateBase, QColor(BG1))
    pal.setColor(QPalette.Text, QColor(TEXT1))
    pal.setColor(QPalette.Button, QColor(BG1))
    pal.setColor(QPalette.ButtonText, QColor(TEXT1))
    pal.setColor(QPalette.ToolTipBase, QColor(BG0))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT0))
    pal.setColor(QPalette.Highlight, QColor(ACCENT_HI))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT0))
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT3))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(TEXT3))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(TEXT3))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(TEXT3))
    app.setPalette(pal)
    SANS = _font_family(
        "Inter", "SF Pro Text", "Segoe UI", "Noto Sans CJK SC", "Noto Sans",
        default="sans-serif",
    )
    MONO = _font_family(
        "Iosevka Term", "JetBrains Mono", "Cascadia Mono", "Fira Code",
        "DejaVu Sans Mono", "Menlo", "Consolas", default="monospace",
    )
    app.setFont(QFont(SANS, BASE_FONT_PT))
    # pyqtgraph 全局画布 = CANVAS_BG (恒浅), 无论 UI mode 怎么切
    pg.setConfigOptions(background=CANVAS_BG, foreground=CANVAS_TEXT_MUTED, antialias=True)
    qss = QSS_TEMPLATE.format(
        BG0=BG0, BG1=BG1, BG2=BG2,
        BORDER0=BORDER0, BORDER1=BORDER1,
        SHADOW=SHADOW, HIGHLIGHT=HIGHLIGHT,
        TEXT0=TEXT0, TEXT1=TEXT1, TEXT2=TEXT2, TEXT3=TEXT3,
        ACCENT=ACCENT, ACCENT_HI=ACCENT_HI, ACCENT_LO=ACCENT_LO,
        DONE=DONE, DANGER=DANGER,
        DANGER_HI=DANGER_HI, DANGER_LO=DANGER_LO,
        WARN=WARN,
        SANS=SANS, MONO=MONO,
        SIZE_SECTION=SIZE_SECTION,
        SIZE_VALUE=SIZE_VALUE,
        SIZE_BODY=SIZE_BODY,
        SIZE_METER=SIZE_METER,
        SIZE_CONTROL=SIZE_CONTROL,
    )
    app.setStyleSheet(qss)

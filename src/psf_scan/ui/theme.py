"""浅色科研绘图工作台主题 — 调色板、字体、应用入口。

QSS 模板见 ``_qss.py``。浅色中性画布避免纯白刺眼，保留绘图可读性。
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

# Danger family — 与 DESIGN.md 对齐到温暖红陶 (terracotta),不再用 vermillion。
# 语义:仪器安全 / 完整性破坏性操作。E-STOP、软限位关闭、寻参、扫描错误。
DANGER = "#b55345"
DANGER_HI = "#c86b5d"
DANGER_LO = "#984438"

# Warn (measurement-quality caution) —— 数据可信度类预警,不到 DANGER 那种"会动停"的程度。
# 语义:SATURATED 像素、MIP ROI 预算回缩提示。
WARN = "#d6892b"

# Bevel Effect Tokens —— 暖偏移近白, 保留扁平仪器面板上的 1px 高光感
SHADOW = "#d4cfc3"    # Same as BORDER0
HIGHLIGHT = "#fefdf7"

# ── 间距 (Geometric Scale) ──────────────────────
G_4 = 4
G_8 = 8
G_16 = 16
G_24 = 24
G_32 = 32
G_48 = 48
PANEL_GUTTER = 24


# ── 字体 (Tokens) ──────────────────────────────
SIZE_SECTION = "13px"
SIZE_VALUE = "14px"
SIZE_BODY = "11px"
SIZE_METER = "10px"
SIZE_CONTROL = "12px"

SANS = "sans-serif"
MONO = "monospace"


def _font_family(*candidates: str, default: str) -> str:
    available = set(QFontDatabase.families())
    for c in candidates:
        if c in available:
            return c
    return default


def apply_theme(app: QApplication) -> None:
    global SANS, MONO, _combo_enforcer
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
    app.setFont(QFont(SANS, 11))
    pg.setConfigOptions(background=BG0, foreground=TEXT2, antialias=True)
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

"""QSS 模板字符串 — 由 theme.apply_theme 注入颜色后应用。

抽离独立文件让 theme.py 保持薄。
"""

QSS_TEMPLATE = """
* {{
    color: {TEXT1};
}}
QMainWindow, QWidget {{
    background-color: {BG1};
    font-family: "{SANS}";
}}
QStatusBar {{
    background-color: {BG0};
    color: {TEXT2};
    font-family: "{MONO}";
    font-size: 11px;
    padding: 2px 6px;
    border-top: 1px solid {BORDER0};
}}
QSplitter::handle {{ background: {BG0}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QLabel[role="section"] {{
    color: {TEXT0};
    font-family: "{SANS}";
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    padding: 14px 0 6px 0;
}}
QFrame[role="rule"] {{
    background-color: {BORDER0};
    max-height: 1px; min-height: 1px;
    border: none;
    margin: 0 0 4px 0;
}}
QFrame[role="vrule"] {{
    background-color: {BORDER0};
    max-width: 1px; min-width: 1px;
    border: none;
}}
QLabel[role="hint"] {{
    color: {TEXT3};
    font-size: 11px;
    font-family: "{MONO}";
}}
QLabel[role="value"] {{
    color: {TEXT0};
    font-family: "{MONO}";
    font-size: 13px;
    font-weight: 500;
}}
QLabel[role="meter"] {{
    color: {TEXT2};
    font-family: "{MONO}";
    font-size: 11px;
    padding: 2px 6px;
}}

QDoubleSpinBox, QSpinBox {{
    background-color: {BG0};
    color: {TEXT0};
    font-family: "{MONO}";
    font-size: 12px;
    border: 1px solid {BORDER0};
    border-radius: 0;
    padding: 4px 6px;
    min-height: 22px;
    selection-background-color: {ACCENT_LO};
}}
QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled {{
    background-color: {BG2};
    color: {TEXT3};
    border-color: {BORDER1};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0; height: 0; border: none;
}}

QComboBox {{
    background: {BG0};
    color: {TEXT1};
    border: 1px solid {BORDER0};
    padding: 4px 8px;
    min-height: 22px;
    font-family: "{MONO}";
    font-size: 12px;
}}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox:disabled {{
    background: {BG2};
    color: {TEXT3};
    border-color: {BORDER1};
}}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background: {BG0}; color: {TEXT1};
    border: 1px solid {BORDER1};
    selection-background-color: {ACCENT_LO};
    selection-color: {TEXT0};
}}

QPushButton {{
    background: transparent;
    color: {TEXT1};
    border: 1px solid {BORDER1};
    padding: 6px 14px;
    font-family: "{SANS}";
    font-size: 11px;
    letter-spacing: 0.5px;
    min-height: 22px;
}}
QPushButton:hover {{ background: {BG2}; border-color: {TEXT3}; }}
QPushButton:pressed {{ background: {BG0}; }}
QPushButton:disabled {{
    background: {BG2};
    color: {TEXT3};
    border-color: {BORDER1};
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    color: {TEXT0};
    border: 1px solid {ACCENT};
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton[role="primary"]:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton[role="primary"]:pressed {{ background: {ACCENT_LO}; border-color: {ACCENT_LO}; }}
QPushButton[role="primary"]:disabled {{
    background: {BG2}; color: {TEXT3}; border-color: {BORDER1};
}}
QPushButton[role="danger"]:hover {{ color: {DANGER}; border-color: {DANGER}; }}

QSlider::groove:horizontal {{ height: 2px; background: {BORDER1}; border: none; }}
QSlider::handle:horizontal {{
    width: 12px; margin: -6px 0;
    background: {ACCENT}; border: none;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HI}; }}
QSlider::groove:horizontal:disabled {{ background: {BORDER0}; }}
QSlider::handle:horizontal:disabled {{ background: {TEXT3}; }}
QCheckBox {{ color: {TEXT1}; spacing: 6px; font-size: 11px; }}
QCheckBox:disabled {{ color: {TEXT3}; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    border: 1px solid {BORDER1}; background: {BG0};
}}
QCheckBox::indicator:hover {{ border-color: {TEXT3}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ background: {BG2}; border-color: {BORDER1}; }}

QTabBar {{ background: transparent; }}
QTabWidget::pane {{ border: none; top: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT2};
    padding: 6px 14px;
    border: none;
    border-bottom: 1px solid transparent;
    font-family: "{SANS}";
    font-size: 11px;
    letter-spacing: 1px;
    min-width: 60px;
}}
QTabBar::tab:hover {{ color: {TEXT2}; }}
QTabBar::tab:selected {{ color: {TEXT0}; border-bottom: 1px solid {ACCENT}; }}
QTabBar::tab:disabled {{ color: {TEXT3}; }}

QToolTip {{
    background: {BG0}; color: {TEXT0};
    border: 1px solid {BORDER1};
    padding: 4px 6px;
    font-family: "{MONO}"; font-size: 11px;
}}
"""

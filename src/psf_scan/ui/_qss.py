"""QSS 模板字符串 — 由 theme.apply_theme 注入颜色后应用。

抽离独立文件让 theme.py 保持薄。
"""

QSS_TEMPLATE = """
* {{
    color: {TEXT1};
}}
QMainWindow, QDialog, QFrame, QSplitter, QTabWidget, QStackedWidget,
QScrollArea, QScrollArea > QWidget > QWidget,
QWidget#CentralWidget, QWidget#StatusStrip, QWidget#PsfControlPanel {{
    background-color: {BG1};
    font-family: "{SANS}";
}}
QTabWidget::pane {{
    background-color: {BG1};
    border: none;
}}
QLabel {{
    background-color: transparent;
}}

QMenuBar {{
    background-color: {BG1};
    color: {TEXT1};
    border-bottom: 1px solid {BORDER0};
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
    padding: 2px 4px;
    spacing: 2px;
}}
QMenuBar::item {{
    background: transparent;
    color: {TEXT1};
    padding: 4px 10px;
    border: none;
}}
QMenuBar::item:selected {{
    background-color: {ACCENT_HI};
    color: {TEXT0};
}}
QMenuBar::item:pressed {{
    background-color: {ACCENT};
    color: {TEXT0};
}}
QMenuBar::item:disabled {{ color: {TEXT3}; }}
QStatusBar {{
    background-color: {BG0};
    color: {TEXT2};
    font-family: "{MONO}";
    font-size: {SIZE_METER};
    padding: 2px 6px;
    border-top: 1px solid {BORDER0};
}}
QSplitter::handle {{ background: {BG0}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QLabel[role="section"] {{
    color: {TEXT0};
    font-family: "{SANS}";
    font-size: {SIZE_SECTION};
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
    color: {TEXT2};
    font-size: {SIZE_BODY};
    font-family: "{SANS}";
    font-weight: 500;
}}
QLabel[role="value"] {{
    color: {TEXT0};
    font-family: "{MONO}";
    font-size: {SIZE_VALUE};
    font-weight: 500;
}}
QLabel[role="meter"] {{
    color: {TEXT1};
    font-family: "{MONO}";
    font-size: {SIZE_METER};
    padding: 2px 6px;
}}

QDoubleSpinBox, QSpinBox, QLineEdit, QTextEdit {{
    background-color: {BG0};
    color: {TEXT0};
    font-family: "{MONO}";
    font-size: {SIZE_CONTROL};
    border: 1px solid {BORDER0};
    border-radius: 0;
    padding: 4px 6px;
    min-height: 22px;
    selection-background-color: {ACCENT_LO};
}}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QDoubleSpinBox:hover:!focus, QSpinBox:hover:!focus,
QLineEdit:hover:!focus, QTextEdit:hover:!focus {{
    border-top: 1px solid {BORDER1};
    border-left: 1px solid {BORDER1};
    border-bottom: 1px solid {BORDER1};
    border-right: 1px solid {BORDER1};
}}
QDoubleSpinBox:disabled, QSpinBox:disabled, QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {BG2};
    color: {TEXT3};
    border: 1px solid {BORDER1};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0; height: 0; border: none;
}}

QComboBox {{
    background-color: {BG0};
    color: {TEXT1};
    border: 1px solid {BORDER0};
    padding: 4px 20px 4px 8px;
    min-height: 22px;
    font-family: "{MONO}";
    font-size: {SIZE_CONTROL};
}}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox:hover:!focus {{
    border-top: 1px solid {BORDER1};
    border-left: 1px solid {BORDER1};
    border-bottom: 1px solid {BORDER1};
    border-right: 1px solid {BORDER1};
}}
QComboBox:disabled {{
    background: {BG2};
    color: {TEXT3};
    border: 1px solid {BORDER1};
}}
QComboBox::drop-down {{ 
    border: none; 
    width: 16px; 
    subcontrol-origin: padding;
    subcontrol-position: top right;
}}
QComboBox::down-arrow {{ 
    image: none; 
    width: 0; height: 0; 
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 3px solid {BORDER1};
    margin-right: 6px;
}}
QComboBox::down-arrow:hover {{
    border-top-color: {TEXT1};
}}
QComboBox QAbstractItemView {{
    background: {BG0}; color: {TEXT1};
    border: 1px solid {BORDER1};
    outline: 0;
    selection-background-color: {ACCENT_LO};
    selection-color: {TEXT0};
}}
QComboBox QAbstractItemView::item {{
    background: {BG0};
    color: {TEXT1};
    padding: 4px 8px;
    border: none;
}}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {{
    background-color: {ACCENT_HI};
    color: {TEXT0};
}}

QListView, QTreeView, QTableView {{
    background-color: {BG0};
    color: {TEXT1};
    border: 1px solid {BORDER0};
    selection-background-color: {ACCENT_HI};
    selection-color: {TEXT0};
    alternate-background-color: {BG1};
    outline: 0;
}}
QListView::item, QTreeView::item, QTableView::item {{
    background: transparent;
    color: {TEXT1};
    padding: 3px 6px;
    border: none;
}}
QListView::item:selected, QTreeView::item:selected, QTableView::item:selected {{
    background-color: {ACCENT_HI};
    color: {TEXT0};
}}
QHeaderView {{ background-color: {BG1}; border: none; }}
QHeaderView::section {{
    background-color: {BG1};
    color: {TEXT1};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {BORDER0};
    border-bottom: 1px solid {BORDER0};
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
}}

QTabBar {{ background-color: {BG1}; }}
QTabBar::tab {{
    background-color: {BG1};
    color: {TEXT2};
    border: none;
    border-bottom: 1px solid {BORDER0};
    padding: 6px 14px;
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
    letter-spacing: 1px;
    margin-right: 1px;
    min-width: 60px;
}}
QTabBar::tab:selected {{
    background-color: {BG1};
    color: {TEXT0};
    border-bottom: 1px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT1}; background-color: {BG0}; }}
QTabBar::tab:disabled {{ color: {TEXT3}; }}

QGroupBox {{
    background-color: transparent;
    color: {TEXT1};
    border: 1px solid {BORDER0};
    border-radius: 0;
    margin-top: 10px;
    padding-top: 6px;
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {TEXT0};
    background-color: {BG1};
}}

QToolTip {{
    background-color: {BG0};
    color: {TEXT0};
    border: 1px solid {BORDER1};
    padding: 4px 8px;
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
}}

QToolBar {{
    background-color: {BG1};
    border: none;
    border-bottom: 1px solid {BORDER0};
    spacing: 2px;
    padding: 2px;
}}
QToolBar::separator {{
    background-color: {BORDER0};
    width: 1px; height: 1px;
    margin: 4px 4px;
}}

QDockWidget {{
    background-color: {BG1};
    color: {TEXT1};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {BG1};
    color: {TEXT0};
    padding: 4px 8px;
    border-bottom: 1px solid {BORDER0};
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
}}

QScrollBar:vertical {{
    background: {BG1};
    width: 10px;
    border: none;
    margin: 0;
}}
QScrollBar:horizontal {{
    background: {BG1};
    height: 10px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {BORDER1};
    border: none;
    min-height: 18px;
    min-width: 18px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {TEXT3};
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
    width: 0; height: 0;
}}

QProgressBar {{
    background-color: {BG0};
    color: {TEXT0};
    border: 1px solid {BORDER0};
    border-radius: 0;
    text-align: center;
    font-family: "{MONO}";
    font-size: {SIZE_METER};
    min-height: 14px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
}}
/* Finished scan — 与 StageView 已采样点同色,把"完成"信号带回进度区。*/
QProgressBar[role="finished"]::chunk {{
    background-color: {DONE};
}}

QMessageBox, QInputDialog, QFileDialog {{
    background-color: {BG1};
    color: {TEXT1};
}}
QMessageBox QLabel, QInputDialog QLabel {{
    color: {TEXT1};
    background: transparent;
}}

QPushButton {{
    background-color: {HIGHLIGHT};
    color: {TEXT1};
    border: 1px solid {BORDER1};
    padding: 5px 12px;
    font-family: "{SANS}";
    font-size: {SIZE_CONTROL};
    font-weight: 600;
    letter-spacing: 0.6px;
    min-height: 26px;
}}
QPushButton:hover {{ 
    background-color: {BG2};
    border-color: {ACCENT};
}}
QPushButton:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton:pressed {{ 
    background-color: {BG0};
    border: 1px solid {BORDER1};
}}
QPushButton:disabled {{
    background: {BG2};
    color: {TEXT3};
    border: 1px solid {BORDER1};
}}
QPushButton[role="primary"] {{
    background-color: {ACCENT};
    color: {ON_ACCENT};
    border: 1px solid {ACCENT_LO};
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QPushButton[role="primary"]:hover {{ 
    background-color: {ACCENT_HI};
}}
QPushButton[role="primary"]:pressed {{ 
    background-color: {ACCENT_LO};
    border: 1px solid {ACCENT_LO};
}}
QPushButton[role="primary"]:disabled {{
    background: {BG2}; color: {TEXT3}; border-color: {BORDER1};
}}
QPushButton[role="danger"]:hover {{ color: {DANGER}; border-color: {DANGER}; }}

QPushButton[role="estop"] {{
    background-color: {DANGER};
    color: {BG0};
    border: 1px solid {DANGER_LO};
    border-radius: 0;
    padding: 8px 14px;
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
    font-weight: 700;
    letter-spacing: 2px;
    min-height: 22px;
}}
QPushButton[role="estop"]:hover {{
    background-color: {DANGER_HI};
    border-color: {DANGER_LO};
}}
QPushButton[role="estop"]:pressed {{
    background-color: {DANGER_LO};
    border-color: {DANGER_LO};
}}
QPushButton[role="estop"]:disabled {{
    background: {BG2}; color: {TEXT3}; border-color: {BORDER1};
}}

QSlider::groove:horizontal {{
    height: 2px;
    background: {BORDER1};
    border: none;
    border-radius: 0;
}}
QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    background-color: {ACCENT};
    border: 1px solid {ACCENT_LO};
    border-radius: 0;
}}
QSlider::handle:horizontal:hover {{
    background-color: {ACCENT_HI};
}}
QSlider::groove:horizontal:disabled {{ background: {BORDER0}; }}
QSlider::handle:horizontal:disabled {{ background: {BORDER1}; border-color: {BORDER1}; }}
QCheckBox {{ color: {TEXT1}; spacing: 6px; font-size: {SIZE_BODY}; }}
QCheckBox:disabled {{ color: {TEXT3}; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    border: 1px solid {BORDER1};
    background-color: {BG0};
}}
QCheckBox::indicator:hover {{ border-color: {TEXT3}; }}
QCheckBox::indicator:checked {{ 
    background-color: {ACCENT};
    border: 1px solid {ACCENT_LO};
}}
QCheckBox::indicator:disabled {{ background: {BG2}; border: 1px solid {BORDER1}; }}

QTabWidget::pane {{ border: none; background-color: {BG1}; }}

/* 移除 StageView 内部多余的边框线 */
QWidget#StageView QFrame, QWidget#StageView QWidget {{
    border: none;
}}
QTabBar::tab {{
    background-color: {BG1};
    color: {TEXT2};
    padding: 6px 14px;
    border: none;
    border-bottom: 1px solid {BORDER0};
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
    letter-spacing: 1px;
    min-width: 60px;
}}
QTabBar::tab:hover {{ color: {TEXT1}; background-color: {BG0}; }}
QTabBar::tab:selected {{ 
    background-color: {BG1};
    color: {TEXT0}; 
    border-bottom: 1px solid {ACCENT}; 
}}
QTabBar::tab:disabled {{ color: {TEXT3}; }}

QToolTip {{
    background: {BG0}; color: {TEXT0};
    border: 1px solid {BORDER1};
    padding: 4px 6px;
    font-family: "{MONO}"; font-size: {SIZE_METER};
}}

QLabel[role="sat-badge"] {{
    color: {ON_ACCENT};
    background: {WARN};
    border: 1px solid {WARN};
    padding: 2px 8px;
    font-family: "{MONO}";
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel[role="status-mode"] {{
    color: {TEXT0};
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0 6px 0 4px;
}}
QLabel[role="status-detail"] {{
    color: {TEXT2};
    font-family: "{MONO}";
    font-size: {SIZE_METER};
    padding: 0 6px;
}}
QLabel[role="status-progress"] {{
    color: {TEXT0};
    font-family: "{MONO}";
    font-size: {SIZE_SECTION};
    font-weight: 500;
    letter-spacing: 1px;
}}
QToolButton {{
    background-color: {HIGHLIGHT};
    color: {TEXT1};
    border: 1px solid {BORDER1};
    padding: 4px;
    border-radius: 0;
    font-family: "{SANS}";
    font-size: {SIZE_CONTROL};
    min-width: 28px;
    min-height: 28px;
}}
QToolButton:hover {{ 
    background-color: {BG2};
    border-color: {ACCENT}; 
}}
QToolButton:focus {{
    border: 1px solid {ACCENT};
}}
QToolButton:pressed, QToolButton:checked {{ 
    background-color: {ACCENT};
    color: {ON_ACCENT};
    border: 1px solid {ACCENT_LO};
}}
QToolButton[role="iconbtn"] {{
    color: {TEXT2};
    background: transparent;
    border: none;
    padding: 0 8px;
    font-family: "{SANS}";
    font-size: {SIZE_CONTROL};
    letter-spacing: 1px;
    font-weight: 600;
}}
QToolButton[role="iconbtn"]:hover {{ color: {TEXT0}; }}
QToolButton[role="iconbtn"]:checked {{ color: {ACCENT}; }}
QToolButton[role="settings"] {{
    color: {TEXT2};
    background: transparent;
    border: none;
    padding: 0 8px;
    font-family: "{SANS}";
    font-size: 20px;
    min-width: 32px;
    min-height: 28px;
}}
QToolButton[role="settings"]:hover {{ color: {TEXT0}; }}
QToolButton[role="settings"]:focus {{ color: {TEXT0}; }}
QFrame[role="group-rule"] {{
    background-color: {BORDER0};
    max-width: 1px; min-width: 1px;
    border: none;
    margin: 4px 0;
}}
QPushButton[role="connect"] {{
    background-color: {ACCENT};
    color: {ON_ACCENT};
    border: 1px solid {ACCENT_LO};
    font-weight: 600;
    letter-spacing: 1px;
    padding: 3px 12px;
    min-height: 22px;
}}
QPushButton[role="connect"]:hover {{ 
    background-color: {ACCENT_HI};
}}
QPushButton[role="connect"]:pressed {{ 
    background-color: {ACCENT_LO};
    border: 1px solid {ACCENT_LO};
}}
QPushButton[role="disconnect-link"] {{
    background: transparent;
    color: {TEXT2};
    border: none;
    padding: 0 6px;
    text-decoration: underline;
    font-family: "{SANS}";
    font-size: 10px;
    letter-spacing: 1px;
    font-weight: 600;
}}
QPushButton[role="disconnect-link"]:hover {{ color: {DANGER}; }}
QToolButton[role="folder-toggle"] {{
    color: {TEXT2};
    background: transparent;
    border: none;
    padding: 2px 6px;
    font-family: "{SANS}";
    font-size: 10px;
    letter-spacing: 2px;
    font-weight: 600;
    text-align: left;
}}
QToolButton[role="folder-toggle"]:hover {{ color: {TEXT0}; }}
QToolButton[role="folder-toggle"]:checked {{ color: {TEXT0}; }}

/* 右键菜单 — 浅色 paper 风,避免落回系统深色默认 */
QMenu {{
    background-color: {BG0};
    color: {TEXT1};
    border: 1px solid {BORDER1};
    padding: 2px 0;
    font-family: "{SANS}";
    font-size: {SIZE_BODY};
}}
QMenu::item {{
    background: transparent;
    color: {TEXT1};
    padding: 4px 18px;
    border: none;
}}
QMenu::item:selected {{
    background-color: {ACCENT_HI};
    color: {TEXT0};
}}
QMenu::item:disabled {{ color: {TEXT3}; }}
QMenu::separator {{
    height: 1px;
    background-color: {BORDER0};
    margin: 3px 6px;
}}
QMenu::indicator {{ width: 12px; height: 12px; margin-left: 4px; }}
QMenu::indicator:non-exclusive:checked,
QMenu::indicator:exclusive:checked {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT_LO};
}}
QMenu::indicator:non-exclusive:unchecked,
QMenu::indicator:exclusive:unchecked {{
    background-color: {BG0};
    border: 1px solid {BORDER1};
}}
"""

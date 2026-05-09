"""共用小 widget — section header、值标签等。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class SectionHeader(QWidget):
    """小型 section 标题：左侧大写跟踪字标签，右侧延伸的细横线。"""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lbl = QLabel(title.upper())
        lbl.setProperty("role", "section")
        h.addWidget(lbl)
        rule = QFrame()
        rule.setProperty("role", "rule")
        rule.setFrameShape(QFrame.NoFrame)
        h.addWidget(rule, stretch=1)


class ValueLabel(QLabel):
    """等宽数值标签（位置、计数等）。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "value")
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)


class HintLabel(QLabel):
    """次要标签 / 单位 / 占位提示。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "hint")


class MeterLabel(QLabel):
    """覆盖在图像上的小数值带（fps、peak）。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "meter")

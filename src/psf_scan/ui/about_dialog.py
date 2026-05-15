"""About / 关于 对话框 — 版本与运行时支持信息。

铁律: 源码内不出现任何具名联系方式. 实际联系内容由部署方通过环境变量
``PSF_SCAN_SUPPORT_INFO`` 或运行目录下 ``support.txt`` 注入; 未注入时只显示
"如需技术支持, 请联系系统维护人员" 占位.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .._version import __version__
from ..core.i18n import tr

SUPPORT_ENV = "PSF_SCAN_SUPPORT_INFO"
SUPPORT_FILE = "support.txt"


def resolve_support_info() -> str:
    env = os.environ.get(SUPPORT_ENV, "").strip()
    if env:
        return env
    for base in _candidate_dirs():
        candidate = base / SUPPORT_FILE
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                return text
    return tr("about.support_fallback")


def _candidate_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent
    seen: list[Path] = []
    for path in (Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else None,
                 Path.cwd(), here, here.parent.parent.parent):
        if path is not None and path not in seen:
            seen.append(path)
    return seen


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("about.title"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)

        title = QLabel(f"<h3>PSF Scan</h3>")
        title.setTextFormat(Qt.RichText)
        layout.addWidget(title)

        layout.addWidget(QLabel(tr("about.version", v=__version__)))
        layout.addWidget(QLabel(tr("about.description")))

        deps = QLabel(tr("about.dependencies"))
        deps.setWordWrap(True)
        deps.setStyleSheet("color:#666;font-size:11px;")
        layout.addWidget(deps)

        support = QLabel(resolve_support_info())
        support.setWordWrap(True)
        support.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(support)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

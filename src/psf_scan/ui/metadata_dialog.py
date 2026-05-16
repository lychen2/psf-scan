"""元数据对话框 — 样品、物镜、波长等实验信息输入。

从控制面板移出到弹窗以保持主界面整洁。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLineEdit, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.i18n import tr
from . import theme
from .control_panel_helpers import dspin as _dspin, kv as _kv
from .settings import UserSettings


class MetadataDialog(QDialog):
    def __init__(self, settings: UserSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("panel.metadata"))
        self.setMinimumWidth(400)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.G_24, theme.G_24, theme.G_24, theme.G_24)
        layout.setSpacing(theme.G_16)

        self.le_sample = QLineEdit()
        self.le_sample.setPlaceholderText("e.g. Bead-001")
        self.le_objective = QLineEdit()
        self.le_objective.setPlaceholderText("e.g. 100X / 1.40 Oil")
        self.sp_na = _dspin(0.0, 2.0, 1.40)
        self.sp_lambda = _dspin(200.0, 2000.0, 532.0)
        self.te_note = QTextEdit()
        self.te_note.setPlaceholderText("extra notes...")
        self.te_note.setFixedHeight(100)

        layout.addLayout(_kv(tr("panel.meta_sample"), self.le_sample))
        layout.addLayout(_kv(tr("panel.meta_objective"), self.le_objective))
        layout.addLayout(_kv(tr("panel.meta_na"), self.sp_na))
        layout.addLayout(_kv(tr("panel.meta_lambda"), self.sp_lambda))
        layout.addLayout(_kv(tr("panel.meta_note"), self.te_note))

        # 加载当前值
        self.le_sample.setText(str(settings._settings.value("meta/sample_name", "")))
        self.le_objective.setText(str(settings._settings.value("meta/objective", "")))
        self.sp_na.setValue(float(settings._settings.value("meta/na", 1.40) or 1.40))
        self.sp_lambda.setValue(float(settings._settings.value("meta/wavelength_nm", 532.0) or 532.0))
        self.te_note.setPlainText(str(settings._settings.value("meta/note", "")))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self) -> None:
        self._settings.set_value("meta/sample_name", self.le_sample.text())
        self._settings.set_value("meta/objective", self.le_objective.text())
        self._settings.set_value("meta/na", float(self.sp_na.value()))
        self._settings.set_value("meta/wavelength_nm", float(self.sp_lambda.value()))
        self._settings.set_value("meta/note", self.te_note.toPlainText())
        self.accept()

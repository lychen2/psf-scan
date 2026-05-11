"""PI 控制器/位移台连接参数对话框。

设计要点:
- 控制器与 stage 给常见型号下拉, 可改写为自定义 (PI 型号生命周期长, 不必硬限制)
- 接口三选一: USB (默认, 枚举或填 serial) / TCP (填 IP) / RS232 (COM + baud)
- 参考模式 FRF (推荐) / FNL / FPL / none-跳过
- "skip referencing" 勾选时, refmode 灰掉
- 顶部固定的"初始化警示": stage 上电首次连接会机械寻参, 行程最大 ±150mm
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from . import theme

CONTROLLERS = ("C-863", "C-863.11", "C-863.12", "C-884.DB", "C-867", "E-873", "C-413")
STAGES = ("M-531.DG", "M-531.DD", "M-531.PD", "M-531.1S1", "M-531.5IH")
REFMODES = ("FRF", "FNL", "FPL", "none")

INFO_TEXT = (
    "M-531 初始化流程 (pitools.startup):\n"
    "  1. ConnectUSB/TCP/RS232 → 建立通信\n"
    "  2. CST → 把控制器参数表切到所选 stage 型号\n"
    "  3. SVO ON → 闭环伺服\n"
    "  4. 参考归零 (refmode):\n"
    "     • FRF — 找参考标记 (推荐, 在行程中间)\n"
    "     • FNL — 找负向限位\n"
    "     • FPL — 找正向限位\n"
    "     • none — 跳过, 绝对位置无效, 仅当 stage 已 referenced 且控制器未掉电时用\n"
    "\n"
    "⚠ 寻参期间 stage 会机械移动, 最多约半行程 (M-531 标准 ~150 mm).\n"
    "确认平台周围没有挡物、样品架、镜筒前先点 connect."
)


class PIConnectDialog(QDialog):
    def __init__(self, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PI Stage Connection")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background:{theme.BG0};color:{theme.TEXT0};")
        self._build(params)

    def _build(self, params: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── 警示 ──
        info = QTextEdit()
        info.setReadOnly(True)
        info.setPlainText(INFO_TEXT)
        info.setMaximumHeight(180)
        info.setStyleSheet(
            f"QTextEdit{{background:{theme.BG1};color:{theme.TEXT1};"
            f"border:1px solid {theme.BORDER0};padding:6px;"
            "font-family:'Iosevka Term',monospace;font-size:10px;}"
        )
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.cb_controller = _editable_combo(CONTROLLERS, str(params.get("controller", "C-863")))
        form.addRow("controller", self.cb_controller)

        self.cb_stage = _editable_combo(STAGES, str(params.get("stage", "M-531.DG")))
        form.addRow("stage model", self.cb_stage)

        self.cb_refmode = QComboBox()
        self.cb_refmode.addItems(REFMODES)
        ref = str(params.get("refmode", "FRF")).upper() or "FRF"
        idx = max(0, self.cb_refmode.findText(ref, Qt.MatchFixedString))
        self.cb_refmode.setCurrentIndex(idx)
        form.addRow("reference mode", self.cb_refmode)

        self.chk_skip = QCheckBox("skip referencing (stage 已对过, 控制器未掉电)")
        self.chk_skip.setChecked(bool(params.get("skip_referencing", False)))
        self.chk_skip.toggled.connect(self._on_skip_toggled)
        form.addRow("", self.chk_skip)

        self.cb_interface = QComboBox()
        self.cb_interface.addItems(("usb", "tcp", "rs232"))
        iface = str(params.get("interface", "usb")).lower()
        ix = max(0, self.cb_interface.findText(iface))
        self.cb_interface.setCurrentIndex(ix)
        self.cb_interface.currentTextChanged.connect(self._on_iface_changed)
        form.addRow("interface", self.cb_interface)

        # 接口参数 — stacked
        self._iface_stack = QStackedWidget()
        self._iface_stack.addWidget(self._build_usb_page(params))
        self._iface_stack.addWidget(self._build_tcp_page(params))
        self._iface_stack.addWidget(self._build_rs232_page(params))
        form.addRow("", self._iface_stack)

        self.sp_velocity = QSpinBox()
        self.sp_velocity.setRange(0, 50_000)
        self.sp_velocity.setSuffix(" µm/s")
        self.sp_velocity.setSpecialValueText("stage default")
        self.sp_velocity.setValue(int(params.get("velocity_um_s", 0) or 0))
        form.addRow("velocity", self.sp_velocity)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_iface_changed(self.cb_interface.currentText())
        self._on_skip_toggled(self.chk_skip.isChecked())

    def _build_usb_page(self, p: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("serial #"))
        self.le_serial = QLineEdit(str(p.get("serialnum", "") or ""))
        self.le_serial.setPlaceholderText("留空则枚举选第一个")
        row.addWidget(self.le_serial, stretch=1)
        return w

    def _build_tcp_page(self, p: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("ip"))
        self.le_ip = QLineEdit(str(p.get("ip", "") or ""))
        self.le_ip.setPlaceholderText("192.168.0.x")
        row.addWidget(self.le_ip, stretch=1)
        return w

    def _build_rs232_page(self, p: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("COM"))
        self.sp_com = QSpinBox()
        self.sp_com.setRange(0, 64)
        self.sp_com.setValue(int(p.get("comport", 0) or 0))
        row.addWidget(self.sp_com)
        row.addWidget(QLabel("baud"))
        self.cb_baud = QComboBox()
        for b in (9600, 19200, 38400, 57600, 115200):
            self.cb_baud.addItem(str(b), b)
        cur_baud = int(p.get("baudrate", 115200) or 115200)
        ix = self.cb_baud.findData(cur_baud)
        if ix >= 0:
            self.cb_baud.setCurrentIndex(ix)
        row.addWidget(self.cb_baud)
        row.addStretch()
        return w

    def _on_iface_changed(self, kind: str) -> None:
        idx = {"usb": 0, "tcp": 1, "rs232": 2}.get(kind, 0)
        self._iface_stack.setCurrentIndex(idx)

    def _on_skip_toggled(self, on: bool) -> None:
        self.cb_refmode.setEnabled(not on)

    def values(self) -> dict:
        return {
            "controller": self.cb_controller.currentText().strip(),
            "stage": self.cb_stage.currentText().strip(),
            "refmode": "none" if self.chk_skip.isChecked() else self.cb_refmode.currentText(),
            "interface": self.cb_interface.currentText(),
            "serialnum": self.le_serial.text().strip(),
            "ip": self.le_ip.text().strip(),
            "comport": int(self.sp_com.value()),
            "baudrate": int(self.cb_baud.currentData() or 115200),
            "velocity_um_s": int(self.sp_velocity.value()),
            "skip_referencing": bool(self.chk_skip.isChecked()),
        }


def _editable_combo(items: tuple[str, ...], current: str) -> QComboBox:
    cb = QComboBox()
    cb.setEditable(True)
    cb.addItems(items)
    cb.setCurrentText(current or items[0])
    return cb

"""PI 控制器/位移台连接参数对话框。

字段:
- 设备: controller, stage
- 链路: interface (usb/tcp/rs232/rs232-daisy) + 接口子页
- 参考: refmode + referencing (skip/auto/force)
- 安全限位 (µm): travel_min, travel_max, velocity_max, step_min, velocity (默认速度)

referencing=skip (默认安全): 不机械寻参, 用连接时位置作为基准, 由 TravelGuard 全程 clamp。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from . import theme
from . import pi_scan
from ..core.i18n import tr
from .widgets import double_spin, editable_combo, fixed_combo

CONTROLLERS = ("C-863", "C-863.11", "C-863.12", "C-884.DB", "C-867", "E-873", "C-413")
STAGES = ("M-531.DG", "M-531.DD", "M-531.PD", "M-531.1S1", "M-531.5IH")
REFMODES = ("FRF", "FNL", "FPL")
INTERFACES = ("usb", "tcp", "rs232", "rs232-daisy")
REFERENCING = ("skip", "auto", "force")
REF_HINT_KEYS = {
    "skip": "pi.ref_hint_skip",
    "auto": "pi.ref_hint_auto",
    "force": "pi.ref_hint_force",
}
INFO_TEXT_KEY = "pi.info_text"


class PIConnectDialog(QDialog):
    def __init__(self, params: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PI Stage Connection")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background:{theme.BG0};color:{theme.TEXT0};")
        self._build(params)

    def _build(self, p: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        info = QTextEdit()
        info.setReadOnly(True)
        info.setPlainText(tr(INFO_TEXT_KEY))
        info.setMaximumHeight(60)
        info.setStyleSheet(
            f"QTextEdit{{background:{theme.BG1};color:{theme.TEXT1};"
            f"border:1px solid {theme.BORDER0};padding:6px;"
            f"font-family:'Iosevka Term',monospace;font-size:{theme.SIZE_METER};}}"
        )
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)

        self.cb_controller = editable_combo(CONTROLLERS, str(p.get("controller", "C-863")))
        self.cb_stage = editable_combo(STAGES, str(p.get("stage", "M-531.DG")))
        form.addRow(tr("pi.controller"), self.cb_controller)
        form.addRow(tr("pi.stage_model"), self.cb_stage)

        self.cb_refmode = fixed_combo(REFMODES, str(p.get("refmode", "FRF")).upper())
        self.cb_referencing = fixed_combo(REFERENCING, str(p.get("referencing", "skip")))
        self.lbl_ref_hint = QLabel(tr(REF_HINT_KEYS[self.cb_referencing.currentText()]))
        self.lbl_ref_hint.setStyleSheet(f"color:{theme.TEXT2};font-size:{theme.SIZE_METER};")
        self.cb_referencing.currentTextChanged.connect(
            lambda t: self.lbl_ref_hint.setText(tr(REF_HINT_KEYS.get(t, "pi.ref_hint_skip")))
        )
        form.addRow(tr("pi.refmode"), self.cb_refmode)
        form.addRow(tr("pi.referencing"), self.cb_referencing)
        form.addRow("", self.lbl_ref_hint)

        self.cb_interface = fixed_combo(INTERFACES, str(p.get("interface", "usb")).lower())
        self.cb_interface.currentTextChanged.connect(self._on_iface_changed)
        form.addRow(tr("pi.interface"), self.cb_interface)
        self._iface_stack = QStackedWidget()
        self._iface_stack.addWidget(self._build_usb_page(p))
        self._iface_stack.addWidget(self._build_tcp_page(p))
        self._iface_stack.addWidget(self._build_rs232_page(p, daisy=False))
        self._iface_stack.addWidget(self._build_rs232_page(p, daisy=True))
        form.addRow("", self._iface_stack)

        self.sp_tmin = double_spin(p.get("travel_min_um", 0.0), -1e9, 1e9, 1, " µm")
        self.sp_tmax = double_spin(p.get("travel_max_um", 150_000.0), -1e9, 1e9, 1, " µm")
        self.sp_vel = double_spin(p.get("velocity_um_s", 0.0), 0, 1e9, 0, " µm/s", special="stage default")
        self.sp_vmax = double_spin(p.get("velocity_max_um_s", 2_000.0), 1, 1e9, 0, " µm/s")
        self.sp_step = double_spin(p.get("step_min_um", 0.4), 0.01, 1e6, 2, " µm")
        self.sp_poll = double_spin(p.get("poll_hz", 30), 1, 240, 0, " Hz")
        self.sp_tol = double_spin(p.get("position_tolerance_um", 0.05), 0.001, 100, 3, " µm")
        form.addRow(tr("pi.travel_min"), self.sp_tmin)
        form.addRow(tr("pi.travel_max"), self.sp_tmax)
        form.addRow(tr("pi.velocity_default"), self.sp_vel)
        form.addRow(tr("pi.velocity_max"), self.sp_vmax)
        form.addRow(tr("pi.step_min"), self.sp_step)
        form.addRow(tr("pi.poll_rate"), self.sp_poll)
        form.addRow(tr("pi.position_tol"), self.sp_tol)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._on_iface_changed(self.cb_interface.currentText())

    def _build_usb_page(self, p: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("pi.serial")))
        self.le_serial = QLineEdit(str(p.get("serialnum", "") or ""))
        self.le_serial.setPlaceholderText(tr("pi.serial_hint"))
        row.addWidget(self.le_serial, stretch=1)
        btn = QPushButton(tr("pi.scan")); btn.clicked.connect(self._scan_usb)
        row.addWidget(btn)
        return w

    def _build_tcp_page(self, p: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("pi.ip")))
        self.le_ip = QLineEdit(str(p.get("ip", "") or ""))
        self.le_ip.setPlaceholderText(tr("pi.ip_hint"))
        row.addWidget(self.le_ip, stretch=1)
        row.addWidget(QLabel(tr("pi.port")))
        self.sp_ipport = QSpinBox()
        self.sp_ipport.setRange(1, 65535)
        self.sp_ipport.setValue(int(p.get("ipport", 50000) or 50000))
        row.addWidget(self.sp_ipport)
        return w

    def _build_rs232_page(self, p: dict, *, daisy: bool) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("pi.com")))
        sp_com = QSpinBox(); sp_com.setRange(0, 64)
        sp_com.setValue(int(p.get("comport", 0) or 0))
        row.addWidget(sp_com)
        row.addWidget(QLabel(tr("pi.baud")))
        cb_baud = QComboBox()
        for b in (9600, 19200, 38400, 57600, 115200):
            cb_baud.addItem(str(b), b)
        ix = cb_baud.findData(int(p.get("baudrate", 115200) or 115200))
        if ix >= 0:
            cb_baud.setCurrentIndex(ix)
        row.addWidget(cb_baud)
        btn_com = QPushButton(tr("pi.scan_com"))
        btn_com.clicked.connect(lambda: self._scan_com(sp_com))
        row.addWidget(btn_com)
        if daisy:
            row.addWidget(QLabel(tr("pi.device_id")))
            self.sp_did = QSpinBox(); self.sp_did.setRange(1, 16)
            self.sp_did.setValue(int(p.get("device_id", 1) or 1))
            row.addWidget(self.sp_did)
            btn_dc = QPushButton(tr("pi.scan_chain"))
            btn_dc.clicked.connect(lambda: self._scan_daisy(sp_com, cb_baud))
            row.addWidget(btn_dc)
            self.sp_com_d, self.cb_baud_d = sp_com, cb_baud
        else:
            self.sp_com, self.cb_baud = sp_com, cb_baud
        row.addStretch()
        return w

    def _scan_usb(self) -> None:
        mask = self.cb_controller.currentText().strip() or "C-863"
        items = pi_scan.enumerate_usb_controllers(mask)
        if not items:
            self.le_serial.setPlaceholderText(tr("pi.scan_no_usb")); return
        ch, ok = QInputDialog.getItem(self, tr("pi.usb_devices_title"), tr("pi.choose_serial"), items, 0, False)
        if ok and ch: self.le_serial.setText(ch)

    def _scan_com(self, sp_com: QSpinBox) -> None:
        items = pi_scan.list_com_ports()
        if not items:
            QInputDialog.getText(self, tr("pi.com_ports_title"), tr("pi.scan_no_com")); return
        labels = [desc for _n, desc in items]
        ch, ok = QInputDialog.getItem(self, tr("pi.com_ports_title"), tr("pi.choose_label"), labels, 0, False)
        if not ok or not ch: return
        for n, desc in items:
            if desc == ch: sp_com.setValue(n); return

    def _scan_daisy(self, sp_com: QSpinBox, cb_baud: QComboBox) -> None:
        ctrl = self.cb_controller.currentText().strip() or "C-863"
        com = sp_com.value(); baud = cb_baud.currentData() or 115200
        try:
            items = pi_scan.scan_rs232_daisy(ctrl, com, baud)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("pi.chain_title"), str(exc))
            return
        if not items:
            QInputDialog.getText(self, tr("pi.chain_title"), tr("pi.scan_no_chain")); return
        ch, ok = QInputDialog.getItem(self, tr("pi.chain_title"), tr("pi.chain_devices"), items, 0, False)
        if not ok or not ch: return
        try:
            did = int(ch.split("-", 1)[0].strip())
            self.sp_did.setValue(did)
        except (ValueError, AttributeError): pass

    def _on_iface_changed(self, kind: str) -> None:
        idx = {"usb": 0, "tcp": 1, "rs232": 2, "rs232-daisy": 3}.get(kind, 0)
        self._iface_stack.setCurrentIndex(idx)

    def values(self) -> dict:
        iface = self.cb_interface.currentText()
        daisy = iface == "rs232-daisy"
        com = self.sp_com_d.value() if daisy else self.sp_com.value()
        baud = (self.cb_baud_d if daisy else self.cb_baud).currentData() or 115200
        return {
            "controller": self.cb_controller.currentText().strip(),
            "stage": self.cb_stage.currentText().strip(),
            "refmode": self.cb_refmode.currentText(),
            "referencing": self.cb_referencing.currentText(),
            "interface": iface,
            "serialnum": self.le_serial.text().strip(),
            "ip": self.le_ip.text().strip(),
            "ipport": int(self.sp_ipport.value()),
            "comport": int(com),
            "baudrate": int(baud),
            "device_id": int(self.sp_did.value()) if hasattr(self, "sp_did") else 0,
            "travel_min_um": float(self.sp_tmin.value()),
            "travel_max_um": float(self.sp_tmax.value()),
            "velocity_um_s": float(self.sp_vel.value()),
            "velocity_max_um_s": float(self.sp_vmax.value()),
            "step_min_um": float(self.sp_step.value()),
            "poll_hz": int(self.sp_poll.value()),
            "position_tolerance_um": float(self.sp_tol.value()),
        }

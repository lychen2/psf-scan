"""PI 接口自动扫描 — COM port / USB controller / RS-232 daisy chain devices。

lazy import pyserial / pipython, 没装时返回空 list 而非崩。所有函数纯查询, 不改任何状态。
"""

from __future__ import annotations

from typing import Optional


def list_com_ports() -> list[tuple[int, str]]:
    """返回 [(COM 号 int, 描述), ...]。pyserial 没装则空 list。

    Linux 上用 auto-fallback: 返回 /dev/ttyUSB* 的序号。
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    out: list[tuple[int, str]] = []
    for p in list_ports.comports():
        num = _parse_com_num(p.device)
        label = f"{p.device} - {p.description}" if p.description else p.device
        if p.device.startswith("/dev/ttyUSB"):
            # Linux: 用字符串路径, num 只作 label 用
            out.append((num or 0, label))
        elif num is not None:
            out.append((num, label))
        elif p.device:
            out.append((0, label))
    return out


def find_pi_serial_port() -> str:
    """Linux: 自动探测 PI USB 串口路径, 空则 ''。"""
    import os
    by_id = "/dev/serial/by-id"
    if os.path.isdir(by_id):
        try:
            for name in sorted(os.listdir(by_id)):
                if "PI_" in name and "if00" in name:
                    path = os.path.realpath(os.path.join(by_id, name))
                    if os.path.exists(path):
                        return path
        except OSError:
            pass
    for dev in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"):
        if os.path.exists(dev):
            return dev
    return ""


def enumerate_usb_controllers(controller_mask: str = "C-863") -> list[str]:
    """枚举 PI USB 设备 (返回 serial 字符串列表)。pipython 没装则空。"""
    try:
        from pipython import GCSDevice
    except ImportError:
        return []
    try:
        dev = GCSDevice(controller_mask)
        return list(dev.EnumerateUSB(mask=controller_mask) or [])
    except Exception:  # noqa: BLE001
        return []


def scan_rs232_daisy(controller: str, comport, baudrate: int = 115200) -> list[str]:
    """扫 RS-232 daisy chain 设备列表 (字符串描述含 device id)。

    扫描完会自动 CloseDaisyChain; 失败/没装 pipython 返回空。
    Linux 上 comport 可为 None 或 '', 自动探测串口路径。
    """
    try:
        from pipython import GCSDevice
    except ImportError:
        return []
    try:
        from ..drivers import pi_link
        dev = GCSDevice(controller)
        import sys
        if sys.platform in ("linux", "linux2"):
            sp = comport if isinstance(comport, str) and comport else ""
            items = pi_link.scan_rs232_daisy(dev, baudrate=int(baudrate), serialport=sp)
        else:
            c = int(comport) if comport else 0
            items = pi_link.scan_rs232_daisy(dev, comport=c, baudrate=int(baudrate))
        return items
    except Exception:  # noqa: BLE001
        return []


def _parse_com_num(name: str) -> Optional[int]:
    """从 'COM5' / '/dev/ttyS5' / '/dev/ttyUSB0' 提取整数 COM 号。"""
    if not name:
        return None
    # 'COM5' 风格
    if name.upper().startswith("COM"):
        try: return int(name[3:])
        except ValueError: return None
    # Linux: 取尾部数字
    digits = ""
    for ch in reversed(name):
        if ch.isdigit(): digits = ch + digits
        else: break
    if digits:
        try: return int(digits)
        except ValueError: return None
    return None

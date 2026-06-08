"""PI 控制器链路封装 (USB / TCP / RS232 / RS232-Daisy / USB-Daisy)。

把 5 种连接方式从 PIStage 里抽出来, 保持 stage_pi.py 在 200 行内。
另持有 PIStageConfig dataclass — 单一 source-of-truth 的配置容器,
所有字段单位与 pi_params() 一致 (µm / µm/s / 整型端口号)。

Linux 注意:
- C-863 等 FTDI USB 控制器在 Linux 上不走 EnumerateUSB/ConnectUSB, 必须用 RS-232
  菊花链, 通过 PI_OpenRS232DaisyChainByDevName("/dev/ttyUSB0", 9600) 连接。
- PIPython 的 OpenRS232DaisyChain 只接受 int 型 COM 端口 (Windows 专用),
  Linux 下需要直接调用 DLL 的 ByDevName 变体。
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PIStageConfig:
    """PI stage 全配置 (链路 + 参考 + 限位 + 速度 + 步长)。"""
    # 设备 / 链路
    controller: str = "C-863"
    stage: str = "M-531.DG"
    interface: str = "usb"  # usb / tcp / rs232 / rs232-daisy / usb-daisy
    serialnum: Optional[str] = None
    ip: Optional[str] = None
    ipport: int = 50000
    comport: Optional[int] = None  # Windows: COM 口编号; Linux: 可给 None
    baudrate: int = 9600
    device_id: Optional[int] = None
    serialport: str = ""  # Linux RS-232 设备路径 (eg /dev/ttyUSB0), 空则自动探测
    # 参考策略
    refmode: str = "FRF"
    referencing: str = "skip"  # skip / auto / force
    # 限位 / 限速 / 步长 (µm 或 µm/s)
    travel_min_um: float = 32_500.0
    travel_max_um: float = 97_600.0
    velocity_um_s: Optional[float] = None
    velocity_max_um_s: float = 2_000.0  # 2 mm/s — 5 cm 缓冲 ≈ 25 秒, 够走到电脑前急停
    step_min_um: float = 0.4
    invert_z: bool = False  # z 轴反向 (driver 内部 invert, 不在 GUI 层)
    safe_radius_um: float = 100.0  # 未参考时, 连接后行程默认锁到 ctrl 当前点 ± 此半径
    # 高级 (一般不需要改)
    poll_hz: int = 30  # 位置轮询频率
    position_tolerance_um: float = 0.05  # qONT 失败时位置到位判断容差

    @classmethod
    def from_kwargs(cls, **kwargs) -> "PIStageConfig":
        """从 kwargs 构造 (含老 skip_referencing 兼容)。未知字段忽略。"""
        cfg = cls()
        skip = kwargs.pop("skip_referencing", None)
        if skip is True and "referencing" not in kwargs:
            kwargs["referencing"] = "skip"
        elif skip is False and kwargs.get("referencing", "skip") == "skip":
            kwargs["referencing"] = "auto"
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


def find_bundled_gcs2_dll() -> Optional[Path]:
    """Return a packaged or user-placed Windows PI GCS2 DLL path."""
    if sys.platform != "win32":
        return None
    for base in _gcs2_dll_search_dirs():
        dll = base / "PI_GCS2_DLL_x64.dll"
        if dll.is_file():
            return dll
    return None


def make_gcs_device(gcs_device_type, controller: str):
    """Create GCSDevice with the packaged Windows DLL path when available."""
    dll_path = find_bundled_gcs2_dll()
    if dll_path:
        return gcs_device_type(controller, gcsdll=str(dll_path))
    return gcs_device_type(controller)


def _gcs2_dll_search_dirs() -> list[Path]:
    """Search PyInstaller's internal dir, the exe dir, then the launch dir."""
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass))
    dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path.cwd())
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _is_linux() -> bool:
    return sys.platform in ("linux", "linux2")


def _find_pi_serial_port() -> Optional[str]:
    """自动探测 PI USB 串口设备路径 (通过 /dev/serial/by-id)。

    返回第一个匹配 "PI" 或 "Physik" 的 ttyUSB/ttyACM 设备路径。
    """
    by_id = "/dev/serial/by-id"
    if not os.path.isdir(by_id):
        return None
    try:
        for name in sorted(os.listdir(by_id)):
            if "PI_" in name or "Physik" in name and "if00" in name:
                path = os.path.realpath(os.path.join(by_id, name))
                if os.path.exists(path):
                    return path
    except OSError:
        pass
    # 回退: 常见路径
    for dev in ("/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"):
        if os.path.exists(dev):
            return dev
    return None


def _dll_rs232_daisy_open(gcsdevice, port: str, baudrate: int) -> tuple[int, int, list[str]]:
    """直接调 libpi_pi_gcs2 的 OpenRS232DaisyChainByDevName (Linux)。

    返回 (dcid, numdev, [device_descriptions])。失败抛 GCSError。
    """
    from pipython.pidevice.interfaces.gcsdll import PI_DLL_CODEPAGE
    dll = gcsdevice.dll
    cdevname = ctypes.c_char_p(port.encode(PI_DLL_CODEPAGE))
    cbaudrate = ctypes.c_int(int(baudrate))
    numdev = ctypes.c_int()
    bufsize = 10000
    bufstr = ctypes.create_string_buffer(b"\x00", bufsize + 2)
    dcid = getattr(dll._handle, dll._prefix + "OpenRS232DaisyChainByDevName")(
        cdevname, cbaudrate, ctypes.byref(numdev), bufstr, bufsize
    )
    if dcid < 0:
        from pipython.pidevice import GCSError
        err = getattr(dll._handle, dll._prefix + "GetError")(dcid)
        raise GCSError(err)
    devlist = bufstr.value.decode(encoding=PI_DLL_CODEPAGE, errors="ignore").split("\n")
    devlist = [item.strip() for item in devlist if item.strip()]
    dll._dcid = dcid
    dll._ifdescription = f"RS-232 daisy chain at {port}, {baudrate} Baud"
    return dcid, numdev.value, devlist


def _dll_rs232_daisy_close(gcsdevice) -> None:
    """直接调 libpi_pi_gcs2 的 CloseDaisyChain。"""
    dll = gcsdevice.dll
    try:
        if dll._dcid >= 0:
            getattr(dll._handle, dll._prefix + "CloseDaisyChain")(dll._dcid)
            dll._dcid = -1
    except Exception:
        pass


def _dll_rs232_daisy_connect(gcsdevice, daisychain_id: int, device_id: int) -> None:
    """直接调 libpi_pi_gcs2 的 ConnectDaisyChainDevice。"""
    dll = gcsdevice.dll
    cdaisychainid = ctypes.c_int(int(daisychain_id))
    cdeviceid = ctypes.c_int(int(device_id))
    new_id = getattr(dll._handle, dll._prefix + "ConnectDaisyChainDevice")(cdaisychainid, cdeviceid)
    if new_id < 0:
        from pipython.pidevice import GCSError
        err = getattr(dll._handle, dll._prefix + "GetError")(new_id)
        raise GCSError(err)
    dll._id = new_id
    if dll._ifdescription:
        dll._ifdescription += "; "
    dll._ifdescription += f"daisy chain {daisychain_id}, device {device_id}"
    dll.flush()


def _choose_interface(cfg: PIStageConfig) -> str:
    """解析实际使用的 interface 类型, 处理 Linux 降级。

    Linux 上 'usb' 和 'usb-daisy' 会降级为 RS-232 菊花链
    (C-863 等 FTDI 控制器在 Linux 上不支持原生 USB 枚举)。
    """
    iface = (cfg.interface or "usb").lower()
    if not _is_linux():
        return iface
    # Linux: USB 降级为 RS-232 菊花链
    if iface in ("usb", "usb-daisy"):
        return "rs232-daisy"
    return iface


def open_link(
    dev,
    *,
    interface: str,
    controller: str,
    serialnum: Optional[str] = None,
    ip: Optional[str] = None,
    ipport: int = 50000,
    comport: Optional[int] = None,
    baudrate: int = 9600,
    device_id: Optional[int] = None,
    usb_description: Optional[str] = None,
    serialport: str = "",
) -> Optional[int]:
    """根据 interface 打开 PI 链路。返回 daisychain id 或 None。"""
    iface = (interface or "usb").lower()

    if iface == "tcp":
        if not ip:
            raise RuntimeError("TCP 模式缺 IP 地址")
        dev.ConnectTCPIP(ipaddress=ip, ipport=int(ipport))
        return None

    if iface == "rs232":
        if _is_linux() and (serialport or comport is None):
            devport = serialport or _find_pi_serial_port()
            if not devport:
                raise RuntimeError("Linux RS232 模式缺串口路径, 自动探测失败")
            dev.ConnectRS232(comport=devport, baudrate=int(baudrate))
            return None
        if not comport:
            raise RuntimeError("RS232 模式缺 COM 端口号")
        dev.ConnectRS232(comport=int(comport), baudrate=int(baudrate))
        return None

    if iface == "rs232-daisy":
        return _open_daisy_rs232(dev, comport, baudrate, device_id, serialport)

    if iface == "usb-daisy":
        desc = usb_description or serialnum or controller
        if not desc:
            raise RuntimeError("USB-Daisy 模式缺 description / serial / controller")
        devlist = list(dev.OpenUSBDaisyChain(description=desc) or [])
        if not devlist:
            dev.CloseDaisyChain()
            raise RuntimeError("USB 菊花链上未发现设备")
        target_id = int(device_id) if device_id is not None else _pick_first_device(devlist)
        dev.ConnectDaisyChainDevice(target_id)
        return _current_daisy_id(dev)

    # 默认 USB 直连
    if serialnum:
        dev.ConnectUSB(serialnum=serialnum)
        return None
    devices = dev.EnumerateUSB(mask=controller)
    if not devices:
        raise RuntimeError(f"未找到 {controller} USB 设备")
    dev.ConnectUSB(serialnum=devices[0])
    return None


def _open_daisy_rs232(
    dev,
    comport: Optional[int],
    baudrate: int,
    device_id: Optional[int],
    serialport: str,
) -> Optional[int]:
    """打开 RS-232 菊花链, 连接指定 device (或自动选第一个)。"""
    if _is_linux():
        # Linux: 走 OpenRS232DaisyChainByDevName, 自动重试常见波特率
        devport = serialport or _find_pi_serial_port()
        if not devport:
            raise RuntimeError("RS-232 Daisy 模式缺串口路径, 自动探测失败")
        dcid = numdev = -1
        devlist = []
        baud_rates = [int(baudrate)] + [b for b in (9600, 38400, 19200, 57600, 115200) if b != int(baudrate)]
        last_err = None
        for bd in baud_rates:
            try:
                dcid, numdev, devlist = _dll_rs232_daisy_open(dev, devport, bd)
                break
            except Exception as e:
                last_err = e
                continue
        if dcid < 0:
            raise RuntimeError(f"菊花链连接失败 (已尝试 baud={baud_rates}): {last_err}")
    else:
        # Windows: PIPython returns the device list; it keeps the daisy-chain
        # handle internally and ConnectDaisyChainDevice() reads it when the
        # daisychainid argument is omitted.
        if comport is None:
            raise RuntimeError("RS232-Daisy 模式缺 COM 端口号")
        devlist = list(dev.OpenRS232DaisyChain(comport=int(comport), baudrate=int(baudrate)) or [])
        dcid = _current_daisy_id(dev)
        numdev = len(devlist)

    if numdev == 0:
        _dll_rs232_daisy_close(dev) if _is_linux() else dev.CloseDaisyChain()
        raise RuntimeError("菊花链上未发现设备")

    if device_id is not None:
        target_id = int(device_id)
    else:
        # 自动选第一个非 "not connected" 的设备
        target_id = _pick_first_device(devlist)

    if _is_linux():
        _dll_rs232_daisy_connect(dev, dcid, target_id)
    else:
        dev.ConnectDaisyChainDevice(target_id)

    # 把 devlist 写回 dev.dcdevices (GCSDevice 用 property 动态读 dll, 直接设不行,
    # 但 scan_rs232_daisy 返回 list 给上层染色)
    return dcid


def _pick_first_device(devlist: list[str]) -> int:
    """从菊花链设备列表中找第一个在线设备, 返回 1-based 序号。"""
    for i, desc in enumerate(devlist):
        d = desc.strip()
        if d and "not connected" not in d.lower():
            return i + 1
    raise RuntimeError("菊花链上所有设备都未连接")


def _current_daisy_id(dev) -> int:
    """Return PIPython's current daisy-chain ID for later cleanup."""
    try:
        return int(getattr(dev, "dcid"))
    except (AttributeError, TypeError, ValueError):
        return 0


def close_link(dev, daisychain_id: Optional[int]) -> None:
    """关闭 PI 链路。daisy chain 模式额外关掉 chain 句柄。"""
    if dev is None:
        return
    try:
        if dev.IsConnected():
            try:
                dev.STP(noraise=True)
            except Exception:  # noqa: BLE001
                pass
            dev.CloseConnection()
    except Exception:  # noqa: BLE001
        pass
    if daisychain_id is not None:
        try:
            if _is_linux():
                _dll_rs232_daisy_close(dev)
            else:
                dev.CloseDaisyChain()
        except Exception:  # noqa: BLE001
            pass


def scan_rs232_daisy(dev, comport=None, baudrate: int = 115200, serialport: str = "") -> list[str]:
    """扫描 RS-232 daisy chain 上的设备, 返回 dcdevices 字符串列表。

    成功 / 失败都自动 CloseDaisyChain 释放 chain 句柄; 出错时抛异常给上层显示。
    Linux 上 comport 可为 None, 自动探测串口路径。
    """
    if _is_linux():
        devport = serialport or _find_pi_serial_port()
        if not devport:
            raise RuntimeError("未找到 PI 串口设备")
        dcid, numdev, devlist = _dll_rs232_daisy_open(dev, devport, baudrate)
    else:
        if comport is None:
            raise RuntimeError("未设置 COM 端口号")
        devlist = list(dev.OpenRS232DaisyChain(comport=int(comport), baudrate=int(baudrate)) or [])
    try:
        return devlist
    finally:
        try:
            if _is_linux():
                _dll_rs232_daisy_close(dev)
            else:
                dev.CloseDaisyChain()
        except Exception:  # noqa: BLE001
            pass


def reference_if_needed(dev, pitools, axis: str, refmode: str, referencing: str) -> bool:
    """按 referencing 策略决定是否对该轴执行 FRF/FNL/FPL。

    referencing: 'skip' | 'auto' | 'force'
    返回当前是否处于"已参考"状态 (绝对位置可信)。
    """
    try:
        already = bool(dev.qFRF(axis)[axis])
    except Exception:  # noqa: BLE001
        already = False
    if referencing == "skip":
        return already
    if referencing == "auto" and already:
        return True
    mode = (refmode or "FRF").upper()
    if mode not in ("FRF", "FNL", "FPL"):
        mode = "FRF"
    getattr(dev, mode)(axis)
    pitools.waitontarget(dev, axes=[axis])
    return True

"""海康 MVS 相机驱动。

vendor 了 ``src/psf_scan/vendor/MvImport``（来自 ``/opt/MVS/Samples/64/Python/MvImport``）。
启动时自动找 MVS Runtime 库目录，多重保险登记 DLL 搜索路径，用户零配置。
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from ctypes import POINTER, byref, c_ubyte, cast, sizeof
from typing import Optional

import numpy as np

from ..core.camera import CameraBase
from .camera_mvs_features import MVSAdvancedMixin

# ── 自动定位 MVS Runtime 库目录 ────────────────────────────────────
# Linux 库放在 .../lib/64/libMvCameraControl.so
# Windows 库放在 .../win64/MvCameraControl.dll，根据安装方式可能在多处。
_LINUX_ROOTS = [
    os.environ.get("MVCAM_COMMON_RUNENV"),
    "/opt/MVS/lib",
    os.path.expanduser("~/MVS/lib"),
]
_WINDOWS_DLL_DIRS = [
    os.environ.get("MVCAM_COMMON_RUNENV"),
    r"C:\Program Files (x86)\MVS\Development\Libraries\win64",
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64",
    r"C:\Program Files\MVS\Development\Libraries\win64",
    r"C:\Program Files\Common Files\MVS\Runtime\Win64_x64",
]


def _diag_log(msg: str) -> None:
    """Append a diagnostic line to %LOCALAPPDATA%\\PsfScan\\logs\\mvs-loader.log.

    Cheap to call; failure is silent.
    """
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.psf_scan")
        log_dir = os.path.join(base, "PsfScan", "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "mvs-loader.log"), "a", encoding="utf-8") as fp:
            fp.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


if sys.platform == "win32":
    _diag_log(f"MVS loader start: PATH heads={os.environ.get('PATH','')[:200]!r}")
    _matched = None
    for _d in _WINDOWS_DLL_DIRS:
        if not _d:
            continue
        dll_path = os.path.join(_d, "MvCameraControl.dll")
        exists = os.path.isfile(dll_path)
        _diag_log(f"  candidate {_d!r} exists={exists}")
        if not exists:
            continue
        _matched = _d
        # 1) Hikvision 自己的环境变量（部分 SDK 路径用得到）
        os.environ["MVCAM_COMMON_RUNENV"] = _d
        # 2) Python 3.8+ 安全搜索登记
        try:
            os.add_dll_directory(_d)
            _diag_log(f"  add_dll_directory({_d!r}) OK")
        except (AttributeError, OSError) as e:
            _diag_log(f"  add_dll_directory({_d!r}) FAILED: {e!r}")
        # 3) 进程级 PATH 前置（MvImport 用的 winmode=0 走标准搜索）
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
        # 4) 用绝对路径预加载，把 DLL 与其同目录依赖项一起灌进进程内存。
        #    LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008 让依赖项也从 _d 找。
        try:
            ctypes.WinDLL(dll_path, winmode=0x00000008)
            _diag_log(f"  pre-load WinDLL({dll_path!r}) OK")
        except OSError as e:
            _diag_log(f"  pre-load WinDLL({dll_path!r}) FAILED: {e!r}")
        break
    if _matched is None:
        _diag_log("  no MVS DLL directory matched; MvImport will likely fail.")
else:
    for _root in _LINUX_ROOTS:
        if not _root:
            continue
        if os.path.exists(os.path.join(_root, "64", "libMvCameraControl.so")):
            os.environ["MVCAM_COMMON_RUNENV"] = _root
            break

from ..vendor.MvImport import (  # noqa: E402  ── 必须在设环境变量 / add_dll_directory 之后
    MV_ACCESS_Exclusive,
    MV_CC_DEVICE_INFO,
    MV_CC_DEVICE_INFO_LIST,
    MV_FRAME_OUT_INFO_EX,
    MV_GIGE_DEVICE,
    MV_USB_DEVICE,
    MVCC_INTVALUE,
    MvCamera,
    PixelType_Gvsp_Mono8,
    PixelType_Gvsp_Mono16,
)


class MVSCamera(MVSAdvancedMixin, CameraBase):
    """海康 MVS 相机（GigE / USB3 通用）。"""

    def __init__(self, sn: Optional[str] = None, exposure_us: int = 10_000) -> None:
        super().__init__()
        self._sn = sn
        self._cam = MvCamera()
        self._connected = False
        self._streaming = False
        self._w = 0
        self._h = 0
        self._buf_size = 0
        self._lock = threading.Lock()
        self._stream_thread: Optional[threading.Thread] = None
        self._exposure_us = int(exposure_us)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def frame_size(self) -> tuple[int, int]:
        return (self._w, self._h)

    def connect(self) -> None:
        info_list = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, info_list)
        if ret != 0 or info_list.nDeviceNum == 0:
            self.error.emit(f"未发现 MVS 设备 (ret=0x{ret:x})")
            return
        # TODO: SN 匹配；当前默认选第 0 个
        # pDeviceInfo[i] 是 POINTER(MV_CC_DEVICE_INFO)；CreateHandle 内部会再 byref，
        # 所以这里必须解引用成结构体本身，否则报 MV_E_PARAMETER (0x80000004)
        info = cast(info_list.pDeviceInfo[0], POINTER(MV_CC_DEVICE_INFO)).contents
        ret = self._cam.MV_CC_CreateHandle(info)
        if ret != 0:
            self.error.emit(f"CreateHandle 失败: 0x{ret:x}")
            return
        ret = self._cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != 0:
            self.error.emit(f"OpenDevice 失败: 0x{ret:x}")
            return
        # 显式设连续采集 + 关触发，并校验
        ret = self._cam.MV_CC_SetEnumValueByString("AcquisitionMode", "Continuous")
        if ret != 0:
            self.error.emit(f"AcquisitionMode=Continuous 失败: 0x{ret:x}")
        ret = self._cam.MV_CC_SetEnumValueByString("TriggerMode", "Off")
        if ret != 0:
            self.error.emit(f"TriggerMode=Off 失败: 0x{ret:x}")
        # 关掉自动曝光，避免某些固件 stuck 在 Auto
        self._cam.MV_CC_SetEnumValueByString("ExposureAuto", "Off")
        self._cam.MV_CC_SetEnumValueByString("GainAuto", "Off")
        # 读取宽高
        wv, hv = MVCC_INTVALUE(), MVCC_INTVALUE()
        self._cam.MV_CC_GetIntValue("Width", wv)
        self._cam.MV_CC_GetIntValue("Height", hv)
        self._w, self._h = int(wv.nCurValue), int(hv.nCurValue)
        # 单帧最大占用 (Mono16 上限 2 字节/px)
        self._buf_size = self._w * self._h * 2
        self.set_exposure_us(self._exposure_us)
        self._connected = True

    def disconnect(self) -> None:
        if self._streaming:
            self.stop_streaming()
        if self._connected:
            self._cam.MV_CC_CloseDevice()
            self._cam.MV_CC_DestroyHandle()
            self._connected = False

    def start_streaming(self) -> None:
        if not self._connected:
            self.error.emit("相机未连接")
            return
        ret = self._cam.MV_CC_StartGrabbing()
        if ret != 0:
            self.error.emit(f"StartGrabbing 失败: 0x{ret:x}")
            return
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()

    def stop_streaming(self) -> None:
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=1.0)
            self._stream_thread = None
        if self._connected:
            self._cam.MV_CC_StopGrabbing()

    def grab_one(self, timeout_ms: int = 1000) -> np.ndarray:
        return self._grab_locked(timeout_ms)

    def set_exposure_us(self, us: int) -> None:
        self._exposure_us = int(us)
        if self._connected:
            self._cam.MV_CC_SetFloatValue("ExposureTime", float(us))

    def set_gain(self, gain: float) -> None:
        if self._connected:
            self._cam.MV_CC_SetFloatValue("Gain", float(gain))

    # ── 内部 ───────────────────────────────────────────
    def _stream_loop(self) -> None:
        consecutive_fails = 0
        last_reported = ""
        while self._streaming:
            try:
                frame = self._grab_locked(timeout_ms=500)
                self.frame_ready.emit(frame, time.time())
                consecutive_fails = 0
            except RuntimeError as exc:
                consecutive_fails += 1
                msg = str(exc)
                if consecutive_fails in (1, 10, 50) and msg != last_reported:
                    self.error.emit(f"取帧失败 ×{consecutive_fails}: {msg}")
                    last_reported = msg
                continue

    def _grab_locked(self, timeout_ms: int) -> np.ndarray:
        with self._lock:
            buf = (c_ubyte * self._buf_size)()
            info = MV_FRAME_OUT_INFO_EX()
            ret = self._cam.MV_CC_GetOneFrameTimeout(
                cast(buf, POINTER(c_ubyte)),
                self._buf_size,
                info,
                timeout_ms,
            )
            if ret != 0:
                raise RuntimeError(f"GetOneFrameTimeout: 0x{ret:x}")
            n = int(info.nFrameLen)
            h, w = int(info.nHeight), int(info.nWidth)
            pix = int(info.enPixelType)
            if pix == PixelType_Gvsp_Mono16:
                arr = np.frombuffer(buf, dtype=np.uint16, count=n // 2)
                return arr.reshape(h, w).copy()
            # 其它 Mono / Bayer 均按 8-bit 处理（如需色彩转换可后续补 ConvertPixelType）
            arr = np.frombuffer(buf, dtype=np.uint8, count=n)
            return arr.reshape(h, w).copy() if pix == PixelType_Gvsp_Mono8 else arr[: h * w].reshape(h, w).copy()

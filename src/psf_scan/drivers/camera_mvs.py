"""海康 MVS 相机驱动。

vendor 了 ``src/psf_scan/vendor/MvImport``（来自 ``/opt/MVS/Samples/64/Python/MvImport``）。
启动时自动找 MVS Runtime 库目录，多重保险登记 DLL 搜索路径，用户零配置。
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import POINTER, c_ubyte, cast
from typing import Optional

import numpy as np

from ..core.camera import CameraBase

# 注意: ``camera_mvs_features`` 顶层会 ``from ..vendor.MvImport import ...``,
# 触发 vendored 海康 ``check_sys_and_update_dll`` 立即拼接
# ``os.getenv('MVCAM_COMMON_RUNENV') + "/64/libMvCameraControl.so"``。
# 因此 ``MVSAdvancedMixin`` 的 import 必须等下面 ``_LINUX_ROOTS`` /
# ``_WINDOWS_DLL_DIRS`` 探测把 env 设好后再做(挪到文件末尾的 vendor import 之后);
# 否则桌面会话没继承 ``MVCAM_COMMON_RUNENV`` 时,模块导入立即抛
# ``NoneType + str``,UI 弹出"连接失败"。

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
    _matched = None
    for _root in _LINUX_ROOTS:
        if not _root:
            continue
        if os.path.exists(os.path.join(_root, "64", "libMvCameraControl.so")):
            os.environ["MVCAM_COMMON_RUNENV"] = _root
            _matched = _root
            break
    if _matched is None:
        raise RuntimeError(
            "未检测到 MVS Runtime 库。请安装海康 MVS SDK,或设环境变量 "
            "MVCAM_COMMON_RUNENV=<sdk-lib-root> (期望存在 "
            "<root>/64/libMvCameraControl.so)。"
            f"已尝试: {[r for r in _LINUX_ROOTS if r]}"
        )

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
from .camera_mvs_features import (  # noqa: E402  ── 同上, 需等 env 设完
    MVSAdvancedMixin,
    get_float,
    resulting_frame_rate,
    set_frame_rate_value,
)

_log = logging.getLogger(__name__)


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
        self._raw_buf = None
        self._lock = threading.Lock()
        self._preview_lock = threading.Lock()
        self._preview_pending = False
        self._stats_lock = threading.Lock()
        self._reset_stream_stats()
        self._stream_thread: Optional[threading.Thread] = None
        self._exposure_us = int(exposure_us)
        self._target_frame_rate: float | None = None

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
        self._raw_buf = (c_ubyte * self._buf_size)()
        self.set_exposure_us(self._exposure_us)
        self._connected = True

    def disconnect(self) -> None:
        if self._streaming:
            self.stop_streaming()
        if self._connected:
            self._cam.MV_CC_CloseDevice()
            self._cam.MV_CC_DestroyHandle()
            self._connected = False
        self._raw_buf = None

    def start_streaming(self) -> None:
        if not self._connected:
            self.error.emit("相机未连接")
            return
        ret = self._cam.MV_CC_StartGrabbing()
        if ret != 0:
            self.error.emit(f"StartGrabbing 失败: 0x{ret:x}")
            return
        self._reset_stream_stats()
        self._set_preview_pending(False)
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
        self._set_preview_pending(False)

    def grab_one(self, timeout_ms: int = 1000) -> np.ndarray:
        return self._grab_locked(timeout_ms)

    def set_exposure_us(self, us: int) -> None:
        self._exposure_us = int(us)
        if self._connected:
            ret = self._cam.MV_CC_SetFloatValue("ExposureTime", float(us))
            if ret != 0:
                self.error.emit(f"ExposureTime 设置失败: 0x{ret:x}")

    def set_gain(self, gain: float) -> None:
        if self._connected:
            ret = self._cam.MV_CC_SetFloatValue("Gain", float(gain))
            if ret != 0:
                self.error.emit(f"Gain 设置失败: 0x{ret:x}")

    def set_frame_rate(self, fps: float) -> None:
        self._target_frame_rate = float(fps)
        if not self._connected:
            return
        with self._lock:
            ok = set_frame_rate_value(self._cam, self._target_frame_rate)
            actual = self._frame_rate_state_unlocked()
        if not ok:
            self.error.emit(f"AcquisitionFrameRate 设置失败: {self._target_frame_rate:.1f} fps")
            return
        if actual is None:
            self.error.emit("AcquisitionFrameRate 已写入,但回读失败")
            return
        _log.info(
            "frame rate target=%.1f device=%.1f resulting=%.1f",
            self._target_frame_rate,
            actual["device_fps"],
            actual["resulting_fps"],
        )

    def get_exposure_us(self) -> int:
        if not self._connected:
            return self._exposure_us
        state = get_float(self._cam, "ExposureTime")
        if state is None:
            raise RuntimeError("读取 ExposureTime 失败")
        return int(round(state[0]))

    def get_gain(self) -> float:
        if not self._connected:
            return 1.0
        state = get_float(self._cam, "Gain")
        if state is None:
            raise RuntimeError("读取 Gain 失败")
        return float(state[0])

    def exposure_range(self) -> tuple[int, int]:
        if not self._connected:
            return (10, 1_000_000)
        state = get_float(self._cam, "ExposureTime")
        if state is None:
            raise RuntimeError("读取 ExposureTime 范围失败")
        return (int(round(state[1])), int(round(state[2])))

    def gain_range(self) -> tuple[float, float]:
        if not self._connected:
            return (0.0, 32.0)
        state = get_float(self._cam, "Gain")
        if state is None:
            raise RuntimeError("读取 Gain 范围失败")
        return (float(state[1]), float(state[2]))

    def mark_preview_delivered(self) -> None:
        self._set_preview_pending(False)

    # ── 内部 ───────────────────────────────────────────
    def _stream_loop(self) -> None:
        consecutive_fails = 0
        last_reported = ""
        while self._streaming:
            try:
                if not self._claim_preview_slot():
                    self._grab_locked(timeout_ms=500, copy_frame=False)
                    self._record_grab(None)
                    self._record_skip()
                    continue
                frame = self._grab_locked(timeout_ms=500, copy_frame=True)
                self._record_grab(frame)
                self._record_emit()
                self.frame_ready.emit(frame, time.time())
                consecutive_fails = 0
            except RuntimeError as exc:
                self._set_preview_pending(False)
                self._record_fail()
                consecutive_fails += 1
                msg = str(exc)
                if consecutive_fails in (1, 10, 50) and msg != last_reported:
                    self.error.emit(f"取帧失败 ×{consecutive_fails}: {msg}")
                    last_reported = msg
                continue

    def _claim_preview_slot(self) -> bool:
        with self._preview_lock:
            if self._preview_pending:
                return False
            self._preview_pending = True
            return True

    def _set_preview_pending(self, pending: bool) -> None:
        with self._preview_lock:
            self._preview_pending = pending

    def diagnostics(self) -> dict[str, object]:
        with self._stats_lock:
            elapsed = max(1e-6, time.time() - self._stats_started_at)
            data = {
                "connected": self._connected,
                "streaming": self._streaming,
                "grabbed": self._grabbed_frames,
                "grab_fps": round(self._grabbed_frames / elapsed, 2),
                "preview_emit": self._preview_emitted,
                "preview_skip": self._preview_skipped,
                "grab_fail": self._grab_failures,
                "last_shape": self._last_frame_shape,
                "last_dtype": self._last_frame_dtype,
                "pending": self._preview_pending,
            }
        data.update(self._frame_rate_diagnostics())
        return data

    def _frame_rate_diagnostics(self) -> dict[str, object]:
        if not self._connected:
            return {"target_fps": self._target_frame_rate}
        with self._lock:
            state = self._frame_rate_state_unlocked()
        if state is None:
            return {"target_fps": self._target_frame_rate, "device_fps": None, "resulting_fps": None}
        return {"target_fps": self._target_frame_rate, **state}

    def _frame_rate_state_unlocked(self) -> dict[str, float] | None:
        state = get_float(self._cam, "AcquisitionFrameRate")
        if state is None:
            return None
        resulting = resulting_frame_rate(self._cam)
        return {
            "device_fps": float(state[0]),
            "resulting_fps": float(resulting if resulting is not None else state[0]),
        }

    def _reset_stream_stats(self) -> None:
        with self._stats_lock:
            self._stats_started_at = time.time()
            self._grabbed_frames = 0
            self._preview_emitted = 0
            self._preview_skipped = 0
            self._grab_failures = 0
            self._last_frame_shape = None
            self._last_frame_dtype = ""

    def _record_grab(self, frame: np.ndarray | None) -> None:
        with self._stats_lock:
            self._grabbed_frames += 1
            if frame is None:
                return
            self._last_frame_shape = tuple(frame.shape)
            self._last_frame_dtype = str(frame.dtype)

    def _record_emit(self) -> None:
        with self._stats_lock:
            self._preview_emitted += 1

    def _record_skip(self) -> None:
        with self._stats_lock:
            self._preview_skipped += 1

    def _record_fail(self) -> None:
        with self._stats_lock:
            self._grab_failures += 1

    def _grab_locked(self, timeout_ms: int, *, copy_frame: bool = True) -> np.ndarray | None:
        with self._lock:
            if self._raw_buf is None:
                raise RuntimeError("MVS raw buffer is not allocated")
            info = MV_FRAME_OUT_INFO_EX()
            ret = self._cam.MV_CC_GetOneFrameTimeout(
                cast(self._raw_buf, POINTER(c_ubyte)),
                self._buf_size,
                info,
                timeout_ms,
            )
            if ret != 0:
                raise RuntimeError(f"GetOneFrameTimeout: 0x{ret:x}")
            if not copy_frame:
                return None
            return self._array_from_buffer(info)

    def _array_from_buffer(self, info: MV_FRAME_OUT_INFO_EX) -> np.ndarray:
            n = int(info.nFrameLen)
            h, w = int(info.nHeight), int(info.nWidth)
            pix = int(info.enPixelType)
            if pix == PixelType_Gvsp_Mono16:
                arr = np.frombuffer(self._raw_buf, dtype=np.uint16, count=n // 2)
                return arr.reshape(h, w).copy()
            # 其它 Mono / Bayer 均按 8-bit 处理（如需色彩转换可后续补 ConvertPixelType）
            arr = np.frombuffer(self._raw_buf, dtype=np.uint8, count=n)
            return arr.reshape(h, w).copy() if pix == PixelType_Gvsp_Mono8 else arr[: h * w].reshape(h, w).copy()

"""MVS 相机高级 feature 读写助手。

把 SDK 的细节（FloatValue / IntValue / EnumValue / Enable 旁支开关）封到
几个稳健的小函数里，供 :mod:`camera_mvs` 调用。所有函数对 ret≠0 静默
失败（advanced 控件可缺，相机不会因此停摆），便于 UI 用 None 表示
"该相机没这功能"。"""
from __future__ import annotations

from ctypes import c_uint32

from ..vendor.MvImport import (
    MVCC_ENUMVALUE,
    MVCC_FLOATVALUE,
    MVCC_INTVALUE,
)


def _ok(ret: int) -> bool:
    return ret == 0


def get_float(cam, key: str) -> tuple[float, float, float] | None:
    """返回 (current, min, max)；不可用时 None。"""
    v = MVCC_FLOATVALUE()
    if not _ok(cam.MV_CC_GetFloatValue(key, v)):
        return None
    return (float(v.fCurValue), float(v.fMin), float(v.fMax))


def set_float(cam, key: str, value: float) -> bool:
    return _ok(cam.MV_CC_SetFloatValue(key, float(value)))


def get_int(cam, key: str) -> tuple[int, int, int] | None:
    v = MVCC_INTVALUE()
    if not _ok(cam.MV_CC_GetIntValue(key, v)):
        return None
    return (int(v.nCurValue), int(v.nMin), int(v.nMax))


def set_int(cam, key: str, value: int) -> bool:
    return _ok(cam.MV_CC_SetIntValue(key, int(value)))


def set_bool(cam, key: str, value: bool) -> bool:
    return _ok(cam.MV_CC_SetBoolValue(key, bool(value)))


def get_enum_symbolic(cam, key: str) -> str | None:
    v = MVCC_ENUMVALUE()
    if not _ok(cam.MV_CC_GetEnumValue(key, v)):
        return None
    # nCurValue 是数值，对应可选项；可选项 symbolic 用 EnumEntries API
    n = int(v.nCurValue)
    entries = enum_entries(cam, key)
    for sym, value in entries:
        if value == n:
            return sym
    return None


def enum_entries(cam, key: str) -> list[tuple[str, int]]:
    """返回 [(symbolic, numeric), ...]。MVS Python wrapper 没直接暴露
    `MV_CC_GetEnumEntries`，靠 `MV_XML_GetSymbolicByEnumIntValue`
    一个一个枚举效率太低 — 这里用 SDK 的 GetEnumEntries 走 ctypes。"""
    # 先尝试 wrapper 上的 high-level API（部分 vendor 包含）
    if hasattr(cam, "MV_CC_GetEnumEntries"):
        from ..vendor.MvImport import MV_CC_ENUM_ENTRIES_LIST
        lst = MV_CC_ENUM_ENTRIES_LIST()
        if _ok(cam.MV_CC_GetEnumEntries(key, lst)):
            out = []
            for i in range(int(lst.nEnumEntryBufferNum)):
                e = lst.pstEnumEntries[i]
                if not e:
                    continue
                ent = e.contents if hasattr(e, "contents") else e
                out.append((ent.chSymbolic.decode(errors="ignore").strip("\x00 "), int(ent.nValue)))
            return out
    return []


def enable_feature(cam, enable_key: str, on: bool) -> bool:
    """很多 feature 需要先打开 *Enable* 开关；不存在该 key 不算错。"""
    if not _ok(cam.MV_CC_SetBoolValue(enable_key, bool(on))):
        # 当 key 不存在时 SDK 会返回非 0；这是正常的，不报错
        return False
    return True


# ── 高级 feature 套件 ──────────────────────────────────────

def gamma_state(cam) -> tuple[float, float, float] | None:
    """开启 GammaEnable，再读 Gamma 当前/范围。"""
    enable_feature(cam, "GammaEnable", True)
    return get_float(cam, "Gamma")


def set_gamma_value(cam, value: float) -> bool:
    enable_feature(cam, "GammaEnable", True)
    return set_float(cam, "Gamma", value)


def black_level_state(cam) -> tuple[int, int, int] | None:
    enable_feature(cam, "BlackLevelEnable", True)
    return get_int(cam, "BlackLevel")


def set_black_level_value(cam, value: int) -> bool:
    enable_feature(cam, "BlackLevelEnable", True)
    return set_int(cam, "BlackLevel", value)


def frame_rate_state(cam) -> tuple[float, float, float] | None:
    enable_feature(cam, "AcquisitionFrameRateEnable", True)
    return get_float(cam, "AcquisitionFrameRate")


def set_frame_rate_value(cam, value: float) -> bool:
    enable_feature(cam, "AcquisitionFrameRateEnable", True)
    return set_float(cam, "AcquisitionFrameRate", value)


def resulting_frame_rate(cam) -> float | None:
    state = get_float(cam, "ResultingFrameRate")
    return None if state is None else state[0]


def pixel_format_state(cam) -> tuple[str | None, list[str]]:
    """返回 (current_symbolic, [available_symbolic, ...])。"""
    cur = get_enum_symbolic(cam, "PixelFormat")
    entries = enum_entries(cam, "PixelFormat")
    return (cur, [sym for sym, _ in entries])


def set_pixel_format_value(cam, symbolic: str) -> bool:
    return _ok(cam.MV_CC_SetEnumValueByString("PixelFormat", symbolic))


# 海康 MVS 不同型号的暗场补偿节点名各异; 按优先级试一遍, 命中即用.
# 直接 SetBoolValue(True) -- 节点存在且接受才返回 0, 否则视为不支持.
_HARDWARE_DARK_NODES: tuple[str, ...] = (
    "NUCEnable",                  # Non-Uniformity Correction (DSNU/PRNU)
    "DarkFieldCorrectionEnable",  # 部分工业线相机
    "DPCEnable",                  # Defective Pixel Correction (兜底)
)

# 触发型 NUC 的命令节点 (相机当下捕获 dark 计算 offset, 烧入 RAM).
# 出厂校准型相机这些节点不存在, SetCommandValue 会返回非零, 视为不支持.
_HARDWARE_DARK_TRIGGER_NODES: tuple[str, ...] = (
    "NUCExecute",                  # 部分海康 / GenICam
    "DarkFieldCorrectionExecute",  # 工业线相机
    "OBCExecute",                  # On-board Black Correction
    "RunDarkCalibration",          # 部分科研 sCMOS
)


def engage_hardware_dark(cam) -> str | None:
    """逐个尝试启用相机内置暗场补偿; 返回命中的节点名, 全部失败时 None."""
    for key in _HARDWARE_DARK_NODES:
        if _ok(cam.MV_CC_SetBoolValue(key, True)):
            return key
    return None


def trigger_hardware_dark(cam) -> str | None:
    """执行触发型相机 NUC; 返回命中的命令节点名, 没命中返回 None.

    调用前必须确认镜头已盖, 相机在 grab 帧. 命令节点不存在的相机 SetCommandValue
    返回非零, 安静跳过, 不污染相机状态.
    """
    if not hasattr(cam, "MV_CC_SetCommandValue"):
        return None
    for key in _HARDWARE_DARK_TRIGGER_NODES:
        if _ok(cam.MV_CC_SetCommandValue(key)):
            return key
    return None


def disengage_hardware_dark(cam, node: str | None) -> None:
    """关闭曾经启用的节点; node 为 None 时遍历全部已知节点静默关闭."""
    keys = (node,) if node else _HARDWARE_DARK_NODES
    for key in keys:
        if key:
            cam.MV_CC_SetBoolValue(key, False)


# ── CameraBase 高级方法的 MVS Mixin ────────────────────────

class MVSAdvancedMixin:
    """混入 :class:`MVSCamera`，把 advanced 抽象方法落到 SDK 调用。

    要求宿主类有 ``self._cam`` (MvCamera) 和 ``self._connected`` (bool)。
    """

    _cam: object  # 类型提示：MvCamera
    _connected: bool
    _hw_dark_node: str | None = None

    # gamma ─────────────────────────────
    def set_gamma(self, gamma: float) -> None:
        if self._connected:
            set_gamma_value(self._cam, gamma)

    def get_gamma(self) -> float | None:
        if not self._connected:
            return None
        s = gamma_state(self._cam)
        return None if s is None else s[0]

    def gamma_range(self) -> tuple[float, float] | None:
        if not self._connected:
            return None
        s = gamma_state(self._cam)
        return None if s is None else (s[1], s[2])

    # black level ──────────────────────
    def set_black_level(self, level: int) -> None:
        if self._connected:
            set_black_level_value(self._cam, level)

    def get_black_level(self) -> int | None:
        if not self._connected:
            return None
        s = black_level_state(self._cam)
        return None if s is None else s[0]

    def black_level_range(self) -> tuple[int, int] | None:
        if not self._connected:
            return None
        s = black_level_state(self._cam)
        return None if s is None else (s[1], s[2])

    # frame rate ───────────────────────
    def set_frame_rate(self, fps: float) -> None:
        if self._connected:
            set_frame_rate_value(self._cam, fps)

    def get_frame_rate(self) -> float | None:
        if not self._connected:
            return None
        s = frame_rate_state(self._cam)
        return None if s is None else s[0]

    def frame_rate_range(self) -> tuple[float, float] | None:
        if not self._connected:
            return None
        s = frame_rate_state(self._cam)
        return None if s is None else (s[1], s[2])

    # pixel format ─────────────────────
    def set_pixel_format(self, fmt: str) -> None:
        if self._connected:
            set_pixel_format_value(self._cam, fmt)

    def get_pixel_format(self) -> str | None:
        if not self._connected:
            return None
        cur, _ = pixel_format_state(self._cam)
        return cur

    def pixel_formats(self) -> tuple[str, ...]:
        if not self._connected:
            return ()
        _, options = pixel_format_state(self._cam)
        return tuple(options)

    # hardware dark-field ────────────────
    def try_enable_hardware_dark(self) -> bool:
        if not self._connected:
            return False
        node = engage_hardware_dark(self._cam)
        self._hw_dark_node = node
        return node is not None

    def disable_hardware_dark(self) -> None:
        if self._connected:
            disengage_hardware_dark(self._cam, self._hw_dark_node)
        self._hw_dark_node = None

    @property
    def hardware_dark_active(self) -> bool:
        return self._hw_dark_node is not None

    @property
    def hardware_dark_node(self) -> str | None:
        return self._hw_dark_node

    def trigger_hardware_dark_calibration(self) -> str | None:
        if not self._connected:
            return None
        return trigger_hardware_dark(self._cam)

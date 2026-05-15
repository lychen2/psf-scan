"""Off-axis interferogram quality diagnostics.

参考 Zhao et al. Light: Sci & Appl. 2021 (II-PMS) 一拍式离轴 FFT 算法,
对当前帧给出可操作的中文告警与硬件调整建议。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .phase import Sideband

CARRIER_MIN_CYCLES = 20.0
SAT_WARN_FRACTION = 0.01
SAT_INFO_FRACTION = 1e-4
CONTRAST_LOW = 0.10
CONTRAST_HEALTHY = 0.30
SIDEBAND_DC_RATIO_LOW = 0.02
DC_EXCLUSION_FRACTION = 0.08
PEAK_HALF_THRESHOLD = 0.5
EPS = 1e-12


@dataclass(frozen=True)
class DiagnosticsWarning:
    severity: str  # "info" | "warn" | "error"
    code: str
    message: str


@dataclass(frozen=True)
class InterferogramDiagnostics:
    image_shape: tuple[int, int]
    sideband: Sideband
    carrier_cycles: float
    carrier_angle_deg: float
    fringe_contrast: float
    sideband_to_dc_ratio: float
    sample_bandwidth_cycles: float
    dc_sideband_clearance: float
    saturated_fraction: float
    max_value: int | None

    def warnings(self) -> list[DiagnosticsWarning]:
        out: list[DiagnosticsWarning] = []
        out.extend(_carrier_warnings(self))
        out.extend(_contrast_warnings(self))
        out.extend(_sideband_warnings(self))
        out.extend(_overlap_warnings(self))
        out.extend(_saturation_warnings(self))
        return out

    def summary(self) -> str:
        return (
            f"载频 {self.carrier_cycles:.1f} cy ({self.carrier_angle_deg:+.0f}°), "
            f"对比度 {self.fringe_contrast:.2f}, "
            f"旁瓣/DC {self.sideband_to_dc_ratio:.3f}, "
            f"样品带宽 {self.sample_bandwidth_cycles:.1f} cy, "
            f"DC余量 {self.dc_sideband_clearance:+.1f} cy, "
            f"饱和 {self.saturated_fraction * 100:.2f}%"
        )


def diagnose_interferogram(
    image: np.ndarray,
    sideband: Sideband | None = None,
) -> InterferogramDiagnostics:
    gray = _to_gray(image)
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    fft_shift = np.fft.fftshift(np.fft.fft2(gray))
    mag = np.abs(fft_shift)
    sb = sideband if sideband is not None else _detect_sideband(mag, cx, cy)
    sx, sy = float(sb.x), float(sb.y)
    dx, dy = sx - cx, sy - cy
    carrier_cycles = float(np.hypot(dx, dy))
    carrier_angle = float(np.degrees(np.arctan2(dy, dx)))
    sb_amp = float(mag[int(round(sy)), int(round(sx))])
    dc_amp = float(mag[cy, cx])
    sb_to_dc = float(sb_amp / max(dc_amp, EPS))
    contrast = float(min(2.0 * sb_to_dc, 1.0))
    sample_bw = _peak_half_width(mag, int(round(sx)), int(round(sy)))
    dc_bw = _peak_half_width(mag, cx, cy)
    clearance = carrier_cycles - dc_bw - sample_bw
    sat_frac, max_val = _saturation(image)
    return InterferogramDiagnostics(
        image_shape=(h, w),
        sideband=Sideband(x=sx, y=sy, radius=float(sb.radius)),
        carrier_cycles=carrier_cycles,
        carrier_angle_deg=carrier_angle,
        fringe_contrast=contrast,
        sideband_to_dc_ratio=sb_to_dc,
        sample_bandwidth_cycles=sample_bw,
        dc_sideband_clearance=clearance,
        saturated_fraction=sat_frac,
        max_value=max_val,
    )


def format_warnings(warnings: list[DiagnosticsWarning]) -> str:
    if not warnings:
        return "干涉图诊断: 通过"
    tag = {"info": "[i]", "warn": "[!]", "error": "[X]"}
    lines = [f"{tag.get(w.severity, '[?]')} {w.message}" for w in warnings]
    return "干涉图诊断:\n" + "\n".join(lines)


def _detect_sideband(mag: np.ndarray, cx: int, cy: int) -> Sideband:
    h, w = mag.shape
    masked = np.log1p(mag).astype(np.float32, copy=True)
    radius = max(4, int(min(h, w) * DC_EXCLUSION_FRACTION))
    yy, xx = np.ogrid[:h, :w]
    masked[(xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2] = -np.inf
    y, x = np.unravel_index(int(np.nanargmax(masked)), masked.shape)
    dist = float(np.hypot(x - cx, y - cy))
    return Sideband(x=float(x), y=float(y), radius=float(min(80.0, max(4.0, dist * 0.35))))


def _peak_half_width(mag: np.ndarray, x: int, y: int) -> float:
    """Equivalent radius of the area where magnitude >= 50% peak,
    inside a small window centered on the peak."""
    h, w = mag.shape
    win = max(8, min(h, w) // 6)
    x0, x1 = max(0, x - win), min(w, x + win + 1)
    y0, y1 = max(0, y - win), min(h, y + win + 1)
    region = mag[y0:y1, x0:x1]
    threshold = float(region.max()) * PEAK_HALF_THRESHOLD
    area = float(np.sum(region >= threshold))
    return float(np.sqrt(area / np.pi))


def _saturation(image: np.ndarray) -> tuple[float, int | None]:
    if np.issubdtype(image.dtype, np.integer):
        info = np.iinfo(image.dtype)
        max_val = int(info.max)
        sat = int(np.sum(image >= max_val - 1))
    else:
        max_val = None
        peak = float(np.nanmax(image))
        sat = int(np.sum(image >= peak * 0.999))
    return sat / float(image.size), max_val


def _to_gray(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=2)
    return arr.astype(np.float32, copy=False)


def _carrier_warnings(d: InterferogramDiagnostics) -> list[DiagnosticsWarning]:
    if d.carrier_cycles < CARRIER_MIN_CYCLES:
        return [DiagnosticsWarning("warn", "carrier_low", (
            f"载频仅 {d.carrier_cycles:.1f} cycles (推荐 ≥{CARRIER_MIN_CYCLES:.0f}), 旁瓣易与 DC 重叠。"
            " 实验调整: 增大参考臂入射角 (调 BS2 后 L2 在 x 方向偏移), 或换更大像素数的相机区域。"
        ))]
    nyquist = min(d.image_shape) / 4.0
    if d.carrier_cycles > nyquist:
        return [DiagnosticsWarning("warn", "carrier_high", (
            f"载频 {d.carrier_cycles:.1f} cycles 超过安全 Nyquist/2 ({nyquist:.0f}), 条纹会混叠。"
            " 实验调整: 减小参考臂入射角。"
        ))]
    return []


def _contrast_warnings(d: InterferogramDiagnostics) -> list[DiagnosticsWarning]:
    if d.fringe_contrast < CONTRAST_LOW:
        return [DiagnosticsWarning("warn", "contrast_low", (
            f"干涉对比度仅 {d.fringe_contrast:.2f} (<{CONTRAST_LOW:.2f}), 重建相位会被噪声主导。"
            " 实验调整: 在参考路加 ND 让 |E_ref|² ≈ |E_obj|², 检查 CP1/CP2 偏振一致, 确认两路光程差 < 激光相干长度。"
        ))]
    if d.fringe_contrast < CONTRAST_HEALTHY:
        return [DiagnosticsWarning("info", "contrast_marginal", (
            f"对比度 {d.fringe_contrast:.2f} 偏低 (推荐 >{CONTRAST_HEALTHY:.2f}), 可微调参考臂强度或偏振对齐。"
        ))]
    return []


def _sideband_warnings(d: InterferogramDiagnostics) -> list[DiagnosticsWarning]:
    if d.sideband_to_dc_ratio < SIDEBAND_DC_RATIO_LOW:
        return [DiagnosticsWarning("warn", "sideband_weak", (
            f"旁瓣峰值仅为 DC 的 {d.sideband_to_dc_ratio:.3f}, 调制信号过弱。"
            " 实验调整: 增大物体路透过率, 提升参考臂强度, 同时确认 CCD 处于线性区不饱和。"
        ))]
    return []


def _overlap_warnings(d: InterferogramDiagnostics) -> list[DiagnosticsWarning]:
    if d.dc_sideband_clearance <= 0:
        return [DiagnosticsWarning("error", "dc_sideband_overlap", (
            f"DC 与旁瓣半宽相加 ≥ 载频距离 ({d.carrier_cycles:.1f} cy, 余量 {d.dc_sideband_clearance:+.1f} cy), 滤波后样品频谱被 DC 污染, 相位失真。"
            " 实验调整: (1) 增大参考臂入射角抬高载频; (2) 缩小 metalens 视场或换更低 NA 样品减小相位陡度。"
        ))]
    if d.dc_sideband_clearance < d.carrier_cycles * 0.2:
        return [DiagnosticsWarning("warn", "dc_sideband_close", (
            f"DC 与旁瓣余量仅 {d.dc_sideband_clearance:.1f} cy (<20% 载频), 边缘可能混叠。"
            " 实验调整: 提高载频, 或后处理收紧 sideband 滤波半径。"
        ))]
    return []


def _saturation_warnings(d: InterferogramDiagnostics) -> list[DiagnosticsWarning]:
    if d.saturated_fraction > SAT_WARN_FRACTION:
        return [DiagnosticsWarning("warn", "saturated", (
            f"饱和像素 {d.saturated_fraction * 100:.1f}% (>1%), 亮处振幅截断会在相位边缘形成假纹理。"
            " 实验调整: 降曝光或增益, 必要时在两路加 ND 衰减。"
        ))]
    if d.saturated_fraction > SAT_INFO_FRACTION:
        return [DiagnosticsWarning("info", "saturated_minor", (
            f"少量饱和像素 ({d.saturated_fraction * 100:.2f}%), 关注亮斑是否落在样品视场内。"
        ))]
    return []

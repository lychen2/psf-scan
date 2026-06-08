"""i18n — 字典式中英文翻译。

设计:
- ``tr(key, **fmt)`` 优先返回当前语言对应翻译, 缺失时回退英文, 再回退 key 本身.
- 语言切换通过 ``set_language(code)``, 立即生效但已 build 的 widget 文本不自动刷新;
  约定 widget 持有 ``retranslate()`` 方法, 由 settings dialog 在切换后调用.
- 简单实践: 多数情况下保存设置后弹 "需重启" 提示, 避免遍历刷新.

key 命名: ``section.subsection.string`` (snake_case).
"""

from __future__ import annotations

from typing import Callable

# 默认中文
_lang: str = "zh"
_listeners: list[Callable[[str], None]] = []

# 用 LANG 标识跟 QSettings 配合
LANGUAGE_KEY = "ui/language"
DEFAULT_LANGUAGE = "zh"
SUPPORTED = {"zh": "中文", "en": "English"}

_DICT: dict[str, dict[str, str]] = {
    # ── 通用 ────────────────────────────────────────────
    "common.ok": {"zh": "确定", "en": "OK"},
    "common.cancel": {"zh": "取消", "en": "Cancel"},
    "common.save": {"zh": "保存", "en": "Save"},
    "common.close": {"zh": "关闭", "en": "Close"},
    "common.yes": {"zh": "是", "en": "Yes"},
    "common.no": {"zh": "否", "en": "No"},
    "common.warning": {"zh": "警告", "en": "Warning"},
    "common.error": {"zh": "错误", "en": "Error"},
    "common.confirm": {"zh": "确认", "en": "Confirm"},
    "common.apply": {"zh": "应用", "en": "Apply"},
    "common.settings": {"zh": "设置", "en": "Settings"},

    # ── 状态条 ──────────────────────────────────────────
    "status.state": {"zh": "状态", "en": "state"},
    "status.position": {"zh": "位置", "en": "pos"},
    "status.run": {"zh": "进度", "en": "run"},
    "status.camera": {"zh": "相机", "en": "cam"},
    "status.plan": {"zh": "计划", "en": "plan"},
    "status.data": {"zh": "数据", "en": "data"},
    "status.open": {"zh": "打开", "en": "open"},
    "status.change": {"zh": "更改…", "en": "change…"},
    "status.offline": {"zh": "未连接", "en": "offline"},
    "status.online": {"zh": "在线", "en": "online"},
    "status.connecting": {"zh": "连接中", "en": "connecting"},
    "status.already_connected": {"zh": "设备已连接", "en": "devices already connected"},
    "status.disconnect_link": {"zh": "断开", "en": "disconnect"},
    "status.scanning": {"zh": "扫描中", "en": "scanning"},
    "status.saved": {"zh": "已保存", "en": "saved"},
    "status.canceled": {"zh": "已取消", "en": "canceled"},
    "status.error": {"zh": "错误", "en": "error"},
    "status.not_saved": {"zh": "未保存", "en": "not saved"},
    "status.saving": {"zh": "保存中…", "en": "saving…"},
    "status.timeseries_waiting": {
        "zh": "时间序列 · 已完成 {done}/{total} · {wait_s:.0f} s 后开始下一次",
        "en": "time series · {done}/{total} done · next in {wait_s:.0f} s",
    },
    "status.timeseries_progress": {
        "zh": "时间序列 · 第 {idx}/{total} 次",
        "en": "time series · run {idx}/{total}",
    },

    # ── 控制面板 ────────────────────────────────────────
    "panel.devices": {"zh": "设备", "en": "Devices"},
    "panel.stage": {"zh": "位移台", "en": "Stage"},
    "panel.scan_plan": {"zh": "扫描计划", "en": "Scan plan"},
    "panel.metadata": {"zh": "元数据", "en": "Metadata"},
    "panel.meta_sample": {"zh": "样品", "en": "sample"},
    "panel.meta_objective": {"zh": "物镜", "en": "objective"},
    "panel.meta_na": {"zh": "NA", "en": "NA"},
    "panel.meta_lambda": {"zh": "波长 (nm)", "en": "λ (nm)"},
    "panel.meta_note": {"zh": "备注", "en": "note"},
    "panel.repeat": {"zh": "重复", "en": "repeat"},
    "panel.interval_min": {"zh": "间隔 (分)", "en": "interval (min)"},
    "panel.autofocus": {"zh": "自动对焦", "en": "auto focus"},
    "panel.line_profile": {"zh": "画线", "en": "line"},
    "panel.stage_driver": {"zh": "位移台型号", "en": "stage driver"},
    "panel.camera_driver": {"zh": "相机型号", "en": "camera driver"},
    "panel.connect": {"zh": "连接", "en": "connect"},
    "panel.disconnect": {"zh": "断开", "en": "disconnect"},
    "panel.device_state": {"zh": "状态", "en": "state"},
    "panel.target_x": {"zh": "目标 x", "en": "target x"},
    "panel.target_y": {"zh": "目标 y", "en": "target y"},
    "panel.target_z": {"zh": "目标 z", "en": "target z"},
    "panel.move_stage": {"zh": "移动", "en": "move stage"},
    "panel.home": {"zh": "归零", "en": "home"},
    "panel.limits": {"zh": "限位…", "en": "limits…"},
    "panel.z_start": {"zh": "z 起", "en": "z start"},
    "panel.z_stop": {"zh": "z 止", "en": "z stop"},
    "panel.z_step": {"zh": "步长", "en": "step"},
    "panel.dwell": {"zh": "停顿", "en": "dwell"},
    "panel.avg": {"zh": "平均", "en": "avg"},
    "panel.repeat_count": {"zh": "重复次数", "en": "repeat"},
    "panel.repeat_interval_min": {"zh": "间隔 (分钟)", "en": "interval (min)"},
    "panel.include_xy_grid": {"zh": "增加 XY 网格扫描", "en": "include xy grid"},
    "panel.start_scan": {"zh": "开始扫描", "en": "START SCAN"},
    "panel.stop": {"zh": "停止", "en": "stop"},
    "panel.x_start": {"zh": "x 起", "en": "x start"},
    "panel.y_start": {"zh": "y 起", "en": "y start"},
    "panel.x_stop": {"zh": "x 止", "en": "x stop"},
    "panel.x_step": {"zh": "x 步长", "en": "x step"},
    "panel.y_stop": {"zh": "y 止", "en": "y stop"},
    "panel.y_step": {"zh": "y 步长", "en": "y step"},
    "panel.offline": {"zh": "未连接", "en": "offline"},
    "panel.online": {"zh": "在线", "en": "online"},
    "panel.ready_connect": {"zh": "就绪 · 连接设备", "en": "ready · connect devices"},
    "panel.ready_plan": {"zh": "就绪 · 设置扫描计划", "en": "ready · set scan plan"},
    "panel.unit_um": {"zh": "µm", "en": "µm"},
    "panel.unit_ms": {"zh": "ms", "en": "ms"},

    # ── 工作流引导 (顶部四步) ──────────────────────────
    "workflow.step1": {"zh": "① 连接设备", "en": "① CONNECT"},
    "workflow.step2": {"zh": "② 设定计划", "en": "② PLAN"},
    "workflow.step3": {"zh": "③ 开始扫描", "en": "③ SCAN"},
    "workflow.step4": {"zh": "④ 导出结果", "en": "④ EXPORT"},

    # ── 控件 tooltip (鼠标悬停说明; 新手向) ────────────
    "tip.connect": {
        "zh": "建立到位移台与相机的连接 · 顶部 [PI…] 可改连接方式",
        "en": "Connect to stage + camera · [PI…] above lets you change link mode",
    },
    "tip.disconnect": {
        "zh": "断开设备 · 停止采集与轮询",
        "en": "Disconnect devices · stops streaming and polling",
    },
    "tip.pi_settings": {
        "zh": "PI 控制器连接参数 (controller / 接口 / 限位 / 速度)",
        "en": "PI controller connection params (controller / interface / limits / speed)",
    },
    "tip.target_xyz": {
        "zh": "目标坐标 (用户视角 µm) · 点 [移动] 下发",
        "en": "Target position (user-frame µm); click [move] to dispatch",
    },
    "tip.move": {
        "zh": "移动到目标坐标 · 受软限位与大幅移动确认保护",
        "en": "Move to target · guarded by soft limits and large-move confirm",
    },
    "tip.sharpness_trend": {
        "zh": "近 60 帧 Brenner 锐度走势(右侧为最新)",
        "en": "Brenner sharpness over recent 60 frames (newest at right)",
    },
    "tip.home": {
        "zh": "回到用户视角 (0, 0, 0) · 未参考时禁用 (绝对零点不可信)",
        "en": "Go to user origin (0,0,0) · disabled when not referenced",
    },
    "tip.z_start": {
        "zh": "z 起始位置 µm (相对用户零点)",
        "en": "z scan start (µm, user-frame)",
    },
    "tip.z_stop": {
        "zh": "z 结束位置 µm",
        "en": "z scan stop (µm)",
    },
    "tip.z_step": {
        "zh": "z 步长 µm · 建议 ≤ λ/(4·NA²) 满足 Nyquist",
        "en": "z step (µm) · keep ≤ λ/(4·NA²) for Nyquist",
    },
    "tip.x_start": {"zh": "x 起始位置 µm (相对当前 user 帧)", "en": "x scan start (µm, user frame)"},
    "tip.x_stop": {"zh": "x 结束位置 µm (相对当前 user 帧)", "en": "x scan stop (µm, user frame)"},
    "tip.x_step": {"zh": "x 步长 µm", "en": "x step (µm)"},
    "tip.y_start": {"zh": "y 起始位置 µm (相对当前 user 帧)", "en": "y scan start (µm, user frame)"},
    "tip.y_stop": {"zh": "y 结束位置 µm (相对当前 user 帧)", "en": "y scan stop (µm, user frame)"},
    "tip.y_step": {"zh": "y 步长 µm", "en": "y step (µm)"},
    "tip.dwell": {
        "zh": "每个 z 点采样总时长 ms (跨多个平均帧)",
        "en": "Total dwell at each z (ms), spread across avg samples",
    },
    "tip.avg": {
        "zh": "每个 z 点的平均帧数 · 大值降噪但变慢",
        "en": "Frames averaged per z point · higher = less noise, slower",
    },
    "tip.repeat_count": {
        "zh": "时间序列: 同一扫描重复 N 次, 文件名自动加 _t00.._tNN 后缀, 设 1 = 单次。",
        "en": "Time series: repeat the same scan N times, files auto-suffixed _t00.._tNN. 1 = single scan.",
    },
    "tip.repeat_interval": {
        "zh": "相邻两次扫描的开始间隔 (分钟), 0 = 上次保存完立即开始下一次。",
        "en": "Wall-clock interval between consecutive scan starts (minutes). 0 = start next immediately after save.",
    },
    "tip.start_scan": {
        "zh": "开始扫描 · 软限位拦截 + Esc/Space/急停 随时中断",
        "en": "Start scan · soft limits checked first; Esc/Space/E-STOP anytime",
    },
    "tip.stop_scan": {
        "zh": "停止当前扫描 · 已采集帧会保留 + 保存",
        "en": "Stop current scan · collected frames are kept and saved",
    },
    "tip.exposure": {
        "zh": "曝光时间 µs · 值越大越亮越慢, 优先调它再调增益",
        "en": "Exposure (µs) · brighter & slower; adjust this first, then gain",
    },
    "tip.gain": {
        "zh": "模拟增益 dB · 值越大噪声越多; 先把曝光顶到上限再加增益",
        "en": "Analog gain (dB) · higher = noisier; max out exposure first",
    },
    "tip.gamma": {
        "zh": "伽马 (γ) · 仅显示与录像的非线性映射, 不影响 PSF 数据",
        "en": "Gamma (γ) · display / record only, raw PSF stays linear",
    },
    "tip.black_level": {
        "zh": "黑阶 (sensor offset) · 减暗场之前的硬件偏移基线",
        "en": "Black level (sensor offset) · hardware floor before dark-frame",
    },
    "tip.frame_rate": {
        "zh": "目标帧率 fps · 上限由曝光与读出时间决定",
        "en": "Target frame rate (fps) · ceiling limited by exposure + readout",
    },
    "tip.pixel_format": {
        "zh": "相机像素格式 · 8bit 快, 12/16bit 信息更细但带宽高",
        "en": "Pixel format · 8-bit fast, 12/16-bit richer but higher bandwidth",
    },
    "tip.snapshot": {
        "zh": "保存当前画面为 TIFF + 着色 PNG (按当前伪彩)",
        "en": "Save current frame as TIFF + colored PNG (current colormap)",
    },
    "tip.record": {
        "zh": "录像 · 按当前帧率保存到数据目录",
        "en": "Record live video to current data folder",
    },
    "tip.auto_levels": {
        "zh": "仅调整实时画面的显示亮度范围，不改变相机曝光、增益或保存数据",
        "en": "Adjust live display range only; exposure, gain, and saved data are unchanged",
    },
    "tip.auto_exposure": {
        "zh": "按当前画面峰值自动调曝光时间，把峰值压到满量程约 80%",
        "en": "Tune exposure from live peak to about 80% of full scale",
    },
    "tip.hardware_dark": {
        "zh": "盖住镜头后触发相机端暗场/NUC；优先使用硬件校正，避免软件减暗场",
        "en": "With lens capped, trigger camera-side dark/NUC; prefer hardware correction over software subtraction",
    },
    "tip.colormap": {
        "zh": "实时画面伪彩 · 灰阶最忠实, viridis 对比好",
        "en": "Live colormap · gray is faithful, viridis has best contrast",
    },
    "tip.advanced": {
        "zh": "展开高级相机参数 (gamma / black / fps / pixel)",
        "en": "Expand advanced camera params (gamma / black / fps / pixel)",
    },
    "tip.estop": {
        "zh": "急停 · 立刻停位移台 + 取消扫描 (Esc / Space 通用)",
        "en": "E-STOP · halt stage + cancel scan (Esc / Space global)",
    },
    "tip.jog_step": {
        "zh": "Jog 步长 µm · ◀▶ 按一次的相对移动量",
        "en": "Jog step (µm) · how far ◀▶ moves per click",
    },
    "tip.jog_left": {
        "zh": "向负方向 jog 一个步长 (z)",
        "en": "Jog one step toward negative z",
    },
    "tip.jog_right": {
        "zh": "向正方向 jog 一个步长 (z)",
        "en": "Jog one step toward positive z",
    },
    "tip.zero": {
        "zh": "把当前位置定义为用户视角 (0) · 物理不动, 软限位跟随平移",
        "en": "Define current pos as user 0 · stage stays; limits shift",
    },
    "tip.rec_min": {
        "zh": "记下负向边界 (现在的 z 当作软限位下界候选)",
        "en": "Mark current z as lower limit candidate",
    },
    "tip.rec_max": {
        "zh": "记下正向边界 (现在的 z 当作软限位上界候选)",
        "en": "Mark current z as upper limit candidate",
    },
    "tip.apply": {
        "zh": "把记录的 [下限, 上限] 应用为软限位",
        "en": "Apply recorded [low, high] as the soft limits",
    },
    "tip.reset_range": {
        "zh": "以当前位置为 user 0, 行程重设为 ±半径 µm",
        "en": "Re-base: current pos = user 0; total travel = ±radius µm",
    },
    "tip.data_dir_open": {
        "zh": "在文件管理器中打开数据保存目录",
        "en": "Open the data folder in your file manager",
    },
    "tip.data_dir_change": {
        "zh": "更换数据保存目录",
        "en": "Pick a different data folder",
    },
    "tip.settings": {
        "zh": "应用设置 (语言 / 软限位 / 相机 / 数据目录 / 轴反转)",
        "en": "App settings (language / limits / camera / data / axes)",
    },
    "tip.xy_grid": {
        "zh": "勾选后扫描会在每个 z 上再走一遍 xy 网格 (3D 数据集; 慢但完整)",
        "en": "Add an xy raster at each z (3D dataset; slower but complete)",
    },
    "tip.meta_sample": {
        "zh": "样品名 · 写入 meta.json, 扫描后保存",
        "en": "Sample name · written to meta.json after scan",
    },
    "tip.meta_objective": {
        "zh": "物镜型号 (例如 Nikon CFI Plan 100×) · 写入 meta.json",
        "en": "Objective model (e.g. Nikon CFI Plan 100×) · meta.json",
    },
    "tip.meta_na": {
        "zh": "物镜数值孔径 NA · 用于计算 Nyquist 步长 λ/(4·NA²)",
        "en": "Numerical aperture NA · drives Nyquist step λ/(4·NA²)",
    },
    "tip.meta_lambda": {
        "zh": "光源波长 (nm) · 用于计算理论 PSF 与 Nyquist 步长",
        "en": "Wavelength (nm) · used for theoretical PSF & Nyquist step",
    },
    "tip.meta_note": {
        "zh": "自由备注 · 写入 meta.json, 在历史 stack 中可查",
        "en": "Free-form note · written to meta.json with this scan",
    },
    "tip.scan_repeat": {
        "zh": "时间序列: 重复次数 (1 表示单次扫描)",
        "en": "Time-series: repeat count (1 = single scan)",
    },
    "tip.scan_interval": {
        "zh": "时间序列: 每次扫描结束到下一次开始的间隔分钟数",
        "en": "Time-series: minutes between scan finish and next start",
    },
    "tip.autofocus": {
        "zh": "自动对焦: 粗扫 z 后做局部细化，每点多帧平均后用 Brenner 锐度找峰值",
        "en": "Autofocus: coarse z sweep, local refinement, multi-frame averaged Brenner peak",
    },
    "tip.line_profile": {
        "zh": "画线工具: 在画面上拖一条线, 弹窗显示亮度剖面 + FWHM 拟合",
        "en": "Line tool: drag a line on the image to plot intensity + FWHM fit",
    },
    "tip.settings_lang": {
        "zh": "界面语言 (中/英) · 切换后需重启生效",
        "en": "UI language (zh/en) · restart required",
    },
    "tip.ui_scale": {
        "zh": "整体放大界面字体。自动档按屏幕 DPI 推荐;手动档覆盖自动值。改后需重启。",
        "en": "Scale all UI fonts. Auto follows screen DPI; manual overrides it. Restart required.",
    },
    "tip.settings_safety_enable": {
        "zh": "总开关: 取消勾选只关闭 safety/* 软限位；驱动层行程检查仍会生效",
        "en": "Master switch: disables only safety/* soft limits; driver travel checks still apply",
    },
    "tip.settings_axis_min": {
        "zh": "该轴允许的最小用户视角坐标 µm",
        "en": "Lowest allowed user-frame coordinate on this axis (µm)",
    },
    "tip.settings_axis_max": {
        "zh": "该轴允许的最大用户视角坐标 µm",
        "en": "Highest allowed user-frame coordinate on this axis (µm)",
    },
    "tip.settings_large_move": {
        "zh": "单次 z 位移 >= 此值时弹框确认 (兜底防撞)",
        "en": "Confirmation dialog kicks in when single z move >= this",
    },
    "tip.settings_invert": {
        "zh": "勾选则该轴目标值取负发给驱动 (装反方向时用)",
        "en": "Negate target value before dispatch (use for inverted mount)",
    },
    "tip.settings_gamma_enable": {
        "zh": "勾选才允许高级栏的 γ 控件 (默认关, PSF 数据始终线性)",
        "en": "Enable γ control in advanced bar (off by default; raw PSF stays linear)",
    },
    "tip.pixel_calibration_enable": {
        "zh": "启用后扫描保存时会写入 camera 像素到真实长度的换算数据。画线标定需要回到相机画面使用 Line 工具。",
        "en": "When enabled, saved scans include camera pixel-to-length calibration metadata.",
    },
    "tip.pixel_size_um": {
        "zh": "相机传感器单个像素的物理尺寸，单位 µm。",
        "en": "Physical sensor pixel pitch in µm.",
    },
    "tip.objective_magnification": {
        "zh": "物镜放大倍率。实际像素长度 = 像素尺寸 / 物镜放大倍率。",
        "en": "Objective magnification. Real pixel length = pixel pitch / magnification.",
    },
    "tip.settings_data_dir": {
        "zh": "扫描结果、快照、录像和校正文件的保存根目录",
        "en": "Base folder for scans, snapshots, recordings, and calibration files",
    },
    "tip.settings_data_choose": {"zh": "选择新的数据保存目录", "en": "Choose a new data folder"},
    "tip.settings_data_open": {"zh": "用系统文件管理器打开当前数据目录", "en": "Open current data folder"},
    "tip.calibration_dark_enable": {
        "zh": "启用后预览和扫描都会减去暗场背景；相机硬件暗场已开启时，暗场文件会作为残余暗场继续扣除",
        "en": "Subtract dark background in preview and scans; with hardware dark active, a dark file is applied as residual dark",
    },
    "tip.calibration_flat_enable": {
        "zh": "启用后用平场（Flat）修正照明和像素响应不均；扫描仍保留原始帧",
        "en": "Use flat-field correction for illumination/pixel response; raw frames are still saved",
    },
    "tip.calibration_flat_mode": {
        "zh": "普通强度平场允许除法校正；相干或全息平场会被明确拒绝",
        "en": "Intensity flat allows division; coherent/holographic flats are explicitly refused",
    },
    "tip.calibration_path": {"zh": "校正帧 .npz 文件路径", "en": "Path to a calibration .npz file"},
    "tip.calibration_choose": {"zh": "选择已有校正文件", "en": "Choose an existing calibration file"},
    "tip.calibration_capture": {
        "zh": "从当前相机采集 50 帧，取每个像素的中位数生成校正文件",
        "en": "Capture 50 frames from the current camera and median-stack them",
    },
    "tip.settings_pi_open": {
        "zh": "打开 PI 控制器连接参数 (controller / 接口 / 限位 / 速度)",
        "en": "Open PI connection params (controller / interface / limits / speed)",
    },
    "tip.settings_ref": {
        "zh": "执行 PI 物理寻参 · 危险, 会动位移台, 通常不必",
        "en": "Trigger physical PI referencing · dangerous, stage moves, rarely needed",
    },
    "tip.pi_native_dlg": {
        "zh": "调用 PI 官方 InterfaceSetupDlg 选择设备 (需要 pipython[gui])",
        "en": "Open PI's native InterfaceSetupDlg picker (requires pipython[gui])",
    },

    # ── 相机 ────────────────────────────────────────────
    "camera.exposure": {"zh": "曝光时间", "en": "exposure time"},
    "camera.gain": {"zh": "增益", "en": "gain"},
    "camera.colormap": {"zh": "伪彩", "en": "colormap"},
    "camera.advanced": {"zh": "高级", "en": "advanced"},
    "camera.snapshot": {"zh": "抓拍", "en": "snapshot"},
    "camera.record": {"zh": "录像", "en": "record"},
    "camera.recording": {"zh": "● 录像中", "en": "● REC"},
    "camera.gamma": {"zh": "伽马", "en": "gamma"},
    "camera.gamma_enable": {"zh": "启用伽马", "en": "enable gamma"},
    "camera.black_level": {"zh": "黑阶", "en": "black level"},
    "camera.frame_rate": {"zh": "帧率", "en": "frame rate"},
    "camera.pixel_format": {"zh": "像素格式", "en": "pixel format"},
    "camera.peak": {"zh": "峰值", "en": "peak"},
    "camera.saturated": {"zh": "饱和", "en": "SATURATED"},
    "camera.no_signal": {"zh": "无信号 · 连接相机", "en": "NO SIGNAL · connect camera"},
    "camera.no_signal_hint": {
        "zh": "点 [连接] 按钮开始 · 设置 → 位移台 也可配 PI 控制器",
        "en": "click [connect] to start · configure PI in Settings → Stage",
    },
    "camera.waiting_frame": {"zh": "等待画面", "en": "WAITING FOR FRAME"},
    "camera.waiting_frame_hint": {
        "zh": "已连接 · 等待相机推送第一帧",
        "en": "connected · waiting for first frame",
    },
    "camera.image_dims": {"zh": "画幅 {w}×{h}", "en": "image {w}×{h}"},
    "camera.peak_val": {"zh": "峰值 {val}", "en": "peak {val}"},
    "camera.fps_val": {"zh": "{fps:.1f} fps", "en": "{fps:.1f} fps"},

    # ── PSF 视图 ────────────────────────────────────────
    "psf.view_section": {"zh": "视图", "en": "View"},
    "psf.render": {"zh": "渲染", "en": "render"},
    "psf.colormap": {"zh": "伪彩", "en": "colormap"},
    "psf.min": {"zh": "最低", "en": "min"},
    "psf.max": {"zh": "最高", "en": "max"},
    "psf.threshold": {"zh": "阈值", "en": "threshold"},
    "psf.layers": {"zh": "层数", "en": "layers"},
    "psf.detail": {"zh": "精度", "en": "detail"},
    "psf.z_interp": {"zh": "z 倍", "en": "z x"},
    "psf.xy_interp": {"zh": "xy 倍", "en": "xy x"},
    "psf.volume": {"zh": "体渲染", "en": "volume"},
    "psf.alpha": {"zh": "透明度", "en": "alpha"},
    "psf.brightness": {"zh": "光强", "en": "light"},
    "psf.colorbar": {"zh": "色条", "en": "colorbar"},
    "psf.auto_levels": {"zh": "自动范围", "en": "auto levels"},
    "psf.axes": {"zh": "坐标轴", "en": "axes"},
    "psf.z_marker": {"zh": "z 标线", "en": "z marker"},
    "psf.rect_zoom": {"zh": "框选缩放", "en": "rect zoom"},
    "psf.reset_view": {"zh": "重置视角", "en": "reset view"},
    "psf.save_preset": {"zh": "保存…", "en": "save…"},
    "psf.load_preset": {"zh": "载入…", "en": "load…"},
    "psf.export_plot": {"zh": "导出图像…", "en": "export plot…"},
    "psf.empty_state": {"zh": "扫描结果会在这里显示", "en": "scan result loads here"},
    "psf.empty_state_hint": {
        "zh": "完成一次扫描后自动加载 · 也可在数据目录里手动打开 stack.h5",
        "en": "auto-loads after a scan · or open stack.h5 manually from the data folder",
    },
    "psf.fast": {"zh": "快速", "en": "fast"},
    "psf.fine": {"zh": "精细", "en": "fine"},
    "psf.surface": {"zh": "等值面", "en": "surface"},
    "psf.slices": {"zh": "切片", "en": "slices"},
    "psf.x_cut": {"zh": "x 切", "en": "x cut"},
    "psf.y_cut": {"zh": "y 切", "en": "y cut"},
    "psf.z_cut": {"zh": "z 切", "en": "z cut"},
    "psf.plot_error": {"zh": "绘图出错: {exc}", "en": "plot error: {exc}"},

    # ── 位移台视图 ──────────────────────────────────────
    "stage.x": {"zh": "x", "en": "x"},
    "stage.y": {"zh": "y", "en": "y"},
    "stage.z": {"zh": "z", "en": "z"},
    "stage.current_pos": {"zh": "当前位置", "en": "current pos"},
    "stage.trail": {"zh": "近期轨迹", "en": "trail"},
    "stage.sampled": {"zh": "已采", "en": "sampled"},
    "stage.planned": {"zh": "计划", "en": "planned"},
    "stage.soft_limit": {"zh": "软限位", "en": "soft limit"},

    # ── 扫描状态 ────────────────────────────────────────
    "scan.scanning_status": {"zh": "扫描中 · 等待平均帧", "en": "scanning · waiting for averaged frames"},
    "scan.position_format": {"zh": "x {x:+8.3f}   y {y:+8.3f}   z {z:+8.3f}  µm",
                             "en": "x {x:+8.3f}   y {y:+8.3f}   z {z:+8.3f}  µm"},

    # ── 设置对话框 ──────────────────────────────────────
    "settings.title": {"zh": "设置", "en": "Settings"},
    "settings.tab_general": {"zh": "通用", "en": "General"},
    "settings.tab_stage": {"zh": "位移台", "en": "Stage"},
    "settings.tab_camera": {"zh": "相机", "en": "Camera"},
    "settings.tab_calibration": {"zh": "校正", "en": "Calibration"},
    "settings.tab_data": {"zh": "数据", "en": "Data"},
    "settings.language": {"zh": "界面语言", "en": "Language"},
    "settings.language_hint": {"zh": "切换语言需要重启应用生效", "en": "Restart required after switching"},
    "settings.appearance_section": {"zh": "界面外观", "en": "Appearance"},
    "settings.ui_scale": {"zh": "界面缩放", "en": "UI scale"},
    "settings.ui_scale_auto": {"zh": "自动 ({percent}%)", "en": "Auto ({percent}%)"},
    "settings.ui_scale_restart_hint": {
        "zh": "切换 UI 缩放需要重启应用生效。4K 屏建议 150%—175%。",
        "en": "Restart required after changing UI scale. 150%–175% recommended on 4K screens.",
    },
    "settings.theme": {"zh": "界面主题", "en": "Theme"},
    "settings.theme_light": {"zh": "浅色", "en": "Light"},
    "settings.theme_dark": {"zh": "MVS 深色 (默认)", "en": "MVS dark (default)"},
    "settings.theme_restart_hint": {
        "zh": "切换主题需要重启应用生效。MVS 深色会改变相机采集区和界面 chrome；PSF、位移台等分析画布保持浅色以保证 colormap 准确。",
        "en": "Restart required after switching theme. MVS dark changes the camera acquisition surface and UI chrome; PSF and stage analysis canvases stay light to keep colormap fidelity.",
    },
    "tip.settings_theme": {
        "zh": "在 MVS 深色和浅色 UI 之间切换。PSF、位移台等分析画布保持浅色。",
        "en": "Switch between MVS dark and light UI. PSF and stage analysis canvases stay light.",
    },
    "settings.timeseries_section": {"zh": "时间序列扫描", "en": "Time-series scan"},
    "settings.timeseries_repeat": {"zh": "重复次数", "en": "Repeat count"},
    "settings.timeseries_interval": {"zh": "间隔 (分钟)", "en": "Interval (min)"},
    "settings.timeseries_hint": {
        "zh": "重复次数 > 1 时,每完成一轮扫描后,等待间隔再开始下一轮。",
        "en": "If repeat > 1, the scan waits the interval between each run.",
    },
    "settings.safety_section": {"zh": "软限位 (防止撞镜头)", "en": "Soft Limits (anti-collision)"},
    "settings.safety_enable": {"zh": "启用软限位", "en": "Enable soft limits"},
    "settings.safety_disable_warning": {
        "zh": "⚠ 关闭后只是不检查 safety/* 这 6 个应用层软限位；驱动层行程范围仍会检查。请确认你知道在做什么.",
        "en": "⚠ This disables only the six safety/* soft limits; driver travel-range checks still apply. Proceed only if you understand.",
    },
    "settings.z_min": {"zh": "z 最小 (µm)", "en": "z min (µm)"},
    "settings.z_max": {"zh": "z 最大 (µm)", "en": "z max (µm)"},
    "settings.x_min": {"zh": "x 最小 (µm)", "en": "x min (µm)"},
    "settings.x_max": {"zh": "x 最大 (µm)", "en": "x max (µm)"},
    "settings.y_min": {"zh": "y 最小 (µm)", "en": "y min (µm)"},
    "settings.y_max": {"zh": "y 最大 (µm)", "en": "y max (µm)"},
    "settings.large_move_threshold": {"zh": "大幅移动阈值 (µm)", "en": "Large move threshold (µm)"},
    "settings.reference_section": {"zh": "寻参 (危险, 平时不用)", "en": "Reference (dangerous, rarely needed)"},
    "settings.reference_warning": {
        "zh": "寻参会让 stage 物理移动到参考标记位置 (PI 控制器自己执行, 不受软限位保护)。\n"
              "仅在控制器掉电后绝对位置失效, 或绝对零点漂移时使用。\n"
              "确认平台周围无样品架/镜筒/手指后再点。",
        "en": "Referencing moves the stage physically to its ref mark (driven by PI controller, "
              "soft limits don't apply). Only use after controller power-cycle or zero drift. "
              "Check for obstacles first.",
    },
    "settings.reference_button": {"zh": "执行寻参…", "en": "Run reference…"},

    # ── 像素长度标定 ────────────────────────────────────
    "pixel_calibration.section": {"zh": "像素长度标定", "en": "Pixel length calibration"},
    "pixel_calibration.enable": {"zh": "启用像素长度标定", "en": "Enable pixel length calibration"},
    "pixel_calibration.method": {"zh": "标定方式", "en": "Method"},
    "pixel_calibration.method_sensor_objective": {
        "zh": "像素尺寸 / 物镜倍率",
        "en": "Pixel pitch / objective",
    },
    "pixel_calibration.method_line": {"zh": "画线标定", "en": "Line calibration"},
    "pixel_calibration.pixel_size": {"zh": "像素尺寸", "en": "Pixel pitch"},
    "pixel_calibration.objective_mag": {"zh": "物镜倍率", "en": "Objective magnification"},
    "pixel_calibration.status_empty": {
        "zh": "画线步骤: 保存设置并关闭此窗口 → 连接相机 → 在相机工具栏点 Line → 拖动图像上的线段端点 → 在弹窗输入已知长度 → 点“写入像素标定”。",
        "en": "No line calibration saved. Open the camera Line tool, drag the segment, enter known length, then apply.",
    },
    "pixel_calibration.status_off": {
        "zh": "像素长度标定未启用。当前输入: {detail}",
        "en": "Pixel length calibration is disabled. Current input: {detail}",
    },
    "pixel_calibration.status_invalid": {"zh": "像素标定无效: {msg}", "en": "Pixel calibration invalid: {msg}"},
    "pixel_calibration.sensor_value": {
        "zh": "像素尺寸 {pixel:.3f} µm / 物镜 {mag:.1f}× = {um:.6f} µm/px",
        "en": "Pixel pitch {pixel:.3f} µm / objective {mag:.1f}× = {um:.6f} µm/px",
    },
    "pixel_calibration.line_saved": {
        "zh": "已保存画线: {px:.3f} px = {um:.3f} µm, 换算 {scale:.6f} µm/px",
        "en": "Saved line: {px:.3f} px = {um:.3f} µm, scale {scale:.6f} µm/px",
    },
    "pixel_calibration.line_too_short": {
        "zh": "画线太短, 无法用作标定参考 · 请重新拖一条更长的线段。",
        "en": "Line too short to use as a reference · drag a longer segment.",
    },
    "pixel_calibration.no_settings": {
        "zh": "当前会话未就绪, 无法写入标定 · 请关闭对话框后重试。",
        "en": "Session not ready · close this dialog and try again.",
    },
    "pixel_calibration.line_applied": {
        "zh": "画线标定已写入: {px:.3f} px = {um:.3f} µm",
        "en": "Line calibration saved: {px:.3f} px = {um:.3f} µm",
    },
    "pixel_calibration.failed": {"zh": "像素标定失败: {msg}", "en": "Pixel calibration failed: {msg}"},
    "pixel_calibration.meter_off": {"zh": "像素标定未启用", "en": "scale off"},
    "pixel_calibration.meter_invalid": {"zh": "像素标定无效: {msg}", "en": "scale invalid: {msg}"},
    "pixel_calibration.meter_value": {"zh": "像素 {um:.6f} µm/px", "en": "scale {um:.6f} µm/px"},

    # ── Jog 面板 (急停 / 置零 / 相对移动 / 标定) ────────
    "jog.estop": {"zh": "急停  —  Esc / Space", "en": "E-STOP — Esc / Space"},
    "jog.zero": {"zh": "置零", "en": "Zero"},
    "jog.rec_min": {"zh": "记下限", "en": "Rec-"},
    "jog.rec_max": {"zh": "记上限", "en": "Rec+"},
    "jog.apply": {"zh": "应用", "en": "Apply"},
    "jog.reset": {"zh": "重设范围", "en": "Reset"},
    "jog.reference": {"zh": "寻参", "en": "Reference"},
    "jog.pos_range_empty": {"zh": "位置: —    范围: —", "en": "pos: —    range: —"},
    "jog.pos_range_norange": {
        "zh": "位置: {pos:+.2f}  µm    范围: —",
        "en": "pos: {pos:+.2f}  µm    range: —",
    },
    "jog.pos_range_full": {
        "zh": "位置: {pos:+.2f}    范围: [{lo:.1f}, {hi:.1f}] µm",
        "en": "pos: {pos:+.2f}    range: [{lo:.1f}, {hi:.1f}] µm",
    },
    "jog.calib_hint": {
        "zh": "标定: jog 到边缘 → 记下限/记上限 → 应用",
        "en": "calib: jog to edge → Rec-/Rec+ → Apply",
    },
    "jog.calib_status": {
        "zh": "标定: 下={lo}  上={hi}  µm",
        "en": "calib: -={lo}  +={hi}  µm",
    },
    "jog.calib_need_rec": {
        "zh": "标定: 先按 记下限 和 记上限",
        "en": "calib: press Rec- and Rec+ first",
    },
    "jog.calib_applied": {
        "zh": "标定: 已写入 [{lo:.1f}, {hi:.1f}] µm",
        "en": "calib: applied [{lo:.1f}, {hi:.1f}] µm",
    },
    "jog.reset_title": {"zh": "重设范围 — 以当前位置为 0", "en": "Reset Range — current as 0"},
    "jog.reset_prompt": {
        "zh": "新行程半径 (µm) — 总范围将是 ±此值:",
        "en": "New travel radius (µm) — total range will be ±this:",
    },
    "calib.open": {"zh": "标定行程范围…", "en": "Calibrate range…"},
    "calib.title": {"zh": "标定行程范围", "en": "Calibrate Range"},
    "calib.intro": {
        "zh": "用主面板的 ◀ ▶ 把位移台移到下限,点[记下限];移到上限,点[记上限];最后[应用]写入软限位。重设范围会以当前位置为 0 重置行程。",
        "en": "Use ◀ ▶ on the main panel to drive the stage to the lower limit, click Rec-; drive to the upper limit, click Rec+; then Apply to commit. Reset Range zeroes travel around current position.",
    },
    "calib.current_pos": {
        "zh": "当前位置: {z:+.3f} µm",
        "en": "current: {z:+.3f} µm",
    },
    "calib.close": {"zh": "关闭", "en": "Close"},

    # ── PI 连接对话框 ────────────────────────────
    "pi.controller": {"zh": "控制器", "en": "controller"},
    "pi.stage_model": {"zh": "位移台型号", "en": "stage model"},
    "pi.refmode": {"zh": "寻参方式", "en": "ref mode"},
    "pi.referencing": {"zh": "寻参策略", "en": "referencing"},
    "pi.interface": {"zh": "接口", "en": "interface"},
    "pi.travel_min": {"zh": "行程下限", "en": "travel min"},
    "pi.travel_max": {"zh": "行程上限", "en": "travel max"},
    "pi.velocity_default": {"zh": "默认速度", "en": "velocity (default)"},
    "pi.velocity_max": {"zh": "速度上限", "en": "velocity max"},
    "pi.step_min": {"zh": "最小步长", "en": "step min"},
    "pi.poll_rate": {"zh": "轮询频率", "en": "poll rate"},
    "pi.position_tol": {"zh": "位置容差", "en": "position tol"},
    "pi.serial": {"zh": "序列号", "en": "serial #"},
    "pi.serial_hint": {"zh": "留空则枚举选第一个", "en": "empty = enumerate, pick first"},
    "pi.ip": {"zh": "IP", "en": "ip"},
    "pi.ip_hint": {"zh": "192.168.0.x", "en": "192.168.0.x"},
    "pi.port": {"zh": "端口", "en": "port"},
    "pi.com": {"zh": "COM", "en": "COM"},
    "pi.baud": {"zh": "波特率", "en": "baud"},
    "pi.device_id": {"zh": "设备号", "en": "device id"},
    "pi.scan": {"zh": "扫描", "en": "Scan"},
    "pi.scan_com": {"zh": "扫描 COM", "en": "Scan COM"},
    "pi.scan_chain": {"zh": "扫描菊花链", "en": "Scan Chain"},
    "pi.usb_devices_title": {"zh": "USB 设备", "en": "USB devices"},
    "pi.choose_serial": {"zh": "选择序列号:", "en": "Choose serial:"},
    "pi.com_ports_title": {"zh": "COM 端口", "en": "COM ports"},
    "pi.choose_label": {"zh": "选择:", "en": "Choose:"},
    "pi.chain_title": {"zh": "菊花链", "en": "Daisy chain"},
    "pi.chain_devices": {"zh": "设备 (含设备号):", "en": "Device (with id):"},
    "pi.scan_no_usb": {
        "zh": "(扫描无结果, 检查 pipython / USB 连接)",
        "en": "(no result, check pipython / USB)",
    },
    "pi.scan_no_com": {"zh": "(未发现; 检查 pyserial)", "en": "(none; check pyserial)"},
    "pi.scan_no_chain": {"zh": "(扫描无结果)", "en": "(no result)"},
    "pi.ref_hint_skip": {
        "zh": "不寻参 (推荐): 用连接时位置为基准, 软限位全程防撞",
        "en": "skip (recommended): use connect-time pos as ref; soft limits guard",
    },
    "pi.ref_hint_auto": {
        "zh": "智能: qFRF 检测, 已对零则跳过, 未对零才寻参",
        "en": "auto: qFRF check, skip if referenced else FRF",
    },
    "pi.ref_hint_force": {
        "zh": "强制 FRF: 总是机械寻参 (最多半行程 ~150 mm 移动)",
        "en": "force FRF: always reference (~150 mm motion)",
    },
    "pi.info_text": {
        "zh": "防撞: skip=不机械, auto/force=可能 FRF ±150mm; TravelGuard 越界拒绝下发\n"
              "下方所有参数可调; [扫描] 按钮自动列出 COM / USB / 菊花链 设备",
        "en": "Anti-collision: skip=no motion, auto/force=may FRF ±150mm; out-of-range rejected\n"
              "All params below adjustable; [Scan] auto-lists COM / USB / chain devices",
    },
    "settings.pi_section": {"zh": "PI 控制器连接", "en": "PI Controller"},
    "settings.pi_open": {"zh": "PI 连接参数…", "en": "PI connection…"},
    "settings.data_dir": {"zh": "数据保存目录", "en": "Data folder"},
    "settings.data_dir_choose": {"zh": "选择…", "en": "Choose…"},
    "settings.data_dir_open": {"zh": "打开", "en": "Open"},
    "calibration.dark_enable": {"zh": "启用暗场（Dark）校正", "en": "Enable dark correction"},
    "calibration.flat_enable": {"zh": "启用平场（Flat）校正", "en": "Enable flat correction"},
    "calibration.dark_path": {"zh": "暗场文件", "en": "Dark file"},
    "calibration.flat_path": {"zh": "平场文件", "en": "Flat file"},
    "calibration.flat_mode": {"zh": "平场类型", "en": "Flat mode"},
    "calibration.mode_intensity": {"zh": "普通强度平场", "en": "Intensity flat"},
    "calibration.mode_coherent": {"zh": "相干/全息平场（拒绝除法）", "en": "Coherent flat (refuse division)"},
    "calibration.choose": {"zh": "选择…", "en": "Choose…"},
    "calibration.capture_dark": {"zh": "采集暗场…", "en": "Capture dark…"},
    "calibration.capture_flat": {"zh": "采集平场…", "en": "Capture flat…"},
    "calibration.dark_prompt": {
        "zh": "请盖住镜头或关闭光源。确认后将采集 50 帧并取中位数生成暗场文件。",
        "en": "Cover the lens or turn off illumination. 50 frames will be captured and median-stacked.",
    },
    "calibration.dark_lens_cap_prompt": {
        "zh": "请先盖上镜头或关闭光源。系统会按 [相机触发→相机出厂校准→软件拍照] 三层尝试,自动选第一个能用的。确认开始?",
        "en": "Cover the lens or turn off illumination. System will try [camera trigger → camera factory baked → software capture] in order. Continue?",
    },
    "calibration.dark_trigger_ok": {
        "zh": "相机已记录暗场 (节点: {node})。后续帧在相机内部减基线,不需要保存文件。",
        "en": "Camera recorded dark internally (node: {node}). On-chip correction; no file needed.",
    },
    "calibration.dark_enable_ok": {
        "zh": "相机使用出厂烧录的暗场 (节点: {node})。已就绪,不需要采集文件。",
        "en": "Camera uses factory-baked dark (node: {node}). Ready; no capture needed.",
    },
    "calibration.dark_status_off": {"zh": "暗场: 未启用", "en": "dark: off"},
    "calibration.dark_status_trigger": {
        "zh": "暗场来源: 相机内部 (触发型 · {node})",
        "en": "dark source: on-camera (trigger · {node})",
    },
    "calibration.dark_status_enable": {
        "zh": "暗场来源: 相机内部 (出厂校准 · {node})",
        "en": "dark source: on-camera (factory · {node})",
    },
    "calibration.dark_status_hardware_residual": {
        "zh": "暗场来源: 相机内部 ({node}) + 软件残余 (文件: {file})",
        "en": "dark source: on-camera ({node}) + software residual (file: {file})",
    },
    "calibration.dark_status_software": {
        "zh": "暗场来源: 软件减法 (文件: {file})",
        "en": "dark source: software (file: {file})",
    },
    "calibration.dark_calibrate_button": {"zh": "校准暗场…", "en": "Calibrate dark…"},
    "calibration.flat_prompt": {
        "zh": "请切到均匀照明并移除样品结构。确认后将采集 50 帧并取中位数生成平场文件。",
        "en": "Use uniform illumination and remove sample structure. 50 frames will be captured and median-stacked.",
    },
    "calibration.no_camera": {"zh": "请先连接相机后再采集校正帧。", "en": "Connect a camera before capturing calibration frames."},
    "calibration.saved": {"zh": "校正文件已保存: {path}", "en": "Calibration file saved: {path}"},
    "calibration.failed": {"zh": "校正失败: {msg}", "en": "Calibration failed: {msg}"},
    "calibration.status_off": {"zh": "校正未启用", "en": "calibration off"},
    "calibration.status_dark": {"zh": "暗场校正已启用", "en": "dark correction on"},
    "calibration.status_dark_flat": {"zh": "暗场+平场校正已启用", "en": "dark+flat correction on"},
    "calibration.hint": {
        "zh": "启用后预览显示校正图；扫描会保存原始帧，并额外保存校正帧。曝光、增益、像素格式不匹配时会拒绝使用。",
        "en": "Preview shows corrected frames. Scans save raw plus corrected data. Mismatched exposure/gain/pixel format is refused.",
    },
    "settings.applied": {"zh": "设置已保存", "en": "Settings saved"},
    "settings.axes_section": {"zh": "轴方向 (反转)", "en": "Axis direction (invert)"},
    "settings.invert_x": {"zh": "反转 X", "en": "Invert X"},
    "settings.invert_y": {"zh": "反转 Y", "en": "Invert Y"},
    "settings.invert_z": {"zh": "反转 Z", "en": "Invert Z"},
    "settings.axes_hint": {
        "zh": "勾选则该轴目标值取负发给位移台 (用于安装方向与软件约定相反的情形).",
        "en": "Checked → target value sent to stage is negated (use when stage mount direction disagrees with software convention).",
    },

    # ── 错误 / 安全 ────────────────────────────────────
    "safety.move_refused": {
        "zh": "移动被软限位拒绝 · 硬件 {axis}={value:.2f} µm 超出允许范围 [{lo:.2f}, {hi:.2f}]。可在设置中放宽限位, 或把目标收回范围内。",
        "en": "Move refused by soft limit · hw {axis}={value:.2f} µm is outside [{lo:.2f}, {hi:.2f}]. Widen the limit in Settings, or pull the target back into range.",
    },
    "safety.scan_refused": {
        "zh": "扫描路径越过软限位 · 硬件 {axis} 上有点 {value:.2f} µm 超出 [{lo:.2f}, {hi:.2f}]。请收小扫描范围, 或在设置里放宽限位。",
        "en": "Scan path violates soft limit · hw {axis} contains {value:.2f} µm outside [{lo:.2f}, {hi:.2f}]. Tighten the scan range, or raise the limit in Settings.",
    },
    "safety.range_refused": {
        "zh": "目标超出位移台行程 · 硬件 z={value:.2f} µm 超出 [{lo:.2f}, {hi:.2f}] µm。请先标定行程, 或收小目标。",
        "en": "Target outside stage travel · hw z={value:.2f} µm outside [{lo:.2f}, {hi:.2f}] µm. Calibrate travel, or shrink the target first.",
    },
    "safety.start_illegal_limits": {
        "zh": "移动被拒绝 · 当前硬件 {axis}={value:.2f} µm 已落在软限位 [{lo:.2f}, {hi:.2f}] 之外。请确认位移台实际位置, 或在设置中放宽软限位后再试。",
        "en": "Move refused · current hw {axis}={value:.2f} µm is already outside soft limit [{lo:.2f}, {hi:.2f}]. Verify the stage position, or widen the limit in Settings.",
    },
    "safety.start_illegal_range": {
        "zh": "移动被拒绝 · 当前硬件 z={value:.2f} µm 已落在位移台行程 [{lo:.2f}, {hi:.2f}] µm 之外。请先标定行程, 或手动把位移台移回范围内。",
        "en": "Move refused · current hw z={value:.2f} µm is already outside stage travel range [{lo:.2f}, {hi:.2f}] µm. Calibrate the travel range, or manually move the stage back into range.",
    },
    "safety.hw_frame_hint": {
        "zh": "以下数值使用硬件坐标 (controller 原始读数), 不随归零 / 重设范围变化。当前位移台位置超出此范围时, 所有移动操作均被拒绝。",
        "en": "Values are in hardware (controller raw) coordinates and do not shift with zero/reset-range. Moves are refused while the stage sits outside this range.",
    },
    "exit.title": {"zh": "退出 PSF Scan", "en": "Exit PSF Scan"},
    "exit.busy_prefix": {"zh": "退出前请处理:", "en": "Before exit:"},
    "exit.confirm": {"zh": "确定退出?", "en": "Confirm exit?"},
    "exit.scanning": {"zh": "扫描进行中", "en": "scan in progress"},
    "exit.recording": {"zh": "录像进行中", "en": "recording in progress"},
    "exit.connected": {"zh": "设备已连接", "en": "devices still connected"},

    # ── Autofocus (C.6) ────────────────────────────────
    "panel.auto_focus": {"zh": "自动对焦", "en": "auto focus"},
    "tip.auto_focus": {
        "zh": "沿 z 轴粗扫，随后在峰值附近做局部细化；每点会多帧平均后再算 Brenner。搜索范围取最大半径、软限位、行程范围三者最严。",
        "en": "Coarse z sweep plus local peak refinement. Each point is averaged across frames before Brenner scoring. Range is constrained by max radius, soft limits, and travel.",
    },
    "settings.autofocus_section": {"zh": "自动对焦", "en": "Autofocus"},
    "settings.autofocus_enable": {"zh": "启用自动对焦按钮", "en": "Enable autofocus button"},
    "settings.autofocus_max": {"zh": "最大搜索半径 (µm)", "en": "Max search radius (µm)"},
    "settings.autofocus_step": {"zh": "粗扫步长 (µm)", "en": "Coarse step (µm)"},
    "settings.autofocus_dwell": {"zh": "每点停顿 (ms)", "en": "Dwell per point (ms)"},
    "settings.autofocus_samples": {"zh": "每点取帧数", "en": "Frames per point"},
    "tip.settings_autofocus_enable": {
        "zh": "关闭后主界面的自动对焦按钮会置灰，用于实机调试期临时屏蔽。",
        "en": "Disable → autofocus button stays gray. Use during hardware bring-up to block the feature.",
    },
    "tip.settings_autofocus_max": {
        "zh": "单次搜索 z 最远位移. 实际范围 = 此值 ∩ 软限位 ∩ 位移台行程, 取最小. 实机建议 ≤ 2 mm.",
        "en": "Max one-shot z travel. Effective = min(this, soft-limit, travel-range). For real hardware keep ≤ 2 mm.",
    },
    "tip.settings_autofocus_step": {
        "zh": "粗扫每点的 z 步长。峰值附近会追加细化采样；细化间距不小于 PI 连接参数里的最小步长。",
        "en": "z step per coarse sweep point. Refinement spacing is never below the PI step-min setting.",
    },
    "tip.settings_autofocus_dwell": {
        "zh": "移动到每个 z 点后等待多久再取帧。光弱或机械稳定慢时可以适当加长。",
        "en": "Wait time after each z move before grabbing a frame. Increase it for dim samples or slow settling.",
    },
    "tip.settings_autofocus_samples": {
        "zh": "每个 z 点连续采集多少帧并取平均后再算 Brenner。光弱时增大可降低噪声，但会变慢。",
        "en": "Frames captured and averaged at each z before Brenner scoring. Increase for dim samples; autofocus will be slower.",
    },

    "autofocus.title": {"zh": "自动对焦 · 粗扫+细化", "en": "Autofocus · sweep + refine"},
    "autofocus.range_label": {
        "zh": "z 范围 [{lo:.1f}, {hi:.1f}] µm · {n} 点",
        "en": "z range [{lo:.1f}, {hi:.1f}] µm · {n} points",
    },
    "autofocus.z_label": {"zh": "z (user 帧, µm)", "en": "z (user frame, µm)"},
    "autofocus.score_label": {"zh": "Brenner 锐度", "en": "Brenner sharpness"},
    "autofocus.status_running": {"zh": "扫描中 {done}/{total}", "en": "scanning {done}/{total}"},
    "autofocus.status_done": {
        "zh": "✓ 完成 · 峰 @ z={z:.2f} µm · score={score:.1f}",
        "en": "✓ done · peak @ z={z:.2f} µm · score={score:.1f}",
    },
    "autofocus.status_low_light": {
        "zh": "完成, 但亮度不足 · 峰 @ z={z:.2f} µm · score={score:.1f}",
        "en": "done, but low light · peak @ z={z:.2f} µm · score={score:.1f}",
    },
    "autofocus.status_saturated": {
        "zh": "完成, 但画面饱和 · 峰 @ z={z:.2f} µm · score={score:.1f}",
        "en": "done, but saturated · peak @ z={z:.2f} µm · score={score:.1f}",
    },
    "autofocus.refused_disabled": {
        "zh": "自动对焦在设置中已禁用。请打开设置 → 自动对焦 → 勾选启用后再使用。",
        "en": "Autofocus is disabled in Settings. Open Settings → Autofocus → enable to use this feature.",
    },
    "autofocus.refused_too_narrow": {
        "zh": "可搜索 z 范围太窄: 当前位置距软限位/行程边界不足 {step:.1f} µm × 2。请先手动将位移台移到样品附近, 再使用自动对焦。",
        "en": "Effective z range too narrow: distance to soft-limit / travel edge < {step:.1f} µm × 2. Move the stage closer to the sample manually before running autofocus.",
    },
    "autofocus.starting": {
        "zh": "自动对焦开始 · 当前 z={z0:.2f} → 搜索 [{lo:.2f}, {hi:.2f}] µm · 步长 {step:.1f} · {n} 点",
        "en": "autofocus start · z={z0:.2f} → search [{lo:.2f}, {hi:.2f}] µm · step {step:.1f} · {n} pts",
    },
    "autofocus.done": {
        "zh": "自动对焦完成 · 峰 @ z={z:.2f} µm · 位移台已停在最锐点",
        "en": "autofocus done · peak @ z={z:.2f} µm · stage settled at peak",
    },
    "autofocus.low_light_warning": {
        "zh": "自动对焦完成, 但画面亮度不足 · 锐度曲线可能主要受噪声影响。请增加照明或曝光后重新对焦。",
        "en": "Autofocus finished, but the image is too dim. The sharpness curve may be noise-dominated. Increase illumination or exposure and refocus.",
    },
    "autofocus.low_light_status": {
        "zh": "自动对焦亮度不足 · 请增加照明或曝光后复测",
        "en": "Autofocus low light · increase illumination or exposure and retry",
    },
    "autofocus.saturated_warning": {
        "zh": "自动对焦完成, 但画面接近满量程或出现饱和像素 · 锐度曲线可能被截顶影响。请降低曝光、增益或光源强度后重新对焦。",
        "en": "Autofocus finished, but the image is near full scale or saturated. The sharpness curve may be clipped. Reduce exposure, gain, or illumination and refocus.",
    },
    "autofocus.saturated_status": {
        "zh": "自动对焦画面饱和 · 请降低曝光、增益或光源强度后复测",
        "en": "Autofocus saturated · reduce exposure, gain, or illumination and retry",
    },
    "autofocus.canceled": {"zh": "自动对焦已取消 · 位移台停在中断时的位置", "en": "autofocus canceled · stage stopped at the interrupt point"},

    # ── 启动恢复 (C.4) ─────────────────────────────────
    "recovery.title": {"zh": "发现未完成的扫描", "en": "Unfinished scans detected"},
    "recovery.found": {
        "zh": "数据目录里有 {n} 个文件夹包含 stack.h5 但没有 meta.json, 可能是上次崩溃或强制退出留下的:",
        "en": "Found {n} folder(s) with stack.h5 but no meta.json, likely from a previous crash or forced exit:",
    },
    "recovery.hint": {
        "zh": "这些 stack.h5 仍然可以用 h5py / Matlab 直接打开看已经采集的帧. 若不需要可手动删目录.",
        "en": "These stack.h5 files can still be opened with h5py / Matlab to inspect captured frames. Delete the folder manually if unused.",
    },

    # ── Line profile 工具 (C.3) ────────────────────────
    "line_profile.title": {"zh": "Line profile · 强度沿线 + FWHM 拟合", "en": "Line profile · intensity along line + FWHM fit"},
    "line_profile.x_label": {"zh": "位置", "en": "position"},
    "line_profile.y_label": {"zh": "强度", "en": "intensity"},
    "line_profile.fit": {"zh": "高斯拟合", "en": "Gauss fit"},
    "line_profile.export_csv": {"zh": "导出 CSV", "en": "Export CSV"},
    "line_profile.known_length": {"zh": "已知长度", "en": "known length"},
    "line_profile.set_pixel_calibration": {"zh": "写入像素标定", "en": "Set pixel calibration"},
    "line_profile.fwhm_placeholder": {"zh": "在图像上拖动两端点", "en": "drag the line endpoints on the image"},
    "line_profile.fwhm_no_fit": {"zh": "拟合关闭或失败 — 仅显示原始曲线", "en": "fit disabled or failed — raw curve only"},
    "line_profile.fwhm_value": {
        "zh": "FWHM = {fwhm:.3f} {unit} · 中心 {center:.3f} · R² {r2:.3f}",
        "en": "FWHM = {fwhm:.3f} {unit} · center {center:.3f} · R² {r2:.3f}",
    },
    "camera.auto_exposure": {"zh": "自动曝光", "en": "Auto Exp"},
    "camera.auto_levels": {"zh": "显示范围", "en": "Levels"},
    "camera.hardware_dark": {"zh": "硬件暗场", "en": "HW Dark"},
    "camera.auto_exposure_running": {"zh": "自动曝光中 · 等待画面稳定", "en": "auto exposure · waiting for frames"},
    "camera.auto_exposure_done": {"zh": "自动曝光完成 · {exposure} µs", "en": "auto exposure done · {exposure} µs"},
    "camera.auto_exposure_failed": {"zh": "自动曝光失败: {msg}", "en": "auto exposure failed: {msg}"},
    "camera.auto_exposure_scanning": {"zh": "扫描中不调整曝光。", "en": "Exposure is locked while scanning."},
    "camera.hardware_dark_prompt": {
        "zh": "请盖住镜头或挡光后继续。相机会尝试执行硬件暗场/NUC，并启用无软件暗场文件的暗场校正。",
        "en": "Cap or block the lens first. The camera will try hardware dark/NUC and enable dark correction without a software dark file.",
    },
    "camera.hardware_dark_active": {"zh": "硬件暗场已启用 · {node}", "en": "hardware dark active · {node}"},
    "camera.hardware_dark_failed": {"zh": "硬件暗场失败: {msg}", "en": "hardware dark failed: {msg}"},
    "camera.hardware_dark_unavailable": {"zh": "当前相机不支持硬件暗场命令。", "en": "This camera does not expose a hardware dark command."},
    "camera.line_profile_tool": {"zh": "Line", "en": "Line"},
    "tip.line_profile_tool": {
        "zh": "打开 line profile 工具: 图像上画一条线测沿线强度 + 高斯 FWHM。再次点击关闭。",
        "en": "Toggle line profile tool: draw a line on the image to measure intensity + Gaussian FWHM. Click again to close.",
    },

    # ── PHASE 相位重建 ─────────────────────────────────
    "phase.title": {"zh": "相位重建", "en": "Phase reconstruction"},
    "phase.empty": {"zh": "PHASE · 导入干涉图或取当前相机帧", "en": "PHASE · load an interferogram or use current camera frame"},
    "phase.view": {"zh": "视图", "en": "view"},
    "phase.load_sample": {"zh": "导入样品图", "en": "Load sample"},
    "phase.load_reference": {"zh": "导入参考图", "en": "Load reference"},
    "phase.live_sample": {"zh": "当前帧 → 样品", "en": "Live → sample"},
    "phase.live_reference": {"zh": "当前帧 → 参考", "en": "Live → reference"},
    "phase.reference_correction": {"zh": "参考矫正", "en": "reference correction"},
    "phase.auto_sideband": {"zh": "自动旁瓣", "en": "auto sideband"},
    "phase.unwrap": {"zh": "导出展开", "en": "unwrap export"},
    "phase.sideband_x": {"zh": "旁瓣 x", "en": "sideband x"},
    "phase.sideband_y": {"zh": "旁瓣 y", "en": "sideband y"},
    "phase.radius": {"zh": "半径", "en": "radius"},
    "phase.ref_sigma": {"zh": "参考平滑 σ", "en": "ref σ"},
    "phase.ref_sigma_tip": {
        "zh": "对参考相位做复数域高斯平滑的 σ (px)。0 = 关闭。建议从 2~4 起,过大会把系统像差(同心环)也磨平,反而抬高残差。",
        "en": "Complex-domain Gaussian σ (px) applied to the reference phase before subtraction. 0 disables it. Start around 2–4; too large erases the slow system aberration you want to keep.",
    },
    "phase.process": {"zh": "处理", "en": "Process"},
    "about.menu": {"zh": "关于(&A)", "en": "&About"},
    "about.help_menu": {"zh": "帮助(&H)", "en": "&Help"},
    "menu.tools": {"zh": "工具(&T)", "en": "&Tools"},
    "menu.settings": {"zh": "设置...(&S)", "en": "&Settings..."},
    "menu.open_data_dir": {"zh": "打开数据目录(&D)", "en": "Open &Data Folder"},
    "about.title": {"zh": "关于 PSF Scan", "en": "About PSF Scan"},
    "about.version": {"zh": "版本: {v}", "en": "Version: {v}"},
    "about.description": {
        "zh": "PSF 采集与离轴干涉相位重建工作台 (PI 位移台 + 海康 MVS 相机)。",
        "en": "PSF acquisition and off-axis interferometric phase workbench (PI stage + Hikvision MVS).",
    },
    "about.dependencies": {
        "zh": "构建于 PySide6 / NumPy / SciPy / h5py / tifffile / pipython / pyserial 等开源组件。",
        "en": "Built on PySide6, NumPy, SciPy, h5py, tifffile, pipython, pyserial and other open-source components.",
    },
    "about.support_fallback": {
        "zh": "如需技术支持, 请联系系统维护人员。",
        "en": "For technical support, please contact your system administrator.",
    },
    "phase.save_result": {"zh": "保存结果", "en": "Save result"},
    "phase.status_empty": {"zh": "phase ─", "en": "phase ─"},
    "phase.sample_empty": {"zh": "样品 ─", "en": "sample ─"},
    "phase.reference_empty": {"zh": "参考 ─", "en": "reference ─"},
    "phase.sample": {"zh": "样品", "en": "sample"},
    "phase.reference": {"zh": "参考", "en": "reference"},
    "phase.open_title": {"zh": "选择干涉图", "en": "Choose interferogram"},
    "phase.source_live": {"zh": "当前相机帧", "en": "live camera frame"},
    "phase.no_live_provider": {"zh": "当前窗口没有绑定 live camera。", "en": "No live camera provider is bound."},
    "phase.no_live_frame": {"zh": "当前没有可用相机帧。请先连接相机并等待画面。", "en": "No live frame available. Connect camera and wait for an image."},
    "phase.need_sample": {"zh": "请先导入样品干涉图或取当前帧作为样品。", "en": "Load a sample interferogram first."},
    "phase.need_reference": {"zh": "已启用参考矫正，请先导入无样品参考图。", "en": "Reference correction is enabled. Load a reference interferogram first."},
    "phase.process_failed": {"zh": "相位处理失败 · {msg}", "en": "Phase processing failed · {msg}"},
    "phase.save_failed": {"zh": "相位结果保存失败 · {msg}", "en": "Failed to save phase result · {msg}"},
    "phase.nothing_to_save": {
        "zh": "还没有可保存的相位结果 · 先点击处理生成相位图。",
        "en": "No phase result to save · click Process first to generate one.",
    },
    "phase.saved": {"zh": "已保存 · {name}", "en": "saved · {name}"},
    "phase.status_result": {
        "zh": "旁瓣 x={x:.1f} y={y:.1f} r={r:.1f}",
        "en": "sideband x={x:.1f} y={y:.1f} r={r:.1f}",
    },
    "phase.interferogram_title": {"zh": "干涉图", "en": "interferogram"},
    "phase.fft_title": {
        "zh": "FFT 幅度 · 点击可手动选旁瓣",
        "en": "FFT magnitude · click to set sideband",
    },
    "phase.phase_title": {"zh": "Wrapped phase [-π, π]", "en": "Wrapped phase [-π, π]"},
    "phase.corrected_title": {"zh": "参考矫正相位 [-π, π]", "en": "Reference-corrected phase [-π, π]"},
    "phase.fft_empty": {"zh": "先点击处理生成 FFT 预览", "en": "Process first to generate FFT preview"},
    "phase.phase_empty": {"zh": "先点击处理生成相位图", "en": "Process first to generate phase"},

    # ── PSF 视图控件 tooltip ────────────────────────────
    "tip.psf_threshold": {
        "zh": "等值面阈值 (相对全局最大归一化亮度 0-1) · 越大保留体素越少, 突出最亮的 PSF 主体",
        "en": "Isosurface threshold (normalized 0-1) · higher = fewer voxels kept, only the brightest PSF body",
    },
    "tip.psf_layers": {
        "zh": "体积渲染叠加的等值面层数 · 越多越精细但更慢",
        "en": "Number of stacked isosurface layers · more = finer detail, slower",
    },
    "tip.psf_fine_z": {
        "zh": "z 方向插值倍数 · 让 PSF 看起来更连续, 不会改变原始数据",
        "en": "z interpolation factor · cosmetic smoothing only, raw data unchanged",
    },
    "tip.psf_fine_xy": {
        "zh": "xy 方向插值倍数 · 让 PSF 看起来更连续, 不会改变原始数据",
        "en": "xy interpolation factor · cosmetic smoothing only, raw data unchanged",
    },
    "tip.psf_alpha": {
        "zh": "等值面 / 切片不透明度 (0.05-1.0)",
        "en": "Isosurface / slice opacity (0.05-1.0)",
    },
    "tip.psf_brightness": {
        "zh": "体积渲染亮度倍率 · 拖动滑块快速调节",
        "en": "Volume render brightness multiplier · drag the slider to tweak",
    },
    "tip.psf_level_min": {
        "zh": "色图最低映射值 · 关闭 auto 后手动控制",
        "en": "Lower colormap level · only used when auto is off",
    },
    "tip.psf_level_max": {
        "zh": "色图最高映射值 · 关闭 auto 后手动控制",
        "en": "Upper colormap level · only used when auto is off",
    },
    "tip.psf_detail": {
        "zh": "渲染精度 · fast 跳过插值适合快速浏览, fine 启用插值倍率",
        "en": "Render detail · fast skips interpolation for quick browse, fine applies interp factors",
    },
    "tip.psf_volume_style": {
        "zh": "体积渲染样式 · surface 显示等值面, slices 显示薄层",
        "en": "Volume render style · surface = isosurfaces, slices = thin sections",
    },
    "tip.psf_auto_levels": {
        "zh": "勾选后色图最低/最高用整体 PSF 1-99 分位自动设定",
        "en": "When checked, colormap min/max auto-pick from PSF 1-99 percentile",
    },
    "tip.psf_colorbar": {"zh": "切换色条显示", "en": "Toggle colorbar"},
    "tip.psf_axes": {"zh": "切换坐标轴标注", "en": "Toggle axis labels"},
    "tip.psf_z_marker": {"zh": "切换当前 z 切片标记", "en": "Toggle current-z marker overlay"},
    "tip.psf_rect_zoom": {"zh": "切换框选缩放: 在图像上拖一个矩形放大该区域", "en": "Rectangle-zoom: drag a box on the image to zoom"},
    "tip.psf_reset_view": {"zh": "复位视图缩放和旋转角度", "en": "Reset view zoom and rotation"},
    "tip.psf_save_preset": {
        "zh": "把当前 PSF 视图参数 (色图/阈值/层数/插值/角度) 保存为预设",
        "en": "Save current PSF view parameters (cmap/threshold/layers/interp/angle) as a preset",
    },
    "tip.psf_load_preset": {"zh": "载入此前保存的 PSF 视图参数预设", "en": "Load a previously saved PSF view preset"},
    "tip.psf_export_plot": {
        "zh": "导出当前 PSF 视图为 PNG (适合放到论文 / 报告里)",
        "en": "Export the current PSF view as a PNG (paper/report-ready)",
    },
}


def set_language(code: str) -> None:
    global _lang
    if code in SUPPORTED:
        _lang = code
        for cb in _listeners:
            cb(code)


def get_language() -> str:
    return _lang


def add_listener(cb: Callable[[str], None]) -> None:
    if cb not in _listeners:
        _listeners.append(cb)


def tr(key: str, **fmt) -> str:
    entry = _DICT.get(key)
    if entry is None:
        return key.format(**fmt) if fmt else key
    text = entry.get(_lang) or entry.get("en") or key
    return text.format(**fmt) if fmt else text

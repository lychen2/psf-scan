# PSF Scan — 待办与后续优化

> 更新时间：2026-05-13
> 阅读前先 `git status` 确认未提交改动是否还在工作树。

---

## 0. 现状速览（只列 **未完** 的）

| 模块 | 进度 | 备注 |
|---|---|---|
| PI 驱动 + Jog 面板 + `.mat` 保存 + 退出顺序 | ✅ | |
| 软限位 dataclass + 设置 UI + `_on_move` / `_on_scan_start` 接入 | ✅ 基础接入 | **语义需重构** ← 见 §A.1 |
| i18n 字典 (含 `settings.large_move_threshold`) | ✅ | |
| Gamma 使能开关接入 camera_view | ✅ | |
| stage_view 软限位红线 | ✅ | |
| 数据 dir / 状态栏齿轮 / 状态文本 i18n | ✅ | |
| 元数据栏 (sample / 物镜 / NA / λ / note) | ✅ | C.1 已完成 |
| 实时锐度数 (Brenner) | ✅ | C.2 已完成 |
| save_scan 后台线程 (`_SaveWorker`) | ✅ | |

---

## A. 必修小坑

### A.1 软限位语义重构 ⚠️ 高优先(已确认要做)

> **核心原则**：**如果不太对劲就不要移动。**
> 任何"看起来怪"的状态(当前位置越限、坐标系不一致、range 读不到、driver 异常等)都按拒绝移动处理；让用户先手动检查再决定下一步，宁可烦一下用户也别让 stage 撞东西。

**问题**：当前 `_on_move` / `_on_scan_start` 已经在调 `SafetyLimits.check_point` / `check_path`，但数值是在 **user 帧** 解读的。`set_zero` / `reset_range` 会让 user 坐标平移，导致限位语义跟着漂移。

**新需求**(用户 2026-05-13 提出)：
1. **限位改为硬件帧** — `SafetyLimits` 的 6 个数值固定为 controller raw 坐标，不随 `set_zero` / `reset_range` 改变。设置 UI 也要明确这一点。
2. **当前位置不合法 → 拒绝任何移动** — 即使目标在限位内也拒。同时适用于:
   - SafetyLimits 软限位
   - stage 物理 travel range (`travel_limits_um` / `hw_travel_um`)

**改动**：
- `core/stage.py`：`StageBase` 加 `user_to_hw(x, y, z) -> (hx, hy, hz)`，默认 `return (x, y, z)`
- `drivers/stage_mock.py` / `drivers/stage_pi.py`：override `user_to_hw`，复用现有 offset + invert_z 反向变换
- `app.py` `_on_move` / `_on_jog` / `_on_scan_start`：
  ```
  hw_now = stage.raw_position
  if limits.check_point(*hw_now) or out_of_range(hw_now): refuse
  hw_target = stage.user_to_hw(x, y, z)
  if limits.check_point(*hw_target) or out_of_range(hw_target): refuse
  ```
- `ui/settings_dialog.py`：safety 分组顶部加一行小字"以硬件坐标设置(不随归零/重设范围变化)"
- `core/i18n.py`：补 `safety.start_illegal_*` / `safety.hw_frame_hint`

### A.2 PIConnectDialog 漏接 `InterfaceSetupDlg`(可选)

**用户问过**：`pidevice.InterfaceSetupDlg()` 会弹 PI 官方的图形选择窗。在 PIConnectDialog 顶部加 `[ PI 官方选择… ]` 按钮可让新手一键挑接口。

注意：`InterfaceSetupDlg` 是阻塞调用，要先 `pip install pipython[gui]`(Tk 依赖)。纯 PySide6 路线不做也行。

---

## B. UX / 清晰度

### B.1 SpinSlider 未全覆盖
- `_stage()` 里的 `target x/y/z` 还是普通 `_dspin`，没换成 SpinSlider
- PSF render 控件(threshold、layers、fine_z、alpha)可加 SpinSlider

### B.2 系统化 tooltip
当前控件 tooltip 已有少量(`tip.meta_objective` 等)，但远未覆盖。建议每控件用 i18n key + `.tooltip` 后缀批量补：
- `panel.connect.tooltip` = "建立到位移台与相机的连接"
- `panel.z_step.tooltip` = "Z 步长 µm。建议 ≤ λ/(4·NA²) 以满足 Nyquist"
- `camera.exposure.tooltip` = "曝光时间 µs。值越大，越亮但越慢"
- `camera.gain.tooltip` = "增益 dB。值越大噪声越多，先调曝光，曝光到顶再调增益"

按区域批量加，30 分钟左右。

### B.3 工作流引导更明显
`WorkflowGuide` 只是三个数字。建议改成：
```
①连接设备 → ②选扫描范围 → ③开始扫描 → ④结果导出
```
当前阶段高亮，下一步用浅箭头指引。

### B.4 空状态文案
- LIVE IMAGE "无信号 · 连接相机" → 加一行 "点左下角 [连接] 按钮"
- PSF STACK "扫描结果会在这里显示" → 加一行 "或点右下 [载入…] 打开历史 stack"

### B.5 相机 advanced 拆分
当前 advanced bar 把 gamma / black level / framerate / pixel format 全堆在一行。建议展开后分两行：曝光相关 / 图像相关。

---

## C. 科研功能(剩 5 项)

### C.3 Line profile 工具 (~1 天)
- camera_view & psf_view 加 "draw line" 工具按钮
- pyqtgraph LineROI；弹出小窗口画沿线 intensity + 拟合 FWHM
- 导出 CSV
- 新增 `ui/line_profile_dialog.py` + `core/profile.py` (FWHM 拟合)

### C.4 崩溃安全流式写盘 (~1 天)
- `Scanner.run` 接收 `out_h5_path`，**每采一帧立即 append HDF5** (`maxshape` + `resize` + `flush`)
- 内存只留最后一帧
- `data_io.save_scan` → 改名 `finalize_scan`，只补 meta/tif/mat/csv
- 启动时检测未完成 stack.h5(meta.json 缺失即视为未完成) → 弹"恢复未完成扫描"对话框
- **最大改动**，放最后做

### C.5 时间序列扫描 (~半天)
- ControlPanel 扫描计划加 "repeat N 次 · 每隔 X 分钟"
- 文件名自动 `_t00.._tNN`
- 每次完整流程：移到起点 → 扫描 → 保存 → 等间隔 → 下一次
- app 层 orchestrate，不动 Scanner

### C.6 自动对焦扫描 (基础完成，持续调参)
- 新按钮“自动对焦”：粗扫 z (默认 step 5µm) → 每点多帧平均 → Brenner 评分 → 峰值附近三点抛物线细化 → 停到最高分位置
- 细化采样间距不小于 `pi/step_min_um`，避免要求位移台执行小于最小有效移动距离的动作
- 亮度不足时提示用户增加照明或曝光，避免把噪声主导的锐度曲线当作可信焦点
- **安全约束**：
  - 单次搜索 z 总位移上限可配置(默认 ±2mm，UserSettings 提供)
  - 同时受 SafetyLimits.z_min/z_max 软限位约束
  - 同时受 stage range (PIStage.range / mock range) 物理约束
  - 三者取交集；用户配置 > 实际可移动范围时提示先手动靠近再搜
- 已新增 `core/autofocus.py` + `ui/autofocus_dialog.py`

### C.7 Dark/Flat 校正 (基础完成，待实机验收)

目标：给普通强度成像提供可复现的暗场 / 平场校正；默认不对相干干涉、全息、结构光等会把相位/干涉条纹写进 flat 的场景做除法校正。

#### C.7.1 术语与算法
- Dark frame（暗场）：遮光后采集的相机背景，包含偏置、暗电流、固定图案噪声。
- Flat frame（平场）：均匀照明下采集的响应图，描述像素响应不均、照明不均、轻微暗角。
- 标准强度校正：
  ```
  corrected = (raw - dark) / max(flat - dark, eps) * mean(flat - dark)
  ```
- `eps` 必须显式配置或使用命名常量，避免 flat 里接近 0 的像素把噪声放大。
- 输出 dtype 建议先用 float32 保存中间结果；导出 TIFF/MAT 时再按需要裁剪或转换。

#### C.7.2 采集向导
- 设置新增“校正”标签页：
  - 暗场文件路径、平场文件路径；
  - 启用暗场、启用平场两个开关；
  - 采集暗场、采集平场、验证校正三个按钮。
- Dark 采集：
  - 弹窗提示盖住镜头或关闭光源；
  - 自动采集 50 帧；
  - 对每个像素取中位数，保存为 dark frame。
- Flat 采集：
  - 弹窗提示切换到均匀照明、移除样品结构；
  - 自动采集 50 帧；
  - 对每个像素取中位数；
  - 保存前检查 `flat - dark` 的最小值、均值、坏点比例。
- 验证校正：
  - 显示 raw / corrected 的均值、标准差、最小最大值；
  - 如果 flat 过暗、饱和、坏点过多，直接报错，不静默降级。

#### C.7.3 文件与元数据
- 新增 `core/calibration.py`：
  - `CalibrationFrame`：保存数组、类型、采集时间、相机型号、曝光、增益、像素格式、shape、dtype、SHA256；
  - `CalibrationConfig`：保存启用状态、路径、校正模式；
  - `apply_calibration(raw, config)`：只做显式启用的校正，失败直接抛错。
- 校正文件建议使用 HDF5 或 NPZ，不用裸 TIFF 存元数据。
- `meta.json` 写入：
  - 暗场 / 平场是否启用；
  - 暗场 / 平场文件路径；
  - 暗场 / 平场 SHA256；
  - 采集时曝光、增益、像素格式；
  - 校正公式版本。

#### C.7.4 安全与拒绝条件
- 曝光、增益、像素格式、图像尺寸与当前相机不一致时拒绝使用校正文件。
- flat 中 `flat - dark <= eps` 的像素比例超过阈值时拒绝。
- flat 中饱和像素比例超过阈值时拒绝。
- `flat_coherent` 类型默认拒绝做除法校正，只允许用户显式切换为普通强度 flat。
- 校正失败必须让扫描失败或弹明确错误，不返回未校正数据伪装成功。

#### C.7.5 接入点
- 实时预览：只用于显示，可单独开关；不要改变原始采集帧。
- 扫描保存：默认保存 raw，同时可保存 corrected；HDF5 中建议新增 `/frames_corrected`，不要覆盖 `/frames`。
- TIFF/MAT/CSV：导出时明确标注 raw 或 corrected。
- UI 状态条显示当前校正状态：未启用 / dark / dark+flat / 校正文件不匹配。

#### C.7.6 测试
- mock 相机生成带固定暗电平和乘性渐晕的测试帧，验证 dark/flat 后均匀性提高。
- dark 尺寸不匹配、flat 过暗、flat 饱和、SHA256 改变、像素格式改变都要有失败测试。
- 保存后重新读取校正文件，校验数组、元数据和 SHA256 一致。

---

## D. 小手脚清单(可选打磨)

| 文件 | 行 | 内容 |
|---|---|---|
| `app.py:_on_done` | — | save_scan 已走 `_SaveWorker` 后台线程 ✅ |
| `data_io.save_scan` | — | `oned_as="column"` 把 timestamps 写成列向量，Matlab 用着可能反直觉 |
| `stage_pi._poll` | 195 | poll 30Hz 在 USB 上一次 ~3ms，CPU 5%；要省电可换成 stage.is_moving 时才高频 |

---

## E. 测试 / 实机部署 checklist

### E.1 mock 路径
- [x] mock stage + mock camera 全流程跑通
- [x] mock 焦点位置随机 — 自动对焦功能可用真值校验
- [ ] **mock 模拟 PI driver 报错**(断电、超限位)→ 验证 `_show_error` 和 `_on_emergency_stop` 路径

### E.2 PI 实机
1. PIMikroMove 里独立测：USB 能枚举、`FRF` 能跑、qPOS 实时刷新
2. PIConnectDialog `[Scan]` 应该列出设备
3. 第一次接：勾 referencing=skip，确认 stage 不动
4. **小心**：切到 referencing=auto/force 前先解除样品架，确保前后空 ±150mm
5. 标定 `Rec-` / `Rec+` 至少跑一次，把软限位写到实际可移动范围

### E.3 Windows installer 验收
- [ ] Program Files 下安装后启动，保存能落到 Documents
- [ ] 关窗口测试：扫描中、录像中、空闲 — 三种弹窗都对
- [ ] 中文系统下 i18n 默认中文，菜单/弹窗都没乱码

---

## F. 文档

| 文件 | 状态 |
|---|---|
| README.md | ✅ 已建 |
| DEVELOPER.md | ✅ 已建 |
| USER_GUIDE.md | ⚠️ 已更新部分，PI 章节 + safety 章节仍需补 |

---

## 建议下一步

按顺序：
1. **A.1 软限位重构**(hw 帧 + 起始位置非法拒绝；上面已详述)
2. **C.5 时间序列**(改动最小)
3. **C.3 Line profile**
4. **C.6 自动对焦**
5. **C.4 流式写盘**(最后做，改动最大)
6. C.7 校正(可选，最大开销)

# PSF Scan 使用文档

PSF Scan 是一个用于显微/光学实验台的 PSF 采集 GUI。它把位移台移动、相机取帧、Z/XY 扫描、PSF 堆栈查看和结果保存放在同一个界面里。

当前仓库支持：

- 位移台驱动：`mock`
- 相机驱动：`mock`、`mvs`
- 启动方式：`python -m psf_scan` 或安装后的 `psf-scan`
- 输出格式：HDF5、TIFF、CSV、JSON

## Windows 用户：直接装

如果你只想使用、不打算从源码开发，从分发渠道拿到 `PsfScan-Setup-X.Y.Z.exe` 后双击安装即可。安装包会同时静默安装 MVS 相机运行时（连接海康相机必需）。

技术支持联系方式以分发渠道（你拿到 `.exe` 的地方）公布的信息为准。

如果你是开发者或要从源码构建，继续往下看。

## 1. 环境准备

### Python 环境

需要 Python 3.10 或更高版本。

在项目根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows PowerShell 对应激活命令：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

安装依赖来自 `pyproject.toml`，主要包括 `PySide6`、`pyqtgraph`、`PyOpenGL`、`numpy`、`h5py`、`tifffile` 和 `scipy`。

### MVS 相机运行时

只有选择 `mvs` 相机驱动时才需要海康 MVS Runtime。程序会自动尝试查找这些位置：

- 环境变量 `MVCAM_COMMON_RUNENV`
- Linux: `/opt/MVS/lib`
- Linux: `~/MVS/lib`
- Windows: `C:\Program Files (x86)\MVS\Development\Libraries`

仓库中已经包含 Python SDK 绑定文件：`src/psf_scan/vendor/MvImport/`。但真实相机仍需要系统已安装 MVS Runtime 和相机驱动。

## 2. 启动程序

开发环境中推荐：

```bash
python -m psf_scan
```

如果已通过 `pip install -e .` 安装，也可以使用：

```bash
psf-scan
```

启动后主界面包含：

- `LIVE IMAGE`：实时相机图像、曝光、增益、伪彩色和高级相机参数。
- `PSF STACK`：扫描过程和扫描完成后的 PSF 堆栈视图。
- 右侧 Stage 视图：显示扫描路径、当前位置和已完成点。
- 底部控制面板：设备连接、手动移动、扫描计划和运行状态。

## 3. 快速模拟扫描

没有真实硬件时，可以用 `mock` 模式验证完整流程。

1. 在 `1 Devices` 中选择：
   - `stage driver`: `mock`
   - `camera driver`: `mock`
2. 点击 `connect`。
3. 确认 `LIVE IMAGE` 出现模拟 PSF 图像。
4. 在 `2 Stage` 中输入目标 `x/y/z`，点击 `move stage` 可手动移动。
5. 在 `3 Scan plan` 中设置 Z 扫描范围：
   - `z start`: 起始 Z，单位 um
   - `stop`: 结束 Z，单位 um
   - `step`: Z 步长，单位 um
   - `dwell`: 每个点的采样时间窗口，单位 ms
   - `avg`: 每个点平均的帧数
6. 点击 `START SCAN`。
7. 扫描完成后，界面自动切换到 `PSF STACK`，结果自动保存到 `psf_data/`。

## 4. 使用 MVS 相机

连接真实海康相机前先确认：

- MVS Runtime 已安装。
- 相机已被系统识别。
- 没有其它程序独占相机。
- USB3/GigE 连接稳定。

操作步骤：

1. 在 `1 Devices` 中选择：
   - `stage driver`: 当前仅支持 `mock`
   - `camera driver`: `mvs`
2. 点击 `connect`。
3. 程序会枚举 GigE 和 USB3 MVS 设备，并默认打开第一个设备。
4. 连接成功后，`LIVE IMAGE` 会显示实时图像。
5. 根据图像峰值调整曝光和增益。

如果连接或取帧失败，先运行诊断脚本：

```bash
python diagnose_mvs.py
```

诊断脚本会打印设备枚举、打开设备、设置采集模式、设置曝光和连续取 5 帧的 SDK 返回码。

## 5. 相机视图

`LIVE IMAGE` 顶部可调：

- `exposure time`：曝光时间，单位 us。
- `gain`：相机增益。
- `colormap`：实时图像显示色图，包含 `gray`、`viridis`、`magma` 等。
- `advanced`：展开高级参数。

高级参数按相机能力启用：

- `gamma`
- `black`
- `fps`
- `pixel`

底部状态显示：

- 图像尺寸。
- 当前峰值 `peak`。
- 实时帧率。
- 峰值接近满量程时显示 `SATURATED`。

## 6. 位移台操作

`2 Stage` 区域用于手动移动：

- `target x/y/z`：目标位置，单位 um。
- `move stage`：移动到目标位置。
- `home`：回到 `(0, 0, 0)`。

当前位置会显示在顶部状态条、底部状态栏和右侧 Stage 视图中。

当前真实位移台驱动尚未接入，界面中的可选位移台只有 `mock`。

## 7. 扫描计划

基础扫描是 Z 轴扫描。路径点生成规则：

- Z 是内层循环。
- 如果开启 XY 网格，X 是中层循环，Y 是外层循环。
- XY 网格默认使用蛇形路径，减少回程移动。

参数说明：

- `z start`：Z 起点，单位 um。
- `stop`：Z 终点，单位 um。
- `step`：Z 步长，单位 um。
- `dwell`：每个扫描点的采样时间窗口，单位 ms。
- `avg`：每个扫描点平均的帧数。
- `include xy grid`：开启 XY 网格扫描。
- `x/y start`、`stop`、`step`：XY 网格范围和步长，单位 um。

控制面板会实时显示计划摘要：

- 点数 `pts`
- 实际抓取帧数 `frames`
- 估算采样时长

注意：估算时长只包含 `dwell`，不包含位移台移动、稳定等待和保存文件耗时。

## 8. 扫描过程

点击 `START SCAN` 后：

1. 程序生成完整路径。
2. Stage 视图显示计划路径。
3. 扫描线程逐点移动位移台。
4. 到位后等待短暂稳定时间。
5. 丢弃移动期间排队的旧帧。
6. 在 `dwell` 时间内取 `avg` 帧并做平均。
7. 更新实时图像、进度条、Stage 已完成点和 PSF 堆栈。

点击 `stop` 会取消扫描。取消后如果已经采集到帧，程序会保存已采集部分；如果没有任何帧，会报告未采集到任何帧。

## 9. PSF 堆栈查看

扫描完成后会自动切换到 `PSF STACK`。

可选渲染模式：

- `ORTHO`：显示 XY、XZ、YZ 三个正交切面。
- `MIP`：显示 XY、XZ、YZ 三个方向的最大强度投影。
- `VOLUME`：显示体数据视图。

通用显示控制：

- `colormap`：选择色图。
- `colorbar`：显示或隐藏色条。
- `auto levels`：自动使用当前数据最小/最大值。
- `min/max`：关闭 `auto levels` 后手动设置显示范围。
- `axes`：显示或隐藏坐标轴。
- `z marker`：在切片视图中显示当前切片定位线。
- `rect zoom`：使用矩形框缩放。
- `reset view`：重置视图范围。

体数据显示控制：

- `threshold`：体数据显示阈值。
- `layers`：等值面层数。
- `detail`: `fast` 或 `fine`。
- `volume`: `surface` 或 `volume render`。
- `alpha`：体数据透明度。
- `x/y/z cut`：裁切体数据，便于观察内部结构。

底部信息行会显示当前切片编号、峰值和对应的 `x/y/z` 位置。

## 10. 数据保存

每次扫描完成后自动保存到：

```text
psf_data/psf_YYYYMMDD_HHMMSS/
```

目录内包含：

- `stack.h5`：主数据文件，包含 `frames`、`positions`、`timestamps` 和扫描参数属性。
- `stack.tif`：多页 TIFF，方便 ImageJ/Fiji 等软件打开。
- `positions.csv`：每个扫描点的位置表，列为 `x_um,y_um,z_um`。
- `meta.json`：人类可读元信息，包括参数、开始/结束时间、帧数、图像尺寸和数据类型。

HDF5 数据结构：

```text
frames      (N, H, W) 或 (N, H, W, C)
positions   (N, 3)
timestamps  (N,)
attrs:
  params
  started_at
  finished_at
```

## 11. 用户设置

程序会通过 Qt `QSettings` 持久化部分 UI 参数，包括：

- 设备下拉框选择。
- 扫描参数。
- 是否开启 XY 网格。
- 相机色图。
- 曝光和增益。
- PSF 视图模式、色图、显示范围和体数据显示参数。

这些设置会在下次启动时自动恢复。

## 12. 常见问题

### 启动时报 `ModuleNotFoundError`

确认已经在项目根目录安装：

```bash
python -m pip install -e .
```

### Qt 或 OpenGL 相关报错

确认 `PySide6`、`pyqtgraph`、`PyOpenGL` 已安装。体数据视图依赖 OpenGL；如果只需要检查数据，可先使用 `ORTHO` 或 `MIP` 模式。

### MVS 相机连接失败

运行：

```bash
python diagnose_mvs.py
```

检查输出中的 `EnumDevices`、`OpenDevice`、`StartGrabbing` 和每一帧 `GetOneFrameTimeout` 返回码。

### 图像显示 `SATURATED`

说明峰值接近满量程。降低曝光时间或增益后重新观察。

### 扫描路径为空

检查起点、终点和步长。步长不能为 0，且范围不要设置成无法生成点的组合。

### 保存失败

检查当前工作目录是否有写入权限。默认输出目录是项目根目录下的 `psf_data/`。

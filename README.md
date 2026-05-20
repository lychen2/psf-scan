# PSF Scan（中文 README）

PSF Scan 是一个用于显微/光学实验台的采集软件：把位移台控制、相机取帧、扫描计划、PSF 堆栈查看和数据导出放在同一界面。

## 1. 功能概览

- 实时相机预览（曝光、增益、色图、高级参数）
- Z 扫描与可选 XY 网格扫描（蛇形路径）
- 扫描进度与 Stage 路径可视化
- PSF 堆栈查看（ORTHO / MIP / VOLUME）
- 自动保存 `HDF5 + TIFF + MAT + CSV + JSON`
- 安全机制：软限位、单次大幅移动确认、急停

## 2. 当前支持的驱动

- 位移台：`mock`、`pi-m531`（PI 单轴）
- 相机：`mock`、`mvs`（海康 MVS）

## 3. 直接使用（Windows）

如果你拿到的是安装包 `PsfScan-Setup-X.Y.Z.exe`，双击安装后直接运行即可。

说明：安装包可包含 MVS 运行时，是否包含以你拿到的分发版本为准。

## 4. 源码运行（开发/调试）

### 4.1 环境准备

要求 Python 3.10+。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 4.2 启动

```bash
python -m psf_scan
```

或：

```bash
psf-scan
```

## 5. PI 防撞快速指引（第一次连机必看）

1. 先在 `Settings -> Stage` 设置软限位（`x/y/z min/max`）并保持 `Safety enabled` 打开。
2. 第一次连接 PI 时默认 `referencing=skip`，连接不做机械寻参。
3. 确认机械空间安全后，再在 Settings 里手动点击寻参按钮。
4. 任何时候可用 `Esc / Space / 急停` 中断运动或寻参。

## 6. 数据保存位置

默认保存目录不是仓库内 `psf_data/`，而是系统文档目录下：

- Windows: `Documents/PSF Scan`
- Linux/macOS: `~/Documents/PSF Scan`（取决于 Qt `DocumentsLocation`）

可在设置或状态栏齿轮里修改。

## 7. 文档入口

- 用户手册：[`USER_GUIDE.md`](./USER_GUIDE.md)
- 开发接手文档：[`DEVELOPER.md`](./DEVELOPER.md)
- 待办与优化列表：[`docs/TODO.md`](./docs/TODO.md)

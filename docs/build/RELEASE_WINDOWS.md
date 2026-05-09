# PSF Scan Windows 发版操作手册（SOP）

> 每次发版照着跑一遍。设计依据见 `docs/plans/2026-05-09-windows-installer-design.md`。

适用产物：
- `release/PsfScan-Setup-X.Y.Z.exe`（安装器）
- `release/PsfScan-X.Y.Z-portable.zip`（解压即用）

目标系统：Windows 10 1809+ x64 / Windows 11 x64

---

## 0. 选哪条路

| | 路径 | 何时用 | 是否带 MVS SDK 静默装 |
|---|---|---|---|
| **A** | 手动在 Windows 构建机跑 `installer\build.ps1` | 给海康相机用户准备的"全包" | ✅（前提：`installer/vendored/MVS_SDK_*.exe` 就位） |
| **B** | 推 git tag → GitHub Actions 自动出包 | 日常发版、给非相机用户、内部测试 | ❌（CI 拿不到 SDK；用户需自行装） |

两条路产物名字一样，但**A 的 .exe 包含 SDK 静默装条目**、**B 的 .exe 没有**。
版本号相同时区分一下下载源即可。

### B 路径：CI 自动化使用方法

1. 把 `installer/version.json` 的 `version` 改成新版本号（例如 `1.0.1`）
2. `git commit -am "release: 1.0.1"`
3. `git tag v1.0.1 && git push origin master v1.0.1`
4. 在 GitHub 仓库 **Actions** 页等 ~10 分钟，构建完成后 release 页会自动出现 `PsfScan-Setup-1.0.1.exe` 与 `PsfScan-1.0.1-portable.zip`
5. 验证（在干净 VM 上按 §B.5 跑一遍）

也可以 **手动触发**：Actions → "Build Windows installer" → Run workflow，无需打 tag，artifact 在 workflow run 页下载（30 天保留）。

A 路径继续看下面。

---

## A. 一次性环境准备（构建机）

> 第一次在某台机器上发版才需要做。完成后可重复用。

### A.1 操作系统与硬件

- Windows 10/11 x64（实体机或 VM 都可）
- 至少 20 GB 空闲磁盘
- 至少 8 GB 内存
- 联网（用于装依赖；之后构建可离线）

### A.2 装 Python 3.11 x64

1. 从 <https://www.python.org/downloads/windows/> 下载 **Python 3.11.x x64 installer**。
2. 安装时 **勾选 "Add python.exe to PATH"**。
3. 验证：

   ```powershell
   py -3.11 --version
   # 应输出: Python 3.11.x
   ```

> 不要用 Python 3.12+：PySide6 与某些科学库的 wheel 兼容性可能落后；3.11 是当前稳态。

### A.3 装 Inno Setup 6

1. 下载 <https://jrsoftware.org/isdl.php>，安装时勾选 **Inno Setup Preprocessor (ISPP)**。
2. 验证：

   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /?
   ```

3. 把 `C:\Program Files (x86)\Inno Setup 6\` 加到 PATH（或 build.ps1 里直接写绝对路径）。

### A.4 装 Git 与克隆仓库

```powershell
git clone <仓库地址> psf_scan
cd psf_scan
```

### A.5 创建构建 venv

```powershell
py -3.11 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r installer\requirements-build.txt
pip install -e .
```

`requirements-build.txt` 包含运行依赖 + `pyinstaller>=6.5`。

---

## B. 每次发版步骤

> 估计耗时：5–10 分钟构建 + 10 分钟 VM 验证。

### B.1 同步版本号

改 `installer/version.json`：

```json
{ "version": "1.0.1", "build": "2026-05-15" }
```

然后跑：

```powershell
python installer\bump_version.py
```

它会把版本号同步到：

- `pyproject.toml` `[project] version`
- `src/psf_scan/_version.py` `__version__`
- `installer/PsfScan.iss` 的 `MyAppVersion` 宏（通过 `#define`）
- PyInstaller spec 用的 `version_info.txt`

提交：

```powershell
git add -A
git commit -m "release: bump to 1.0.1"
git tag v1.0.1
```

### B.2 准备 MVS SDK 二进制

把 MVS SDK 安装器复制到 `installer/vendored/`：

```powershell
mkdir -Force installer\vendored
copy MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe `
     installer\vendored\
```

> `installer/vendored/` 在 `.gitignore` 中，不入库。
> 升级 SDK 版本时换文件名，并同步更新 `PsfScan.iss` 的 `[Files]` / `[Run]` 段引用。

### B.3 一键构建

```powershell
.\installer\build.ps1
```

构建脚本依次跑：

1. `pyinstaller --noconfirm --clean installer\psf_scan.spec`
2. `ISCC.exe installer\PsfScan.iss`

成功输出：

```
[OK] PyInstaller 完成: build\dist\PsfScan\PsfScan.exe (1480 文件 / 247 MB)
[OK] Inno 编译完成: release\PsfScan-Setup-1.0.1.exe (298 MB)
```

### B.4 自验（构建机本地）

```powershell
.\release\PsfScan-Setup-1.0.1.exe
```

走完安装向导，桌面/开始菜单确认有 "PSF Scan" 快捷方式，启动 GUI 后跑一次 `mock` 扫描。

### B.5 干净 VM 验证（必做）

> 自验 ≠ VM 验证。构建机已有 Python、依赖、可能装过旧版 MVS，本地装"看起来通"不代表干净环境装得通。

准备一台 **干净 Windows 10/11 x64 VM**（可用 VirtualBox / Hyper-V / VMware 快照）：

| 检查项 | 通过条件 |
|---|---|
| 装 | 双击安装器，全程无报错，看到"安装完成" |
| MVS SDK | 装完后 `C:\Program Files (x86)\MVS\` 出现 |
| 启动 | 双击桌面快捷方式，5 秒内 GUI 显示 |
| mock 扫描 | 用 mock+mock 跑一次 Z 扫描，psf_data/ 有输出 |
| mvs 扫描 | （有相机时）切 mvs 驱动，能枚举设备并取帧 |
| 卸载 | 控制面板能找到 "PSF Scan" → 卸载 → `C:\Program Files\PsfScan\` 消失 |
| 升级 | 旧版本之上装新版本，能正常覆盖、设置保留 |

任一项失败，**不发布**。回到 B.3 调整。

### B.6 发布

```powershell
git push origin master
git push origin v1.0.1
```

把 `release/PsfScan-Setup-1.0.1.exe` 上传到内部分发渠道（共享盘 / 网盘 / 内网下载页）。

附带发布说明（可手写或抓 git log）：

```
PSF Scan 1.0.1 (2026-05-15)
- 修复：XY 网格扫描时进度条卡顿
- 改进：MVS 相机重连后曝光值恢复

下载：\\share\releases\PsfScan-Setup-1.0.1.exe
SHA256: <build.ps1 输出>
```

---

## C. 常见问题与排错

### C.1 构建期

**Q: PyInstaller 报 `Hidden import not found`**
A: 在 `installer/psf_scan.spec` 的 `hiddenimports` 列表里加上对应模块名。常见漏掉：`scipy.special._cdflib`、`OpenGL.platform.win32`、`pyqtgraph.opengl.shaders`。

**Q: 构建出来的 exe 启动闪退、没任何提示**
A: 临时把 spec 里 `console=False` 改成 `console=True`，重打包，从 cmd 跑能看到错误。修完改回 False。

**Q: ISCC.exe 报 `File not found: ..\build\dist\PsfScan\*`**
A: PyInstaller 步骤未成功。先单独跑 `pyinstaller installer\psf_scan.spec` 看错误。

**Q: 安装包大于 400 MB**
A: 检查 spec 是否带入了不必要的依赖（如 PyQt5 与 PySide6 共存、tkinter）；打开 `excludes`。

### C.2 装机期

**Q: 安装时报 "MVS SDK 静默安装失败"**
A: 查看 `%TEMP%\MVS*.log`。常见原因：旧版 MVS 已装、需先卸载；或杀软拦截。可让用户先手动卸旧版再重装。

**Q: 装完启动后 mvs 驱动找不到设备**
A: 通常是 USB3 / GigE 物理连接 / 防火墙；先在 MVS 自带的 `MVS Viewer` 里能不能看到设备，再查我们这一侧。

**Q: SmartScreen 弹"未识别的应用"**
A: 未签名的预期行为，v1.0 不解决。临时绕：右键 → 属性 → "解除锁定"。v1.1 加代码签名后消失。

### C.3 运行期

**Q: 用户报告"启动后立即崩溃"**
A: 让用户把 `%LOCALAPPDATA%\PsfScan\logs\YYYY-MM-DD.log` 发回来。日志含完整 traceback。

**Q: 双击 exe 几秒内毫无反应**
A: 检查任务管理器是否有 `PsfScan.exe` 进程；若有进程但无窗口，多半是 Qt 平台插件加载失败 → 检查目录里 `PySide6\plugins\platforms\qwindows.dll` 是否存在。

---

## D. 版本号变更点速查表

每次发版**只改 `installer/version.json` 一处**，其它由 `bump_version.py` 同步。理论上不该手改。

如果 `bump_version.py` 失效（被改坏 / 还没写），手改这几个文件保持一致：

| 文件 | 字段 | 示例 |
|---|---|---|
| `installer/version.json` | `version` | `"1.0.1"` |
| `pyproject.toml` | `[project] version` | `version = "1.0.1"` |
| `src/psf_scan/_version.py` | `__version__` | `__version__ = "1.0.1"` |
| `installer/PsfScan.iss` | `#define MyAppVersion` | `#define MyAppVersion "1.0.1"` |

---

## E. 回滚

如果某版本发布后发现严重问题：

1. 把上一版安装器（`PsfScan-Setup-X.Y.Z-1.exe`）重新放回分发渠道首位。
2. 用户直接装它即可——Inno Setup 同 `AppId` GUID 会作为"覆盖安装"处理，**不需要先卸载**。
3. 在内部记一笔 `release-incidents.md`，写清现象、影响范围、根因、修复版本号。

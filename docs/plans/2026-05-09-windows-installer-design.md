---
date: 2026-05-09
status: approved
project: psf_scan
audience: 维护者 / 后续发版者
---

# Windows 安装包设计（PSF Scan v1.0）

把 PSF Scan（Python + PySide6 桌面 GUI）打包成单文件 Windows 安装器，并在装机过程中静默安装海康 MVS SDK 运行时。

---

## 1. 目标 / 非目标

**v1.0 必做：**

- 交付**单一文件** `PsfScan-Setup-X.Y.Z.exe`，用户双击即装。
- 安装过程同时**静默安装** `MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe`。
- 装完 `mock` 与 `mvs` 两个相机驱动均可用，无需用户预装 Python。
- 支持 Windows 10 1809+ x64 / Windows 11 x64。
- 标准卸载入口（控制面板 → 程序与功能）。
- 启动崩溃时显示**友好对话框**而非黑窗 traceback，日志写入 `%LOCALAPPDATA%\PsfScan\logs\`。
- 启动时显示 splash 图，掩盖 Qt + numpy + h5py 模块加载延迟。

**v1.0 不做（推迟到后续版本）：**

- 代码签名（v1.1，需购买证书）。
- 自动更新机制（实验台机器多数离线，暂不需要）。
- x86 / Windows 7 / 8 / 8.1 支持。
- MSI / 企业批量部署。
- 多语言切换（界面已默认中文，安装器走 Inno Setup 自带中文资源）。

---

## 2. 关键决策

| # | 决策点 | 选定方案 | 否决方案 |
|---|---|---|---|
| 1 | Python 运行时 | **PyInstaller `--onedir` 冻结**：用户机不需 Python，启动 < 2s | embeddable Python（首装慢）/ 依赖系统 Python（运维差） |
| 2 | MVS SDK 集成 | **内嵌 .exe + 静默调起**（`/S` 参数）一次装齐 | 手动后装 / 安装时弹窗询问 |
| 3 | 目标平台 | **Windows 10/11 x64 唯一** | x86（PySide6 已停 32-bit）/ Win7（PySide6 不支持） |
| 4 | 安装器技术 | **Inno Setup 6**：脚本简洁、社区成熟、`[Run]` 段一行调外部 exe | NSIS（语法繁）/ WiX（XML 过重） |
| 5 | 版本号 SSOT | `installer/version.json` 一处定义，构建脚本同步到其它 | 各处独立维护（易漂） |

---

## 3. 三阶段架构

```
┌────────────────────────── 阶段 A：构建（每次发版）────────────────────────┐
│                                                                          │
│   psf_scan/ 源码                                                          │
│        │                                                                 │
│        ▼  pip install -r installer/requirements-build.txt                │
│   .venv-build/  (Python 3.11 + 运行依赖 + pyinstaller)                    │
│        │                                                                 │
│        ▼  pyinstaller installer/psf_scan.spec                            │
│   build/dist/PsfScan/   ← onedir，约 1500 文件 / 250 MB                   │
│        │                                                                 │
│        ▼  ISCC.exe installer/PsfScan.iss                                 │
│   release/PsfScan-Setup-X.Y.Z.exe   ← 单文件交付物，约 300 MB             │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────── 阶段 B：装机（用户机一次性）─────────────────────┐
│   双击 PsfScan-Setup-X.Y.Z.exe                                            │
│   ↓ 欢迎页 → EULA → 选目录 → 选组件 → 安装                                  │
│   ↓ 解压 PsfScan/ → C:\Program Files\PsfScan\                             │
│   ↓ 静默调起 vendored\MVS_SDK_*.exe /S                                     │
│   ↓ 写注册表卸载入口                                                       │
│   ↓ 建 Start Menu / 桌面 快捷方式 → 完成                                    │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────── 阶段 C：启动（每次双击）────────────────────────┐
│   双击 C:\Program Files\PsfScan\PsfScan.exe                               │
│   ↓ _bootstrap.py 装全局 sys.excepthook                                   │
│   ↓ QSplashScreen 显示 splash.png                                         │
│   ↓ 加载 psf_scan.app → MainWindow.show() → splash.finish()               │
│                                                                          │
│   崩溃时 → %LOCALAPPDATA%\PsfScan\logs\YYYY-MM-DD.log + 友好对话框          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 仓库新增文件清单

```
psf_scan/
├── installer/                          # 新增：所有打包资产
│   ├── build.ps1                       # 一键构建脚本（PowerShell）
│   ├── psf_scan.spec                   # PyInstaller spec
│   ├── PsfScan.iss                     # Inno Setup 脚本
│   ├── requirements-build.txt          # 构建期 pip 依赖
│   ├── version.json                    # {"version": "1.0.0"} 唯一来源
│   ├── bump_version.py                 # 把 version.json 同步到其它文件
│   ├── resources/
│   │   ├── icon.ico                    # 应用图标（多分辨率 .ico）
│   │   ├── splash.png                  # 启动 splash（推荐 480×320）
│   │   ├── license.rtf                 # EULA（首次发版可放占位文）
│   │   ├── installer-icon.ico          # 安装器自身图标（可与上同）
│   │   └── installer-image.bmp         # 安装向导左侧大图（可空）
│   ├── vendored/                       # gitignore（大文件）
│   │   └── MVS_SDK_*.exe               # 发版者从仓库根复制进来
│   └── README.md                       # 指向 docs/build/RELEASE_WINDOWS.md
└── src/psf_scan/
    ├── _bootstrap.py                   # 新增：sys.excepthook + 日志目录
    ├── _splash.py                      # 新增：QSplashScreen 包装
    ├── _version.py                     # 新增：__version__ = "1.0.0"
    └── __main__.py                     # 修改：先调 _bootstrap、显 splash
```

`installer/vendored/MVS_SDK_*.exe` 不入库（57 MB 二进制不放仓库）；构建前由发版者从外部复制就位。具体见 `docs/build/RELEASE_WINDOWS.md`。

---

## 5. 各文件职责

### `installer/version.json`

```json
{ "version": "1.0.0", "build": "2026-05-09" }
```

唯一版本号源。`bump_version.py` 读它然后同步到 `pyproject.toml`、`src/psf_scan/_version.py`、`PsfScan.iss` 的 `MyAppVersion` 宏、PyInstaller spec 的 `version_file`。

### `installer/psf_scan.spec`（PyInstaller）

- `Analysis(['src/psf_scan/__main__.py'], ...)`
- `hiddenimports`: 显式列出 `pyqtgraph`、`OpenGL.platform.win32`、`scipy.special._cdflib`、`h5py.defs` 等动态导入。
- `datas`: 包括 `src/psf_scan/vendor/MvImport/**`、`installer/resources/splash.png`。
- `binaries`: 不手工塞 MVS DLL（运行时由系统 PATH 找已装的 MVS Runtime）。
- `version_file`: 指向构建脚本生成的 `version_info.txt`，让 exe 属性页显示产品名/公司/版权。
- `icon`: `installer/resources/icon.ico`。
- 建议 `console=False`，发布版无黑窗。

### `installer/PsfScan.iss`（Inno Setup）

关键段（伪代码）：

```pascal
[Setup]
AppId={{A37C9B4D-...}}                     ; 固定 GUID，不变
AppName=PSF Scan
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\PsfScan            ; %ProgramFiles%\PsfScan
DefaultGroupName=PSF Scan
OutputDir=..\release
OutputBaseFilename=PsfScan-Setup-{#MyAppVersion}
Compression=lzma2/ultra
SolidCompression=yes
MinVersion=10.0.17763                       ; Win10 1809+
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=resources\installer-icon.ico
WizardImageFile=resources\installer-image.bmp
LicenseFile=resources\license.rtf

[Files]
Source: "..\build\dist\PsfScan\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "vendored\MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe"; \
    DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\PSF Scan"; Filename: "{app}\PsfScan.exe"
Name: "{commondesktop}\PSF Scan"; Filename: "{app}\PsfScan.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe"; \
    Parameters: "/S"; \
    StatusMsg: "正在安装 MVS SDK 运行时（约 1 分钟）..."; \
    Flags: waituntilterminated

Filename: "{app}\PsfScan.exe"; Description: "立即启动 PSF Scan"; \
    Flags: nowait postinstall skipifsilent
```

### `installer/build.ps1`

```powershell
# 1. 校验 venv、Inno Setup 路径
# 2. python installer\bump_version.py --read   → 取版本
# 3. pyinstaller --noconfirm --clean installer\psf_scan.spec
# 4. ISCC.exe installer\PsfScan.iss
# 5. 输出 release\PsfScan-Setup-X.Y.Z.exe 路径与大小
```

### `src/psf_scan/_bootstrap.py`

装 `sys.excepthook` → 写日志 → 弹 `QMessageBox.critical`。日志目录用 `QStandardPaths.AppDataLocation` 拿 `%LOCALAPPDATA%\PsfScan\logs\`。

### `src/psf_scan/_splash.py`

`QSplashScreen` 包装。在 `__main__.py` 里 `_splash.show() → import psf_scan.app → MainWindow().show() → _splash.finish(window)`。

---

## 6. 数据流

**构建期：** 源码 + venv → PyInstaller 冻结目录 → Inno 编译 → 单 exe。

**安装期：** Inno 解压 dist/ → `Program Files\PsfScan\` ；`vendored/MVS_SDK_*.exe` 解压到 `%TEMP%`，跑完静默安装即被 Inno 自动删除（`deleteafterinstall`）。

**运行期：** PsfScan.exe 启动 → 加载同目录 python311.dll + Qt6*.dll → 从 `%PROGRAMW6432%\MVS\Development\Libraries\win64\MvCameraControl.dll` 加载海康 SDK → 调相机。

---

## 7. 错误处理

| 失败点 | 处理 |
|---|---|
| PyInstaller 漏 hidden import（运行时 ImportError） | spec 里 `hiddenimports` 显式列出；首次发版前在干净 VM 跑一遍捕获 |
| MVS SDK 静默安装失败 / 退出码非 0 | Inno `[Run]` 默认 `waituntilterminated`；非 0 弹错但**不阻塞**整体安装（用户可手动后装） |
| Visual C++ Runtime 缺失 | MVS SDK 安装器已内置 VC redist；不另装 |
| 用户系统 < Win10 1809 | Inno `MinVersion` 检查，安装器启动即拒绝 |
| 启动时模块加载抛异常 | `_bootstrap.py` 全局 excepthook 写日志 + 友好弹框，附"日志位置：…" |
| 装 32-bit 系统上 | `ArchitecturesAllowed=x64` 直接拒绝 |
| 升级安装（旧版在） | 同 `AppId` GUID → Inno 自动覆盖；目录与卸载入口复用 |
| 卸载残留 | `[UninstallDelete]` 段清空 `%LOCALAPPDATA%\PsfScan\` 由用户决定（默认保留日志） |

---

## 8. 测试策略

**最小验证矩阵（每次发版）：**

| 场景 | 操作系统 | 预装 Python | 预装 MVS | 期望 |
|---|---|---|---|---|
| 全新装 | Win10 22H2 x64 干净 VM | 否 | 否 | 装上、跑 mock 通、卸干净 |
| 全新装 | Win11 23H2 x64 干净 VM | 否 | 否 | 装上、跑 mock 通、卸干净 |
| 真机带相机 | Win10/11 x64 实机 | 否 | 否 | 装完直接 mvs 模式抓帧 |
| 升级 | 装过 1.0.0 的 VM | 否 | 是 | 1.0.1 安装器覆盖、保留设置 |

**冒烟脚本（CI 友好）：**

- 启动 PsfScan.exe → 等 5s → 截图 → 比对窗口存在
- mock 扫描 1 个 z 点 → 检查 `psf_data/` 有输出
- 卸载后 → 检查 `Program Files\PsfScan\` 不存在、注册表 `Uninstall` 项不存在

---

## 9. 未来扩展

- **v1.1 代码签名**：购买 EV / OV 证书，`signtool sign /tr <时间戳服务器>` 同时签 `PsfScan.exe` 与 `PsfScan-Setup-*.exe`。
- **v1.2 CI 出包**：GitHub Actions Windows runner 自动跑 build.ps1，tag 触发产出 release。
- **v1.3 自动更新**：嵌入版本检查接口（连内网更新源）、Inno 升级安装链路。
- **v2.0 增量更新**：考虑 Squirrel.Windows / WinSparkle，仅适用于联网场景。

---

## 10. 决策日志

- 2026-05-09：初版设计，与维护者通过 brainstorming 流程定下 4 项关键决策。

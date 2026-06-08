# installer/

PSF Scan 的 Windows 打包资产。

- 设计依据：[`docs/plans/2026-05-09-windows-installer-design.md`](../docs/plans/2026-05-09-windows-installer-design.md)
- 发版步骤：[`docs/build/RELEASE_WINDOWS.md`](../docs/build/RELEASE_WINDOWS.md)
- 实施计划：[`docs/plans/2026-05-09-windows-installer-impl.md`](../docs/plans/2026-05-09-windows-installer-impl.md)

## 文件一览

| 文件 | 作用 | 修改场景 |
|---|---|---|
| `version.json` | 版本号唯一来源 | 每次发版 bump |
| `bump_version.py` | 把 `version.json` 同步到 `pyproject.toml` / `_version.py` / `PsfScan.iss` | 不动 |
| `psf_scan.spec` | PyInstaller `--onedir` 配置 | 加新依赖时调整 hiddenimports |
| `PsfScan.iss` | Inno Setup 安装器脚本 | 改安装目录 / 快捷方式 / 静默调用时 |
| `build.ps1` | 一键构建（PowerShell） | 不动 |
| `requirements-build.txt` | 构建期 pip 依赖（仅 pyinstaller） | 升级 pyinstaller 时 |
| `resources/` | 图标、splash、EULA、版本信息 | 美术资产更新时 |
| `_make_placeholder_resources.py` | 占位图标生成器（需 Pillow） | 仅占位阶段 |
| `vendored/` | 大文件本地存放（**不入库**）：MVS SDK 安装器、`PI_GCS2_DLL_x64.dll` | 升级设备运行时时 |

## 一键构建（Windows 构建机）

前置环境一次性准备：见 RELEASE_WINDOWS.md §A。

```powershell
.\installer\build.ps1
```

成功输出：

```
[OK] 安装包: release\PsfScan-Setup-1.0.0.exe  (~300 MB)
[OK] SHA256: <hash>
```

PI 位移台需要 PI 官方 GCS2 运行时。本地 Windows 构建时，把 `PI_GCS2_DLL_x64.dll` 放到 `installer/vendored/`；发布 workflow 会先从 `pi-runtime` GitHub release asset 恢复该 DLL。PyInstaller 会把它打进 onedir payload，程序启动时会依次查找 `_internal/`、`PsfScan.exe` 所在目录和启动目录。

## 联系方式

仓库不存放真实联系方式。本地构建时把发版者信息填到 `installer/support_contact.json`（**已 gitignore，不入库**），模板见 `installer/support_contact.example.json`。

运行时 `_bootstrap.py` 按以下顺序解析：

1. 环境变量 `PSF_SCAN_SUPPORT`
2. 安装目录里的 `support_contact.json`（PyInstaller 打包时如果存在就一起带上）
3. 默认占位 "Contact your distributor's support channel"

这套机制让公开仓库 / CI 出的 .exe 永远不含个人号码，只有发版者本地构建的私下分发版本才带真实联系方式。

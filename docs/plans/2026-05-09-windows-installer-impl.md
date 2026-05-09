# Windows 安装包实施计划（PSF Scan v1.0）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal：** 把已批准的 Windows 安装器设计（见 `docs/plans/2026-05-09-windows-installer-design.md`）落地到代码与脚本，使 `installer/build.ps1` 能一键产出 `release/PsfScan-Setup-X.Y.Z.exe`。

**Architecture：** 三阶段流水线——构建（PyInstaller `--onedir`）→ 打包（Inno Setup）→ 装机（静默调起 MVS SDK exe）。版本号以 `installer/version.json` 为单一来源，`bump_version.py` 同步到 `pyproject.toml`、`src/psf_scan/_version.py`、`installer/PsfScan.iss`。运行时通过 `_bootstrap.py` 装全局 `sys.excepthook`、`_splash.py` 显示启动 splash，掩盖 Qt 加载延迟。

**Tech Stack：** Python 3.11 x64、PyInstaller 6.x、Inno Setup 6、PySide6、PowerShell 5.1+、pytest。

---

## 平台说明

T0–T5（Python 代码）可在 Linux 或 Windows 上开发与测试。
T6–T12（PyInstaller / Inno Setup / build.ps1）**必须在 Windows 10/11 x64 上**进行真实构建与端到端验证。

如果当前是 Linux 开发机，T6 起的"运行命令验证"步骤可在 Windows 构建机或 VM 上完成；前置 Python 任务先在 Linux 上 TDD 通过即可。

---

## Phase 0 — 测试基建

### Task 0：引入 pytest 与 tests/ 骨架

**Files：**
- Modify：`pyproject.toml`
- Create：`tests/__init__.py`
- Create：`tests/conftest.py`
- Create：`tests/test_smoke.py`

**Step 1：写第一个会失败的烟囱测试**

```python
# tests/test_smoke.py
def test_pytest_is_running():
    assert 1 + 1 == 2
```

**Step 2：跑测试确认 pytest 还没装**

```bash
cd /home/zonazcy/Projects/psf_scan
.venv/bin/python -m pytest tests/ -q
```
Expected：`No module named pytest` 或类似错误（视环境而定）。

**Step 3：在 `pyproject.toml` 加 dev 依赖**

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-qt>=4.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

**Step 4：装 dev 依赖并跑测试**

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```
Expected：`1 passed`。

**Step 5：建空 `tests/__init__.py` 与 `tests/conftest.py`**

```python
# tests/__init__.py
# (空文件)
```

```python
# tests/conftest.py
"""Shared pytest fixtures."""
```

**Step 6：提交**

```bash
git add pyproject.toml tests/
git commit -m "test: bootstrap pytest infrastructure"
```

---

## Phase 1 — 版本号单一来源

### Task 1：建立 version.json 与 _version.py

**Files：**
- Create：`installer/version.json`
- Create：`src/psf_scan/_version.py`
- Modify：`src/psf_scan/__init__.py`
- Create：`tests/test_version.py`

**Step 1：写失败测试**

```python
# tests/test_version.py
import json
from pathlib import Path

import psf_scan


def test_package_version_matches_json():
    repo = Path(__file__).resolve().parent.parent
    data = json.loads((repo / "installer" / "version.json").read_text())
    assert psf_scan.__version__ == data["version"]


def test_version_is_semver_like():
    parts = psf_scan.__version__.split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()
```

**Step 2：跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_version.py -v
```
Expected：FileNotFoundError on `installer/version.json` 或 AssertionError。

**Step 3：建 `installer/version.json`**

```json
{
  "version": "1.0.0",
  "build": "2026-05-09"
}
```

**Step 4：建 `src/psf_scan/_version.py`**

```python
"""Single source of truth for the runtime package version.

Kept in sync with ``installer/version.json`` by ``installer/bump_version.py``.
"""

__version__ = "1.0.0"
```

**Step 5：让 `__init__.py` 转发版本**

把现在的：

```python
"""PSF stage-scan acquisition GUI."""

__version__ = "0.1.0"
```

改成：

```python
"""PSF stage-scan acquisition GUI."""

from ._version import __version__

__all__ = ["__version__"]
```

**Step 6：跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_version.py -v
```
Expected：`2 passed`。

**Step 7：提交**

```bash
git add installer/version.json src/psf_scan/_version.py src/psf_scan/__init__.py tests/test_version.py
git commit -m "feat(version): introduce version.json as single source of truth"
```

---

### Task 2：bump_version.py 同步脚本

**Files：**
- Create：`installer/bump_version.py`
- Create：`tests/test_bump_version.py`

**Step 1：写失败测试**

```python
# tests/test_bump_version.py
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "installer" / "bump_version.py"


def _read_version_json() -> dict:
    return json.loads((REPO / "installer" / "version.json").read_text())


def _read_pyproject_version() -> str:
    text = (REPO / "pyproject.toml").read_text()
    for line in text.splitlines():
        if line.startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("version not found in pyproject.toml")


def test_bump_script_syncs_pyproject_and__version_py(tmp_path):
    original = _read_version_json()
    new_value = "9.9.9"
    target = REPO / "installer" / "version.json"
    target.write_text(json.dumps({"version": new_value, "build": "2026-05-09"}))
    try:
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=REPO)
        assert _read_pyproject_version() == new_value
        assert (
            f'__version__ = "{new_value}"'
            in (REPO / "src" / "psf_scan" / "_version.py").read_text()
        )
    finally:
        target.write_text(json.dumps(original))
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=REPO)
```

**Step 2：跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_bump_version.py -v
```
Expected：FileNotFoundError 或 CalledProcessError。

**Step 3：实现 `installer/bump_version.py`**

```python
"""Synchronize the version in installer/version.json to all dependent files.

Reads installer/version.json["version"] and rewrites:
  - pyproject.toml  ([project] version = "X.Y.Z")
  - src/psf_scan/_version.py  (__version__ = "X.Y.Z")
  - installer/PsfScan.iss     (#define MyAppVersion "X.Y.Z")  [if file exists]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_JSON = REPO / "installer" / "version.json"
PYPROJECT = REPO / "pyproject.toml"
VERSION_PY = REPO / "src" / "psf_scan" / "_version.py"
ISS = REPO / "installer" / "PsfScan.iss"


def read_target_version() -> str:
    data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    v = data["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise SystemExit(f"version.json version not semver-like: {v!r}")
    return v


def patch_pyproject(v: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{v}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new == text:
        raise SystemExit("pyproject.toml: no [project] version line matched")
    PYPROJECT.write_text(new, encoding="utf-8")


def patch_version_py(v: str) -> None:
    VERSION_PY.write_text(
        '"""Single source of truth for the runtime package version.\n\n'
        "Kept in sync with ``installer/version.json`` by ``installer/bump_version.py``.\n"
        '"""\n\n'
        f'__version__ = "{v}"\n',
        encoding="utf-8",
    )


def patch_iss(v: str) -> None:
    if not ISS.exists():
        return
    text = ISS.read_text(encoding="utf-8")
    new = re.sub(
        r'^#define\s+MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion "{v}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new != text:
        ISS.write_text(new, encoding="utf-8")


def main() -> int:
    v = read_target_version()
    patch_pyproject(v)
    patch_version_py(v)
    patch_iss(v)
    print(f"[bump_version] synced -> {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4：跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_bump_version.py -v
```
Expected：`1 passed`。

**Step 5：手动 sanity check**

```bash
.venv/bin/python installer/bump_version.py
```
Expected：`[bump_version] synced -> 1.0.0`。`pyproject.toml` 与 `_version.py` 内容不变（值已经一致）。

**Step 6：提交**

```bash
git add installer/bump_version.py tests/test_bump_version.py
git commit -m "feat(version): add bump_version.py to synchronize version sources"
```

---

## Phase 2 — 运行时保护网

### Task 3：_bootstrap.py（全局崩溃捕获）

**Files：**
- Create：`src/psf_scan/_bootstrap.py`
- Create：`tests/test_bootstrap.py`

**Step 1：写失败测试**

```python
# tests/test_bootstrap.py
import logging
from pathlib import Path
from unittest.mock import patch

from psf_scan._bootstrap import (
    install_excepthook,
    log_directory,
    write_crash_log,
)


def test_log_directory_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = log_directory()
    assert p == tmp_path / "PsfScan" / "logs"
    assert p.is_dir()


def test_write_crash_log_creates_dated_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        path = write_crash_log(type(e), e, e.__traceback__)
    assert path.exists()
    assert "RuntimeError: boom" in path.read_text(encoding="utf-8")


def test_install_excepthook_replaces_sys_excepthook():
    import sys
    original = sys.excepthook
    try:
        install_excepthook(gui=False)
        assert sys.excepthook is not original
    finally:
        sys.excepthook = original
```

**Step 2：跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -v
```
Expected：ImportError on `psf_scan._bootstrap`。

**Step 3：实现 `_bootstrap.py`**

```python
"""Global crash handler and log directory bootstrap.

Installed by ``psf_scan.__main__`` before any GUI code runs so that any
ImportError or initialization crash still produces a user-friendly log.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import traceback
from pathlib import Path
from types import TracebackType


def log_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / "PsfScan" / "logs"
    else:
        root = Path.home() / ".psf_scan" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_crash_log(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> Path:
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = log_directory() / f"crash_{stamp}.log"
    with path.open("w", encoding="utf-8") as fp:
        fp.write(f"{exc_type.__name__}: {exc_value}\n\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=fp)
    return path


def install_excepthook(*, gui: bool = True) -> None:
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        path = write_crash_log(exc_type, exc_value, exc_tb)
        if gui:
            try:
                from PySide6.QtWidgets import QApplication, QMessageBox
                if QApplication.instance() is not None:
                    QMessageBox.critical(
                        None,
                        "PSF Scan 异常",
                        f"程序遇到未处理的异常，已记录日志：\n{path}\n\n"
                        f"{exc_type.__name__}: {exc_value}",
                    )
            except Exception:
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
```

**Step 4：跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -v
```
Expected：`3 passed`。

**Step 5：提交**

```bash
git add src/psf_scan/_bootstrap.py tests/test_bootstrap.py
git commit -m "feat(runtime): add _bootstrap with global crash handler"
```

---

### Task 4：_splash.py（Qt 启动 splash）

**Files：**
- Create：`src/psf_scan/_splash.py`
- Create：`tests/test_splash.py`

**Step 1：写失败测试**

```python
# tests/test_splash.py
import pytest

pytestmark = pytest.mark.skipif(
    pytest.importorskip("PySide6", reason="PySide6 not available") is None,
    reason="PySide6 not available",
)


def test_show_splash_returns_widget(qtbot):
    from psf_scan._splash import show_splash
    splash = show_splash()
    qtbot.addWidget(splash)
    assert splash.isVisible()
    splash.close()


def test_show_splash_returns_none_without_qapplication(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from psf_scan._splash import show_splash
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    assert show_splash() is None
```

**Step 2：跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_splash.py -v
```
Expected：ImportError。

**Step 3：实现 `_splash.py`**

```python
"""Startup splash screen.

Shown by ``psf_scan.__main__`` while heavy modules (Qt, numpy, h5py,
pyqtgraph) load, then closed when the main window is ready.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen


def _splash_pixmap() -> QPixmap:
    try:
        candidate = files("psf_scan").joinpath("resources/splash.png")
        if candidate.is_file():
            return QPixmap(str(candidate))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    repo_asset = (
        Path(__file__).resolve().parent.parent.parent
        / "installer" / "resources" / "splash.png"
    )
    if repo_asset.is_file():
        return QPixmap(str(repo_asset))
    pix = QPixmap(480, 320)
    pix.fill(Qt.GlobalColor.white)
    return pix


def show_splash() -> QSplashScreen | None:
    if QApplication.instance() is None:
        return None
    splash = QSplashScreen(_splash_pixmap(), Qt.WindowType.WindowStaysOnTopHint)
    splash.showMessage(
        "PSF Scan 正在启动…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
    )
    splash.show()
    QApplication.processEvents()
    return splash
```

**Step 4：跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_splash.py -v
```
Expected：`2 passed`（Linux 上若无 X / Wayland，可加 `QT_QPA_PLATFORM=offscreen`）。

**Step 5：提交**

```bash
git add src/psf_scan/_splash.py tests/test_splash.py
git commit -m "feat(runtime): add _splash for startup splash screen"
```

---

### Task 5：把 _bootstrap + _splash 接进 __main__.py

**Files：**
- Modify：`src/psf_scan/__main__.py`
- Create：`tests/test_main_smoke.py`

**Step 1：写失败的烟囱测试**

```python
# tests/test_main_smoke.py
import os
import subprocess
import sys
from pathlib import Path


def test_module_imports_without_error():
    repo = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PSF_SCAN_SMOKE"] = "1"
    out = subprocess.run(
        [sys.executable, "-c", "import psf_scan.__main__"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 0, out.stderr
```

**Step 2：跑测试**

```bash
.venv/bin/python -m pytest tests/test_main_smoke.py -v
```
当前应通过（导入 `__main__` 模块不会运行 `main()`）。

**Step 3：改写 `__main__.py`，把 _bootstrap、_splash 接入**

```python
"""Entry point: ``python -m psf_scan`` or ``psf-scan``."""

from __future__ import annotations

import os
import sys

from . import _bootstrap


def main() -> int:
    _bootstrap.install_excepthook(gui=False)
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    _bootstrap.install_excepthook(gui=True)

    from .ui.settings import APP_NAME, ORG_NAME
    from .ui.theme import apply_theme
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    apply_theme(app)

    from ._splash import show_splash
    splash = show_splash()

    from .app import MainWindow
    win = MainWindow()
    win.resize(1280, 820)
    win.show()
    if splash is not None:
        splash.finish(win)

    if os.environ.get("PSF_SCAN_SMOKE") == "1":
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4：扩烟囱测试**

补一个用例验证 `main()` 在 smoke 模式下能跑完：

```python
def test_main_runs_under_smoke_mode():
    repo = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PSF_SCAN_SMOKE"] = "1"
    out = subprocess.run(
        [sys.executable, "-m", "psf_scan"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
```

**Step 5：跑测试**

```bash
.venv/bin/python -m pytest tests/test_main_smoke.py -v
```
Expected：`2 passed`。

**Step 6：手动跑一次（人眼看 splash + 主窗口）**

```bash
.venv/bin/python -m psf_scan
```
Expected：splash 一闪 → 主窗口打开。

**Step 7：提交**

```bash
git add src/psf_scan/__main__.py tests/test_main_smoke.py
git commit -m "feat(runtime): wire _bootstrap and _splash into entry point"
```

---

## Phase 3 — PyInstaller 打包

> 以下任务文件可在 Linux 写出来，但**`pyinstaller` 命令必须在 Windows 上跑**。Linux 阶段把文件创建出来即可，"运行命令"步骤记入 release runbook 的 Windows 验证环节。

### Task 6：installer/requirements-build.txt 与 .gitignore

**Files：**
- Create：`installer/requirements-build.txt`
- Modify：`.gitignore`（项目根，不存在则新建）

**Step 1：建 `installer/requirements-build.txt`**

```text
# 运行依赖（与 pyproject [project].dependencies 保持一致）
PySide6>=6.7
pyqtgraph>=0.13
PyOpenGL>=3.1
numpy>=1.24
h5py>=3.10
tifffile>=2024.1
scipy>=1.11

# 构建期依赖
pyinstaller>=6.5
```

**Step 2：更新 `.gitignore`**

加入或确保已有：

```gitignore
# 构建产物
/build/
/dist/
/release/

# PyInstaller
*.spec.bak

# Inno Setup 中间产物
*.iss.bak

# 安装器内嵌大文件（发版者本地放置，不入库）
/installer/vendored/

# 测试 / Python 缓存
__pycache__/
*.pyc
.pytest_cache/
```

**Step 3：提交**

```bash
git add installer/requirements-build.txt .gitignore
git commit -m "build: add installer requirements and gitignore for build artifacts"
```

---

### Task 7：installer/resources/ 占位资产

**Files：**
- Create：`installer/resources/icon.ico`（占位，64×64 单色即可）
- Create：`installer/resources/splash.png`（480×320 占位）
- Create：`installer/resources/license.rtf`（最简 RTF）
- Create：`installer/resources/installer-icon.ico`（可与 icon.ico 同）
- Create：`installer/resources/version_info.txt`（PyInstaller VS_VERSIONINFO 模板）

**Step 1：用 Python 生成占位 splash.png 与 icon.ico**

```python
# 一次性脚本，可在 .venv 里跑
from PIL import Image, ImageDraw
splash = Image.new("RGB", (480, 320), "white")
ImageDraw.Draw(splash).text((24, 144), "PSF Scan", fill="black")
splash.save("installer/resources/splash.png")
icon = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
ImageDraw.Draw(icon).rectangle([8, 8, 56, 56], fill="#1a4d8c")
icon.save("installer/resources/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
icon.save("installer/resources/installer-icon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
```

> 需要 `pip install Pillow` 才能生成；占位资产可后续替换为正式美术资源。

**Step 2：建 `installer/resources/license.rtf`**

```rtf
{\rtf1\ansi\deff0
{\fonttbl{\f0 Calibri;}}
\f0\fs20
PSF Scan\par
版权所有 \'a9 2026.\par
本软件按现状提供，使用即视为接受相关条款。\par
}
```

**Step 3：建 `installer/resources/version_info.txt`**（PyInstaller VS_VERSIONINFO 模板）

```python
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'PSF Scan'),
        StringStruct('FileDescription', 'PSF Scan - Stage-scan PSF acquisition GUI'),
        StringStruct('FileVersion', '1.0.0'),
        StringStruct('InternalName', 'PsfScan'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026'),
        StringStruct('OriginalFilename', 'PsfScan.exe'),
        StringStruct('ProductName', 'PSF Scan'),
        StringStruct('ProductVersion', '1.0.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
```

> `bump_version.py` 后续可扩展同步 `filevers` / `FileVersion` / `ProductVersion`，初版手动同步即可。

**Step 4：提交**

```bash
git add installer/resources/
git commit -m "build: add placeholder installer resources (icon, splash, license, version)"
```

---

### Task 8：installer/psf_scan.spec（PyInstaller 配置）

**Files：**
- Create：`installer/psf_scan.spec`

**Step 1：写 spec**

```python
# installer/psf_scan.spec  -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent
SRC = REPO / "src"

block_cipher = None

a = Analysis(
    [str(SRC / "psf_scan" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(SRC / "psf_scan" / "vendor" / "MvImport"),
         "psf_scan/vendor/MvImport"),
        (str(REPO / "installer" / "resources" / "splash.png"),
         "psf_scan/resources"),
    ],
    hiddenimports=[
        "pyqtgraph",
        "pyqtgraph.opengl",
        "OpenGL.platform.win32",
        "scipy.special._cdflib",
        "h5py.defs",
        "h5py.utils",
        "h5py._proxy",
        "tifffile",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "matplotlib",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PsfScan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(REPO / "installer" / "resources" / "icon.ico"),
    version=str(REPO / "installer" / "resources" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PsfScan",
)
```

**Step 2：在 Windows 构建机上验证（首次发版前必跑）**

```powershell
cd psf_scan
.\.venv-build\Scripts\Activate.ps1
pyinstaller --noconfirm --clean installer\psf_scan.spec
```
Expected：`build\dist\PsfScan\PsfScan.exe` 存在；目录树包含 `python311.dll`、`PySide6\`、`numpy\` 等子目录。

**Step 3：本地试跑冻结版**

```powershell
.\build\dist\PsfScan\PsfScan.exe
```
Expected：splash + 主窗口出现，mock 模式扫描通。

**Step 4：提交**

```bash
git add installer/psf_scan.spec
git commit -m "build: add pyinstaller spec for onedir frozen exe"
```

---

## Phase 4 — Inno Setup 安装器

### Task 9：installer/PsfScan.iss

**Files：**
- Create：`installer/PsfScan.iss`

**Step 1：写 .iss 脚本**

```pascal
; installer/PsfScan.iss — Inno Setup 6 (with ISPP)
#define MyAppName        "PSF Scan"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "PSF Scan"
#define MyAppExeName     "PsfScan.exe"
#define MvsExeName       "MVS_SDK_V4_7_0_3_MVFG_V2_7_0_2_VC90_Runtime_STD_251113.exe"

[Setup]
AppId={{4F7B2D9E-3A1C-4F0D-9C7A-2E1B6D5F8A3C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PsfScan
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=PsfScan-Setup-{#MyAppVersion}
Compression=lzma2/ultra
SolidCompression=yes
MinVersion=10.0.17763
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no
DisableProgramGroupPage=yes
SetupIconFile=resources\installer-icon.ico
LicenseFile=resources\license.rtf
WizardStyle=modern
ShowLanguageDialog=auto

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "en";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "mvssdk";      Description: "同时安装 MVS SDK 运行时（连接海康相机必需）"; GroupDescription: "运行时组件:"

[Files]
Source: "..\build\dist\PsfScan\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "vendored\{#MvsExeName}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Tasks: mvssdk

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\{#MvsExeName}"; \
    Parameters: "/S"; \
    StatusMsg: "正在安装 MVS SDK 运行时（约 1 分钟）..."; \
    Flags: waituntilterminated; \
    Tasks: mvssdk

Filename: "{app}\{#MyAppExeName}"; \
    Description: "立即启动 {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
```

**Step 2：在 Windows 构建机上编译**

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\PsfScan.iss
```
Expected：`release\PsfScan-Setup-1.0.0.exe` 出现，体积约 280-320 MB。

**Step 3：在干净 VM 上验证**

参照 `docs/build/RELEASE_WINDOWS.md` §B.5 的验证矩阵。

**Step 4：提交**

```bash
git add installer/PsfScan.iss
git commit -m "build: add Inno Setup installer script"
```

---

### Task 10：installer/build.ps1 一键构建脚本

**Files：**
- Create：`installer/build.ps1`

**Step 1：写脚本**

```powershell
# installer/build.ps1
[CmdletBinding()]
param(
    [switch]$SkipPyInstaller,
    [switch]$SkipInno,
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

# --- 1. 校验 venv 与 PyInstaller ----------------------------------------
$python = Join-Path $repo ".venv-build\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "构建 venv 不存在：$python`n请先按 docs/build/RELEASE_WINDOWS.md §A.5 创建。"
}

# --- 2. 同步版本号 -------------------------------------------------------
& $python "installer\bump_version.py"
$version = (Get-Content "installer\version.json" | ConvertFrom-Json).version
Write-Host "[build] target version: $version" -ForegroundColor Cyan

# --- 3. 准备 MVS SDK exe -------------------------------------------------
$vendored = Join-Path $repo "installer\vendored"
$mvsExe   = Get-ChildItem $vendored -Filter "MVS_SDK_*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $mvsExe) {
    throw "未找到 installer\vendored\MVS_SDK_*.exe；请按 RELEASE_WINDOWS.md §B.2 复制就位。"
}
Write-Host "[build] using MVS SDK: $($mvsExe.Name)" -ForegroundColor Cyan

# --- 4. PyInstaller -------------------------------------------------------
if (-not $SkipPyInstaller) {
    Write-Host "[build] running PyInstaller..." -ForegroundColor Cyan
    & $python -m PyInstaller --noconfirm --clean "installer\psf_scan.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败 ($LASTEXITCODE)" }
}

$dist = Join-Path $repo "build\dist\PsfScan"
if (-not (Test-Path (Join-Path $dist "PsfScan.exe"))) {
    throw "PyInstaller 产物缺失：$dist\PsfScan.exe"
}

# --- 5. Inno Setup --------------------------------------------------------
if (-not $SkipInno) {
    if (-not (Test-Path $InnoSetupPath)) {
        throw "ISCC.exe 不在：$InnoSetupPath；请装 Inno Setup 6 或用 -InnoSetupPath 指定。"
    }
    Write-Host "[build] running Inno Setup..." -ForegroundColor Cyan
    & $InnoSetupPath "installer\PsfScan.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno 编译失败 ($LASTEXITCODE)" }
}

# --- 6. 报告 -------------------------------------------------------------
$out = Join-Path $repo "release\PsfScan-Setup-$version.exe"
if (Test-Path $out) {
    $sz = "{0:N1} MB" -f ((Get-Item $out).Length / 1MB)
    $sha = (Get-FileHash $out -Algorithm SHA256).Hash
    Write-Host ""
    Write-Host "[OK] 安装包: $out  ($sz)" -ForegroundColor Green
    Write-Host "[OK] SHA256: $sha" -ForegroundColor Green
} else {
    throw "未生成预期产物：$out"
}
```

**Step 2：在 Windows 构建机跑一次**

```powershell
.\installer\build.ps1
```
Expected：依次跑完 bump_version、PyInstaller、ISCC，最后打印 `[OK] 安装包: release\PsfScan-Setup-1.0.0.exe (...)`。

**Step 3：测试 `-Skip*` 开关**

```powershell
.\installer\build.ps1 -SkipPyInstaller   # 仅重打 Inno
.\installer\build.ps1 -SkipInno          # 仅重打 PyInstaller
```

**Step 4：提交**

```bash
git add installer/build.ps1
git commit -m "build: add one-shot build.ps1 orchestrator"
```

---

## Phase 5 — 收尾

### Task 11：installer/README.md 与文档交叉链接

**Files：**
- Create：`installer/README.md`
- Modify：`USER_GUIDE.md`（顶部加链接到 RELEASE_WINDOWS.md，告知如何获取 .exe）

**Step 1：建 `installer/README.md`**

```markdown
# installer/

PSF Scan 的 Windows 打包资产。

- 设计依据：[`docs/plans/2026-05-09-windows-installer-design.md`](../docs/plans/2026-05-09-windows-installer-design.md)
- 发版步骤：[`docs/build/RELEASE_WINDOWS.md`](../docs/build/RELEASE_WINDOWS.md)

## 文件一览

| 文件 | 作用 |
|---|---|
| `version.json` | 版本号唯一来源 |
| `bump_version.py` | 把 version.json 同步到其它文件 |
| `psf_scan.spec` | PyInstaller 配置 |
| `PsfScan.iss` | Inno Setup 安装器脚本 |
| `build.ps1` | 一键构建 |
| `requirements-build.txt` | 构建期 pip 依赖 |
| `resources/` | 图标、splash、EULA 等 |
| `vendored/` | 大文件本地存放，**不入库** |

## 一键构建

```powershell
.\installer\build.ps1
```

详细步骤见 RELEASE_WINDOWS.md。
```

**Step 2：在 USER_GUIDE.md 顶部加 Windows 安装提示**

在第 1 节"环境准备"前面加一段：

```markdown
## Windows 用户：直接装

如果你只想使用、不打算开发，从 `release/PsfScan-Setup-X.Y.Z.exe` 双击安装即可。安装包会同时装 MVS 相机运行时。

如果你是开发者或要从源码构建，继续往下看。
```

**Step 3：提交**

```bash
git add installer/README.md USER_GUIDE.md
git commit -m "docs: add installer README and Windows install pointer"
```

---

### Task 12：在 Windows 上端到端验证并补排错记录

**Files：**
- Modify（按需）：`docs/build/RELEASE_WINDOWS.md` §C 排错章节

**Step 1：在干净 Windows 10/11 x64 VM 跑完整流程**

参照 `docs/build/RELEASE_WINDOWS.md` §A → §B.5 的全部矩阵。

**Step 2：把碰到的真实问题写回 §C**

每个排查记录格式：

```markdown
**Q: <现象>**
A: <根因> + <修复步骤>
```

**Step 3：提交（如有改动）**

```bash
git add docs/build/RELEASE_WINDOWS.md
git commit -m "docs(release): add real-world troubleshooting from first VM verification"
```

**Step 4：打 tag 并发布**

```bash
git tag v1.0.0
git push origin master
git push origin v1.0.0
```

---

## 完成判据

- [ ] `pytest -q` 全部通过（T0–T5）
- [ ] `pwsh installer\build.ps1` 在干净构建机上跑通且产出 `release\PsfScan-Setup-1.0.0.exe`
- [ ] 干净 Windows 10 x64 VM 装完后能跑 `mock` 扫描
- [ ] 干净 Windows 11 x64 VM 装完后能跑 `mock` 扫描
- [ ] 控制面板"程序与功能"能找到 PSF Scan，能完整卸载，且 `Program Files\PsfScan\` 不残留
- [ ] 文档双向交叉链接齐（设计 ↔ SOP ↔ installer/README）

完成判据全过 = v1.0 可对外发布。

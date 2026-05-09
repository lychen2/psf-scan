# installer/psf_scan.spec  -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows --onedir build.

Run:
    pyinstaller --noconfirm --clean installer/psf_scan.spec

Outputs:
    build/dist/PsfScan/PsfScan.exe (+ Qt / Python DLLs and resources)
"""
from pathlib import Path
import sys

REPO = Path(SPECPATH).resolve().parent
SRC = REPO / "src"
RESOURCES = REPO / "installer" / "resources"

# Platform-specific OpenGL backend modules. PyInstaller would warn for any
# missing entries; listing only what the current platform needs avoids noise.
if sys.platform == "win32":
    _opengl_platform = ["OpenGL.platform.win32"]
elif sys.platform == "linux":
    _opengl_platform = ["OpenGL.platform.glx", "OpenGL.platform.egl"]
elif sys.platform == "darwin":
    _opengl_platform = ["OpenGL.platform.darwin"]
else:
    _opengl_platform = []

block_cipher = None

a = Analysis(
    [str(SRC / "psf_scan" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        # Hikvision MVS Python bindings (.py files, vendored in tree)
        (str(SRC / "psf_scan" / "vendor" / "MvImport"),
         "psf_scan/vendor/MvImport"),
        # Splash image used at runtime via importlib.resources
        (str(RESOURCES / "splash.png"),
         "psf_scan/resources"),
    ],
    hiddenimports=[
        "pyqtgraph",
        "pyqtgraph.opengl",
        "h5py.defs",
        "h5py.utils",
        "h5py._proxy",
        "tifffile",
        "matplotlib.backends.backend_qtagg",
        *_opengl_platform,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "IPython",
        "jupyter",
        "notebook",
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
    icon=str(RESOURCES / "icon.ico"),
    version=str(RESOURCES / "version_info.txt"),
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

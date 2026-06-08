# installer/psf_scan.spec  -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows --onedir build.

Run:
    pyinstaller --noconfirm --clean installer/psf_scan.spec

Outputs:
    build/dist/PsfScan/PsfScan.exe (+ Qt / Python DLLs and resources)
"""
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files

REPO = Path(SPECPATH).resolve().parent
SRC = REPO / "src"
RESOURCES = REPO / "installer" / "resources"
SUPPORT_CONTACT = REPO / "installer" / "support_contact.json"
VENDORED = REPO / "installer" / "vendored"
PIPYTHON_DATAS = collect_data_files("pipython")
PI_GCS2_DLL = VENDORED / "PI_GCS2_DLL_x64.dll"
PI_GCS2_BINARIES = (
    [(str(PI_GCS2_DLL), ".")]
    if sys.platform == "win32" and PI_GCS2_DLL.exists()
    else []
)

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
    binaries=PI_GCS2_BINARIES,
    datas=[
        # Hikvision MVS Python bindings (.py files, vendored in tree)
        (str(SRC / "psf_scan" / "vendor" / "MvImport"),
         "psf_scan/vendor/MvImport"),
        # Splash image used at runtime via importlib.resources
        (str(RESOURCES / "splash.png"),
         "psf_scan/resources"),
        *(
            [(str(SUPPORT_CONTACT), ".")]
            if SUPPORT_CONTACT.exists()
            else []
        ),
        *PIPYTHON_DATAS,
    ],
    hiddenimports=[
        "pyqtgraph",
        "pyqtgraph.exporters",
        "pyqtgraph.opengl",
        "h5py.defs",
        "h5py.utils",
        "h5py._proxy",
        "tifffile",
        "matplotlib.backends.backend_qtagg",
        "pipython",
        "pipython.pidevice",
        "pipython.pidevice.interfaces.gcsdll",
        "serial",
        "serial.tools.list_ports",
        "serial.tools.list_ports_windows",
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

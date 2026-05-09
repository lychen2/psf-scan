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
    """Locate splash.png from packaged resources, dev tree, or fall back to white."""
    try:
        candidate = files("psf_scan").joinpath("resources/splash.png")
        if candidate.is_file():
            return QPixmap(str(candidate))
    except (ModuleNotFoundError, FileNotFoundError, AttributeError):
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

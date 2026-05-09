"""Entry point: ``python -m psf_scan`` or ``psf-scan``.

Uses absolute imports throughout because PyInstaller runs the frozen entry
script as ``__main__`` with no known parent package; relative imports
(``from . import _bootstrap``) raise ImportError under PyInstaller.
"""

from __future__ import annotations

import os
import sys

from psf_scan import _bootstrap


def main() -> int:
    # Install crash handler before any heavy imports so even ImportError surfaces nicely.
    _bootstrap.install_excepthook(gui=False)

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # Upgrade hook now that QApplication exists so we can show a dialog on crash.
    _bootstrap.install_excepthook(gui=True)

    from psf_scan.ui.settings import APP_NAME, ORG_NAME
    from psf_scan.ui.theme import apply_theme
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    apply_theme(app)

    from psf_scan._splash import show_splash
    splash = show_splash()

    from psf_scan.app import MainWindow
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

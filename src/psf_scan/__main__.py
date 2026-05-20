"""Entry point: ``python -m psf_scan`` or ``psf-scan``.

Uses absolute imports throughout because PyInstaller runs the frozen entry
script as ``__main__`` with no known parent package; relative imports
(``from . import _bootstrap``) raise ImportError under PyInstaller.
"""

from __future__ import annotations

import os
import sys
import logging

from psf_scan import _bootstrap


def main() -> int:
    # Install crash handler + logging before any heavy imports so even ImportError
    # surfaces in the log file and a friendly dialog (once GUI is up).
    _bootstrap.install_excepthook(gui=False)
    _bootstrap.install_logging()
    logging.getLogger("psf_scan.startup").info(
        "startup executable=%s argv=%r package=%s module=%s",
        sys.executable,
        sys.argv,
        __import__("psf_scan").__file__,
        __file__,
    )

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # Upgrade hook now that QApplication exists so we can show a dialog on crash.
    _bootstrap.install_excepthook(gui=True)
    _bootstrap.install_qt_message_handler()

    from psf_scan.ui.settings import APP_NAME, ORG_NAME, UserSettings
    from psf_scan.ui.theme import apply_theme
    from psf_scan.ui.scale import effective_scale
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    user_settings = UserSettings()
    apply_theme(app, effective_scale(user_settings.ui_scale_pref(), app), mode=user_settings.ui_theme())

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

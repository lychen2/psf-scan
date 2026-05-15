"""Global crash handler and log directory bootstrap.

Installed by ``psf_scan.__main__`` before any GUI code runs so that any
ImportError or initialization crash still produces a user-friendly log
and a friendly dialog instead of a black-window traceback.

The "support contact" line shown to the user in the crash dialog is
loaded at runtime from ``installer/support_contact.json`` (or the env
var ``PSF_SCAN_SUPPORT``) so that the public source tree never contains
personal contact details. See ``installer/support_contact.example.json``
for the schema.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import logging.handlers
import os
import sys
import traceback
from pathlib import Path
from types import TracebackType


_DEFAULT_SUPPORT_LINE = "Contact your distributor's support channel"


def _load_support_contact() -> str:
    """Resolve a support-contact line from env / bundled JSON / default.

    Lookup order:
      1. ``PSF_SCAN_SUPPORT`` environment variable (highest priority).
      2. ``installer/support_contact.json`` next to the executable
         (PyInstaller ``sys._MEIPASS`` for frozen runs, repo root in dev).
      3. ``_DEFAULT_SUPPORT_LINE`` placeholder.
    """
    env = os.environ.get("PSF_SCAN_SUPPORT", "").strip()
    if env:
        return env

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "support_contact.json")
    candidates.append(
        Path(__file__).resolve().parent.parent.parent
        / "installer" / "support_contact.json"
    )

    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parts: list[str] = []
        for key in ("name", "phone", "email", "url"):
            value = data.get(key)
            if value:
                parts.append(str(value))
        if parts:
            return "  ".join(parts)
    return _DEFAULT_SUPPORT_LINE


SUPPORT_CONTACT = _load_support_contact()


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


def format_crash_message(log_path: Path, exc: BaseException) -> str:
    """Build the user-facing crash dialog text."""
    return (
        "PSF Scan encountered an unhandled exception.\n\n"
        f"{type(exc).__name__}: {exc}\n\n"
        f"Log written to:\n{log_path}\n\n"
        f"Support: {SUPPORT_CONTACT}"
    )


def install_excepthook(*, gui: bool = True) -> None:
    """Install a global ``sys.excepthook`` that logs and (optionally) shows a dialog.

    ``gui=False`` is used before the QApplication exists; ``gui=True`` should be
    called again immediately after ``QApplication`` instantiation so that the
    user actually sees a dialog instead of a silent log.
    """

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
                        "PSF Scan",
                        format_crash_message(path, exc_value),
                    )
            except Exception:
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def install_logging() -> Path:
    """初始化全局日志:rotating 文件 + stderr。返回主日志文件路径。

    所有 ``logging.getLogger(__name__)`` 拿到的 logger 会写到
    ``<log_directory()>/psf_scan.log`` (5MB × 5 份滚动),同时
    把 INFO+ 拷一份到 stderr。Qt 自己的 ``qDebug/qWarning`` 也通过
    ``qInstallMessageHandler`` 接进来。
    """
    log_path = log_directory() / "psf_scan.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if any(getattr(h, "_psf_scan", False) for h in root.handlers):
        return log_path
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    fh._psf_scan = True  # type: ignore[attr-defined]
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh._psf_scan = True  # type: ignore[attr-defined]
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(sh)
    # 三方库噪声太多 — 提升到 WARNING (psf_scan 自己仍保留 DEBUG)
    for name in ("OpenGL", "matplotlib", "PIL", "fontTools"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("psf_scan").info("logging initialized → %s", log_path)
    return log_path


def install_qt_message_handler() -> None:
    """把 Qt 自己的 qDebug/qWarning/qCritical 转给 ``logging``。

    QApplication 还没建之前调没意义,所以单独拆出来,由 main 在
    QApplication() 之后立即调。
    """
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return
    qt_log = logging.getLogger("Qt")
    level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _handler(mode, ctx, message):
        qt_log.log(level_map.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(_handler)

import os
import sys
from pathlib import Path

from psf_scan._bootstrap import (
    SUPPORT_CONTACT,
    format_crash_message,
    install_excepthook,
    log_directory,
    write_crash_log,
)


def test_log_directory_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = log_directory()
    assert p == tmp_path / "PsfScan" / "logs"
    assert p.is_dir()


def test_log_directory_falls_back_when_no_localappdata(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
    else:
        monkeypatch.setenv("HOME", str(tmp_path))
    p = log_directory()
    assert p == tmp_path / ".psf_scan" / "logs"
    assert p.is_dir()


def test_write_crash_log_creates_dated_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        path = write_crash_log(type(e), e, e.__traceback__)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "RuntimeError: boom" in text
    assert "Traceback" in text


def test_format_crash_message_includes_support_contact(tmp_path):
    log_path = tmp_path / "crash_x.log"
    msg = format_crash_message(log_path, RuntimeError("boom"))
    assert "RuntimeError" in msg
    assert "boom" in msg
    assert str(log_path) in msg
    # Whatever is configured for SUPPORT_CONTACT should be echoed in the dialog.
    assert SUPPORT_CONTACT in msg


def test_support_contact_is_non_empty_string():
    assert isinstance(SUPPORT_CONTACT, str)
    assert SUPPORT_CONTACT.strip()


def test_install_excepthook_replaces_sys_excepthook():
    original = sys.excepthook
    try:
        install_excepthook(gui=False)
        assert sys.excepthook is not original
    finally:
        sys.excepthook = original

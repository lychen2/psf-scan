from __future__ import annotations

import sys
import types

import pytest

from psf_scan.drivers import pi_link
from psf_scan.ui import pi_scan


def test_driver_scan_rs232_daisy_requires_comport_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyDev:
        def CloseDaisyChain(self) -> None:
            pass

    monkeypatch.setattr(pi_link, "_is_linux", lambda: False)

    with pytest.raises(RuntimeError, match="COM"):
        pi_link.scan_rs232_daisy(DummyDev(), comport=None, baudrate=9600)


def test_ui_scan_rs232_daisy_propagates_driver_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.SimpleNamespace(GCSDevice=lambda controller: object())
    monkeypatch.setitem(sys.modules, "pipython", fake_module)
    monkeypatch.setattr(
        "psf_scan.drivers.pi_link.scan_rs232_daisy",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(sys, "platform", "win32")

    with pytest.raises(RuntimeError, match="boom"):
        pi_scan.scan_rs232_daisy("C-863", 3, 9600)

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
    class FakeDevice:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    fake_module = types.SimpleNamespace(GCSDevice=lambda controller: FakeDevice())
    monkeypatch.setitem(sys.modules, "pipython", fake_module)
    monkeypatch.setattr(
        "psf_scan.drivers.pi_link.scan_rs232_daisy",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(sys, "platform", "win32")

    with pytest.raises(RuntimeError, match="boom"):
        pi_scan.scan_rs232_daisy("C-863", 3, 9600)


def test_ui_scan_rs232_daisy_closes_device_context(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"entered": False, "exited": False}

    class FakeDevice:
        def __enter__(self):
            state["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            state["exited"] = True

    fake_module = types.SimpleNamespace(GCSDevice=lambda controller: FakeDevice())
    monkeypatch.setitem(sys.modules, "pipython", fake_module)
    monkeypatch.setattr(
        "psf_scan.drivers.pi_link.scan_rs232_daisy",
        lambda *args, **kwargs: ["1 - device"],
    )
    monkeypatch.setattr(sys, "platform", "win32")

    items = pi_scan.scan_rs232_daisy("C-863", 3, 9600)

    assert items == ["1 - device"]
    assert state == {"entered": True, "exited": True}

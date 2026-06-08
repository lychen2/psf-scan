from pathlib import Path
import sys
import tomllib


REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
SPEC = REPO / "installer" / "psf_scan.spec"


def test_pyserial_is_runtime_dependency() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any(dep.startswith("pyserial>=") for dep in deps)
    assert any(dep.startswith("Pillow>=") for dep in deps)
    assert any(dep.startswith("pipython>=") for dep in deps)


def test_pyinstaller_includes_pyserial_modules() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert 'collect_data_files("pipython")' in text
    assert 'PI_GCS2_DLL_x64.dll' in text
    assert 'PI_GCS2_BINARIES' in text
    assert '"pyqtgraph.exporters"' in text
    assert '"pipython"' in text
    assert '"pipython.pidevice.interfaces.gcsdll"' in text
    assert '"serial.tools.list_ports"' in text
    assert '"serial.tools.list_ports_windows"' in text
    assert "support_contact.json" in text


def test_release_workflow_restores_pi_gcs2_dll() -> None:
    text = (REPO / ".github" / "workflows" / "build-and-release.yml").read_text(encoding="utf-8")
    assert "gh release download pi-runtime" in text
    assert "PI_GCS2_DLL_x64.dll was not copied next to PsfScan.exe" in text
    assert "PI_GCS2_DLL_x64.dll was not packaged into _internal" in text


def test_pi_stage_uses_bundled_gcs2_dll(monkeypatch) -> None:
    from psf_scan.drivers.stage_pi import PIStage

    captured = {}

    class FakeGCSDevice:
        def __init__(self, controller, gcsdll=""):
            captured["controller"] = controller
            captured["gcsdll"] = gcsdll

    monkeypatch.setattr(
        "psf_scan.drivers.pi_link.find_bundled_gcs2_dll",
        lambda: Path("C:/app/PI_GCS2_DLL_x64.dll"),
    )

    stage = PIStage(controller="C-863")
    assert stage._make_gcs_device(FakeGCSDevice, "C-863")
    assert captured["controller"] == "C-863"
    assert Path(captured["gcsdll"]) == Path("C:/app/PI_GCS2_DLL_x64.dll")


def test_pi_link_finds_meipass_gcs2_dll(monkeypatch, tmp_path) -> None:
    from psf_scan.drivers import pi_link

    dll = tmp_path / "_internal" / "PI_GCS2_DLL_x64.dll"
    dll.parent.mkdir()
    dll.write_bytes(b"dll")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "_MEIPASS", str(dll.parent), raising=False)

    assert pi_link.find_bundled_gcs2_dll() == dll


def test_pi_link_finds_exe_dir_gcs2_dll(monkeypatch, tmp_path) -> None:
    from psf_scan.drivers import pi_link

    app_dir = tmp_path / "PsfScan"
    app_dir.mkdir()
    dll = app_dir / "PI_GCS2_DLL_x64.dll"
    dll.write_bytes(b"dll")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "PsfScan.exe"))

    assert pi_link.find_bundled_gcs2_dll() == dll


def test_pi_link_finds_launch_dir_gcs2_dll(monkeypatch, tmp_path) -> None:
    from psf_scan.drivers import pi_link

    app_dir = tmp_path / "app"
    cwd = tmp_path / "launch"
    app_dir.mkdir()
    cwd.mkdir()
    dll = cwd / "PI_GCS2_DLL_x64.dll"
    dll.write_bytes(b"dll")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "PsfScan.exe"))
    monkeypatch.chdir(cwd)

    assert pi_link.find_bundled_gcs2_dll() == dll


def test_pi_scan_uses_gcs_device_factory(monkeypatch, tmp_path) -> None:
    from psf_scan.ui import pi_scan

    captured = {}
    app_dir = tmp_path / "PsfScan"
    app_dir.mkdir()
    dll = app_dir / "PI_GCS2_DLL_x64.dll"
    dll.write_bytes(b"dll")

    class FakeGCSDevice:
        def __init__(self, controller, gcsdll=""):
            captured["controller"] = controller
            captured["gcsdll"] = gcsdll

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def EnumerateUSB(self, mask=""):
            return ["SN123"]

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "PsfScan.exe"))
    monkeypatch.setitem(sys.modules, "pipython", type("P", (), {"GCSDevice": FakeGCSDevice}))

    assert pi_scan.enumerate_usb_controllers("C-863") == ["SN123"]
    assert captured["controller"] == "C-863"
    assert Path(captured["gcsdll"]) == dll


def test_pi_stage_formats_missing_gcs2_dll_error() -> None:
    from psf_scan.drivers.stage_pi import PIStage

    stage = PIStage(controller="C-863")
    message = stage._format_connect_error(OSError("C:/app/PI_GCS2_DLL_x64.dll not found"))

    assert "PI_GCS2_DLL_x64.dll not found" in message
    assert "PI Software Suite" in message
    assert "程序目录" in message

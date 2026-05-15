from pathlib import Path
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
    assert '"pyqtgraph.exporters"' in text
    assert '"pipython"' in text
    assert '"pipython.pidevice.interfaces.gcsdll"' in text
    assert '"serial.tools.list_ports"' in text
    assert '"serial.tools.list_ports_windows"' in text
    assert "support_contact.json" in text

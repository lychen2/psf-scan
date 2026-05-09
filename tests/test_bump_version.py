import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "installer" / "bump_version.py"
VERSION_JSON = REPO / "installer" / "version.json"
PYPROJECT = REPO / "pyproject.toml"
VERSION_PY = REPO / "src" / "psf_scan" / "_version.py"


def _read_version_json() -> dict:
    return json.loads(VERSION_JSON.read_text())


def _read_pyproject_version() -> str:
    text = PYPROJECT.read_text()
    for line in text.splitlines():
        if line.startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("version not found in pyproject.toml")


def test_bump_script_syncs_pyproject_and_version_py():
    original = _read_version_json()
    new_value = "9.9.9"
    VERSION_JSON.write_text(
        json.dumps({"version": new_value, "build": "2026-05-09"})
    )
    try:
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=REPO)
        assert _read_pyproject_version() == new_value
        assert (
            f'__version__ = "{new_value}"' in VERSION_PY.read_text()
        )
    finally:
        VERSION_JSON.write_text(json.dumps(original, indent=2) + "\n")
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=REPO)


def test_bump_script_rejects_non_semver(tmp_path):
    original = _read_version_json()
    VERSION_JSON.write_text(
        json.dumps({"version": "not-semver", "build": "2026-05-09"})
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "semver" in (proc.stderr + proc.stdout).lower()
    finally:
        VERSION_JSON.write_text(json.dumps(original, indent=2) + "\n")
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=REPO)

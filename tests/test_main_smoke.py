import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _smoke_env() -> dict:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PSF_SCAN_SMOKE"] = "1"
    return env


def test_module_imports_without_error():
    out = subprocess.run(
        [sys.executable, "-c", "import psf_scan.__main__"],
        cwd=REPO,
        env=_smoke_env(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 0, out.stderr


def test_main_runs_under_smoke_mode():
    out = subprocess.run(
        [sys.executable, "-m", "psf_scan"],
        cwd=REPO,
        env=_smoke_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr

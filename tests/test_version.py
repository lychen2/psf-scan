import json
from pathlib import Path

import psf_scan


def test_package_version_matches_json():
    repo = Path(__file__).resolve().parent.parent
    data = json.loads((repo / "installer" / "version.json").read_text())
    assert psf_scan.__version__ == data["version"]


def test_version_is_semver_like():
    parts = psf_scan.__version__.split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()

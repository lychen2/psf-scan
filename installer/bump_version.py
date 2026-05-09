"""Synchronize the version in installer/version.json to dependent files.

Reads installer/version.json["version"] and rewrites:
  - pyproject.toml             ([project] version = "X.Y.Z")
  - src/psf_scan/_version.py   (__version__ = "X.Y.Z")
  - installer/PsfScan.iss      (#define MyAppVersion "X.Y.Z") if it exists
  - installer/resources/version_info.txt  (PyInstaller VS_VERSIONINFO) if it exists
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_JSON = REPO / "installer" / "version.json"
PYPROJECT = REPO / "pyproject.toml"
VERSION_PY = REPO / "src" / "psf_scan" / "_version.py"
ISS = REPO / "installer" / "PsfScan.iss"
VERSION_INFO = REPO / "installer" / "resources" / "version_info.txt"


def read_target_version() -> str:
    data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    v = data["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise SystemExit(f"version.json version not semver-like: {v!r}")
    return v


def patch_pyproject(v: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new, n = re.subn(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{v}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        raise SystemExit("pyproject.toml: no [project] version line matched")
    if new != text:
        PYPROJECT.write_text(new, encoding="utf-8")


def patch_version_py(v: str) -> None:
    VERSION_PY.write_text(
        '"""Single source of truth for the runtime package version.\n\n'
        "Kept in sync with ``installer/version.json`` by ``installer/bump_version.py``.\n"
        '"""\n\n'
        f'__version__ = "{v}"\n',
        encoding="utf-8",
    )


def patch_iss(v: str) -> None:
    if not ISS.exists():
        return
    text = ISS.read_text(encoding="utf-8")
    new, n = re.subn(
        r'^#define\s+MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion "{v}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        raise SystemExit("PsfScan.iss: no MyAppVersion #define matched")
    if new != text:
        ISS.write_text(new, encoding="utf-8")


def patch_version_info(v: str) -> None:
    if not VERSION_INFO.exists():
        return
    parts = v.split(".")
    tuple_form = f"({parts[0]}, {parts[1]}, {parts[2]}, 0)"
    text = VERSION_INFO.read_text(encoding="utf-8")
    new = re.sub(r"filevers=\([^)]*\)", f"filevers={tuple_form}", text)
    new = re.sub(r"prodvers=\([^)]*\)", f"prodvers={tuple_form}", new)
    new = re.sub(
        r"StringStruct\('FileVersion',\s*'[^']+'\)",
        f"StringStruct('FileVersion', '{v}')",
        new,
    )
    new = re.sub(
        r"StringStruct\('ProductVersion',\s*'[^']+'\)",
        f"StringStruct('ProductVersion', '{v}')",
        new,
    )
    if new != text:
        VERSION_INFO.write_text(new, encoding="utf-8")


def main() -> int:
    v = read_target_version()
    patch_pyproject(v)
    patch_version_py(v)
    patch_iss(v)
    patch_version_info(v)
    print(f"[bump_version] synced -> {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

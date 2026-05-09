"""PSF preset 持久化 I/O。

预设以 JSON 形式存于 ``~/.config/psf-scan/presets/<name>.json``，可手动编辑、
拷贝、版本控制。无关 QSettings — PSF 视图本身已不再自动持久化任何参数。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PRESET_DIR = Path.home() / ".config" / "psf-scan" / "presets"
_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _ensure_dir() -> None:
    PRESET_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(raw: str) -> str:
    """把任意字符串清理成可作文件名的 slug；空串引发 ValueError。"""
    cleaned = _NAME_RE.sub("_", raw.strip()).strip("_")
    if not cleaned:
        raise ValueError("preset 名字必须含字母、数字、下划线或连字符")
    return cleaned[:64]


def list_presets() -> list[str]:
    if not PRESET_DIR.exists():
        return []
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def save_preset(name: str, data: dict[str, Any]) -> Path:
    _ensure_dir()
    safe = safe_name(name)
    path = PRESET_DIR / f"{safe}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def load_preset(name: str) -> dict[str, Any]:
    path = PRESET_DIR / f"{safe_name(name)}.json"
    return json.loads(path.read_text())


def delete_preset(name: str) -> None:
    path = PRESET_DIR / f"{safe_name(name)}.json"
    path.unlink(missing_ok=True)

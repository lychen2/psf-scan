"""Runtime diagnostics for crash and performance investigation."""

from __future__ import annotations

import os
import threading
from pathlib import Path


BYTES_PER_KIB = 1024


def process_snapshot() -> dict[str, object]:
    """Return Linux /proc based process and memory counters."""
    snap = _status_snapshot()
    snap["threading_active"] = threading.active_count()
    snap["open_fds"] = _open_fd_count()
    snap.update(_meminfo_snapshot())
    return snap


def format_kv(data: dict[str, object]) -> str:
    return " ".join(f"{key}={value}" for key, value in data.items())


def _status_snapshot() -> dict[str, object]:
    path = Path("/proc/self/status")
    result: dict[str, object] = {"pid": os.getpid()}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        result["proc_status_error"] = repr(exc)
        return result
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in {"VmRSS", "VmSize", "VmSwap"}:
            result[key.lower() + "_mb"] = _kib_line_to_mb(value)
        elif key == "Threads":
            result["os_threads"] = value.strip()
    return result


def _meminfo_snapshot() -> dict[str, object]:
    path = Path("/proc/meminfo")
    result: dict[str, object] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        result["meminfo_error"] = repr(exc)
        return result
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "SwapFree"}:
            result[key.lower() + "_mb"] = _kib_line_to_mb(value)
    return result


def _kib_line_to_mb(value: str) -> int:
    parts = value.strip().split()
    if not parts:
        return 0
    return int(int(parts[0]) / BYTES_PER_KIB)


def _open_fd_count() -> object:
    try:
        return len(list(Path("/proc/self/fd").iterdir()))
    except OSError as exc:
        return repr(exc)

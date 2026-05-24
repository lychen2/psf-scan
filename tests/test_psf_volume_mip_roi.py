from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from psf_scan.ui.psf_volume_mip_roi import MipRoiOverlay


def test_mip_cache_reuses_same_revision() -> None:
    calls: list[str] = []
    volume = _counting_volume(np.arange(24, dtype=np.float32).reshape(2, 3, 4), calls)
    state = _mip_state()

    first = MipRoiOverlay._mip_for_volume(state, volume, 7)
    second = MipRoiOverlay._mip_for_volume(state, volume, 7)

    assert calls == ["max"]
    np.testing.assert_array_equal(first, second)


def test_mip_cache_refreshes_on_revision_change() -> None:
    calls: list[str] = []
    volume = _counting_volume(np.arange(24, dtype=np.float32).reshape(2, 3, 4), calls)
    state = _mip_state()

    MipRoiOverlay._mip_for_volume(state, volume, 7)
    MipRoiOverlay._mip_for_volume(state, volume, 8)

    assert calls == ["max", "max"]


def test_mip_without_revision_does_not_cache() -> None:
    calls: list[str] = []
    volume = _counting_volume(np.arange(24, dtype=np.float32).reshape(2, 3, 4), calls)
    state = _mip_state()

    MipRoiOverlay._mip_for_volume(state, volume, None)
    MipRoiOverlay._mip_for_volume(state, volume, None)

    assert calls == ["max", "max"]


def _mip_state() -> SimpleNamespace:
    return SimpleNamespace(_mip_cache_key=None, _mip_cache=None)


def _counting_volume(data: np.ndarray, calls: list[str]) -> np.ndarray:
    volume = np.asarray(data).view(_CountingVolume)
    volume.calls = calls
    return volume


class _CountingVolume(np.ndarray):
    calls: list[str]

    def max(self, *args: object, **kwargs: object) -> np.ndarray:
        self.calls.append("max")
        return super().max(*args, **kwargs)

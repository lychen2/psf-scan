from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from psf_scan.ui.psf_view import PSFView


def test_set_data_defers_final_render_until_psf_view_is_visible():
    state = _psf_state(visible=False)

    PSFView._set_stack(
        state,
        np.ones((2, 3, 4), dtype=np.float32),
        np.zeros((2, 3), dtype=np.float32),
        live=False,
    )

    assert state._render_pending
    assert state.refresh_count == 0


def test_set_data_renders_immediately_when_psf_view_is_visible():
    state = _psf_state(visible=True)

    PSFView._set_stack(
        state,
        np.ones((2, 3, 4), dtype=np.float32),
        np.zeros((2, 3), dtype=np.float32),
        live=False,
    )

    assert not state._render_pending
    assert state.refresh_count == 1


def _psf_state(*, visible: bool):
    state = SimpleNamespace(
        _positions=None,
        _volume=None,
        _live=False,
        _render_pending=False,
        refresh_count=0,
    )
    state._controls = SimpleNamespace(set_volume_shape=lambda _shape: None)
    state._live_refresh = SimpleNamespace(start=lambda: None, stop=lambda: None)
    state.isVisible = lambda: visible

    def refresh() -> None:
        state.refresh_count += 1
        state._render_pending = False

    state._refresh_render = refresh
    return state

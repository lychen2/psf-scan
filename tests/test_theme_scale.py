"""UI 缩放 — theme.apply_theme(scale) 与 settings 持久化。"""

from __future__ import annotations

import pytest

QApplication = pytest.importorskip("PySide6.QtWidgets").QApplication

from PySide6.QtCore import QSettings

from psf_scan.ui import theme
from psf_scan.ui.scale import (
    AUTO,
    SCALE_MAX,
    SCALE_MIN,
    clamp_scale,
    effective_scale,
    recommend_scale,
)
from psf_scan.ui.settings import UserSettings


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


def test_apply_theme_scales_tokens(qapp: QApplication) -> None:
    theme.apply_theme(qapp, 1.0)
    base_body = int(theme.SIZE_BODY.rstrip("px"))
    base_meter = int(theme.SIZE_METER.rstrip("px"))

    theme.apply_theme(qapp, 1.5)
    scaled_body = int(theme.SIZE_BODY.rstrip("px"))
    scaled_meter = int(theme.SIZE_METER.rstrip("px"))
    scaled_pt = qapp.font().pointSize()

    assert scaled_body == round(base_body * 1.5)
    assert scaled_meter == round(base_meter * 1.5)
    assert scaled_pt == round(11 * 1.5)
    assert theme.UI_SCALE == pytest.approx(1.5)

    theme.apply_theme(qapp, 1.0)
    assert int(theme.SIZE_BODY.rstrip("px")) == base_body


def test_recommend_scale_returns_within_bounds(qapp: QApplication) -> None:
    v = recommend_scale(qapp)
    assert SCALE_MIN <= v <= SCALE_MAX


def test_clamp_scale_zero_passes_through() -> None:
    assert clamp_scale(0.0) == AUTO
    assert clamp_scale(-1.0) == AUTO
    assert clamp_scale(0.5) == SCALE_MIN
    assert clamp_scale(5.0) == SCALE_MAX
    assert clamp_scale(1.25) == 1.25


def test_effective_scale_auto_uses_recommend(qapp: QApplication) -> None:
    auto = effective_scale(0.0, qapp)
    explicit = effective_scale(1.5, qapp)
    assert auto == recommend_scale(qapp)
    assert explicit == 1.5


def test_settings_ui_scale_round_trip(tmp_path) -> None:
    qs = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    s = UserSettings(qs)
    assert s.ui_scale_pref() == 0.0
    s.set_ui_scale_pref(1.5)
    assert s.ui_scale_pref() == pytest.approx(1.5)
    s.set_ui_scale_pref(0.0)
    assert s.ui_scale_pref() == 0.0

from __future__ import annotations

from psf_scan.ui.camera_advanced import CameraAdvancedBar


class Camera:
    def gamma_range(self) -> tuple[float, float] | None:
        return None

    def get_gamma(self) -> float | None:
        return None

    def black_level_range(self) -> tuple[int, int] | None:
        return None

    def get_black_level(self) -> int | None:
        return None

    def frame_rate_range(self) -> tuple[float, float] | None:
        return (1.0, 120.0)

    def get_frame_rate(self) -> float | None:
        return 30.0

    def pixel_formats(self) -> tuple[str, ...]:
        return ()

    def get_pixel_format(self) -> str | None:
        return None


def test_fps_change_emits_immediately(qtbot):
    bar = CameraAdvancedBar()
    qtbot.addWidget(bar)
    seen: list[float] = []
    bar.frame_rate_changed.connect(seen.append)

    bar.configure(camera=Camera())
    bar.sp_fps.setValue(45.0)

    assert seen == [45.0]


def test_configure_does_not_emit_fps_change(qtbot):
    bar = CameraAdvancedBar()
    qtbot.addWidget(bar)
    seen: list[float] = []
    bar.frame_rate_changed.connect(seen.append)

    bar.configure(camera=Camera())

    assert seen == []

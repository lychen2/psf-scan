from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from psf_scan.ui import psf_plot
from psf_scan.ui.colormap_resolver import resolve_or_default
from psf_scan.ui.psf_plot import ImageSurface
from psf_scan.ui.psf_render import MODE_ORTHO, RenderImage, RenderOptions
from psf_scan.ui.psf_volume_compute import layer_color


def test_surface_layer_color_uses_selected_colormap():
    expected = resolve_or_default("viridis").map([0.5], mode="float")[0]

    color = layer_color(0.5, 0.7, "viridis")

    assert color == (
        float(expected[0]),
        float(expected[1]),
        float(expected[2]),
        0.7,
    )


def test_psf_colorbars_update_on_reused_image_surface(monkeypatch):
    calls: list[tuple[tuple[float, float], str]] = []

    def record_update(bar, *, item, cmap, levels):
        calls.append((levels, getattr(cmap, "name", "")))

    monkeypatch.setattr(psf_plot, "_update_colorbar", record_update)
    options = _options()
    surface = SimpleNamespace(
        _items={0: _FakeImageItem()},
        _plots={0: _FakePlot()},
        _locator_items={},
        _rects={},
        _colorbars={0: object()},
    )

    ImageSurface._update_images(
        surface,
        [_image("A", np.zeros((2, 2), dtype=np.float32))],
        levels=(2.0, 8.0),
        cmap=resolve_or_default("magma"),
        options=options,
    )

    assert calls[-1][0] == (2.0, 8.0)


def _image(title: str, data: np.ndarray) -> RenderImage:
    return RenderImage(
        title=title,
        image=data,
        x_label="x",
        y_label="y",
        locator=None,
        aspect_locked=True,
        rect=(-0.5, -0.5, 2.0, 2.0),
    )


def _options() -> RenderOptions:
    return RenderOptions(
        mode=MODE_ORTHO,
        slice_index=0,
        auto_levels=True,
        level_min=0.0,
        level_max=1.0,
        show_colorbar=True,
        show_labels=True,
        show_locator=False,
        volume_threshold=0.3,
        volume_step=3,
    )


class _FakeImageItem:
    def setImage(self, *_args, **_kwargs) -> None:
        pass

    def setLevels(self, *_args, **_kwargs) -> None:
        pass

    def setLookupTable(self, *_args, **_kwargs) -> None:
        pass

    def setRect(self, *_args, **_kwargs) -> None:
        pass


class _FakePlot:
    items: list = []

    def setTitle(self, *_args, **_kwargs) -> None:
        pass

    def removeItem(self, *_args, **_kwargs) -> None:
        pass

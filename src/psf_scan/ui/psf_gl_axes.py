"""OpenGL coordinate axes and base mesh planes."""

from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph.Qt import QtGui

from .psf_gl_grid_overlay import GLGridOverlayItem


AXIS_OUTSIDE_GAP_FRACTION = 0.18
AXIS_TICK_COUNT = 5
# 奇数划分避免 GLGridItem 的中线穿过网格中心（5 段 → 6 条线，无穿心线）。
BASE_GRID_DIVISIONS = 5
TITLE_OFFSET_FRACTION = 0.10
BASE_GRID_COLOR = (60, 62, 70, 220)
BASE_GRID_WIDTH = 1.6
AXIS_OVERLAY_DEPTH = 100.0
TICK_OFFSET_FRACTION = 0.045
TITLE_FONT_PT = 11
TICK_FONT_PT = 9
MIN_AXIS_LENGTH = 1.0
MIN_AXIS_SPAN = 1e-3


def create_axis_titles() -> list[gl.GLTextItem]:
    font = QtGui.QFont("Helvetica", TITLE_FONT_PT)
    titles = [
        gl.GLTextItem(text="x [px]", color=(70, 120, 255, 255), font=font),
        gl.GLTextItem(text="y [px]", color=(255, 210, 60, 255), font=font),
        gl.GLTextItem(text="z [um]", color=(60, 200, 90, 255), font=font),
    ]
    for title in titles:
        title.setDepthValue(AXIS_OVERLAY_DEPTH)
    return titles


def create_axis_ticks(count: int) -> list[gl.GLTextItem]:
    font = QtGui.QFont("Helvetica", TICK_FONT_PT)
    ticks = [gl.GLTextItem(text="", color=(205, 210, 215, 255), font=font) for _ in range(count)]
    for tick in ticks:
        tick.setDepthValue(AXIS_OVERLAY_DEPTH)
    return ticks


def create_base_grids() -> list[GLGridOverlayItem]:
    grids: list[GLGridOverlayItem] = []
    for _ in range(3):
        g = GLGridOverlayItem(color=BASE_GRID_COLOR, width=BASE_GRID_WIDTH)
        g.setDepthValue(AXIS_OVERLAY_DEPTH)
        grids.append(g)
    return grids


def apply_axis_layout(
    axis: gl.GLAxisItem,
    titles: list[gl.GLTextItem],
    ticks: list[gl.GLTextItem],
    grids: list[GLGridOverlayItem],
    bounds: tuple[np.ndarray, np.ndarray],
    *,
    z_um_per_display: float,
    z_um_at_display_zero: float,
) -> tuple[np.ndarray, np.ndarray]:
    origin, axis_size = axis_frame(bounds)
    axis.resetTransform()
    axis.translate(float(origin[0]), float(origin[1]), float(origin[2]))
    axis.setSize(x=float(axis_size[0]), y=float(axis_size[1]), z=float(axis_size[2]))
    _set_base_grids(grids, origin, axis_size)
    _set_axis_titles(titles, origin, axis_size)
    _set_axis_ticks(ticks, origin, axis_size, z_um_per_display, z_um_at_display_zero)
    return origin, axis_size


def axis_frame(bounds: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    mins, maxs = bounds
    span = np.maximum(maxs - mins, MIN_AXIS_SPAN)
    max_span = float(np.max(span))
    gap = max(max_span * AXIS_OUTSIDE_GAP_FRACTION, MIN_AXIS_LENGTH)
    origin = mins - gap
    axis_size = np.maximum(span + gap * 2.0, MIN_AXIS_LENGTH)
    return origin, axis_size


def _set_base_grids(items: list[GLGridOverlayItem], origin: np.ndarray, axis_size: np.ndarray) -> None:
    _set_grid_xy(items[0], origin, axis_size)
    _set_grid_xz(items[1], origin, axis_size)
    _set_grid_yz(items[2], origin, axis_size)


def _set_grid_xy(item: GLGridOverlayItem, origin: np.ndarray, axis_size: np.ndarray) -> None:
    xs = _grid_values(float(origin[0]), float(axis_size[0]))
    ys = _grid_values(float(origin[1]), float(axis_size[1]))
    pos = _plane_segments(axis=2, fixed=float(origin[2]), u_values=xs, v_values=ys)
    item.set_segments(pos)


def _set_grid_xz(item: GLGridOverlayItem, origin: np.ndarray, axis_size: np.ndarray) -> None:
    xs = _grid_values(float(origin[0]), float(axis_size[0]))
    zs = _grid_values(float(origin[2]), float(axis_size[2]))
    pos = _plane_segments(axis=1, fixed=float(origin[1]), u_values=xs, v_values=zs)
    item.set_segments(pos)


def _set_grid_yz(item: GLGridOverlayItem, origin: np.ndarray, axis_size: np.ndarray) -> None:
    ys = _grid_values(float(origin[1]), float(axis_size[1]))
    zs = _grid_values(float(origin[2]), float(axis_size[2]))
    pos = _plane_segments(axis=0, fixed=float(origin[0]), u_values=ys, v_values=zs)
    item.set_segments(pos)


def _grid_values(start: float, length: float) -> np.ndarray:
    step = max(float(length) / BASE_GRID_DIVISIONS, MIN_AXIS_SPAN)
    count = BASE_GRID_DIVISIONS + 1
    return start + step * np.arange(count, dtype=np.float32)


def _plane_segments(axis: int, fixed: float, u_values: np.ndarray, v_values: np.ndarray) -> np.ndarray:
    first = _segment_set(axis, fixed, u_values, float(v_values[0]), float(v_values[-1]), flip=False)
    second = _segment_set(axis, fixed, v_values, float(u_values[0]), float(u_values[-1]), flip=True)
    return np.vstack((first, second)).astype(np.float32, copy=False)


def _segment_set(
    axis: int,
    fixed: float,
    values: np.ndarray,
    start: float,
    end: float,
    *,
    flip: bool,
) -> np.ndarray:
    segments = np.zeros((len(values) * 2, 3), dtype=np.float32)
    segments[:, axis] = fixed
    u_axis, v_axis = _plane_axes(axis)
    segments[0::2, u_axis if not flip else v_axis] = values
    segments[1::2, u_axis if not flip else v_axis] = values
    segments[0::2, v_axis if not flip else u_axis] = start
    segments[1::2, v_axis if not flip else u_axis] = end
    return segments


def _plane_axes(axis: int) -> tuple[int, int]:
    if axis == 0:
        return 1, 2
    if axis == 1:
        return 0, 2
    return 0, 1


def _set_axis_titles(items: list[gl.GLTextItem], origin: np.ndarray, axis_size: np.ndarray) -> None:
    # 沿轴推到末端再向外退一点 perpendicular，避免和末端 tick 数字"347.5"
    # 这种长字符串在屏上撞到一起。
    along = float(np.max(axis_size)) * TITLE_OFFSET_FRACTION
    perp = along * 0.55
    items[0].setData(pos=np.array((origin[0] + axis_size[0] + along, origin[1] - perp, origin[2]), dtype=np.float32))
    items[1].setData(pos=np.array((origin[0] - perp, origin[1] + axis_size[1] + along, origin[2]), dtype=np.float32))
    items[2].setData(pos=np.array((origin[0] - perp, origin[1] - perp, origin[2] + axis_size[2] + along), dtype=np.float32))


def _set_axis_ticks(
    items: list[gl.GLTextItem],
    origin: np.ndarray,
    axis_size: np.ndarray,
    z_um_per_display: float,
    z_um_at_display_zero: float,
) -> None:
    font = QtGui.QFont("Helvetica", TICK_FONT_PT)
    tick_index = 0
    for axis in range(3):
        tick_index = _set_axis_tick_group(items, tick_index, axis, origin, axis_size, z_um_per_display, z_um_at_display_zero, font)
    for i in range(tick_index, len(items)):
        items[i].setData(text="")


def _set_axis_tick_group(
    items: list[gl.GLTextItem],
    start_index: int,
    axis: int,
    origin: np.ndarray,
    axis_size: np.ndarray,
    z_um_per_display: float,
    z_um_at_display_zero: float,
    font: QtGui.QFont,
) -> int:
    tick_index = start_index
    offset = _tick_label_offset(axis, axis_size)
    for dist in np.linspace(0.0, float(axis_size[axis]), AXIS_TICK_COUNT):
        if tick_index >= len(items):
            return tick_index
        pos = _tick_label_pos(axis, float(dist), origin, offset)
        label_value = _tick_label_value(axis, origin[axis] + dist, z_um_per_display, z_um_at_display_zero)
        items[tick_index].setData(pos=pos, text=_format_tick(label_value), font=font)
        tick_index += 1
    return tick_index


def _tick_label_pos(axis: int, dist: float, origin: np.ndarray, offset: np.ndarray) -> np.ndarray:
    pos = np.array((origin[0], origin[1], origin[2]), dtype=np.float32)
    pos[axis] += dist
    return pos + offset


def _tick_label_offset(axis: int, axis_size: np.ndarray) -> np.ndarray:
    gap = max(float(np.max(axis_size)) * TICK_OFFSET_FRACTION, MIN_AXIS_LENGTH)
    if axis == 0:
        return np.array((0.0, -gap, -gap * 0.25), dtype=np.float32)
    if axis == 1:
        return np.array((gap * 0.55, 0.0, -gap * 0.25), dtype=np.float32)
    return np.array((-gap * 0.75, -gap * 0.75, 0.0), dtype=np.float32)


def _tick_label_value(axis: int, display_value: float, z_um_per_display: float, z_um_at_display_zero: float) -> float:
    if axis == 2:
        return display_value * z_um_per_display + z_um_at_display_zero
    return display_value


def _format_tick(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.1f}"

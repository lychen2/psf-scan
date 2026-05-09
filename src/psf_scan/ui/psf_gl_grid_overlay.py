"""Screen-space grid overlay for pyqtgraph OpenGL views."""

from __future__ import annotations

import numpy as np
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem


CLIP_W_EPSILON = 1e-5
NDC_LIMIT = 1.0


class GLGridOverlayItem(GLGraphicsItem):
    """Draw 3D grid segments through Qt after projecting them to screen space."""

    def __init__(
        self,
        *,
        color: tuple[int, int, int, int],
        width: float,
    ) -> None:
        super().__init__()
        self._segments = np.zeros((0, 3), dtype=np.float32)
        self._pen = _pen(color, width)

    def set_segments(self, segments: np.ndarray) -> None:
        self._segments = np.ascontiguousarray(segments, dtype=np.float32)
        self.update()

    def paint(self) -> None:
        if len(self._segments) < 2:
            return
        projected = self._project_segments()
        if not projected:
            return
        painter = QtGui.QPainter(self.view())
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(self.view().rect())
        painter.setPen(self._pen)
        painter.drawLines(projected)
        painter.end()

    def _project_segments(self) -> list[QtCore.QLineF]:
        mvp = _matrix_array(self.mvpMatrix())
        viewport = QtCore.QRectF(self.view().rect())
        lines: list[QtCore.QLineF] = []
        for start, end in self._segments.reshape((-1, 2, 3)):
            line = _project_line(viewport, mvp, start, end)
            if line is not None:
                lines.append(line)
        return lines


def _project_line(
    viewport: QtCore.QRectF,
    mvp: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> QtCore.QLineF | None:
    p0 = _project_ndc(mvp, start)
    p1 = _project_ndc(mvp, end)
    if p0 is None or p1 is None or _outside_same_ndc_side(p0, p1):
        return None
    return QtCore.QLineF(_viewport_point(viewport, p0), _viewport_point(viewport, p1))


def _matrix_array(matrix: QtGui.QMatrix4x4) -> np.ndarray:
    return np.asarray(matrix.data(), dtype=np.float32).reshape(4, 4).T


def _project_ndc(mvp: np.ndarray, point: np.ndarray) -> np.ndarray | None:
    vector = np.array((float(point[0]), float(point[1]), float(point[2]), 1.0), dtype=np.float32)
    clip = mvp @ vector
    w = float(clip[3])
    if w <= CLIP_W_EPSILON:
        return None
    ndc = np.array((float(clip[0]) / w, float(clip[1]) / w, float(clip[2]) / w), dtype=np.float32)
    return ndc if np.all(np.isfinite(ndc)) else None


def _outside_same_ndc_side(p0: np.ndarray, p1: np.ndarray) -> bool:
    return bool(
        (p0[0] < -NDC_LIMIT and p1[0] < -NDC_LIMIT)
        or (p0[0] > NDC_LIMIT and p1[0] > NDC_LIMIT)
        or (p0[1] < -NDC_LIMIT and p1[1] < -NDC_LIMIT)
        or (p0[1] > NDC_LIMIT and p1[1] > NDC_LIMIT)
        or (p0[2] < -NDC_LIMIT and p1[2] < -NDC_LIMIT)
        or (p0[2] > NDC_LIMIT and p1[2] > NDC_LIMIT)
    )


def _viewport_point(viewport: QtCore.QRectF, ndc: np.ndarray) -> QtCore.QPointF:
    x = viewport.left() + (float(ndc[0]) + 1.0) * viewport.width() / 2.0
    y = viewport.bottom() - (float(ndc[1]) + 1.0) * viewport.height() / 2.0
    return QtCore.QPointF(x, y)


def _pen(color: tuple[int, int, int, int], width: float) -> QtGui.QPen:
    pen = QtGui.QPen(QtGui.QColor(*color))
    pen.setWidthF(float(width))
    pen.setCosmetic(True)
    return pen

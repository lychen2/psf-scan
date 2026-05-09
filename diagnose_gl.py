"""GL 真实渲染诊断：用实际 pyqtgraph GLViewWidget 渲染并截图，
跟之前 matplotlib 版本对比，看 app 里实际看到的是不是同一个东西。
"""
from __future__ import annotations
import os, sys, time
import h5py
import numpy as np
import pyqtgraph as pg

sys.path.insert(0, "src")
from psf_scan.ui.psf_volume_compute import (
    iso_levels, layer_alpha, layer_color,
    prepare_volume, interp_z_positions, display_vertices,
)
from psf_scan.ui.psf_render import RenderOptions, MODE_VOLUME

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import pyqtgraph.opengl as gl


def load_latest():
    base = "psf_data"
    latest = sorted(os.listdir(base))[-1]
    with h5py.File(f"{base}/{latest}/stack.h5", "r") as f:
        return f["frames"][...], f["positions"][...], latest


def make_options(threshold=0.30, layers=3):
    return RenderOptions(
        mode=MODE_VOLUME, slice_index=0, auto_levels=True,
        level_min=0.0, level_max=1.0, show_colorbar=True,
        show_labels=True, show_locator=True,
        volume_threshold=threshold, volume_step=layers,
    )


def render_for(threshold, layer_count, save_path):
    frames, positions, name = load_latest()
    opts = make_options(threshold, layer_count)
    iso = iso_levels(opts, live=False)
    levels = (float(frames.min()), float(frames.max()))
    prepared = prepare_volume(frames.astype(np.float32), levels, live=False)
    z_pos = interp_z_positions(positions[:, 2], live=False)

    view = gl.GLViewWidget()
    view.resize(700, 500)
    view.setBackgroundColor("#f7f5ef")

    print(f"\n=== layers={layer_count}, threshold={threshold} → iso={iso} ===")
    for i, level in enumerate(iso):
        verts, faces = pg.isosurface(np.ascontiguousarray(prepared), float(level))
        if len(verts) == 0:
            print(f"  layer {i}: iso={level:.3f}  EMPTY")
            continue
        alpha = layer_alpha(i, len(iso))
        color = layer_color(i, len(iso), alpha)
        print(f"  layer {i}: iso={level:.3f} alpha={alpha:.2f} color={tuple(round(c,2) for c in color)}  verts={len(verts)}")
        disp = display_vertices(verts, prepared.shape, z_pos)
        md = gl.MeshData(vertexes=disp.astype(np.float32), faces=np.ascontiguousarray(faces))
        item = gl.GLMeshItem(meshdata=md, smooth=True, drawEdges=False,
                             color=color, shader=None, glOptions="translucent")
        view.addItem(item)

    grid = gl.GLGridItem()
    span = max(prepared.shape[1], prepared.shape[2])
    grid.setSize(x=span, y=span)
    view.addItem(grid)
    view.setCameraPosition(distance=span * 1.8, elevation=28, azimuth=-38)

    view.show()
    app.processEvents()
    QTimer.singleShot(50, app.quit)
    app.exec()
    img = view.grabFramebuffer()
    img.save(save_path)
    print(f"saved: {save_path}")
    view.close()


if __name__ == "__main__":
    render_for(0.30, 1, "diagnose_gl_l1.png")
    render_for(0.30, 2, "diagnose_gl_l2.png")
    render_for(0.30, 3, "diagnose_gl_l3.png")
    render_for(0.30, 5, "diagnose_gl_l5.png")

"""抓 OpenGLSurfaceView 中"不动的中心线"的来源。

策略：拿 psf_data 最新一份数据跑通一次 IsosurfaceWorker，把结果塞进
OpenGLSurfaceView。不仅记录所有 addItem 后的项目（含子项），还在画完
后逐项注释掉再截一次图，看哪个 item 是"中心线"。
"""
from __future__ import annotations

import os
import sys

import h5py
import numpy as np
import pyqtgraph as pg

sys.path.insert(0, "src")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

import pyqtgraph.opengl as gl
from psf_scan.ui.psf_render import MODE_VOLUME, RenderOptions
from psf_scan.ui.psf_volume import OpenGLSurfaceView
from psf_scan.ui.psf_volume_compute import IsosurfaceWorker


def load_latest():
    base = "psf_data"
    latest = sorted(os.listdir(base))[-1]
    with h5py.File(f"{base}/{latest}/stack.h5", "r") as f:
        return f["frames"][...].astype(np.float32), f["positions"][...]


def make_options(threshold=0.30, layers=3):
    return RenderOptions(
        mode=MODE_VOLUME, slice_index=0, auto_levels=True,
        level_min=0.0, level_max=1.0, show_colorbar=False,
        show_labels=True, show_locator=True,
        volume_threshold=threshold, volume_step=layers,
    )


def render_one(threshold, layers, save_path):
    frames, positions = load_latest()
    levels = (float(frames.min()), float(frames.max()))
    options = make_options(threshold, layers)

    view = OpenGLSurfaceView()
    view.resize(800, 600)
    view.show()

    worker = IsosurfaceWorker(
        volume=frames, levels=levels, options=options,
        z_positions=positions[:, 2], live=False, generation=1,
    )
    received = []
    worker.signals.done.connect(lambda gen, layers, shape: received.append((gen, layers, shape)))
    worker.run()
    gen, layers_out, shape = received[0]
    print(f"\n[t={threshold} L={layers}] {len(layers_out)} layers, shape={shape}")
    for i, l in enumerate(layers_out):
        print(f"  layer {i}: alpha={l.color[3]:.2f} verts={len(l.vertices)} faces={len(l.faces)}")
    view.set_layers(layers_out, shape)

    app.processEvents()
    QTimer.singleShot(50, app.quit)
    app.exec()
    img = view.grabFramebuffer()
    img.save(save_path)
    print(f"saved: {save_path}")
    view.close()


def main():
    render_one(0.30, 3, "diag_iso_t030_l3.png")
    render_one(0.10, 3, "diag_iso_t010_l3.png")
    render_one(0.50, 3, "diag_iso_t050_l3.png")
    render_one(0.30, 1, "diag_iso_t030_l1.png")


if __name__ == "__main__":
    main()

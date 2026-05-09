"""诊断脚本：用真实扫描数据跑一遍 iso 管线，渲染每层 + 复合图。"""
from __future__ import annotations

import os
import sys

import h5py
import numpy as np
import pyqtgraph as pg
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, "src")
from psf_scan.ui.psf_volume_compute import (
    iso_levels, layer_alpha, layer_color,
    prepare_volume, interp_z_positions, display_vertices,
    SURFACE_SCALE,
)
from psf_scan.ui.psf_render import RenderOptions, MODE_VOLUME


def load_latest():
    base = "psf_data"
    latest = sorted(os.listdir(base))[-1]
    path = os.path.join(base, latest, "stack.h5")
    print(f"[load] {path}")
    with h5py.File(path, "r") as f:
        frames = f["frames"][...]
        positions = f["positions"][...]
    return frames, positions, latest


def make_options(threshold=0.30, layers=3):
    return RenderOptions(
        mode=MODE_VOLUME, slice_index=0, auto_levels=True,
        level_min=0.0, level_max=1.0, show_colorbar=True,
        show_labels=True, show_locator=True,
        volume_threshold=threshold, volume_step=layers,
    )


def render_layer(ax, vertices, faces, color, title):
    if len(vertices) == 0 or len(faces) == 0:
        ax.set_title(f"{title}\n(empty)")
        ax.set_axis_off()
        return
    triangles = vertices[faces]
    poly = Poly3DCollection(
        triangles, facecolors=[color], edgecolors="none", linewidths=0
    )
    ax.add_collection3d(poly)
    # bbox
    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    span = (maxs - mins).max() / 2 + 1
    ctr = (mins + maxs) / 2
    ax.set_xlim(ctr[0]-span, ctr[0]+span)
    ax.set_ylim(ctr[1]-span, ctr[1]+span)
    ax.set_zlim(ctr[2]-span, ctr[2]+span)
    ax.set_title(f"{title}\nverts={len(vertices)} faces={len(faces)}")
    ax.set_box_aspect([1,1,1])


def main():
    frames, positions, name = load_latest()
    print(f"[data] {name}: frames={frames.shape} positions={positions.shape}")
    print(f"[data] frame value range: [{frames.min():.3f}, {frames.max():.3f}]")

    levels = (float(frames.min()), float(frames.max()))
    options = make_options(threshold=0.30, layers=3)
    iso = iso_levels(options, live=False)
    print(f"[iso] threshold=0.30, layers=3 → {iso}")

    prepared = prepare_volume(frames.astype(np.float32), levels, live=False)
    print(f"[prepare] full prepared shape: {prepared.shape} "
          f"range=[{prepared.min():.3f}, {prepared.max():.3f}]")

    z_pos_full = interp_z_positions(positions[:, 2], live=False)

    print(f"\n[run] pg.isosurface for each layer:")
    layers_data = []
    for i, level in enumerate(iso):
        vertices, faces = pg.isosurface(np.ascontiguousarray(prepared), float(level))
        alpha = layer_alpha(i, len(iso))
        color = layer_color(i, len(iso), alpha)
        nv = len(vertices); nf = len(faces) if len(vertices) else 0
        print(f"  layer {i}: iso={level:.3f} alpha={alpha:.2f} "
              f"color={tuple(round(c,2) for c in color)} verts={nv} faces={nf}")
        if nv > 0:
            disp = display_vertices(vertices, prepared.shape, z_pos_full)
            layers_data.append((disp, np.asarray(faces), color, level))
        else:
            layers_data.append((np.zeros((0,3)), np.zeros((0,3),dtype=int), color, level))

    fig = plt.figure(figsize=(16, 5))
    for i, (verts, faces, color, level) in enumerate(layers_data):
        ax = fig.add_subplot(1, len(layers_data) + 1, i + 1, projection='3d')
        render_layer(ax, verts, faces, color, f"iso={level:.2f}")

    # composite
    ax = fig.add_subplot(1, len(layers_data) + 1, len(layers_data) + 1, projection='3d')
    all_verts = []
    for verts, faces, color, level in layers_data:
        if len(verts) == 0:
            continue
        triangles = verts[faces]
        poly = Poly3DCollection(
            triangles, facecolors=[color], edgecolors="none", linewidths=0
        )
        ax.add_collection3d(poly)
        all_verts.append(verts)
    if all_verts:
        all_v = np.concatenate(all_verts, axis=0)
        mins = all_v.min(axis=0); maxs = all_v.max(axis=0)
        span = (maxs - mins).max() / 2 + 1
        ctr = (mins + maxs) / 2
        ax.set_xlim(ctr[0]-span, ctr[0]+span)
        ax.set_ylim(ctr[1]-span, ctr[1]+span)
        ax.set_zlim(ctr[2]-span, ctr[2]+span)
    ax.set_title("composite")
    ax.set_box_aspect([1,1,1])

    out = "diagnose_iso.png"
    plt.tight_layout()
    plt.savefig(out, dpi=110)
    print(f"\n[save] {out}")


if __name__ == "__main__":
    main()

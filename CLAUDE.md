# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run/Test

```bash
# Dev install (editable)
python -m venv .venv && source .venv/bin/activate && python -m pip install -e .

# Run
python -m psf_scan

# Syntax check (fast, no Qt needed)
python -m compileall -q src

# Run all tests (headless -- conftest.py sets QT_QPA_PLATFORM=offscreen)
python -m pytest -q

# Run a single test file or test
python -m pytest tests/test_phase.py
python -m pytest tests/test_phase.py::test_specific_name

# Smoke-test that the GUI can at least import (sets PSF_SCAN_SMOKE=1 internally)
python -m pytest tests/test_main_smoke.py

# Check for missing i18n keys
comm -23 <(rg -No 'tr\("[a-z][a-z_.]*"' src | sed -E 's/.*tr\("([^"]*)".*/\1/' | sort -u) <(rg -No '"[a-z][a-z_.]*"\s*:' src/psf_scan/core/i18n.py | sed -E 's/:$//' | sort -u)
```

Dependencies: PySide6, pyqtgraph, PyOpenGL, numpy, h5py, tifffile, scipy, matplotlib, Pillow, pipython, pyserial. Optional: pytest, pytest-qt.

## Architecture

### Layered design

```
__main__.py  →  _bootstrap.py (crash handler, logging, splash)
            →  app.py (MainWindow: orchestrator, owns all state)
                 ├── ui/       (Qt widgets, zero direct device I/O)
                 ├── core/     (abstract interfaces + pure business logic)
                 └── drivers/  (concrete hardware implementations)
```

**core/** defines abstract interfaces (`StageBase`, `CameraBase`) and pure logic (`Scanner`, `SafetyLimits`, `data_io`, `CalibrationConfig`, `i18n.tr`). core/ must not import from drivers/ or ui/.

**drivers/** implement `StageBase` and `CameraBase` from core. Current hardware drivers: `PIStage` (pipython-based), `MVSCamera` (Hikvision MVS SDK). Mock drivers: `MockStage`, `MockCamera` (with `mock-interference` mode for interferometry testing).

**ui/** contains all Qt widgets. Widgets communicate with app.py via PySide6 signals/slots only — they never call device methods directly. Key widgets: `CameraView` (live feed + controls), `StageView` (XY+Z position plot), `PSFView` (stack visualization with 2D/3D/volume modes), `ControlPanel` (device selection, jog, scan plan), `PhaseView` (interferometry phase reconstruction).

**app.py** (`MainWindow`) is the central orchestrator. It owns `_stage`, `_camera`, `_scanner`, `_scan_thread`, `_save_thread`, `_af_thread` (autofocus). All cross-cutting concerns — safety checks, device lifecycle, thread management, error routing — live here.

### Driver registration

To add a new stage/camera driver:
1. Implement `StageBase` or `CameraBase` in `drivers/`
2. Add the string name to `AVAILABLE_STAGES` or `AVAILABLE_CAMERAS` in `core/stage.py` or `core/camera.py`
3. Add a factory branch in `make_stage()` / `make_camera()`

### Safety: two-layer protection

1. **SafetyLimits** (core/safety.py): 6 user-configurable soft limits (`x/y/z min/max`), enforced by app.py before any move/scan. Checks in `_check_start_state()`, `_check_target()`, `_check_path()`. Default ±100 µm.
2. **TravelGuard** (drivers/pi_travel.py): Hardware-level guard inside `PIStage` that clamps/drops moves outside the controller's physical travel range. App.py checks `hw_travel_z_um` independently.

Additional safety: single large Z-move confirmation dialog (default threshold 1mm), E-STOP (Esc/Space/button) cancels scan + autofocus + stops stage.

### Coordinate frames

User coordinates (µm, user-adjustable zero) vs hardware coordinates (controller raw). `user_to_hw()` maps between them. `invert_z` negates Z at the driver level. Soft limits operate in hardware frame; scan plans are user frame.

### Scan pipeline

1. `ControlPanel` emits `scan_started(ScanParams)`
2. `MainWindow._on_scan_start`: validate path against safety limits → open `StreamingScanWriter` (C.4: writes `stack.h5` frames as they arrive, crash-resilient) → create `Scanner` on `QThread`
3. `Scanner.run()`: iterate path points, `move_to` + `grab_one` (multiple samples averaged per point). Emits `progress`, `frame_acquired`, `finished`/`canceled`/`error`.
4. `_on_done`: finalize streaming writer attrs → launch `_SaveWorker` on another QThread to write tif/mat/csv/meta.json → emit `STATE_SAVED`
5. Time-series mode: `_repeat_total > 1` auto-restarts scan after configurable interval.

### Data formats

Each scan saves to a timestamped subdirectory under the configured data folder (default: `~/Documents/PSF Scan`). Contains: `stack.h5` (HDF5, streaming-written), `stack.tif` (tifffile), `stack.mat` (scipy), `positions.csv`, `meta.json`. Snapshots save TIFF+PNG+CSV+JSON.

### i18n

All UI text goes through `tr(key, **fmt)` from `core/i18n.py`. Key format: `domain.name` (e.g., `panel.connect`, `safety.move_refused`). Supported languages: zh (default), en. Language switch requires restart.

### Design system (DESIGN.md, PRODUCT.md)

Warm neutral palette (Paper/Panel/Surface tones), zero border-radius, 1px rules, no shadows/gradients/blur, mono typography for numeric values, Signal blue for primary actions/current focus, Sampled green for completed scan points. Violations to watch for: dark backgrounds, border-radius > 0, shadows, decorative gradients, animations > 200ms, using volume shell red for UI chrome.

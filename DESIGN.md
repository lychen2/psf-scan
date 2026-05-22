---
name: PSF Scan
description: MVS-inspired industrial camera acquisition console for PySide6 / pyqtgraph PSF scanning.
colors:
  graphite-void: "#121417"
  graphite-bar: "#1a1d21"
  graphite-panel: "#23272d"
  graphite-field: "#2d3238"
  graphite-hover: "#373d45"
  graphite-rule-soft: "#3f454d"
  graphite-rule-firm: "#59616b"
  ink-strong: "#f1eee7"
  ink: "#d9d4ca"
  ink-muted: "#c1beb5"
  ink-dim: "#9ca2aa"
  mvs-orange: "#f08a24"
  mvs-orange-hi: "#ffad45"
  mvs-orange-lo: "#bf661b"
  sampled: "#72a99b"
  danger: "#d76f63"
  danger-hi: "#e58a7c"
  danger-lo: "#a94c43"
  warn: "#e4b04f"
  canvas-paper: "#f2f0e9"
  canvas-rule: "#c9c4b8"
  canvas-ink: "#202326"
  plot-locator: "#2f73a3"
  volume-grid: "#c8d5d7"
  volume-shell-1: "#f0a6a0"
  volume-shell-2: "#db7069"
  volume-shell-3: "#b84642"
  volume-shell-4: "#842a2d"
  volume-shell-5: "#4d161e"
  volume-core: "#101010"
typography:
  section:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "1.6px"
  body:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 400
  value:
    fontFamily: "Iosevka Term, JetBrains Mono, Cascadia Mono, Fira Code, DejaVu Sans Mono, Menlo, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 500
  control-value:
    fontFamily: "Iosevka Term, JetBrains Mono, Cascadia Mono, Fira Code, DejaVu Sans Mono, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
  meter:
    fontFamily: "Iosevka Term, JetBrains Mono, Cascadia Mono, Fira Code, DejaVu Sans Mono, Menlo, Consolas, monospace"
    fontSize: "10px"
    fontWeight: 400
  button:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.6px"
rounded:
  none: "0px"
spacing:
  hairline: "1px"
  g-4: "4px"
  g-8: "8px"
  g-12: "12px"
  g-16: "16px"
  g-24: "24px"
  panel-gutter: "18px"
components:
  button:
    backgroundColor: "{colors.graphite-field}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "5px 12px"
    height: "24px"
  button-primary:
    backgroundColor: "{colors.mvs-orange}"
    textColor: "{colors.graphite-void}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "5px 12px"
    height: "24px"
  spinbox:
    backgroundColor: "{colors.graphite-void}"
    textColor: "{colors.ink-strong}"
    typography: "{typography.control-value}"
    rounded: "{rounded.none}"
    padding: "4px 6px"
    height: "24px"
  combobox:
    backgroundColor: "{colors.graphite-void}"
    textColor: "{colors.ink}"
    typography: "{typography.control-value}"
    rounded: "{rounded.none}"
    padding: "4px 8px"
    height: "24px"
  progressbar:
    backgroundColor: "{colors.graphite-void}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.none}"
    height: "10px"
  tab-selected:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.ink-strong}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
---

# Design System: PSF Scan

## 1. Overview

**Creative North Star: "The MVS Acquisition Bench"**

PSF Scan now borrows its shell from Hikrobot MVS: a dense industrial camera client with dark graphite chrome, compact toolbars, explicit acquisition state, and an orange current-action accent. The user is still a single optical bench operator, but the software should now feel closer to a real camera-control utility than a custom research demo.

The concrete scene is a lab desk with a Hikrobot camera, a PI stage, mixed room lighting, and a monitor used for live acquisition and parameter checks. Dark chrome reduces glare around the live frame. Analysis plots keep a tinted light canvas when contrast and colormap fidelity matter.

**Key Characteristics:**
- MVS-like topology: menu/control strip, acquisition viewport, parameter panels, bottom status.
- Graphite surfaces, 1px separators, square controls, no cards.
- Orange means active tool, primary action, selected tab, focus, and current acquisition command.
- Numeric telemetry is mono: exposure, gain, FPS, peak, frame count, position, progress.
- Camera live view may sit on black graphite; PSF and stage analysis stay on light canvas.

## 2. Colors

The palette is **Restrained but dark**: graphite carries most UI chrome, orange marks the active control path, and green/red/amber are reserved for scan state, safety, and measurement quality.

### Primary
- **MVS Orange** (`#f08a24`): selected toolbar tool, primary action, focus border, active tab underline, checkbox/slider handle, and acquisition progress.
- **MVS Orange Hi** (`#ffad45`): hover and ready-to-click state for primary controls.
- **MVS Orange Lo** (`#bf661b`): pressed state, active command edge, and text selection.

### Secondary
- **Sampled** (`#72a99b`): completed scan points and completed progress. It is not a generic success color.

### Tertiary
- **Danger** (`#d76f63`): E-STOP, hardware or integrity failure, soft-limit violations, destructive or blocking operations.
- **Warn** (`#e4b04f`): camera saturation, ROI render budget warnings, low-light cautions, and other recoverable measurement concerns.
- **Plot Locator** (`#2f73a3`): temporary PSF slice and MIP locator only.
- **Volume Shell Scale**: red PSF isosurface shells. This is scientific rendering, not UI chrome.

### Neutral
- **Graphite Void** (`#121417`): live camera viewport, status strip base, input base in MVS mode.
- **Graphite Bar** (`#1a1d21`): menu bar, camera toolbar, meter bar.
- **Graphite Panel** (`#23272d`): right-side control panel and dialogs.
- **Graphite Field** (`#2d3238`): default buttons, combo fields, hoverable tool cells.
- **Graphite Rules** (`#3f454d`, `#59616b`): 1px dividers, borders, splitter handles, inactive planned path marks.
- **Canvas Paper** (`#f2f0e9`): PSF plots, stage plot, and analysis canvases that need light scientific readability.

### Named Rules
**The Orange Current Path Rule.** Orange means the control that is active now or would start acquisition now. Do not use it for decoration.

**The Black Belongs To Acquisition Rule.** Black or near-black belongs around live camera pixels and top-level chrome. Do not turn PSF analysis plots into black charts.

**The MVS, Not CCTV Rule.** Use industrial camera UI structure, not security-monitor UI language. No multi-camera surveillance grid unless the product actually supports it.

## 3. Typography

**Display Font:** None. This product has no display typography.
**Body Font:** Inter, falling back to SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif.
**Label/Mono Font:** Iosevka Term, falling back to JetBrains Mono, Cascadia Mono, Fira Code, DejaVu Sans Mono, Menlo, Consolas, monospace.

**Character:** Compact sans for labels and commands, mono only for numeric telemetry and editable numeric values. The voice is a camera control application, not a branded SaaS dashboard.

### Hierarchy
- **Section** (600, 13px, tracking 1.6px): `STAGE`, `SCAN PLAN`, `CAMERA`, and settings groups.
- **Body** (500, 11px): dense labels, checkbox text, hints, and short messages. Parameter labels use sans, not mono.
- **Button** (600, 11px, tracking 0.6px): toolbar and command buttons.
- **Control Value** (400, 12px): spinboxes, combo values, editable parameters.
- **Value** (500, 14px): position, device state, scan counts, and important live readouts.
- **Meter** (400, 10px): FPS, peak, image dimensions, bandwidth-like telemetry, status bar detail.

### Named Rules
**The Parameter Tree Rule.** Camera/stage parameters read like MVS feature rows: label, field, unit, status. Labels must be clear sans text; only values are mono. No explanatory marketing copy inside the work surface.

**The Mono Telemetry Rule.** Any changing number uses tabular mono text.

## 4. Elevation

This system uses **no shadows**. Depth comes from dark surface steps, 1px dividers, selected tool fills, and viewport boundaries. Menus and popups can use a firmer border and slightly lighter graphite field, but not blur, glow, or glass.

### Named Rules
**The Docked Panel Rule.** Controls dock to the window edge or to an acquisition toolbar. They do not float as cards.

**The 1px Machine Rule.** Separators, tool boundaries, splitters, and plot axes are 1px. Thick accent stripes are forbidden.

## 5. Components

### Buttons
- **Shape:** Square, `0px` radius, 1px border.
- **Default:** Graphite Field fill, Ink text, Graphite Rule border, `5px 12px` padding.
- **Primary:** MVS Orange fill, Graphite Void text, firm border.
- **Hover / Focus:** Hover lightens the field; focus switches the border to Orange.
- **Danger:** Danger fill only for E-STOP. Other danger actions keep dark fill until hover.

### Camera Toolbar
- **Structure:** One dark horizontal strip above the acquisition viewport.
- **Controls:** exposure, gain, colormap, snapshot, record, line profile, advanced.
- **Selected tool:** Orange fill or orange underline. Use one active treatment at a time.
- **Advanced drawer:** Opens inline below the toolbar, two dense rows, MVS feature-row feel.

### Acquisition Viewport
- **Live frame:** Graphite Void or actual black image pixels. The frame is the visual focus.
- **Overlay:** SATURATED badge uses Warn, mono uppercase, fixed top-right placement.
- **Status meter:** Bottom strip contains image size, peak, sharpness, pixel calibration, FPS. Treat it like MVS acquisition status.

### Inputs / Fields
- **Style:** Graphite Void fill, 1px Graphite Rule Soft border, mono value, no spin buttons.
- **Hover:** Border firms up, fill remains dark.
- **Focus:** Border switches to Orange.
- **Disabled:** Graphite Field with Ink Dim.

### Tabs
- **Style:** Dark graphite tabs, no rounded pane.
- **Selected:** Ink Strong text with 1px Orange underline.
- **Default:** Ink Muted text and Graphite Bar background.

### Progress Bar
- **Default:** 10px rectangular track, Graphite Void fill, 1px rule.
- **Scanning:** Orange chunk.
- **Finished:** Sampled chunk.
- **Ticks:** 1px muted vertical ticks, never decorative blocks.

### Stage And Scan Panels
- **Structure:** Docked right panel with section headers and dividers.
- **Stage:** Z target row, jog row, calibrate, E-STOP, position/range telemetry.
- **Scan plan:** Start/stop/dwell/sample fields read like parameter rows, not cards.

### PSF Plot And Volume View
- **2D plots:** Canvas Paper background, Canvas Ink titles, muted axes, scientific colormaps.
- **3D volume:** Canvas Paper background, Volume Grid, red shell ramp. These colors never become app accents.

## 6. Do's and Don'ts

### Do:
- **Do** make the main shell feel like an industrial camera client: toolbar, viewport, parameter panel, status telemetry.
- **Do** reserve Orange for current command, selection, focus, and primary acquisition action.
- **Do** keep camera telemetry visible in mono at the bottom of the acquisition viewport.
- **Do** keep PSF and stage analysis on Canvas Paper when readability beats MVS darkness.
- **Do** expose hardware, SDK, plot, and render errors visibly.

### Don't:
- **Don't** build a security CCTV layout or multi-tile surveillance wall.
- **Don't** use black-green terminal styling, neon cyberpunk accents, or purple gradients.
- **Don't** use beige SaaS cards, big rounded buttons, icon-heading-description blocks, or hero metrics.
- **Don't** use decorative gradients, glow, background blur, glassmorphism, or gradient text.
- **Don't** add border-left or border-right accent stripes greater than 1px.
- **Don't** use Orange as decoration or on inactive controls.
- **Don't** make UI transitions longer than 200ms.

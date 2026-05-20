---
name: PSF Scan
description: 浅色科研绘图工作台风格的 PySide6 / pyqtgraph 扫描软件视觉系统。
colors:
  paper: "#f7f5ef"
  panel: "#ebe8df"
  surface: "#ddd8cd"
  rule-soft: "#d4cfc3"
  rule-firm: "#b8b1a3"
  ink-strong: "#171a1c"
  ink: "#2a2f32"
  ink-muted: "#626a6c"
  ink-dim: "#6f7470"
  signal: "#9fc6dc"
  signal-hi: "#b8d7e8"
  signal-lo: "#7aa9c5"
  sampled: "#5f8f83"
  danger: "#b55345"
  danger-hi: "#c86b5d"
  danger-lo: "#984438"
  warn: "#d6892b"
  bevel-highlight: "#fefdf7"
  bevel-shadow: "#d4cfc3"
  plot-locator: "#2f73a3"
  volume-grid: "#c8d5d7"
  volume-shell-1: "#f0a6a0"
  volume-shell-2: "#db7069"
  volume-shell-3: "#b84642"
  volume-shell-4: "#842a2d"
  volume-shell-5: "#4d161e"
  volume-core: "#000000"
typography:
  display:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "3px"
  section:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "2px"
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
    fontWeight: 400
    letterSpacing: "0.5px"
  button-primary:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "1px"
rounded:
  none: "0px"
spacing:
  hairline: "1px"
  g-4: "4px"
  g-8: "8px"
  g-16: "16px"
  g-24: "24px"
  g-32: "32px"
  g-48: "48px"
  panel-gutter: "24px"
  column-gap: "32px"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
    height: "22px"
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink-strong}"
    typography: "{typography.button-primary}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
    height: "22px"
  spinbox:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-strong}"
    typography: "{typography.control-value}"
    rounded: "{rounded.none}"
    padding: "4px 6px"
    height: "22px"
  combobox:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control-value}"
    rounded: "{rounded.none}"
    padding: "4px 8px"
    height: "22px"
  progressbar:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.none}"
    height: "14px"
  tab:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
  tab-selected:
    backgroundColor: "transparent"
    textColor: "{colors.ink-strong}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "6px 14px"
  section-header:
    textColor: "{colors.ink-strong}"
    typography: "{typography.section}"
    padding: "14px 0 6px 0"
---

# Design System: PSF Scan

## 1. Overview

**Creative North Star: "The Calibrated Plot Bench"**

PSF Scan is a bright, low-drama instrument panel for a single optical bench workflow. The user is moving a stage, watching a camera image, and checking PSF stack output; the interface must stay physically quiet while the plotted data stays legible. The concrete scene is a microscope desk under mixed lab and office lighting, where a dark UI would hide surface detail and a glossy UI would steal attention from the PSF image.

The system is PySide6 / pyqtgraph first: QSS supplies the control vocabulary, pyqtgraph owns image and plot rendering, and custom widgets only exist when they make measurement faster. The product rejects 黑底科研软件、终端绿/青配黑底、魁北克蓝 + 黄金、大而圆润的阴影卡片、icon-标题-描述三件套、装饰性渐变、光晕、背景模糊、动画过渡 > 200ms.

**Key Characteristics:**
- Warm light plotting surfaces, never pure white and never theatrical dark mode.
- Rectangular controls, 1px rules, no shadows, no card stacking.
- Numeric information is mono by default; labels and buttons use a compact sans.
- Signal blue marks current focus and primary action; sampled green marks completed scan points.
- PSF intensity belongs to scientific colormaps, not UI decoration.

## 2. Colors

The palette is **Restrained**: warm neutral surfaces carry the interface, Signal appears only for current state and primary action, and Sampled is a single secondary status color.

### Primary
- **Signal**: Current position marks, primary buttons, focus borders, selected tab underline, progress chunks, checkbox selected fill, and slider handles.
- **Signal Hi**: Hover state for primary actions and slider handles.
- **Signal Lo**: Pressed primary state and text selection highlight.

### Secondary
- **Sampled**: Completed scan points in `StageView`. It must not be reused for success decoration outside scan completion.

### Tertiary
- **Danger**: Safety, integrity, and destructive operations: E-STOP, soft-limits-disabled warning, find-reference confirmation, scan error info-line, soft-limit dashed lines in StageView, danger button hover/border. Terracotta, intentionally calmer than vermillion — it should read as "halt" without screaming on a warm-neutral surface.
- **Warn**: Measurement-quality cautions that do not threaten safety: SATURATED badge on the camera view, MIP ROI rendered-budget hint. Amber, distinct from both Danger and Sampled. Use only when the user can keep working but the readout is suspect.
- **Plot Locator**: Temporary crosshair locator in PSF slice and MIP views. It is bluer and stronger than axis text, but it fades quickly.
- **Volume Shell Scale**: The PSF 3D surface uses a red shell ramp from outer translucent shells to the dense inner core. This is data rendering, not application chrome.

### Bevel
- **Bevel Highlight** and **Bevel Shadow**: A near-white / warm-gray pair used as 1px top-left + bottom-right borders on inputs, buttons, tabs, and checkboxes to suggest a flush instrument-panel bevel without elevation. They are not surfaces or text colors; they only appear as 1px borders inside component styles.

### Neutral
- **Paper**: Plot canvas, camera image background, status bar, spinbox and combobox surfaces.
- **Panel**: Main window and control panel background.
- **Surface**: Hover and disabled backgrounds.
- **Rule Soft**: Section rules, status dividers, input default borders.
- **Rule Firm**: Button borders, splitter handles, plot axes, planned path points.
- **Ink Strong**: Section labels, selected tab text, value labels, plot titles.
- **Ink**: Default text and button labels.
- **Ink Muted**: Meter labels, status bar text, plot axes, tab text.
- **Ink Dim**: Hint labels and disabled text.

### Named Rules
**The Plot Owns Color Rule.** Scientific image colors come from viridis, magma, inferno, plasma, CET-L4, or the volume shell ramp. Do not recolor UI panels to make data feel intense.

**The Three-State Scan Rule.** Planned, sampled, and current scan points use Rule Firm, Sampled, and Signal respectively. Never blend these states or add a fourth decorative scan color.

**The Warm Neutral Rule.** Paper, Panel, Surface, and rules stay warm gray. Pure white, pure black, cold blue-gray, and SaaS navy are prohibited.

## 3. Typography

**Display Font:** Inter, falling back to SF Pro Text, Segoe UI, Noto Sans CJK SC, Noto Sans, sans-serif
**Body Font:** The same sans stack
**Label/Mono Font:** Iosevka Term, falling back to JetBrains Mono, Cascadia Mono, Fira Code, DejaVu Sans Mono, Menlo, Consolas, monospace

**Character:** Compact sans for the instrument shell, narrow mono for values. The pairing should feel like a lab plotting utility, not an editorial brand surface.

### Hierarchy
- **Display** (700, 12px, tracking 3px): Only the `PSF·SCAN` corner title.
- **Section** (600, 13px, tracking 2px, uppercase): Section headers such as `DEVICES`, `STAGE`, `SCAN PLAN`, and `VIEW`.
- **Body** (400, 11px): Checkbox labels, default button text, and short error text.
- **Value** (500, 14px): Device state, scan summary, current status, and position readouts.
- **Control Value** (400, 12px): Spinboxes and comboboxes.
- **Meter** (400, 10px): FPS, peak, image size, plot metadata, status bar text.
- **Button Primary** (600, 11px, tracking 1px): `START SCAN` and `connect`.

### Named Rules
**The Mono-For-Numbers Rule.** Any repeated numeric readout uses the mono stack: position, exposure, gain, frame count, FPS, peak, progress, threshold, levels, and interpolation factors.

**The Small Type Rule.** This product does not use hero typography. Anything larger than 13px needs a direct measurement reason.

## 4. Elevation

This system uses **zero shadows**. There is no box-shadow, drop shadow, glow, blur, or raised card language. Depth is conveyed by material tone (Paper inside Panel), 1px dividers, splitter handles, and explicit plot axes. Hover and focus are color and border changes only.

### Named Rules
**The Flat Instrument Rule.** Surfaces do not float. Buttons, inputs, tabs, tooltips, progress bars, and plot panels stay flush with the workbench.

**The 1px Rule.** Structural separation is 1px: section rules, splitters, borders, axes, top and bottom bars. Thick accent borders and side stripes are forbidden.

## 5. Components

### Buttons
- **Shape:** Rectangular, no radius (`0px`), 1px border.
- **Default:** Transparent background, Ink text, Rule Firm border, `6px 14px` padding, `22px` minimum height.
- **Primary:** Signal fill, Ink Strong text, heavier sans weight, tracking 1px.
- **Hover / Focus:** Default hover uses Surface and Ink Dim border; primary hover uses Signal Hi; pressed primary uses Signal Lo.
- **Danger:** Same as default until hover, then text and border switch to Danger.

### Inputs / Fields
- **Style:** Spinboxes and comboboxes use Paper fill, Rule Soft border, `0px` radius, compact internal padding.
- **Hover:** Border switches to Rule Firm. ACCENT is reserved for focus only — hover and focus must remain visually distinct.
- **Focus:** Border switches to Signal.
- **Disabled:** Surface fill, Ink Dim text, Rule Firm border.
- **Numeric fields:** Spinbox steppers are removed; values stay mono.

### Checkboxes / Sliders
- **Checkbox:** 13px square, Paper fill, Rule Firm border, Signal fill when checked.
- **Slider:** 2px Rule Firm groove, 12px Signal handle, Signal Hi on hover, no custom track ornament.

### Tabs
- **Style:** Transparent QTabBar, no pane border.
- **Default:** Ink Muted text, `6px 14px` padding, `60px` minimum tab width.
- **Selected:** Ink Strong text with a 1px Signal underline.

### Progress Bar
- **Shape:** 14px high rectangular bar, Paper track, Rule Soft border.
- **Fill:** Signal chunk while scanning. On completion (`idx >= total`) the chunk flips to Sampled green so the progress region matches the StageView legend's "sampled" state. Reset back to Signal when the next scan starts.
- **Text:** Centered mono `10px`, Ink Muted.

### Section Header
- **Structure:** Uppercase label plus a 1px Rule Soft horizontal rule.
- **Spacing:** `14px` top, `6px` bottom, `10px` gap between label and rule.
- **Use:** Sections replace cards. Do not wrap each group in a separate framed panel.

### Camera View
- **Surface:** pyqtgraph ImageView on Paper.
- **Chrome:** Histogram, menu, and ROI controls are hidden.
- **Colormap:** viridis by default. Auto levels happen once on the first frame; subsequent frames keep fixed levels.
- **Meter bars:** Exposure and gain controls sit above the image; image size, peak, and FPS sit below with 1px rules.
- **Saturation:** `SATURATED` appears in Warn (amber), mono, 10px, 700 weight, tracking 2px. It is a measurement-quality caution, not a safety halt.

### Stage View
- **Structure:** Single horizontal Z plot with a legend bar below.
- **Point language:** Current is Signal plus marker at size 14. Sampled is green dots. Planned path is Rule Firm gray dots.
- **Axes:** Ink Dim labels, Rule Firm axis pens, subtle grid alpha 0.18.
- **Performance:** Repaint is throttled at 33ms, about 30 Hz.

### PSF Plot And Volume View
- **2D plots:** Paper background, Ink Strong titles, Ink Muted axes, optional labels and colorbar.
- **Locator:** Plot Locator crosshair appears on slice and MIP views, then fades in 12 steps at 55ms intervals.
- **Modes:** ORTHO, MIP, and VOLUME share the same compact control strip.
- **3D volume:** Background remains Paper, grid uses Volume Grid, isosurface shells use the red Volume Shell Scale. The volume scale is data-specific and must not leak into controls.

### Metadata
- **Input:** Moved to a modal dialog to preserve main screen space. Accessed via the "Metadata..." button in the Scan Plan section.

## 6. Do's and Don'ts

### Do:
- **Do** keep live images, PSF slices, MIP plots, and stage plots on Paper.
- **Do** use mono typography for every value that changes or aligns with another value.
- **Do** use SectionHeader and 1px rules instead of cards, nested panels, and decorative containers.
- **Do** reserve Signal for current focus, primary action, selected state, focus border, progress fill, and checked state.
- **Do** let pyqtgraph colormaps and volume shell colors communicate intensity and 3D density.
- **Do** expose plot and render errors as visible status text, not silent fallback success.

### Don't:
- **Don't** use 黑底科研软件、终端绿/青配黑底.
- **Don't** use 魁北克蓝 + 黄金 or any navy-and-gold scientific SaaS palette.
- **Don't** add 大而圆润的阴影卡片 or icon-标题-描述三件套.
- **Don't** use decorative gradients, glow, background blur, glassmorphism, or gradient text.
- **Don't** add border-left or border-right accent stripes greater than 1px.
- **Don't** use border radius. `0px` is the project-level shape token.
- **Don't** make animations or UI transitions longer than 200ms.
- **Don't** use the red volume shell ramp for buttons, tabs, warnings, or status badges.

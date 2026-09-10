---
name: Mission Tactical Intelligence
colors:
  surface: '#061520'
  surface-dim: '#061520'
  surface-bright: '#2c3b48'
  surface-container-lowest: '#020f1b'
  surface-container-low: '#0e1d29'
  surface-container: '#12212d'
  surface-container-high: '#1d2b38'
  surface-container-highest: '#283643'
  on-surface: '#d5e4f5'
  on-surface-variant: '#bbc9cd'
  inverse-surface: '#d5e4f5'
  inverse-on-surface: '#24323f'
  outline: '#859397'
  outline-variant: '#3c494c'
  surface-tint: '#2fd9f4'
  primary: '#8aebff'
  on-primary: '#00363e'
  primary-container: '#22d3ee'
  on-primary-container: '#005763'
  inverse-primary: '#006877'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#ffd2ce'
  on-tertiary: '#68000a'
  tertiary-container: '#ffaba5'
  on-tertiary-container: '#a20016'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#a2eeff'
  primary-fixed-dim: '#2fd9f4'
  on-primary-fixed: '#001f25'
  on-primary-fixed-variant: '#004e5a'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#061520'
  on-background: '#d5e4f5'
  surface-variant: '#283643'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: 0em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  code-lg:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: -0.01em
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0.02em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.04em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  grid-gutter: 1rem
  grid-margin: 1.5rem
  space-2xs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-base: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
---

## Brand & Style

This design system establishes an ultra-reliable, high-density situational awareness interface engineered for emergency operations centers, municipal incident commanders, and risk analysts. The brand aesthetic merges modern aerospace telemetry consoles with tactical geospatial intelligence systems: surgical, unyielding, authoritative, and frictionless under extreme cognitive load.

Key tenets:
- **Zero Ambiguity:** Visual hierarchy strictly prioritizes live threats, temporal proximity, and geofenced severity over decorative aesthetics.
- **Controlled Density:** Maximizes viewable data on dense multi-monitor workstation setups without inducing alert fatigue. 
- **Mission-Critical Precision:** Incorporates subtle structural gridlines, technical dividers, coordinate references, and low-latency feedback states.
- **Atmosphere:** Dark, high-contrast operational cockpit engineered for low-light command rooms, preserving operator visual acuity over prolonged surveillance intervals.

## Colors

The palette is engineered around dark situational depth and strict semantic alert tiers:

### Structural & Surface Hierarchy
- **Base Backdrop Canvas:** `#08111F` (Deep Navy) — Lowest root level; non-interactive visual void.
- **Panel Base:** `#101C2D` (Dark Slate) — Primary container background for docking modules, maps, and tool strips.
- **Card / Group Surface:** `#162437` (Surface) — Workstation tiles, floating data cards, and viewport HUD widgets.
- **Elevated / Overlay Surface:** `#1D3045` (Elevated Surface) — Modals, tooltips, flyout drawers, and active hover states.
- **Structural Separation:** `#2A3E59` (Precision Stroke) — 1px technical delineations, chart grid lines, and docking seams.

### Semantic Risk Scale
- **Safe / Normal:** `#22C55E` (Emerald) — All telemetry within threshold; confirmed mitigated.
- **Watch / Advisory:** `#F5B942` (Amber) — Trending deviation detected; early algorithmic attention required.
- **Warning / Threat:** `#F97316` (Orange) — High probability incident trajectory; prep emergency protocols.
- **Critical / Active:** `#EF4444` (Alert Red) — Confirmed catastrophic vector; mandatory immediate override.

### Analytical & System Tiers
- **Telemetry & AI Vector:** `#22D3EE` (Cyan) — Predictive models, algorithmic confidence cones, sensor paths.
- **Active Navigation & Control:** `#3B82F6` (Electric Blue) — Interactive triggers, spatial selections, focal anchors.
- **Primary Typography:** `#F4F7FA` (Soft White) — High-legibility readout text and primary labels.
- **Secondary / Meta Typography:** `#9EADBD` (Muted Slate) — Subtitles, inactive filters, dimensional coordinates.

## Typography

The typography strategy leverages structural hierarchy by assigning dedicated fonts to dedicated functions:
- **Headlines (Plus Jakarta Sans):** Geometric, modern, and humanized. Provides swift, legible anchors for region names, hazard classifications, and view titles.
- **Narratives & Analysis (Inter):** Highly legible neutral grotesque engineered for rapid scanning of situation reports, triage procedures, and operator notes.
- **Telemetry, Timestamps & Identifiers (JetBrains Mono):** Monospaced precision for UTC timestamps, geo-coordinates (lat/long), algorithmic confidence percentages, and IoT sensor streams. All numerical data streams align precisely without jitter during real-time streaming updates.

## Layout & Spacing

This design system uses an adjustable multi-pane HUD layout based on a compact 4px baseline rhythm optimized for mission-critical GIS environments:

### Master Framework
- **Desktop / Operations Workstation (≥1440px):** Multi-dock layout consisting of a pinned or collapsible left-side operational index (320px–380px), a full-bleed geospatial situational viewport (center-dominant), and an expandable right telemetry/analytics rail (360px–440px). Bottom edge reserved for a scrubbable temporal predictive timeline (height: 72px–120px).
- **Tablet Tactical Mode (768px - 1439px):** Split-view with a swipeable drawer system. The GIS viewport remains dominant, with risk lists and sensor panels accessible via collapsible sheet overlays.
- **Field Terminal Mobile (&lt;768px):** Single-column stacked triage stream. Viewport switches between tactile map and incident queue via persistent bottom segmented navigation.

### Density Rules
- High-density information panels utilize compact `space-xs` (4px) and `space-sm` (8px) gaps.
- Padding inside data cards is locked to `space-md` (12px) to maximize real estate while keeping touch targets accessible.
- Map overlay chips, telemetry metrics, and coordinate badges float with strict `space-md` offsets from canvas edges.

## Elevation & Depth

Visual hierarchy is maintained through crisp structural borders, surface luminosity layering, and subtle targeted status glows rather than heavy diffused drop shadows.

- **Level 0 (Backdrop / Canvas):** `#08111F` — Absolute base floor.
- **Level 1 (Docked Structural Panels):** `#101C2D` with a persistent `1px solid #2A3E59` boundary. Zero ambient shadow.
- **Level 2 (Active Cards & Floating Viewport HUDs):** `#162437` surrounded by `1px solid #2A3E59`. Elevation is reinforced through background color stepping and an interior `box-shadow: inset 0 1px 0 0 rgba(255, 255, 255, 0.05)`.
- **Level 3 (Tactical Overlays, Menus & Drawers):** `#1D3045` combined with `1px solid #3B82F6` (or severity border) and an ambient occlusion shadow: `0 12px 32px -4px rgba(0, 0, 0, 0.65)`.
- **Critical Status Lighting:** In place of multi-layer decorative shadows, urgent alerts leverage focused optical glows:
  - Critical/Alert Red Glow: `0 0 12px 0 rgba(239, 68, 68, 0.35)`
  - Predictive AI Focus Glow: `0 0 12px 0 rgba(34, 211, 238, 0.3)`

## Shapes

The interface adopts a technical, restrained shape language. Roundedness is strictly constrained to Level 1 (`Soft`, 4px default) to communicate utilitarian precision and maximize usable screen space within data-dense tables and radar feeds.

- **Buttons, Field Inputs, Metric Tiles:** `rounded-sm` (4px border-radius) with sharp, uninterrupted 1px internal strokes.
- **Tactical Chips & Risk Badges:** `rounded-sm` (2px to 4px) to avoid playful pill geometries and preserve an instrumentation-panel look.
- **GIS Canvas Overlays & Floating Toolbars:** `rounded-md` (6px) with clean cutlines.
- **Corner Notches / Status Tics:** High-priority cards optionally feature chamfered or squared 2px status indicators along the left border to reinforce industrial telemetry aesthetics.

## Components

### Buttons
- **Primary Action (System Active):** `#3B82F6` background, `#F4F7FA` text, `rounded-sm` (4px), height 36px (dense) or 40px (standard). Hover: `#2563EB` with subtle cyan perimeter glow. Active: `#1D4ED8`.
- **Mission Critical Trigger:** `#EF4444` background, bold uppercase JetBrains Mono label, persistent soft pulse animation when armed.
- **Ghost / Outlined (Secondary Tools):** Background transparent, border `1px solid #2A3E59`, text `#F4F7FA`. Hover: Background `#1D3045`, border `#9EADBD`.
- **Telemetry Control Button:** Icon-only or compact icon + label, JetBrains Mono font, 32px height, border `1px solid #2A3E59`, background `#101C2D`.

### Risk & Status Chips
- **Structure:** 20px–24px height, padding `2px 8px`, `rounded-sm` (2px–4px). Text styled with `label-caps` (JetBrains Mono, bold, tracking +0.08em).
- **Severity Variants (Alpha-blended backgrounds with solid borders):**
  - Safe: Background `rgba(34, 197, 94, 0.12)`, text `#22C55E`, border `1px solid #22C55E`.
  - Watch: Background `rgba(245, 185, 66, 0.12)`, text `#F5B942`, border `1px solid #F5B942`.
  - Warning: Background `rgba(249, 115, 22, 0.12)`, text `#F97316`, border `1px solid #F97316`.
  - Critical: Background `rgba(239, 68, 68, 0.20)`, text `#EF4444`, border `1px solid #EF4444`, featuring a pulsing 6px warning pip.

### Lists & Telemetry Feeds
- **Incident Stream Rows:** Border-bottom `1px solid #2A3E59`, padding `8px 12px`, alternating row highlight `rgba(29, 48, 69, 0.3)`. Left margin indicator bar (3px width) colored dynamically by risk severity.
- **Tabular Data:** Right-aligned numerical fields formatted in `JetBrains Mono` for rapid vertical scanning. Column headers uppercase `label-caps` in `#9EADBD`.

### Input Fields & Selectors
- **Container:** Background `#101C2D`, border `1px solid #2A3E59`, height 36px, `rounded-sm` (4px), font `Inter` 13px, text `#F4F7FA`.
- **Placeholder:** `#9EADBD` at 60% opacity.
- **Focus State:** Border transitions to `#22D3EE` with an outer ring `0 0 0 1px #22D3EE`.
- **Data Range / Scrubbers:** Specialized timeline sliders with dual-thumb controls, current time marker in `#EF4444`, predictive horizon zone styled with striped cyan hatch pattern.

### Selection Controls (Checkboxes & Radios)
- **Checkboxes:** 16px × 16px square, `rounded-sm` (2px), border `1px solid #2A3E59`, background `#08111F`. Checked state: background `#3B82F6`, border `#3B82F6` with sharp white tick icon.
- **Radio Buttons:** 16px circular boundary, background `#08111F`, border `1px solid #2A3E59`. Checked: border `#3B82F6`, inner dot 6px `#22D3EE`.

### Cards & Modular Docks
- **Container:** Background `#162437`, border `1px solid #2A3E59`, `rounded-sm` (4px), internal padding 12px.
- **Header Structure:** Subdued header strip with `headline-sm` title, live status indicator, and JetBrains Mono coordinate/timestamp metadata.
- **Critical Alert Card:** Emphasized with left border `4px solid #EF4444`, subtle top-to-bottom alert gradient `linear-gradient(180deg, rgba(239, 68, 68, 0.08) 0%, transparent 100%)`.

### Specialized Domain Components
- **Algorithmic Confidence Gauge:** Segmented stepped bar (10 tick units) indicating early-warning certainty percentage, transitioning from Cyan (predictive) to Amber/Red as risk thresholds cross standard deviations.
- **Geofence Coordinate Pill:** Draggable HUD anchor displaying active latitude/longitude in `code-sm`, bound to active telemetry sensors.
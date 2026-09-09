---
title: Location Parallax Rework
date: 2026-09-09
tags:
  - transversal
  - technical
  - frontend
  - locations
  - navigation
  - plan
aliases:
  - Scene Camera Rework
  - Parallax Rework
status: complete
---

# Location Parallax Rework

Rework the location renderer so everything that moves is a GPU `transform`,
driven by a single camera offset, written at most once per frame. Fixes the
jarring "background lags behind" feel during occupant drags.

## Problem

The moving pieces currently use non-composited CSS properties:

- **Background** pans via `background-size`/`background-position` (`bgStyle`) —
  a full repaint of a large overscanned bitmap every drag frame.
- **Dots** move via `left/top` + negative margins — layout/paint, not composite.
- **Hole windows** use `background-attachment: fixed` — forces repaints, blocks
  compositing, and is broken on iOS (and is what forced the negative-margin hack).
- **Per-event churn** — each `mousemove` mutates `map_x/map_y` and recomputes
  `sceneSize`/`panShift`/`toViewportPos` for every dot.

## Target architecture

```
<viewer (overflow:hidden)>
  <scene-layer transform:translate3d(-panX,-panY,0)>
    <bg-img/video  (overscan-sized) />
    <zone/nav/occupant dots  (image-space, transform-centered) />
    <pool rings />
  </scene-layer>
  <self dot + arrival rings + HUD  (screen-space) />
  <travel overlay />
</viewer>
```

One camera object `{ panX, panY, scale, sizeW, sizeH }`; every pan/size
derivation reads from it.

## Slices

### Slice 1 — Background as a translated `<img>`/`<video>` layer

Highest leverage, self-contained.

- `LocationViewer.vue` (template + `bgStyle`/`videoStyle`), scoped CSS.
- Add a `.scene-bg` layer (`overflow: hidden`) holding the `<img>`/`<video>`,
  sized to `sceneSize()` px, moved with `transform: translate3d(-panShift().x, -panShift().y, 0)`.
- Dots untouched (still screen-space via `toViewportPos`).
- **Verify:** build + drag — background tracks the pointer 1:1, no lag; static
  and video backgrounds both.

### Slice 2 — Move world dots into the scene layer

- `LocationViewer.vue` template (zones, nav, `occupantDots`, pool rings), `MapDot.vue` centering.
- Render world dots inside the scene layer at image-space coordinates
  (`z.x/z.y`, `nd.x/nd.y`, `map_x/map_y`) with `transform: translate(-50%,-50%)`.
  Remove `parallaxX/Y` from the render path.
- Self dot, arrival rings, labels, overlay switcher stay screen-space.
- **Verify:** build + drag — dots stay glued to the map, self dot remains 1:1,
  expansion/armed still work.

### Slice 3 — Hole windows off `background-attachment: fixed`

- `MapDot.vue` (`overlayBgStyle` + `.dot-overlay` markup/CSS).
- Destination becomes an inner `<img>`, sized to `coverOverscan`, moved by the
  inverse transform + `scale` (fed from `navDotPerspective` pan/overscan),
  clipped with `border-radius: 50%` + `overflow: hidden`.
- Uniform vignette stays as an inset `box-shadow`.
- **Verify:** hole still pans inversely; no `background-attachment: fixed`;
  iOS-safe.

### Slice 4 — Single camera source + rAF coalescing

- New `composables/useSceneCamera.js` (or module camera ref), `LocationViewer.vue`.
- One camera object; `sceneSize`/`panShift`/`anchorPct`/`toViewportPos`/`toImagePos`
  read from it (then delete the redundant helpers).
- Buffer pointer moves during drag and write the scene transform once per
  `requestAnimationFrame`.
- Fold the teaser-camera mode (`camera` prop + `TEASER_ZOOM`) into the same object.
- **Verify:** build + drag — smooth; mobile teaser-camera mode still zooms correctly.

## Out of scope

- Travel portal overlay (`clip-path` expansion) and arrival rings.
- SSE occupant lerp, GMC/occupant drag logic, armed/breathe animation, HUD drag-fade.
- Backend.

## Risks & rollback

- Slice 2 changes dot centering (the negative-margin hack goes away — intended).
- Main residual risk: keeping self dot / pool rings / labels screen-space while
  world dots move with the scene.
- Each slice is a small `navigation` commit; any slice reverts independently.

## Outcome

All four slices landed (2026-09-09). Deviations from the plan:

- **Slice 2 kept negative-margin centering** instead of switching dots to
  `transform: translate(-50%,-50%)` — the margins are static during panning, so
  they no longer cost anything, and skipping the centering change kept the
  slice small.
- **rAF coalescing (Slice 4's second half) landed early**, as a standalone fix:
  the frame profiler showed ~6 fps during drags (a high-polling mouse starved
  rAF with per-event re-renders). Coalescing + the scene layer took drags to
  the display's full refresh rate (~144 fps, 0 dropped frames on a
  hardware-accelerated display; the earlier ~25 fps numbers were a
  software-composited Pixelbook).
- **Bonus fixes found along the way**: removed `backdrop-filter: blur` from
  dots (nearly invisible, costly on high-DPI), hole alignment clamped to image
  bounds (parallax proportional to remaining space), hole img
  `border-radius: 0` (an overscan-sized img must not clip itself to an
  inscribed ellipse), and a tunable-constants block at the top of the script.
- **Temporary instrumentation**: `composables/frameProfile.js` + its call sites
  (drag frame profiler, `FRAME_PROFILE` toggle) — removable now that the
  measurement is done.

## Related

- [[Location Viewer]] — current design doc (the "before" state).
- [[System Architecture]] — where the renderer sits in the stack.

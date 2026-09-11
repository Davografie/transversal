---
title: UI-UX Refactor Plan (B46)
date: 2026-09-11
tags:
  - transversal
  - technical
  - ui
  - refactor
aliases:
  - B46 Plan
  - Large File Split Plan
---

# UI-UX Refactor Plan (B46)

Working plan for [[Tickets#B46 — Split large Vue files]] (owner: [[ui-ux]]).
Line numbers are from the census below; **re-verify them before slicing** — the
files move.

| File | Lines | Template | Script | Styles |
| --- | --- | --- | --- | --- |
| `components/CharacterSheet.vue` | 3111 | 1–~545 | ~546–2180 | 2183–3111 |
| `App.vue` | 2560 | 1–371 | 373–2473 | 2475–2560 |
| `components/DiceRoller.vue` | 2367 | 1–369 | 371–1983 | 1985–2367 |
| `components/LocationViewer.vue` | 1939 | 1–171 | 173–1505 | 1507–1938 |

Census taken 2026-09-11 (three read-only recon passes) against a tree that was
level with `release-build`; the CharacterSheet numbers moved when the trait
editor landed (see [[#Slices landed]]).

## Slices landed

- **Trait-instance editor — done (2026-09-11).** One `ui/TraitInstanceEditor.vue`
  now serves the sheet and the effect form's *Gain Trait*; `gm/TraitEditor.vue`
  (unreferenced) retired. See [[UI-UX Design#Trait instance editor]].

## Conventions for the remaining slices

- Sub-feature components go in an area folder (`components/<area>/Foo.vue`);
  state goes in `composables/useFoo.js`. Existing area folders: `gm/`, `ui/`,
  `canvas/`.
- A slice is finished when the build is green **and** the surface has been driven
  through CDP (see [[UI-UX#Working notes]]); no frontend unit tests exist.
- Move `<style scoped>` rules with the markup they style. Parent-scoped rules do
  **not** reach into a child component's internals — leave rules for
  child-internal elements (e.g. `MapDot`'s `.dot-*`) where they already work.
- Keep `defineExpose` surfaces, emits, and DOM class contracts intact: `App.vue`
  calls into `locationRef` / `sheetRef` / `diceRef` and reads
  `.sel-slot` / `.total-slot` at drop time.

## App.vue (2560)

Shape: one 270-line entangled login/settings overlay (template 4–274, script
~700 lines), a `.stage` that serves as both desktop layout and mobile band
container (287–356), and SSE/session plumbing.

Bands live at 294 (`loc-band`), 323 (`sheet-band`), 351 (`roller-band`) — all
inside `.dice-panel-wrapper`. **The `--roller-h` binding (287) and the
`mobile-stack focus-* sheet-empty` class contract must not be renamed or
re-nested**; `assets/styles.css:939–1083` keys off them, and `--roller-h` is
consumed at `styles.css:1050`.

Suggested order:

1. `components/app/SseIndicator.vue` + `PeersBar.vue` (template 2, 316–322;
   scoped CSS 2476–2528) — props-only, proves the scoped-CSS move.
2. `composables/useThemeMode.js` + `usePeers.js` (1664–1668; 556–605, 974–975)
   — self-contained, fails loudly if the boundary is wrong.
3. `composables/useMobileBands.js` (1670–1692, 1704–1737) — takes `wrapperEl`
   plus three read-only getters; removes the DOM-measurement code from the root.

Hazards: `useSSE` + the 270-line `watch(lastEvent)` sink (1266–1538);
`provide('gmCurrentLocationId')` (459) must stay an ancestor of `PanelStack`;
six hand-rolled localStorage refs duplicate the existing `usePersistedRef`;
`initSession()` / `initLocation()` are joined at 978–984 and
`ensurePlayer()` fires at line 925 **before** them; the `watch(entityId, …)`
at 634 is `flush: 'sync'` and must be registered before anything assigns
`entityId` during setup.

## LocationViewer.vue (1939)

Template is small (171 lines) and the weight is script: camera math (457–497),
navdot projection (499–568), zone drag (572–644), image probing (691–726),
occupant drag/drop and hit-testing (~760–1400).

Suggested order:

1. `components/location/ArrivalRings.vue` (121–129; 413–421; CSS 1881–1936) —
   props-only canary.
2. `components/location/TravelOverlay.vue` (157–167; CSS 1834–1853) — one prop
   plus its `--travel-x/y` keyframes.
3. `composables/useSceneEffects.js` + `components/location/SceneEffectsLayer.vue`
   (82–86, 111–119; 226–227, 241–363; CSS 1754–1832) — the particle rAF/canvas
   lifecycle, sealed apart from one prop.

Hazards: `viewerEl` is the ResizeObserver target (448–455) and the hit-test
origin (587) — root-element ownership must not move; `imageAspect` is set by a
**detached** image/video probe (706–726), so the camera cannot be extracted
without that watch; `--travel-x/y` are the only inline CSS vars; the teaser
camera is size-driven (`CAMERA_START`/`CAMERA_FULL`, 186–187) with the tunables
at 184–189; four document-level listener pairs must keep their add/remove
pairing; localStorage `effectsEnabled`, `gmDotPositions`; server writes are
`PUT /locations/:id/zones`, `PATCH /entities/:id/map-position`, GraphQL
`updateEntity` (overlay, navPositions). `defineExpose` (1499) is called from
App.vue on SSE (`fetchNav`, `fetchNavWithLerp`).

## DiceRoller.vue (2367)

Cleanest props-only layer first, contested state and the pool/selection engine
last. 17 props, 14 emits, and a 17-member `defineExpose` (1224) that App.vue
calls on SSE — every exposed method is an entry point and must keep its
signature. No SSE subscription and no localStorage here; remote state arrives as
`remotePools` / `remoteResults` props.

Suggested order:

1. `components/dice/ContestResultWidget.vue` (18–49; 577–612) — derived display
   only.
2. `components/dice/PoolTabs.vue` (3–16; 506–552).
3. `components/dice/ConsequencePanel.vue` (286–316; 613–632) — already wraps
   `ConsequenceMenu`, so the boundary is proven.

Hazards: `kind-*` classes live on the root (2) and set `--kind-accent`; the
touch path appends a ghost node to `document.body` and resolves the drop target
with `document.elementFromPoint` + sibling index over `.sel-slot` / `.total-slot`
(1357–1366) — those classes are a contract; four document-level
`touchmove`/`touchend` listeners (1969–1972, removed 1978–1981) — splitting the
drag code risks double registration; the 383-line scoped style block must follow
each template slice.

## CharacterSheet.vue (3111)

The heavy drill-in surface: header pills (110–121), trait-set list (342+),
tab list, trait detail (read-only), and the `#after-*` slot hosts. The trait
editor now composes `ui/TraitInstanceEditor`; the remaining bulk is the detail
panel, the list rows, the SFX cards and the peer tab.

Suggested order (revised after the editor slice — re-verify boundaries):

1. `components/sheet/TraitEditPanel.vue` — the wrapper around the shared editor
   (title, slots, Done/Delete) with `v-model` on the persisted edit refs.
2. `composables/useTraitEditor.js` — `startEdit` / `doSave` / `deleteTrait` /
   `recomputeTraitSets` and the persisted `sheet.*` draft refs.
3. `components/sheet/TraitDetailPanel.vue` and `components/sheet/TraitRow.vue`
   (the row markup is the click/context-menu/long-press contract).

Hazards: ten `usePersistedRef('sheet.*')` keys are the draft state; the row
handlers `@click="openTraitDetail"` / `@contextmenu="startEdit"` / long-press
must move together; the parent sends `addToPool` / `removeFromPool` /
`sfxToggled` / `sheetViewChange` up to App; `setPoolSources` is called by
DiceRoller through App.

## Related

- [[UI-UX Design]] · [[UI-UX]]
- [[Tickets]] · [[Division of Labor]]

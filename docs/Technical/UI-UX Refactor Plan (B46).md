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

| File | Started | Now | Landed |
| --- | --- | --- | --- |
| `App.vue` | 2559 | 2236 | `app/SseIndicator`, `app/PeersBar`, `usePeers`, `useThemeMode`, `useMobileBands`, `usePlayerCharacters` |
| `components/LocationViewer.vue` | 1938 | 1654 | `location/ArrivalRings`, `location/TravelOverlay`, `location/SceneEffectsLayer` |
| `components/DiceRoller.vue` | 2367 | 2278 | `dice/ContestResultWidget`, `dice/PoolTabs` |
| `components/CharacterSheet.vue` | 3281 | 2577 | `ui/TraitInstanceEditor` (shared), `useTraitEditor`, `sheet/TraitEditPanel`, `sheet/SfxCard` |

Census taken 2026-09-11 (three read-only recon passes) against a tree that was
level with `release-build`; the CharacterSheet numbers moved when the trait
editor landed (see [[#Slices landed]]).

## Slices landed

All on 2026-09-11, each verified by build + CDP against the running app.

- **Trait-instance editor.** One `ui/TraitInstanceEditor.vue` now serves the
  sheet and the effect form's *Gain Trait*; `gm/TraitEditor.vue` (unreferenced)
  retired. See [[UI-UX Design#Trait instance editor]].
- **App.vue.** `app/SseIndicator` + `app/PeersBar`; `usePeers` (peer/cache
  logic, `isEntityType` for the GM test) and `useThemeMode` (colorMode +
  theme-color meta); `useMobileBands` (media query, focus, empty-sheet rule,
  roller-content measurement + observers); `usePlayerCharacters` (owned
  characters + the per-character actions).
  - **Lesson:** a composable extraction can pass the build and still be broken
    when the removed call sits inside a `try/catch` — `fetchLocationNames` was
    left out of the destructure and search quietly reported "no characters".
    Grep the file for every removed identifier after the patch, not just for
    build errors.
- **LocationViewer.vue.** `location/ArrivalRings` (three-phase arrival),
  `location/TravelOverlay` (portal wipe), `location/SceneEffectsLayer` (overlay
  layer + canvas particle engine). The effects toggle and its persisted flag
  stay in the parent, which now passes `enabled` down.
- **DiceRoller.vue.** `dice/ContestResultWidget` (scoreboard, step-down arrow,
  taken-out) and `dice/PoolTabs` (grouped switcher, one `select` emit).
- **CharacterSheet.vue.** `useTraitEditor.js` (the `sheet.*` draft refs, the
  editor actions, live-saving `doSave`, delete countdown, spent-die recovery)
  and `sheet/TraitEditPanel.vue` (header + the shared editor + the sheet's
  extras; fully controlled, ~5 v-model fields and one emit per interaction).
  Its CSS moved rule-by-rule — including a one-line-formatting rule the first
  pass missed, so **check single-line rules** when moving CSS out of this file.
- **`sheet/SfxCard.vue`.** Five copies of the SFX card became one presentational
  card fed by `sfxCardModel(sfxId)`; `disabled` reproduces the old inline click
  guard. Its CSS moved including `.detail-section .sfx-card-rules`, a descendant
  rule that would have silently stopped applying once the span left the
  parent's scope — **watch for those when extracting markup with nested rules**.

**Deliberately not extracted:** the roller's consequence panel. Its buttons are
driven by contest state (`iWon` / `iGaveIn` / taken-out / waiting /
decision-pending) whose actions live in the parent — the split would shuffle
props without removing complexity. Revisit alongside a contest composable.

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

## App.vue (2384, was 2560)

Shape: one 270-line entangled login/settings overlay (template 4–274, script
~700 lines), a `.stage` that serves as both desktop layout and mobile band
container, and SSE/session plumbing. The band list below is now spent; the
remaining high-value work is the settings overlay itself and the `useSSE` +
`watch(lastEvent)` sink (1266–1538, re-verify).

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

## LocationViewer.vue (1654, was 1938)

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

## DiceRoller.vue (2278, was 2367)

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

## CharacterSheet.vue (2577, was 3281) — remaining

Editor + SFX cards done. What is left is mostly line count rather than sharing:

1. **`sheet/TraitDetailPanel.vue`** — the read-only view; needs ~10 injected
   behaviours (`canPlayTrait`, `playTrait`, `ratingTypeLabel`,
   `challengeProgressLabel`, the SFX helpers) so the win is mostly line count.
2. **`sheet/TraitRow.vue`** — the list row; carry the click / context-menu /
   long-press handlers together with it.
3. **`useSheetData.js`** — fetch/refresh + trait-set splitting, if the script is
   still unwieldy after the two above.

## App.vue — remaining: the settings/login overlay

The last big entangled block: template 4–274 (a fresh-login branch and a
settings branch) backed by ~450 lines of script spread over 610–2340. It binds
**~55 names**, which is why it has not been rushed — this is the app's entry
path.

What is already out: the character list + per-character actions
(`usePlayerCharacters`). What is still inline and would move next:

- identity + login: `playerId` / `playerName` / `showLoginOverlay` /
  `pendingPlayer` / `nameSuggestions` / `nameStatus` / `nameFound` /
  `checking`, `searchPlayers` + the `playerName` watcher, `onNameEnter`,
  `selectSuggestion`, `findOrCreatePlayer`, `fetchPlayer`, `ensurePlayer`,
  `confirmPlayer` → `usePlayerIdentity.js`.
- identity switching: `switchName` / `switchEditing` / `switchStatus` /
  `switchFound` / `switchSuggestions` / `switchPending` / `switching`,
  `onSwitchEnter`, `confirmSwitch`, `onSwitchBlur` → same composable.
- character switching + resonance: `charSwitchLoading` / `charPending` /
  `resonanceFrom` / `resonanceTo` / `charSwitchDone`, `beginCharacterSwitch`,
  `cancelCharacterSwitch` → `useCharacterSwitch.js`.
- support characters: `mySupportCharacters`, `otherPlayersMains`,
  `assumeSupport`, `openCreateSupport`.
- creation: `newCharName` / `creatingChar` / `createCharError` / `showNewChar`,
  `createCharacter`. Plus the character search (`charSearch*`, `doCharSearch`,
  `chooseFoundCharacter`, `fetchAllCharacters`).
- media quality (`mediaQuality` / `setMediaQuality`) and the Resonance Lab
  toggle (`showLab`).

For the markup, two options were weighed: ~55 explicit props (verbose but
greppable) versus passing one `api` object assembled in the parent (smaller,
but the child would need `.value` unwrapping discipline). **Recommendation:**
extract the script first (the composables above, each verifiable in the running
app), then move the markup with explicit props once the surface is thin — the
login path deserves a step-by-step, harness-verified landing rather than one
big-bang component swap.

The `useSSE` + `watch(lastEvent)` sink stays in the root by design (it drives
every surface).

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

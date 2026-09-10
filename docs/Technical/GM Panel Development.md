---
title: GM Panel Development
tags:
  - transversal
  - technical
  - frontend
  - panels
  - composables
  - conventions
aliases:
  - Panel Development
  - GM Panels
  - Panel Conventions
status: canonical
---

# GM Panel Development

Conventions for building GM panels, established during the panel refactor.
The governing idea: **logic lives in composables; panel components stay thin
renderers that wire composable state to the DOM.**

## Architecture

- `src/components/gm/PanelStack.vue` — the stack: the 🛠 toggle, the root
  `Panel`, and the floating-window layer. Owns the stack anchor's drag and the
  depth-hiding fit loop.
- `src/components/gm/Panel.vue` — self-referential wrapper. Provides the
  `panelKey` navigation context to its slot content, renders nested child
  `Panel`s (tab-group: one active + a chip strip), and carries the per-panel
  geometry: anchor-derived placement, viewport clamp, action rail, drag handle.
- `src/components/gm/PanelWindow.vue` — one detached/floating window: its own
  anchor, its own chain direction, and the dock plumbing. Renders a root `Panel`.
- `src/composables/usePanelAnchor.js` — the anchor model: position (persisted
  per device as `gmPanelAnchor`), edge snap, direction derivation, viewport
  clamps.
- `src/composables/usePanelWindows.js` — the window registry (`spawn/close/
  replace/toggleCollapse/setDock/move/setDirection`), each window carrying
  `{ id, spec, x, y, direction, sourceParentKey }`.
- `src/composables/usePanelDiagnostics.js` — drag-release dumps: every drag
  start/release records the live DOM geometry *and* each panel's internal layout
  state into `window.__PANEL_DUMPS__` (silent unless `window.__PANEL_DEBUG__`).
- A **panel** is the content component rendered inside a `Panel` slot
  (e.g. `GmEntityEditPanel`, `GmTraitEditPanel`). `GmPanel.vue` is the L0 root
  content (modes, entity list, filter bar) — not the wrapper.

Positioning in one paragraph: the chain derives from a draggable **anchor**
(🛠 closed, the shallowest visible panel's rail open — drag the rail's `⠿` or
the 🛠 itself; the anchor snaps to the nearest viewport edge on drop and is
remembered per device). Panels open away from the anchor's edge (left/right/up/
down), are clamped inside the viewport, slide along their parents' edges, and
each rail hugs **its own** panel's edge. Any child panel can detach (`⤢`) into a
floating window, which keeps its own anchor and direction and docks back (`⤓`)
into the panel it came from, matched by `component + spec.id`. See
[[GM Panel Positioning Plan]].

## Rule 1 — Data and mutations live in composables

Each domain owns its queries, mutations, and state in a composable under
`src/composables/`. Panels import and consume the composable.

Do:
- Put `useApi().graphql()` queries and mutations inside the composable.
- Keep the panel focused on rendering + wiring the composable's state.

Don't:
- Inline `graphql()` calls in a panel component (duplicates query/mutation logic).
- Have a parent component fetch data and pass it down as props.
- Re-declare state that a composable already owns.

## Rule 2 — Singleton state for shared domain data

Composables that represent shared domain data declare their state at module
scope, so every consumer shares the same reactive refs (no prop drilling, no
refetch):

```js
// useEntityCrud.js
const entities = ref([])   // module-level singleton
const selected = ref(null)
const form = ref({})

export function useEntityCrud() {
  // ... queries/mutations operate on the shared refs ...
  return { entities, selected, form, /* ... */ }
}
```

Singleton composables (the reference implementations):

- `useEntityCrud` — entities, selection, CRUD, auto-save watcher, imagen job polling.
- `useTraitsConfig` — traitsets, allSfxs, `traitNameMap`, fetch, optimistic `patchData`.
- `useLocationTree` — location tree + expansion state (module-level), derivation computeds.
- `useTroupe` — troupe-play state (spotlight recency, support characters, active mains, current bodies, online players); read by `GmTroupeOverview` and the player settings overlay.

Derivation/helper composables take inputs as parameters and expose computeds
(no shared state):

- `useEntityFilter(entities)` — filter bar, suggestions, filtered projections.
- `useEffectActions()` — effect-action metadata + summarization helpers (module-level cache + in-flight dedup).

One-time side effects (watchers, timers) inside a singleton composable are
guarded with a module-level flag so they run only once, e.g.
`_watchersSetup` in `useEntityCrud.js`.

## Rule 3 — Navigation via `usePanel()`

`usePanel.js` exports `panelKey` and `usePanel()`, which `inject`s the context
provided by `Panel.vue`:

- `panel.open({ component, title, props })` — push a child panel.
- `panel.close()` — close this panel (self).
- `panel.replace(spec)` — replace this panel with another.
- `panel.closeChild()` — pop the current child.

Panels import child panel components directly and open them by component ref
plus identity props.

## Rule 4 — Cross-panel events via `usePanelBus()`

`usePanelBus.js` provides a module-level typed event bus (`on`/`off`/`emit`)
that replaces `window.dispatchEvent`.

- `bus.on(event, handler)` returns an unsubscribe function.
- Subscribe in `onMounted`, store the returned unsubscribe, call it in `onUnmounted`.
- `bus.emit(event, payload)` after a mutation so sibling/detail panels refresh.

## Rule 5 — Reuse shared UI primitives

Repeated UI is extracted into small controlled components; panels compose them
instead of re-implementing:

- `DangerButton` — confirm-on-second-click delete button.
- `SearchDropdown` — search input + dropdown.
- `ChipInput` — chip/tag input with suggestions.
- `GmList` + `GmListItem` — generic controlled list (selection highlight, ✓/+ toggle, drag-reorder, loading/empty). Parents supply pre-filtered `items` and a `#item` slot, and react to `click` / `toggle` / `reorder`. Search stays in the parent.
- `ConditionEditor`, `EffectEditor`, `TraitEditor`, `GmEntityForm` — sub-form editors.
- `GmTraitPicker` — trait search/select with universe filtering.

Shared panel CSS lives in `src/frontend/src/assets/gm-panel.css` (imported
globally in `main.js`). Component-specific styles stay scoped, with a unique
per-component class prefix.

## Rule 6 — Props carry identity/context only

Panels receive IDs or small config (`id`, `index`, `universe`), or the specific
object being edited when the opener already holds it. They never receive a data
tree that a parent assembled specifically to pass down.

## Reference panels

- Thin consumer panels: `GmPanel.vue` (root), `GmEntityEditPanel.vue`, `GmTraitEditPanel.vue`.
- Infrastructure: `PanelStack.vue`, `Panel.vue`, `PanelWindow.vue`, `usePanel.js`, `usePanelBus.js`, `usePanelAnchor.js`, `usePanelWindows.js`, `usePanelDiagnostics.js`.
- Troupe play: `GmTroupeOverview.vue` (recency + active-main groups), `RollTableMenu.vue` (roll-table-as-menu picker), `useRollTableMenu.js`.

## Migration backlog — complete

Life path and roll table panels have been moved onto the composable pattern:

- `useLifePaths` — `paths` singleton + `fetchLifePaths`, `saveLifePath`, `deleteLifePath`.
- `useRollTables` — `tables` / `allTableNames` singletons + `fetchTables`, `fetchAllTableNames`, `fetchTable`, `saveRollTable`, `deleteRollTable`.

Consumed by `GmLifePathDetailPanel`, `GmLifePathEditPanel`, `GmRollTableDetailPanel`, `GmRollTableEditPanel`, `GmRollTableEntryEditPanel` (plus `GmLifePathsPanel` and `GmEntityEditPanel`'s life-path fetch).

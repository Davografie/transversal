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

- `src/components/gm/PanelStack.vue` — root container (fixed, right-aligned,
  viewport-aware). Renders one root `Panel`.
- `src/components/gm/Panel.vue` — self-referential wrapper. Provides the
  `panelKey` navigation context to its slot content and renders a nested child
  `Panel` when `child` is set.
- A **panel** is the content component rendered inside a `Panel` slot
  (e.g. `GmEntityEditPanel`, `GmTraitEditPanel`). `GmPanel.vue` is the L0 root
  content (modes, entity list, filter bar) — not the wrapper.

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
- Infrastructure: `PanelStack.vue`, `Panel.vue`, `usePanel.js`, `usePanelBus.js`.

## Migration backlog — complete

Life path and roll table panels have been moved onto the composable pattern:

- `useLifePaths` — `paths` singleton + `fetchLifePaths`, `saveLifePath`, `deleteLifePath`.
- `useRollTables` — `tables` / `allTableNames` singletons + `fetchTables`, `fetchAllTableNames`, `fetchTable`, `saveRollTable`, `deleteRollTable`.

Consumed by `GmLifePathDetailPanel`, `GmLifePathEditPanel`, `GmRollTableDetailPanel`, `GmRollTableEditPanel`, `GmRollTableEntryEditPanel` (plus `GmLifePathsPanel` and `GmEntityEditPanel`'s life-path fetch).

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

- `src/components/gm/PanelStack.vue` — the stack: the 🛠 toggle, and the one
  panel layer holding a `.panel-unit` per window (the chain, and each float).
  Owns the stack anchor's drag, the depth-hiding fit loop, and the
  raise-on-click listener — see *Panel stacking*.
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
  replace/toggleCollapse/setDock/move/setDirection/raise`), each window carrying
  `{ id, spec, dock, collapsed, x, y, direction, sourceParentKey, z }`. `z` is the
  window's **stacking rank** — see *Panel stacking*. It also **restores and
  stores** the windows per device — see *Panel persistence*.
- `src/composables/panelWindowPersistence.js` — the storage rules for a window
  (pure functions), and `src/constants/restorablePanels.js` — the allow-list of
  panels a reload may bring back, with every exclusion and its reason.
- `src/composables/usePanelDiagnostics.js` — drag-release dumps: every drag
  start/release records the live DOM geometry *and* each panel's internal layout
  state into `window.__PANEL_DUMPS__` (silent unless `window.__PANEL_DEBUG__`).
- A **panel** is the content component rendered inside a `Panel` slot
  (e.g. `GmEntityEditPanel`, `GmTraitEditPanel`). `GmPanel.vue` is the L0 root
  content (modes, entity list, filter bar) — not the wrapper.

### Panel spec fields

`panel.open({ … })` takes `{ component, title, id, props, listeners, context, badge }`.

- `badge` — a short label the chrome shows in the panel header, before the title
  (and on the collapsed chip). Purely declarative: the opener passes the kind of
  thing the panel is editing and the chrome renders it. The entity editor sets
  the entity's type; any panel can use it for the same purpose.
- `context` — values handed to the panel's component through `PanelScope`. This
  is the **only** way a panel's content can pass something to its own child
  panels: children are rendered by `Panel.vue` as siblings of the slot outlet, so
  a `provide` in the opener never reaches them.

Positioning in one paragraph: the chain derives from a draggable **anchor**
(🛠 closed, the shallowest visible panel's rail open — drag the rail's `⠿` or
the 🛠 itself; the anchor snaps to the nearest viewport edge on drop and is
remembered per device). Panels open away from the anchor's edge (left/right/up/
down), are clamped inside the viewport, slide along their parents' edges, and
each rail hugs **its own** panel's edge. Any child panel can detach (`⤢`) into a
floating window, which keeps its own anchor and direction and docks back (`⤓`)
into the panel it came from, matched by `component + spec.id`. See
[[GM Panel Positioning Plan]]. Overlap between a window and the chain it came from
is resolved by *Panel stacking* below — clicking either brings it to the front.

## Panel persistence (per device)

Floating windows — and whether a panel is **collapsed** to its chip — are
remembered in `localStorage` beside the anchor (`gmPanelAnchor`), because they
belong to *this screen*, not to the campaign. Keys: `gmPanelWindows` (the
windows) and `gmPanelStackCollapsed` (the stack root's chip state, a
`usePersistedRef`). A window's collapse rides in its own record.

**A spec cannot be stored, and that is the whole shape of this.** A spec is
`{ component, title, id, props, listeners, context, badge }`: the component is a
Vue object, `listeners` are closures, `context` holds refs and live instances.
So a window is stored as a **registry name + props + geometry** and rebuilt on
load, and `restorablePanels.js` is a short allow-list rather than "every panel" —
a restored window has **no listeners and no context**, so it shows its record and
edits it (its own mutations are its own) but the *opener's* reactions do not fire
(a gallery refresh, a tree re-read after a save). A panel whose spec needs a
context — one that edits a draft handed to it — must **not** be added to the
list; the file records each exclusion with its reason.

Three properties worth keeping when touching this:

- **Match by `__name`, falling back from identity.** The Vite dev server serves a
  module it has invalidated (HMR) under `<path>?t=<stamp>`, so the same SFC can
  exist as two different objects — the opener's and the registry's. Identity alone
  silently missed and *nothing* persisted.
- **Props are checked, not trusted.** A function or a class instance serializes to
  something that restores wrong, so such a window is not persisted at all. A
  **ref** is refused (a live handle would restore as a plain value); a reactive
  proxy is *snapshotted* through `toRaw`, since a panel opened from a shared store
  has proxy props by construction.
- **The stack's 🛠 open/closed state is not a collapse** and is deliberately not
  persisted ([[GM Panel Positioning Plan]]: closing the 🛠 hides the chain, not
  the windows).
- **A spec prop is a copy, so a panel must not read live session state from one.**
  `listeners` and `context` are not the only things a restored window loses: its
  **props are the values from when the panel was opened**, kept verbatim. Anything
  the panel gates on that can change while it is open — the perspective, the GM's
  location — has to come from App's `provide` (`actingEntityId`,
  `gmCurrentLocationId`), with the prop as the fallback. The bug this rule comes
  from: an entity panel opened while the GM was acting as a character kept
  `currentEntityId` = that character forever, so its *Assume* button was hidden
  even after the GM returned to free roam — visible only in a float, where the
  copy outlives the fact. `check-panel-live-state.mjs` sweeps for the shape.
- **A panel holding a credential is never restorable**, and that is a rule rather
  than a case: a window is stored as a name + props, and `GmAdmissionPanel`'s
  subject *is* an admission token — which the API returns exactly once. Storing it
  would write a credential to `localStorage` and restore a QR that admits nobody.
  Whenever a panel's props would be a secret, the answer is "not on the list",
  with the reason recorded beside the others.
- **A restored panel that throws in `setup()` is a boot crash, not a broken
  panel.** A window on this list is rebuilt on *every* load, so anything that
  throws while its `setup()` runs repeats forever — and the close button that
  would remove the window is drawn by the panel that cannot render. The trap that
  has actually bitten: Vue runs a getter source **eagerly** at `watch()` time to
  collect its dependencies, so `watch(() => form, …)` written *above*
  `const form = reactive(…)` reads a `const` in its temporal dead zone
  (`ReferenceError: Cannot access 'form' before initialization`); Vue rethrows in
  dev, so the one error escalates a frame per level — `watcher getter` → `setup
  function` → `component update` at `PanelStack` — once per reactive flush, which
  is what the 2026-10-13 "the app won't load" report looked like ([[life-path]]'s
  `72624e4f`, repaired in `abbe271c`). The corollary is a requirement of this
  list, not a style note: **a panel added here needs a spec that mounts it**,
  because no static check and no build can see it — nothing mounted
  `GmLifePathDetailPanel` until `e2e/tests/life-path-panel-mount.spec.js`.

## Panel stacking (dynamic z-index)

Clicking anywhere in a panel brings it to the front. The unit of stacking is a
**unit**, not a panel: the chain is one (its panels are laid out side by side and
so never overlap each other) and each floating window is one. Units genuinely do
overlap — a detached window parks exactly on the box its panel occupied, and the
next child opened there lands underneath it — which is what has to reorder.

Four properties carry this, and each is load-bearing:

- **One layer, one wrapper per unit.** `PanelStack` renders a single
  `.panel-viewport` (fixed, `z-index: 25`) containing a `.panel-unit` per unit;
  the unit's `z-index` is its rank. This replaced two sibling layers at the same
  `z-index`, where the order was DOM order — the floats were *always* over the
  chain and clicking the chain could not change it. A unit is a **stacking
  context**, so a unit's own popovers (a chip-input dropdown) stay within it,
  and the ranks stay local: a unit can never climb over the 🛠 toggle or a modal,
  however often you click.
- **A rank, not a pixel value.** `usePanelWindows` hands out `++zSeq`, so "the
  top" is "the highest rank" and raising is a bump. `raise(id)` skips a no-op
  (already the top), which also keeps a click from writing storage. The chain has
  **no window record** — its spec is a prop of `PanelStack` — so its rank lives in
  the registry (`rootZ`) and starts at the back on a fresh load.
- **Opening a panel raises its unit.** `openChild` (and `replaceChild`) call
  `raise(props.windowId)` — the panel that just appeared is the one being worked
  in, so its chain or its window comes forward. This is why a nested panel has to
  know its unit: `windowId` is carried down the tree (`PanelStack` passes
  `'root'`, `PanelWindow` its own id, children inherit), where it used to reach a
  window's *root* panel only — which left every child of a float reporting
  `data-panel-window="root"` and nothing able to say which unit to raise. A click
  raises too, but a click is not an open: keyboard activation dispatches `click`
  with no pointerdown, and a panel opened by another panel's reaction has no
  pointer near it at all. The **🛠's own open** raises the chain explicitly
  (`raise('root')` in `onToggleClick`), because neither rule reaches it: the toggle
  sits *outside* the layer, so the capture-phase listener finds no
  `[data-panel-unit]` ancestor, and the chain never goes through `openChild`.
  Measured before that line: with a float on top, a reload restores the float and
  the chain starts closed — and opening the chain with the 🛠 drew it *under* the
  float, so the panel just opened was hidden by one opened earlier. (Closing the
  chain with a click hides this: the pointerdown on its rail raises the chain on
  the way out, so it happens to reopen in front.)
- **Capture-phase `pointerdown` on `window`.** Not a handler per unit: a panel is
  full of controls that stop propagation (`@pointerdown.stop` on the badge and on
  the collapsed chip's buttons), and any of them would be a dead spot. Capture
  runs before all of them, and the nearest `[data-panel-unit]` ancestor is the
  unit to raise — so a click on a *child* panel raises the window it belongs to.
  (Do **not** read `[data-panel-window]` for this: it is on every `.panel-node`,
  and a child panel currently inherits the default `root` id from `Panel.vue`, so
  the innermost node does not name the unit.)
- **The order of the floats is remembered, renormalised.** `z` is stored with the
  window and `deserializeWindows` compacts the restored ranks into a dense 1..N
  run — which also repairs records written before stacking existed (their `z` is
  the spawn index, whose first value is 0 and would tie with the chain and land
  that window *behind* it). The chain's rank is not stored, so the sequence in
  storage has gaps; the **order** is the promise, not the numbers.

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

- `useEntityFilter(entities, playerHoldings?, agencyByEntity?)` — filter bar,
  suggestions, filtered projections. Its **suggestion list** is the whole match
  set, in the canonical order (below) and revealed a page at a time
  (`pageSize: 20`; `GmPanel` calls `loadMore` when the box is scrolled to its
  end, and the combobox's own `move` does at the end of the keyboard's walk).
  It used to be `maxResults: 10`, which **truncated** the list in database order:
  measured live, "wang" matched 21 rows and the last ten Wang GMCs could not be
  surfaced by typing anything at all. Never cap a suggestion list — page it.
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
- `ConditionEditor`, `EffectEditor`, `GmEntityForm` — sub-form editors.
- `TraitInstanceEditor` (in `components/ui/`) — the trait-rating editor shared by
  the character sheet and the effect form's *Gain Trait* action. Controlled:
  `v-model` per field (`ratingType` / `dice` / `capacity` / `die` / `polarity` /
  `statement` / `notes`) plus a `change` event naming the field, so hosts own
  persistence. `mode="array"` edits dice rows (sheet), `mode="single"` edits one
  die with an optional variable mode (effects); `variant="box"` is the compact
  form chrome. Host extras ride the `after-dice` / `after-fields` / `actions`
  slots.
- `GmTraitPicker` — trait search/select with universe filtering.

Shared panel CSS lives in `src/frontend/src/assets/gm-panel.css` (imported
globally in `main.js`). Component-specific styles stay scoped, with a unique
per-component class prefix.

## Rule 6 — Props carry identity/context only

Panels receive IDs or small config (`id`, `index`, `universe`), or the specific
object being edited when the opener already holds it. They never receive a data
tree that a parent assembled specifically to pass down.

## Shared table component — what the GM surfaces need

> [!note] Handover to [[ui-ux]], 2026-09-20 — requirements, not conventions
> Written at the human's request, ahead of [[ui-ux]] building a **unified table
> component** to serve consequence menus, roll tables, life paths and
> character-creation wizards. The durable home for the *conventions* is
> [[UI-UX Design]] § *Shared primitives*, which is [[ui-ux]]'s doc and does not
> yet have a table/list-row section (its nearest is § *Character sheet →
> Sub-traits and containers*). This section is the GM-side input to that; it is
> evidence about the surfaces, not a proposed API.

**Read alongside [[applied-mechanics]]' brief.** They have briefed [[ui-ux]] on the
same component from the *behaviour* side (2026-09-25): the consequence menu's
`menuContext`, `side`, `effectDie` and `excludeIds` are computed from the roll's
outcome in `DiceRoller.vue`, not by the menu, and each can be lost silently by a
generic table. That is their half and this section does not repeat it — but the
split is worth stating, because the files are split the same way: the menu
**components** (`ConsequenceMenu`, `HitchMenu`, `RollTableMenu`) are gm-panels',
while their **data wiring** (`useConsequences`, `useHitchMenu`,
`useRollTableMenu`, `DiceRoller`) is theirs. They also count **five table-like
pickers, not three** — `EntryPicker` is the shared renderer behind all of them —
which agrees with the surface list below.

### Half of it already exists

`GmList` + `GmListItem` (`components/ui/`) are the existing controlled list:
`items`/`itemKey`, selection (`selectedIds`, or `selectable` for a ✓/+ pick
affordance), drag-reorder (`reorderable`, plus `dragHandle` for rows containing
inputs, where whole-row drag would break text selection), per-row semantics
(`rowState` → `is-active|disabled|warning|danger|success|muted`, `rowClass`),
and the `loading` / `emptyText` / `maxHeight` states. Rows render the global
`.entity-row` shell from `assets/gm-panel.css`; drag is `useDragDrop` (HTML5 dnd
plus touch long-press, ⠿ handle = instant).

**13 files, 17 call sites** consume it — `GmPanel` (factions), `TargetSpecBuilder`,
`EffectList`, `GmRollTableEditPanel`, `GmRollTableGroupPanel`, `GmRollTablesPanel`,
`GmLifePathDetailPanel`, `GmTraitEditPanel` (×5), `GmTraitBatchEditPanel`,
`GmTraitsetDetail`, `GmTraitsetsPanel`, `GmSfxManagementPanel`, `GmSfxPickerPanel`.
Which capability each uses is not uniform: `reorderable` in `EffectList`,
`GmRollTableEditPanel`, `TargetSpecBuilder`, `GmTraitsetsPanel`; `selectable` in
`GmSfxPickerPanel`, `GmTraitBatchEditPanel`; `:loading` in only three. A unified
component should **subsume or wrap this**, not sit beside it — otherwise my
surfaces get a second list vocabulary on top of the first.

### What these surfaces need that a fixed-column table cannot give

1. **Column sets that are data-driven, not declared.** `ConditionEditor`'s
   columns change with the condition *type*; `EffectForm` builds one merged field
   list from backend action metadata (`fieldOrder`, `refsFirst`); my
   `GmRollTableEditPanel`'s entry rows switch between min/max, weight, tier and
   nothing depending on the table's sibling `scheme` field. A per-row template
   escape hatch is mandatory.
2. **Rows are stacked blocks of unbounded height**, not single lines —
   `BoundVariablesEditor`, `EffectRefField`, and `TargetSpecBuilder`'s step cards
   embed a whole nested builder per row, and a roll-table entry nests
   `ConditionEditor` + `EffectEditor`.
3. **A row pick can spawn a wizard.** `RollTableMenu` and `ConsequenceMenu` are
   menu → target-resolution (`EffectTargetWizard`) → applied; the row is phase one
   of three, not the whole interaction.
4. **Weighted random pick, and rows that are disabled / priced / toned**
   (`EntryPicker`: 🎲 weighted choice, `cost`, `tone` gm/player edge, disabled).
5. **Async, backend-computed per-row validity.** `TargetSpecBuilder` shows
   `.tsb-valid` / `.tsb-error` from a server-side trace, plus a destination
   summary — validity is not a local predicate.
6. **Order that is semantic but not draggable.** `BoundVariablesEditor`'s
   `scopeFor(i)` exposes only *earlier* rows' variables to row `i`; the order
   matters and there is deliberately no reorder control.
7. **Real read-only tables with derived cells.** `GmRollTableDetailPanel` is a true
   `<table>` (`# | Key | Label | Effects`) whose Key is derived from min–max /
   weight / tier, and `GmLifePathDetailPanel`'s discovery is a two-column table.
8. **Three different reorder write paths, three selection semantics.** Reorder
   either splices a local array and re-PUTs the whole parent
   (`GmRollTableEditPanel`), or emits `update:modelValue` (`EffectList`), or
   writes a path's step order (`TargetSpecBuilder`). Selection is either absent,
   an `editingIndex` highlight, a multi-count candidate set, or a phase machine.

An index column is usually **position-derived** (`#{{ i + 1 }}`), not stored.

### Constraints it must respect (from this scope)

- **Theme tokens only, and my harness will judge it.** `--accent-dim` is a **fill**
  token and flips to a pale tint in light theme, so it must never carry text.
  `scripts/check-theme-tokens.mjs` walks **all** of `src/` and holds every
  `color: var(…)` to a **3:1** floor against the light panel — a new `ui/`
  component is covered automatically — and it asserts it can still fail.
- **`Button` for every action, with `:loading` always wired** when the handler
  awaits. Mind the stale-prop trap: pass the **live ref or shared singleton**,
  never a value snapshotted at panel-open.
- **There are no form primitives.** `components/ui/` has Button, DangerButton,
  EntryPicker, GmList/GmListItem, SearchDropdown, SegmentedControl, TagInput,
  TargetPicker, TraitInstanceEditor — and **no text, number, select or checkbox
  input**. The app hand-rolls **100** `<input>`, **85** `<select>` and 5
  `<textarea>`. An *editable* unified table therefore needs those primitives
  first, or it will hard-code raw elements and reproduce the inconsistency being
  removed.
- **Fix the literals while in there:** `RollTableMenu.vue` overlay
  `rgba(0,0,0,0.5)`, `EffectForm.vue` `rgba(64,184,96,0.2)`, `ConditionEditor.vue`
  `var(--warn, #d8a13a)` fallbacks.
- **"Wizard candidate rows" are on [[UI-UX Design]]'s *raw by design* list** —
  `.etw-candidate` in `EffectTargetWizard.vue` (mine) and the life-path wizard's
  ([[life-path]]'s). Absorbing them retires that entry; the list is [[ui-ux]]'s
  to update (I audited it, per `a1b9ff5`).
- **Reuse the existing form/state vocabulary** in `assets/gm-panel.css` rather
  than inventing a parallel one: `.ps-form` + `.ps-form label` (the stacked
  label/field layout every row editor uses), `.ps-section-title`, `.danger-zone`,
  and the shared `.empty` / `.loading` state text (which is what `GmList` renders
  for `emptyText` and `loading`). The panel header's own actions — detach ⤢, dock
  ⤓, close ×, collapse ▾ — are the vocabulary a table toolbar should sit beside,
  not replace.
- **My scope is the roll-table and menu half of the brief.** Of the four named
  targets, **character-creation wizards** are [[character-sheet]]'s (with
  [[life-path]]'s `LifePathWizard.vue`); the consequence menus, roll tables and
  life-path *authoring* panels are mine. Worth asking those two for their half
  before fixing the API — and [[life-path]] already has an open
  [[ui-ux]] request for a *runtime* choice surface (menu → pick → effects) that
  overlaps `EntryPicker`, so the two requests should be settled together.
- **Panel conventions still apply** (Rules 1–6 above): data and mutations in
  composables, singleton domain state, navigation via `usePanel()`, cross-panel
  events via `usePanelBus()`, props carry identity/context only.
- **A row editor in a child panel cannot be handed a draft by `provide`.**
  Slot content cannot provide to that panel's *children* — use the panel spec's
  `context` + `PanelScope` (see `effects.md`'s note). And a **detached** window
  copies the spec, and so its context, at spawn: it keeps editing the draft it
  was spawned with. Roll-table entries currently open in child panels
  (`GmRollTableEntryEditPanel`), so this is live.
- **Never re-read a list on a row save — patch the row in place.** A re-read
  blanks the list and re-renders it under the cursor; that was [[P7.17]]/`82cb2949`.
- **Ordering must be a total order.** The entity list has no `SORT`, so where a
  table's order matters it is rank → name → id (or position), never arrival order.
  `compareEntityOrder(a, b, agency)` in `constants/entityTypes.js` is that
  comparison, named; the location tree, the sheet's contacts and the peer strip
  each open-code the same three keys from `entityTypeRank`.
- **`.entity-row` and `useDragDrop` are shared with the location tree.** The tree
  is **not** a table consumer — its rows come from `useLocationTree.flattenTree`
  (depth, `more`/`add` rows, three reveal states) — so do not try to fold it in,
  but changing the row shell or the drag composable reaches it.
- **Don't regress the a11y that exists.** `SearchDropdown`, `TagInput` and
  `SegmentedControl` carry proper combobox/listbox/option or radiogroup roles;
  most table-ish GM surfaces carry none, so there is room to add, not to remove.

### Verification

There is no frontend test runner: checks are plain `node` scripts in
`src/frontend/scripts/check-*.mjs`, run against the `transversal2-frontend:latest`
image (build the same way, in Docker). **33 suites exist** (the count was 14 when
the shared table component was handed over) and a shared primitive can move
several — `check-theme-tokens`, `check-combobox`, `check-trait-tree`,
`check-panel-close`, `check-panel-placement`, `check-panel-persistence`,
`check-panel-stacking`, `check-admission-panel`, `check-trait-instances`, `check-panel-live-state`, `check-player-filter`, `check-tree-expand/order/locate`,
`check-place-filter`, `check-trait-explanations`, `check-sheet-profile`,
`check-sheet-api`, `check-landing`, `check-auth-gate`, `check-entity-create`. **Ping [[gm-panels]]
when the component lands** and I will re-run them and migrate my 17 call sites —
tell me whether you want that migration or will take it, and once the API is
chosen, which of the eight capabilities above it covers.

> [!warning] A node check cannot prove a *browser* fact
> `e2e/` (Playwright, run from the host: `cd e2e && npm test`) is the rendering
> and interaction half. Floating-panel persistence is the cautionary case: the
> node check passed **53/53 while the feature did nothing at all**, because
> whether a detach writes to `localStorage` and whether a reload restores a window
> are browser facts. Anything about layout, scrolling, focus or storage belongs in
> a spec there — assert geometry **numerically** rather than with
> `toBeInViewport`, which samples mid-flight and is flaky across engines.

## Reference panels

- Thin consumer panels: `GmPanel.vue` (root), `GmEntityEditPanel.vue`, `GmTraitEditPanel.vue`.
- Infrastructure: `PanelStack.vue`, `Panel.vue`, `PanelWindow.vue`, `usePanel.js`, `usePanelBus.js`, `usePanelAnchor.js`, `usePanelWindows.js`, `usePanelDiagnostics.js`.
- Troupe play: `GmTroupeOverview.vue` (recency + active-main groups), `RollTableMenu.vue` (roll-table-as-menu picker), `useRollTableMenu.js`.
- Trait instances ([[B280]]): `GmTraitInstancesPanel.vue` — every instance of one
  trait **definition**, each row naming the host it hangs off (an entity, a body,
  a relationship, or the super-trait of a sub-trait), with the bulk edits a
  migration cleanup needs. Opened from the trait editor's *Instances* section and
  keyed by trait, so two traits get two panels. The read is the API's
  `traitInstances(traitId)`, which exists because every other trait-setting read
  walks *from* a host and cannot answer "who holds this?". Host wording and the
  filter predicate are pure (`utils/traitInstanceHost.js`); the fan-out is bounded
  (6), because one definition carries 547 instances.
- Admission (SEC-3): `GmAdmissionPanel.vue` — the invitation a GM shows the table. A **block opens it** (`AdmitPlayersBlock` is the Players tab's switch and open list; the QR and the link are the panel), it takes **no props** and reads the shared `useAdmission()` state, so a window closed from the tab cannot leave a QR on screen for a token that no longer admits. A panel that renders a **credential** is never restorable — see *Panel persistence*.

## Migration backlog — complete

Life path and roll table panels have been moved onto the composable pattern:

- `useLifePaths` — `paths` singleton + `fetchLifePaths`, `saveLifePath`, `deleteLifePath`.
- `useRollTables` — `tables` / `allTableNames` singletons + `fetchTables`, `fetchAllTableNames`, `fetchTable`, `saveRollTable`, `deleteRollTable`.

Consumed by `GmLifePathDetailPanel`, `GmLifePathEditPanel`, `GmRollTableDetailPanel`, `GmRollTableEditPanel`, `GmRollTableEntryEditPanel` (plus `GmLifePathsPanel` and `GmEntityEditPanel`'s life-path fetch).

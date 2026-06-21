# Panel — Self-referential Component Plan

> Status: PLANNING | Started: 2026-06-20

## Decisions from user

| # | Question | Answer |
|---|---|---|
| 1 | Component resolution | `defineAsyncComponent` — if it works, it works. Prefer direct component refs (already imported). |
| 2 | Skip (not asked) | — |
| 3 | Parent/child communication | Props down, emits up, `expose` where needed. `open()` creates child; `onRefresh`/`onPatch` flow upward. |
| 4 | Positioning | Flex everywhere. Root PanelStack = `position: fixed`. Inner panels = flex children. Mobile: deepest panel only, closing reveals parent. |

## Architecture

```
PanelStack (position: fixed, flex row-reverse, right-aligned)
  └─ Panel (root)
       └─ GmPanel                              ← L0 content
            └─ Panel (nested, v-if child)
                 └─ GmTraitsetDetail            ← L1 content
                      └─ Panel (nested, v-if child)
                           └─ GmTraitEditPanel  ← L2 content
                                └─ Panel (nested, v-if child)
                                     └─ GmSfxEditPanel  ← L3 (terminal)
```

## Panel.vue API

```vue
<Panel title="Traitsets" closable>
  <template #default="{ open }">
    <!-- editing component gets open({ component, title, props }) -->
  </template>
</Panel>
```

- `open({ component, title, props })` — opens a nested Panel. `component` is a Vue component ref.
- `@close` — emitted when close button clicked. Parent sets `child = null`.
- `nested` prop — true for inner panels (relative positioning), false for root (PanelStack child).

## Task List

| # | File | Change | Priority |
|---|---|---|---|
| 1 | `Panel.vue` | Rewrite: add `child` ref, `nested` prop, scoped slot with `open()`, self-reference | P0 |
| 2 | `PanelStack.vue` | Simplify to single root Panel wrapper. Remove multi-panel array, cascadeCloseTo. Keep viewport clipping. | P0 |
| 3 | `GmPanel.vue` | Remove `activeTrait`/`activeSfx`/`activeTraitId`/`activeSfxId`. Remove `onTraitConfigSelect`/`closeTraitConfigLevel`. Simplify `traitConfigPanels` to L0 only. Entity panels use `open()`. | P0 |
| 4 | `GmTraitsetsPanel.vue` | Accept `open` from slot. `@click` calls `open()`. | P1 |
| 5 | `GmTraitsetDetail.vue` | Accept `open` from slot. Trait clicks and "+ New Trait" call `open()`. Move trait CRUD out. Keep traitset form. | P1 |
| 6 | `GmTraitEditPanel.vue` | Accept `open` from slot. SFX clicks and "+ New SFX" call `open()`. Move SFX CRUD out. Keep trait form, create trait, delete trait. Handle create mode (`trait=null`). | P1 |
| 7 | `GmSfxEditPanel.vue` | Move SFX CRUD in (create, update, delete). Handle create mode (`sfx=null`). Terminal node — no `open`. | P1 |
| 8 | `GmEntityForm.vue` | No changes needed. | — |
| 9 | Tests | Verify backend unchanged. Manual smoke test of frontend panel navigation. | P2 |

## CRUD Ownership (final state)

| Panel | CRUD it owns | Opens via `open()` |
|---|---|---|
| GmTraitsetDetail | Traitset (form auto-save), delete traitset | GmTraitEditPanel |
| GmTraitEditPanel | Trait (form auto-save), create trait, delete trait | GmSfxEditPanel |
| GmSfxEditPanel | SFX (form save), create SFX, delete SFX | — (terminal) |

## Data flow

```
fetchTraitsConfig() in GmPanel
  → traitsets[] (with nested traits)
  → allSfxs[]
  → passed as props down the Panel chain
  → onRefresh / onPatch flow back up
```

## GmPanel — what gets removed

- `activeTrait`, `activeTraitId`, `activeSfx`, `activeSfxId` refs
- `onTraitConfigSelect(item)` — type-sniffing function
- `closeTraitConfigLevel(level)` — cascading close
- `traitConfigPanels` L2/L3 entries
- `sfxForm` ref (moves to GmSfxEditPanel)

## GmPanel — simplified traitConfigPanels

```javascript
const traitConfigPanels = computed(() => {
  if (!open.value) return []
  return [{ id: 'gm', component: GmPanel, hideClose: true }]
  // No more level tracking. GmPanel's template handles sub-panels via Panel.
})
```

Actually, GmPanel itself becomes a regular editing component like the others.
The PanelStack renders: `[root Panel wrapping GmPanel]`.
GmPanel's template uses `open()` to spawn GmTraitsetDetail as a child Panel.

## Edge Cases & Resolutions

| # | Edge Case | Resolution |
|---|---|---|
| E1 | Rapid open/close stacking two of same level | Guard in `open()`: if `child` already set, close it first before opening new one. |
| E2 | Close then re-open (form state loss) | All forms auto-save. Fresh mount picks up latest DB state via props. Acceptable. |
| E3 | Create mode vs edit mode | `trait=null` / `sfx=null` signals create mode. Component renders blank form. On save, calls create mutation + `onRefresh`. |
| E4 | Panel title stale after edit | Title set at open time — won't update if edited. Acceptable trade-off for now. Could add reactive title via `computed` in parent if needed later. |
| E5 | Mobile: deepest panel only | Nested Panel has `position: absolute; inset: 0` inside parent on mobile. Covers parent completely. Closing unmounts → parent visible. |
| E6 | `onRefresh` causes stale refs | After `fetchTraitsConfig`, re-bind `activeTraitset` by matching ID. GmTraitsetDetail does same for `activeTrait`. |
| E7 | Drag-and-drop + click conflict | Check `dragIndex < 0` before calling `open()` on click. Dragging never opens. |
| E8 | Entity panels (inspect/edit/create) in new system | GmPanel manages entity panels internally. `Switch to Sheet` / `Edit` are child Panel swaps. `editing`/`inspectedEntity`/`creating` flags retained for entity mode only. |
| E9 | Animation transitions | Nested panels slide in from right via CSS transition on `transform: translateX()`. `v-if` with `<Transition>` wrapper. |

## Mobile: deepest-panel-only design

```
┌──────────────────────┐
│ PanelStack (fixed)   │
│  ┌──────────────────┐│
│  │ Panel (hidden)   ││ ← parent, covered by child
│  │ ┌──────────────┐ ││
│  │ │ Panel (vis)  │ ││ ← deepest, covers parent
│  │ │  GmTraitEdit │ ││    position: absolute; inset: 0
│  │ │              │ ││
│  │ └──────────────┘ ││
│  └──────────────────┘│
└──────────────────────┘
```

On mobile: nested Panel uses `position: absolute; inset: 0` → fills parent → parent invisible.
On desktop: nested Panel uses flex layout → slides in beside parent.
Close → `child = null` → Panel unmounts → parent Panel visible again.

## Rollback Plan

If self-referential Panels introduce unresolvable complexity:
1. Revert Panel.vue and PanelStack.vue to current state
2. Restore `onTraitConfigSelect` and `activeTrait`/`activeSfx` in GmPanel
3. Fix only the `traitsetId` missing-field bug (one-line change)

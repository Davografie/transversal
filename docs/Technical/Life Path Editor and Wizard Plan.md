---
title: Life Path Editor and Wizard Plan
tags:
  - transversal
  - technical
  - life-path
  - roll-table
  - frontend
  - editor
  - wizard
  - plan
aliases:
  - Editor Wizard Plan
  - Life Path Editor
  - Life Path Wizard
---

# Life Path Editor and Wizard Plan

> [!note] Status
> Agreed plan, pre-implementation. Builds on [[Unified Effects Plan]] and [[SFX and Effects]]. Backend for effects / roll tables / term execution is already complete; this plan covers the authoring and execution **frontend**, plus the small amount of backend authoring API still missing.

## Goal

Replace the old `qualification/curriculum/…` life-path UI with a **recursive panel system** that authors and runs the new model — a life path is an entry point into a graph of linked roll tables whose entries execute effects. Each data layer gets its own GM panel, drilled down in sequence.

## Data layers (one panel each)

1. **Life path** — metadata, discovery, entry table.
2. **Roll table** — scheme, die, optional check, entries.
3. **Entry** — label, range / weight / tier, conditions, effects.
4. **Effect** — the shared vocabulary (timing / type / action / target / result / target_scope / context).
5. **Condition** — type / target / value / narrative.

## Navigation model (drill-down)

```
GmLifePathsPanel            (list paths)
 └─ GmLifePathDetailPanel   (path + its tables)
     ├─ GmLifePathEditPanel (edit path)
     └─ GmRollTableDetailPanel   (table + entries)
         ├─ GmRollTableEditPanel (edit table)
         └─ GmRollTableEntryEditPanel (edit entry)
             ├─ EffectEditor       (leaf — reusable with SFX editor)
             └─ ConditionEditor    (leaf)
```

Recursion comes from following `next_step` effects: from a table you can open the target table, so authoring the linked graph feels like one structure rather than flat forms.

## Backend authoring API (still missing)

The editor/wizard can't be built until the roll-table surface exists in GraphQL:

- **Types** — `RollTable`, `RollTableEntry`, `RollTableCheck`, `Condition` (+ inputs).
- **Expose `Effect.context`** on `Effect` / `EffectInput` (needed for relationship-trait effects and `next_step` `return_to`).
- **Queries** — `rollTables(lifePathId?)`, `rollTable(id)`; extend `lifePaths` (or add `lifePath(id)`) to return the full table graph for a path.
- **Mutations** — `saveRollTable(input)`, `deleteRollTable(id)`. (`saveLifePath` / `deleteLifePath` already exist.)

## Phased rollout

Each phase is independently shippable and visible.

### Phase 1 — Read-only details
Backend read API (types + `rollTables` / `rollTable` + `Effect.context`).
Frontend: `GmLifePathDetailPanel` (path metadata + linked tables) and `GmRollTableDetailPanel` (scheme / check / entries / effects / conditions, read-only).

- *Verify:* can drill path → table and see seeded Verdant + Rogue content; backend pytest + frontend build green.

### Phase 2 — Life path + roll table editing
Backend write API (`saveRollTable` / `deleteRollTable` + inputs + `ConditionInput` + `EffectInput.context`).
Frontend: `GmLifePathEditPanel` (metadata + discovery + entry table) and `GmRollTableEditPanel` (scheme / check / entry list CRUD).

- *Verify:* create/edit/delete a table from the panel and it round-trips through the DB.

### Phase 3 — Entry, effect, condition editors
Frontend: `GmRollTableEntryEditPanel` (label, min/max, weight, tier), plus a shared `EffectEditor` (extracted from `GmSfxEditPanel.vue`) and a `ConditionEditor`.

- *Verify:* author an entry with a `gain_or_step_up` effect and a `has_trait` condition; it renders and re-loads.

### Phase 4 — Life path wizard
Frontend: rebuild `LifePathWizard.vue` on `startTerm` / `resolveStep`. Render the current table with clickable rows, drive check tables server-side, show applied vs `scheduled` effects, and resume mid-term from `pending_term`.

- *Verify:* walk the seeded Rogue Cultivator path start-to-muster on a test character.

### Phase 5 — Target-choice dialogs (deferred, later)
Backend `resolveChoice` + pending-choice persistence on the term checkpoint; frontend modal filtered by `target_scope`. Confirmed out of the initial rollout.

## Deferred (unchanged)

- DiceRoller visibility for every life-path roll.
- Trait-rating signed-value redesign.

## Frontend conventions

- Composition API with `<script setup>`; composables `useApi`, `usePanel`, `usePanelBus`.
- Props down, events up; state in `App.vue`.
- Panels open through the existing panel system (see `GmLifePathsPanel.vue` for the current pattern).

## Decision log

- **Target-choice resolution** deferred to Phase 5; seeded content has no `{choose_*}` targets, so it is not a blocker.
- **Full graph editor** from the start (every layer authorable), rolled out in the phases above.

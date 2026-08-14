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
> Phases 1–4 are complete: roll-table read/write API, editor panels, shared `EffectEditor`/`ConditionEditor`, and the player wizard rebuilt on `startTerm`/`resolveStep` with a roll → highlight → Continue flow. Roll tables now carry a **roll source** (`FIXED_DIE` | `TRAIT_DICE`) and a `trait_dice_count`; the old TIER `check` (difficulty pool) is retired. Phase 5 (target-choice) is deferred. Builds on [[Unified Effects Plan]] and [[SFX and Effects]].

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

- Trait-rating signed-value redesign.
- **Faction picker for multi-faction life paths** — Phase 4 resolves the offering faction via `LifePath.factionIds` and defaults to the first one. When a life path is offered by multiple factions, the wizard must ask which faction to enroll under before calling `startTerm`. When implementing this picker, remember that `startTerm`'s `factionId` is what binds rank/tenure relationship traits to the `character ↔ faction` `membership` edge, so the choice is per-enrollment, not global.
- **Effect `context` field UI** — replace the raw JSON textarea in `EffectEditor` with metadata-driven, per-action context fields (e.g. `relationship` → faction dropdown, `return_to` → roll-table dropdown, `description` → text). Requires extending `EffectActionMeta` with a `context_fields` declaration and exposing it via `effectActions`; `Effect.context` storage stays a dict.

## Frontend conventions

- Composition API with `<script setup>`; composables `useApi`, `usePanel`, `usePanelBus`.
- Props down, events up; state in `App.vue`.
- Panels open through the existing panel system (see `GmLifePathsPanel.vue` for the current pattern).

## Decision log

- **Target-choice resolution** deferred to Phase 5; seeded content has no `{choose_*}` targets, so it is not a blocker.
- **Faction↔life-path link** resolved via `LifePath.factionIds` (GraphQL), derived from faction entities' `suitable_life_path_ids`. Phase 4 defaults to the first faction; the multi-faction picker is deferred (see Deferred).
- **Roll source (trait dice)** — roll tables declare `roll_source` (`FIXED_DIE` = original fixed die | `TRAIT_DICE` = player picks `trait_dice_count` traits they have) and a `trait_dice_count` (default 1, extensible to N≥1). Trait dice apply to RANGE/INDEX/TIER; WEIGHT stays proportional. The rolled number selects the entry: RANGE→min/max, INDEX→position (1-based MOD wrap for out-of-range), TIER→fixed result→tier buckets (1-2 fail, 3-5 marginal, 6-8 success, 9-11 exceptional, 12 perfect). Trait value: static = highest die, resource = sum (capped, then MOD-wrapped). The picker hides traits whose die exceeds the table max.
- **TIER `check` retired** — the old trait-pool/difficulty check is superseded by the roll-source model; `_resolve_check` no longer runs and `check` remains in the model only for backward-compat. TIER is now just "RANGE with fixed ranges".
- **Server-side rolling, surfaced in `DiceRoller.vue`** — the Cortex resolver stays server-side (`/roll`); the wizard pre-populates `DiceRoller` (`mode="lifepath"`) with the table/trait dice, the player clicks Roll, `DiceRoller` shows the faces, and the wizard highlights the matched row; Continue applies it via `resolveStep(index:)`.
- **Full graph editor** from the start (every layer authorable), rolled out in the phases above.

---
title: Unified Effects Plan
tags:
  - transversal
  - technical
  - sfx
  - effects
  - life-path
  - roll-table
  - architecture
  - plan
aliases:
  - Operational Effects
  - Effect Spec
  - Effects Unification
  - RollTable
---

# Unified Effects Plan

> [!note] Status
> Agreed plan, pre-implementation. See [[SFX and Effects]], [[Character Growth]], [[Data Model]], and [[System Architecture]] for surrounding context.

## Goal

One shared effect vocabulary (`type / action / target / result` + `timing`) and one repo-first applier, consumed by both SFX and life-path consequences. The life path is a composition of **roll-tables** whose entries execute effects.

## Core principles

- **One canonical effect model** — no `EffectAction` / `SfxEffect` split, no conversion step.
- **No `polarity` field** — sign derived from `(type, action)` via metadata `category` (`cost` / `benefit` / `either`).
- **An effect is an effect** regardless of which surface authored it. No life-path-exclusive mutation kinds — including flow/control (draft, force-muster, next-step).
- **Checks are tables.** A qualification/survival/advancement check is a roll-table whose entry is selected by the roll result (tier or number range).
- **Two-layer delivery:** the unified Effects layer first, RollTables second.

## Canonical effect spec

```
Effect:
  timing        (immediate | end_of_beat | end_of_scene | end_of_session | after_beats | on_condition)
  type          (modify_trait | transfer_razmerit | rank | life_path | relationship | ...)
  action        (gain | step_up | gain_or_step_up | gain_complication | earn | spend | set | discover | next_step | draft | force_muster | create | ...)
  target        (id | "self" | {choose_trait} placeholder | "" for unresolved)
  result        (die | integer | rank | rel_type | "" — depends on type/action)
  target_scope  (optional narrowing for target choice)
  context       (optional dict — e.g. relationship description)
```

Sign is not stored. Costs (`spend`, `step_down`, `gain_complication`) and benefits (`earn`, `gain`, `step_up`, `gain_or_step_up`) derive from `(type, action)` / `category`.

## Effect vocabulary

**Trait / character**

- `modify_trait` / `gain` — target = trait_id, result = die. Traitset resolved from the trait registry.
- `modify_trait` / `step_up` — target = trait_id.
- `modify_trait` / `gain_or_step_up` — target = trait_id, result = die. Create at `result` if absent, else step up.
- `modify_trait` / `step_down` — target = trait_id.
- `modify_trait` / `gain_complication` — target = trait_id, result = die.
- `modify_trait` / `set` — target = trait_id, result = die.

**Razmerit**

- `transfer_razmerit` / `earn` — target = "self", result = integer.
- `transfer_razmerit` / `spend` — target = "self", result = integer.
- `transfer_razmerit` / `transfer` — target = entity_id, result = integer.

**Rank and life-path flow**

- `rank` / `set` — target = life_path_id, result = rank number.
- `life_path` / `discover` — target = path_id.
- `life_path` / `next_step` — target = "" (or a step id); advances the term.
- `life_path` / `draft` — target = path_id.
- `life_path` / `force_muster` — target = "".

**Relationships**

- `relationship` / `create` — target = entity_id, result = rel_type (+ `context.description`).

Every primitive gets an `EffectActionMeta` entry with `category`, `valid_timings`, `fields`, and `requires_choice` + `target_kind`.

> [!warning] Reconcile step-up semantics
> `step_up` and `gain_or_step_up` should both mean "step up the smallest die, capped at d12." Today the curriculum learn path steps the smallest die while the SFX `step_up` handler steps `dice[0]` — converge on smallest-die/cap-d12.

## Razmerit amounts

Effects carry a **resolved integer**. The executor rolls dice expressions (`"1d6"`) and applies per-term multipliers *before* building the effect, so the applier stays plain.

## RollTables (second change — design sketch)

A `RollTable` is a reusable data unit: a set of entries, each carrying a label, optional condition, and `effects: list[Effect]`.

- **Multiple entry-selection schemes are supported**, configured per table — not one global choice:
  - **Range** — entry declares `min` / `max`; a rolled number falls into one range.
  - **Weight** — entry has a weight; selection is proportional.
  - **Tier** — entry keyed to a Cortex outcome tier (`fail` / `marginal` / `success` / `exceptional` / `perfect`); used by check-tables.
  - **Index** — ordered list; roll 1 → first, 2 → second.
- **Manual / physical dice** — the user can click a row in the table to communicate what they rolled, or provide a rolled number/tier that the app maps to an entry.
- **Flow effects** (`next_step`, `draft`, `force_muster`) move the term forward; a term reduces to *resolve current table → apply the chosen entry's effects → repeat until a terminal flow effect*.

### Settled decisions for Change 2

- **RollTables are first-class ArangoDB documents** in a new `roll_tables` collection, each with `_key`/`id` and `name`, plus an optional `life_path` field (null = shared/general table). A life path holds an entry-point table id; tables are linked by `next_step` effects whose `target` is the next table's `_key`.
- **Checks keep the dice pool.** A check rolls a pool (predetermined trait, combination of traits, or free player choice) against a difficulty; the outcome tier selects a tier-keyed entry. The effect die is degree-of-success, not the pass/fail gate.
- **Learn is a RollTable** — no separate curriculum logic. `CurriculumItem` dissolves into a table entry + `gain_or_step_up` effect + a `min_rank` condition.
- **Conditions/limits become a distinct `Condition` data unit**, parallel to `Effect`: `{ type, target, value, narrative }`, evaluated automatically against the entity. `min_rank`, `at_location`, `has_trait`, `has_relationship`, `always`, and `narrative` are the initial types. SFX's narrative `limit` stays as-is for now.
- **`roll_tables` collection + entries = a new database data type.**

## In scope

1. Unify the effect model and metadata catalog.
2. Repo-first shared applier.
3. Route SFX mutations through the applier.
4. Build the RollTable unit.
5. Re-model life-path phases as tables/checks; per-phase term execution with immediate effects, `Entity.pending_term` checkpoint, and target-choice plumbing.
6. Implement the missing mishap effects (razmerit loss, rank demotion, relationship edge).

## Out of scope (follow-ups)

- Full DiceRoller visibility for every life-path roll.
- Trait-rating signed-value redesign (`TraitSetting.negative` / `ChallengePolarity`).

## Delivery sequence

### Change 1 — Unified Effects layer

**C1.1 — Canonical effect model + vocabulary catalog.**
Introduce a single `Effect` domain model (replacing `EffectAction` + `SfxEffect`), drop `polarity`, add `target_scope` + `context`, and add the vocabulary above (including `gain_or_step_up` and the `life_path` flow effects). Update GraphQL types, `effects_engine` / `effects_applier` (cost check becomes `type + action` only), and seed data. Remove the `SfxEffect → EffectAction` conversion.

- *Verify:* backend pytest green; frontend build green; SFX editor renders without polarity.

**C1.2 — Repo-first applier.**
`apply_effects(entity, effects, repo)` — pure in-memory mutation, no I/O; returns `AppliedEffect` records plus any unresolved `PendingChoice`s. Resolves literal targets, placeholders, and `{choose_*}`.

- *Verify:* unit tests per primitive; no DB/SSE side effects.

**C1.3 — Route SFX mutations through the applier.**
`process_event` keeps trigger matching + scheduling, but mutating effects resolve through `apply_effects`. `EffectAction` fully removed.

- *Verify:* SFX tests green; razmerit spend/earn and trait step-up behave identically.

### Change 2 — RollTables + life-path re-model

**C2.1 — RollTable unit.**
Build the `RollTable` data unit with the selection schemes above and click-to-select manual entry. Table entries execute effects via `apply_effects`.

- *Verify:* unit tests per selection scheme; manual entry selection resolves the correct effects.

**C2.2 — Re-model life-path phases as tables/checks.**
Introduce the `Condition` data unit + evaluator, add the `roll_tables` collection and repository CRUD, and re-shape `LifePath` to reference roll tables (entry-point table + `next_step`-linked tables) instead of the bespoke `QualificationInfo` / `SurvivalInfo` / `EventItem` / `AdvancementInfo` / `MusterOutInfo` types. Flow effects (`next_step`, `draft`, `force_muster`) drive term progression.

- *Verify:* seeded life paths execute equivalently; draft/forced-muster/skip behaviors preserved.

**C2.3 — Per-phase term execution + checkpoint.**
Per-phase mutations (`qualifyTerm`, `learnTerm`, `surviveTerm`, `eventTerm`, `advanceTerm`) commit effects immediately. Add `Entity.pending_term` (phase reached + committed state + roll inputs). Target-choice dialogs interleave on `PendingChoice`. API accepts rolled inputs (number/tier + table row click).

- *Verify:* manual flow — learned trait appears immediately; survive complication immediately; resume mid-term after reload; unresolved target prompts.

**C2.4 — Legacy migration + mishap completion.**
Backward-compatible shim for old `dict`-shaped life-path effects. Implement razmerit loss, rank demotion, and relationship edge as vocabulary effects in mishaps. Wire `timing != immediate` consequences into the `ScheduledEffect` queue.

- *Verify:* existing term/muster tests pass; end-of-scene/session deferred effects fire; forced-muster + demotion covered.

## Follow-ups (scheduled, not in this change)

- Route every life-path roll (mishap, event, muster-out) through the DiceRoller so all dice are visible in one place.
- Trait-rating signed-value redesign.

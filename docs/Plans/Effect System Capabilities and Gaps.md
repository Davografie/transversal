---
title: Effect System Capabilities and Gaps
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
  - plan
aliases:
  - Effect Expression Space
  - Crimson Scars Convergence
  - Effect Capabilities
status: working
---

# Effect System Capabilities and Gaps

A working map of what the effect layer can express today, what it can't, and what's required to make it broadly applicable — worked through the **Crimson Scars** SFX as the concrete example. Complements [[Effect Variables and Primitives]] (the five-dimension framework and inventory) and [[Effect System Convergence Plan]] (the build order).

> [!note] Status
> Working, updated in-session 2026-08-26. The design below is converged but **not yet implemented**; the primitives are sequenced at the end.

## The field of potential (what the system is today)

The effect layer is a fixed pipeline:

> **TRIGGER → CONDITIONS → [ACTION: target + timing + duration]**, plus **cost** (razmerit), **polarity**, and **scope**.

Its five dimensions (from [[Effect Variables and Primitives]]):

1. **WHEN (trigger)** — `manual`, `on_roll`, `on_result`, `on_set`, `on_beat`, `on_scene`, `on_location_change`, `on_trait_change`, menu contexts, …
2. **IF (condition)** — ~12 state predicates (`AT_LOCATION`, `HAS_TRAIT`, `HAS_RAZMERIT`, `IN_UNIVERSE`, …).
3. **WHAT (action)** — 40 actions (`modify_trait`, `modify_roll`, `transfer_razmerit`, `create_entity`, `location`, `projection`, `relationship`, …).
4. **TO WHAT (target)** — `resolve_candidates` + scope grammar + `{choose:*}` / `{random:*}` / `self.*`.
5. **WHEN IN THE LIFECYCLE (timing + duration)** — `immediate` | `end_of_beat` | `end_of_scene` | `end_of_session` | `after_beats` (timing), plus `duration` (schedules the inverse effect on expiry; its `Timer.event` already accepts arbitrary *state-change* events like `location_changed`).

This covers a lot. Crimson Scars is *not one missing feature* — it's a composition that pushed on three of these joints and found them rigid.

## What Crimson Scars illuminated (the gaps)

Three rigid joints and two missing axes:

1. **Conditions read entity state only.** There is no *roll state* in the evaluation context, so "was a die rolled and left unchosen?" is inexpressible.
2. **Targets can't reference a rolled die, nor navigate from one.** The reference grammar knows `entity`/`location`/`trait`/`self.*`, but not "the die", and not `die → trait setting → entity → location` (recursive drillthrough).
3. **Deferral is time- or state-change-gated, not roll-gated.** `timing` maps to fixed beat/scene/session boundaries; `duration.timers` advance on *persisted* state-change events. A *per-roll* event (`on_result`) is ephemeral and has no home in the timer store.
4. **No declaration/arming axis.** `manual` means "activate → fire *now*"; there is no "commit on adding, resolve on result."
5. **`{source_trait}` is reserved but never resolved** — an SFX can't reference the trait setting that granted it (moot once a die *carries* the SFX, but still latent).

## The convergence (decisions)

1. **Triggers = timings.** `on_result` / `on_set` / `end_of_scene` are *one* event vocabulary used in two positions: **trigger** = which event *arms* the SFX, **timing** = which event *fires* the effect. The only asymmetric members are `manual` (trigger-only) and `immediate` (timing-only).
2. **`SFX.duration`** is the SFX's effective lifetime: `rolls`/`beat`/`scene`/`session` or a state-change event (`location_changed`/`trait_updated`). Default `rolls: 1` (one-shot); `None` = indefinite. This is the roll-scoped (per-roll, non-persisted) deferral.
3. **Effect-level conditions, distinct from SFX-level conditions.** SFX conditions gate *whether the SFX can arm*; effect conditions gate *whether the effect fires*. They operate at different times on different state (the effect condition sees the roll state; the SFX condition does not). This is a separation, not a conflation.
4. **`rating_type` in the inline trait editor.** The created trait can be minted as `resource` (or other rating types), not only a static die.
5. **A phase-condition category.** `on adding` is a *phase* predicate ("are we in the pool-building phase"), distinct from *state* predicates (`AT_LOCATION`, `HAS_TRAIT`).
6. **Iteration over a scoped dice set.** `scope` + `condition` define a *set* of dice; the effect iterates over all matches — so a 2d8 trait with two unchosen dice produces two hazards, no tiebreak.

## Crimson Scars worked example

The SFX reads:

> *"At the end of this roll, any unused `<this trait>`'s dice turn into Crimson Scars — environmental hazards at the rolled dice's outcome tiers — until the end of the scene."*

And it is authored as:

```
SFX — sfx-crimson-scars
  Name:      Crimson Scars
  Trigger:   manual                   (player-initiated)
  Condition: on adding                (phase gate: only armable while building the pool)
  Duration:  rolls: 1                 (default one-shot; beat: 1 for the multi-roll reading)

  Effect: gain trait
    timing:    on result              (fire when the result is set)
    condition: die.role == None       (effect-level gate, available because timing is on_result)
    target:    self.location          (the environmental hazard lives where the roll happened)
    rating:    {triggered_die_effect_die}   (variable = the die's outcome-tier effect die)
    statement: Crimson Scar
    notes:     A blood-red scar in the environment, throbbing with potential violence

    Created trait:
      rating-type: resource           (the hazard is a resource-type trait)
      duration:    scene: 1           (the hazard itself expires at end of scene)
```

Three temporal axes, three different owners: **`SFX.duration`** (`rolls: 1`) is how long the SFX stays in effect; **`Effect.timing`** (`on result`) is when the effect fires while it's in effect; **`Effect.duration`** (`scene: 1`) is how long the created hazard persists. The editor keeps them apart by position — the SFX's duration at the SFX level, timing at the top of the effect, the result's duration at the bottom.

## What remains outside this (adjacent, not effect-pipeline)

- **Auto-contribution** — the hazard being a *resource* trait that automatically enters dice pools of entities at its location (the "negative traits auto-added to PC pools, excluded from select GMCs" idea). This is a **trait-model** capability, not an effect action.
- **Recursive drillthrough** — the full `die → traitsetting → entity → location` grammar. Crimson Scars needs only `self.location`, so the general wizard stays deferred.

## Primitive sequencing

Each batch is a coherent, testable increment; contract tests land with each primitive (per [[Effect System Convergence Plan#Sequencing & testing]]).

1. ~~**Temporal spine**~~ — done (`roll_deferral` service + `EffectTiming.ON_ROLL/ON_SET/ON_RESULT` + `SFX.duration`; the SFX arms at trigger time and fires its roll-timing effects on each matching event until the duration expires — `rolls` budget, `None` indefinite, boundary events drop it). *Makes `timing: on result` + `duration: rolls: 1` expressible.*
2. ~~**Effect gating + die references**~~ — done (`Effect.die_filter` predicates + `{triggered_die_*}` substitution + iteration; the effect's own dice are identified by `source_sfx_id` matching the client-stamped `armed_sfx_ids` on the pool dice). *Makes `condition: die.role==None` + `rating: {triggered_die_effect_die}` + per-die iteration expressible.*
3. ~~**Trait model**~~ — done (`gain_*` honor `context.rating_type`; `TraitInstanceEditor` exposes a Rating Type select; `Effect.duration` remains the trait's persistence/revert). *Makes `rating-type: resource` + `duration: scene: 1` on the created trait expressible.*
4. ~~**Authoring UX**~~ — done (`ConditionType.PHASE` ("on adding") + `CONDITION_TYPES` metadata; `SFX.duration` editor input via `DurationBuilder` (`allowRolls`); timing top / duration bottom already in place; `armedSfxIds(entityId)` GraphQL query). *The full SFX is now authorable end-to-end.*

### After the batches: runtime arming UX

The primitives (batches 1–4) are in place, but the **runtime** arming flow is a separate frontend concern: during pool building the client must offer the arm toggle, stamp `armed_sfx_ids` on the trait's dice, and trigger the SFX with `context.phase: "adding"`. This is the piece that actually makes an authored Crimson Scars fire in play; it lives in the DiceRoller, not the effect system.

### Deferred: selective stamping

The `die_filter` supports arbitrary equality predicates on a die — including `ts_id` — but for now the client stamps `armed_sfx_ids` on **all** of the trait's dice ("stamp all"). The future "you may use *any* dice…" vs "these dice *will*…" distinction — letting the user pick *which* of the scoped dice feed the effect — is **not** built. `die_filter`/`ts_id` matching is the hook that would back it; the selection UI is the deferred work.

After batch 4, Crimson Scars is a normal authored composition with no bespoke code; the auto-contribution and recursive-drillthrough tracks can proceed independently.

## Related

- [[Effect Variables and Primitives]] — five dimensions + inventory.
- [[Effect System Convergence Plan]] — build order and testing strategy.
- [[Unified Effects Plan]] — the layer that built the effect system.
- [[SFX and Effects]] — canonical reference.
- [[Dice Mechanics]] — outcome tiers.
- [[to-do]] — running checklist.

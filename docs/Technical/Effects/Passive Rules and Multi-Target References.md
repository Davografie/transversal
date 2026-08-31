---
title: Passive Rules and Multi-Target References
date: 2026-08-27
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
  - plan
aliases:
  - One Trick Plan
  - Target Drillthrough Plan
  - Multi-Target Effects
status: implemented
---

# Passive Rules and Multi-Target References

> [!success] Implemented
> The targeting model + wizard are now built — see the canonical **[[Targeting Model]]** technical reference. This page retains the design rationale and the settled decisions. One Trick is hand-authored (`sfx-one-trick`); Endless Variety is author-facing.

The plan for two SFX — **One Trick** (a passive, always-on global rule) and **Endless Variety** (its compensation counter) — and the two capabilities they force: **passive arming** and a **structured targeting model** with drillthrough.

## Motivation

- **One Trick** — "reusing traits has diminishing returns." Every trait *used* (rolled) in a contest steps down one step for the beat. It is a standing table rule, not a player-triggered or move-triggered SFX.
- **Endless Variety** — a trait-attached SFX that *compensates* (steps the same trait back up), so a specific trait holds its rating through a contest.

These are the first concrete consumers of the deferred **recursive drillthrough** and **select-for-effect** tracks in [[Effect System Capabilities and Gaps]].

## Design (settled)

- **Trigger**: `on_session_start` — arms the rule once for the session (passive; no per-event trigger).
- **Effect timing**: `ON_ROLL` — fires at every roll.
- **Target**: every rolled trait die's owning **traitsetting** (instance), deduped — see the targeting model below.
- **Effect**: `modify_trait` / `step_down`, `steps: 1`, `duration: beat: 1`, condition `ENTITY_TYPE == character`.

"One Trick" therefore reads: *for the whole session, every time a character rolls, each trait instance they rolled steps down one step until end of beat.*

### Targeting model (the general capability)

- **Unified spec, one concept.** A target is a **pipeline of steps** that resolves to a **typed value**. "Resolves to an entity" and "resolves to an integer" are the *same* kind of thing — the difference is only the result type.
- **Type = element × cardinality.** `set<traitsetting>`, `single<entity>`, `single<int>`, `set<die>`, …
- **The effect field declares the type.** Each field that wants a selection (`target`, `entity`, `result`, `steps`, condition operands) states its expected type — element + cardinality. The spec must resolve to a matching type; that's the "what am I selecting for" hint.
- **Cardinality lives on the field, not the grammar.** Resolution modes are `all` (set), `choose` (user picks one), `random` (random one). `choose`/`random` are the single-resolution forms; there is no `any`.
- **Everything uses specs.** `target` *and* `entity` (subject) are object-typed specs; `result`/`steps`/thresholds are scalar-typed specs (a spec ending in `aggregate`) **or a manual literal** (int/string/bool); conditions are spec predicates (uniformly, with or without drillthrough).
- **Owner drillthrough** — `traitsetting._from` resolves the owner (entity | projection); relationship traitsettings drill `_from`/`_to` (the two endpoints). **`projection` is a first-class spec type.**
- **Full migration.** `Effect.target` (and the other reference fields) become specs; the legacy string (`self`, literal, `{choose:*}`/`{random:*}`) is dropped and represented as trivial specs.

## Current state (blockers, grounded)

1. **Single-target, stringly-typed.** `_PLACEHOLDER_MODES = {"choose", "random"}`; `_resolve_target` returns one id (or one pending choice / one random candidate). There is no `all`/`any`, and the target is a flat string (`Effect.target: str`) that must be parsed. Multiplicity today is the per-die *loop* in `roll_deferral.fire_armed` — N single-target applications, not one N-target effect.
2. **`fire_armed("on_roll", …)` passes empty rolls.** `fire_roll_sfx` calls `fire_armed(entity_id, "on_roll", universe, {})`, so `rolls == []` and the per-die loop matches nothing. (`on_set`/`on_result` in `contest_pools.set_result` *do* pass rolls.)
3. **No die→traitsetting reference.** `_substitute_die_context` exposes `{triggered_die_tier/effect_die/result/die}` but not the die's `ts_id`; there is no `die.traitsetting` drillthrough.
4. **Passive arming conflicts with the stamp model.** `arm_sfx` always sets `source_sfx_id = sfx.id`, and `_selects_die` requires that id in each die's `armed_sfx_ids`. A session-armed rule never stamps dice; it must match by `die_filter` (`{source_kind: "trait"}`) alone.
5. **`roll_deferral` is entity-keyed** (`_armed[entity_id]`); a global rule needs a global armed set consulted on every entity's roll.
6. **`step_down` resolves by registry trait id, not instance.** `_apply_step_down` → `_resolve_target(kind="trait")` returns a `trait_id`, then `_trait_owner` + `_find_traitsetting` look up the **first** `ts` where `ts.trait_id == trait_id`. That's lossy (assumes one instance per owner+trait). Step up/down should target the **traitsetting instance** by `ts_id` (`repo.get_traitsetting(ts_id)` already exists); `die.traitsetting` yields that id directly.

## Work items

### 1. Targeting model — spec pipeline (build first)

A spec is an ordered list of steps, each transforming a typed collection (or collapsing it to a scalar). Resolution is a recursive fold: `select` seeds, each step transforms, the final value is type-checked against the field.

```
Step:
    select   <collection>   # seed from a context collection (rolled_dice, entities, occupants, locations, traitsettings, …)
    filter   <predicate>    # narrow; typed, may traverse (traitsetting.traitset == X, pool_owner.type == "gmc", …)
    navigate <edge>         # hop a named edge (die.traitsetting, traitsetting._from, traitsetting._to, entity.location, …)
                            #   dedup is a flag on navigate: collapsing N→1 aggregates min | max | mean | avg_floor | avg_ceil
    aggregate <fn>          # terminal collapse to a scalar: count | min | max | mean | avg_floor | avg_ceil
                            #   (a terminal aggregate is practically a dedup)
```

- **Type catalog (linchpin)** — element types (die, traitsetting, trait, traitset, entity, **projection**, location, universe, …), navigation edges (source→target type, 1→1 or 1→N), aggregations (input→output type), and the aggregatable scalar fields (`die.rating`, `die.result`). Single source of truth for the resolver and the wizard, so only valid steps compose.
- **Edges are union-capable.** An edge's `target` is a *tuple* of possible types (usually length 1), so a polymorphic hop can declare `(entity, projection)` without a schema change. Populate single-element tuples for now; the common polymorphic case is split into already-distinct single-typed edges (`traitsetting.entity` via `entity_id`, `traitsetting.projection` via `projection_id`). True union *resolution* + union-aware wizard highlighting are deferred until a real edge forces them.
- **Each step carries its own config fields** — `select` (collection), `filter` (field + operator + value), `navigate` (edge + dedup flag), `aggregate` (fn + optional field). The spec is an ordered list of these step objects, so the wizard renders them as extensible, reorderable rows.
- **Field type-hints** — the registry's `EffectActionMeta.fields[].field_type` / `target_kind` become a real type vocabulary (element × cardinality). The wizard only offers steps legal for the field's type; the resolver type-checks the result.
- **Resolver** — `evaluate(spec, context) → typed value`; a `set<T>` result fans out over the effect, a `single<T>` passes one value.

Example — *GMCs that used traits from set X in the current test/contest*:

```
select rolled_dice
  filter source_kind == "trait"
  filter pool_owner.type == "gmc"
  navigate traitsetting
  filter traitset == X
  navigate entity
  dedup
```

### 2. Traitsetting identity (instance, not registry trait)

- Targets resolve to `ts_id`; add a `traitsetting` element type / direct-`ts_id` resolution.
- `step_up`/`step_down` act on the instance via `repo.get_traitsetting(ts_id)` instead of `_find_traitsetting(owner, trait_id)`.
- This is a correctness fix independent of the spec grammar; `die.traitsetting` naturally resolves to `ts_id`.

### 3. Targeting wizard

A step-by-step path builder that produces the spec object directly — no string round-trip.

- **Extensible path rows** — each step is a row with its own config inputs (collection / field+operator+value / edge+dedup / fn+field), addable/removable/reorderable.
- **Live type highlighting** — after each step the wizard resolves the current collection type from the catalog and compares it to the field's declared type; a match highlights as "valid target — stop or keep refining."
- **Catalog-driven affordances** — at each step, only legal `select` collections, `filter` fields, `navigate` edges, and `aggregate` fns are offered (from `edges_from`/`fields_for`), so the wizard can't compose an invalid path.
- **Union-aware highlighting is deferred** — until a polymorphic edge is actually resolved, a step that outputs a union (`entity | projection`) highlights as "close, but narrow further."

### 4. Roll context collection + `on_roll` fix

- `ON_ROLL` firing passes the enriched dice as `rolled_dice` (fix `fire_roll_sfx` → `fire_armed("on_roll", …, {"rolls": …})`, mirroring `set_result`). Latent bug independent of targeting.
- `_substitute_die_context` exposes the die as a navigable unit (minimally `ts_id`) so `select rolled_dice → navigate traitsetting` resolves.

### 5. Passive arming

- New `on_session_start` trigger + fire site (armed on the GM's [Session] Start toggle; see Decided).
- Global armed set (not entity-keyed) that `fire_armed` consults for every entity.
- Passive arming skips `source_sfx_id`; matches by `die_filter` only. (The stamp is a *player-choice* signal; a passive rule's scope is declarative, so it selects dice via `filter` — stamping is not needed.)

### 6. Endless Variety

Same targeting primitive (`rolled_dice → traitsetting`), `step_up` compensation firing *after* the step-down on the same instance. Ordering + the `beat:1` revert interaction are the risk points.

## Sequencing

1. **Type catalog** — element types, edges, aggregations, aggregatable fields (the foundation for everything else).
2. **Spec + resolver** — step pipeline, type-checking, field type-hints (unit test: `all` fans out; `dedup`+aggregation collapses).
3. **Traitsetting identity** — target/step by `ts_id`, not `trait_id`.
4. **Wizard** — build specs through drillthrough, catalog-driven.
5. **Roll context + `on_roll` fix** — expose `rolled_dice`; pass real rolls to `fire_armed("on_roll")`.
6. **Passive arming** — `on_session_start` trigger, global armed set, no stamp.
7. Author One Trick end-to-end; add Endless Variety as the compensation counter.

## Decided (was open)

- **Migration: lazy-on-read, author-curated.** Old string targets (`self`, literal ids, `{choose:*}`/`{random:*}`) translate to *trivial* specs on load — the smallest spec that reproduces the string's meaning (a single `select`/`literal`/`filter` step). No migration script. The author reviews the existing ~21 SFX by hand and fixes them where they don't work.
- **Die selection: spec-predicate + `armed_dice` seed.** "Which dice this SFX fires on" is a `select → filter` spec: player-armed = `filter armed_sfx_ids contains {this_sfx}`; passive = no filter. An `armed_dice` seed is shorthand for the same selection. Requires a `contains`/`in` operator and a "this SFX's id" variable.
- **Session start: GM [Session] toggle ON → global armed set.** The passive rule arms in a *global* (session-scoped, not entity-keyed) set when the GM's [Session] button toggles to Start; the End toggle drops it. Late joiners are covered automatically. The Start button is currently a placeholder no-op, so this fire site is built as part of item 6.
- **Values are typed at authoring time.** The wizard emits a typed value from the catalog's `field.type` (`int`/`die`/`string`/`number`), so specs carry typed values from the start and downstream logic can do typed ops (`string + string`, `int + int`) without late coercion.

- Resolution modes: `all` / `choose` / `random` (no `any`).
- `dedup` is a `navigate` flag; `aggregate` is the terminal collapse (practically a dedup).
- Conditions are spec predicates, uniformly.
- Value fields accept a literal or a spec.
- Subject/owner via `traitsetting._from` (entity | projection) or relationship `_from`/`_to`.
- Dedup identity follows the spec element type (`traitsetting` or `trait`).
- Edges are union-capable (target = tuple), single-typed for now; true union resolution + union-aware wizard highlighting are deferred.
- Spec steps carry their own config fields (select/filter/navigate/aggregate); the wizard renders them as extensible, reorderable rows with live type-match highlighting.

## Related

- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.
- [[Effect System Convergence Plan]] — build order and testing strategy.
- [[Effect Variables and Primitives]] — the reference/context primitive inventory.
- [[Unified Effects Plan]] — the layer that built the effect system.

---
title: Passive Rules and Multi-Target References
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
  - Targeting Model
  - Multi-Target Effects
status: planning
---

# Passive Rules and Multi-Target References

The plan for two SFX — **One Trick** (a passive, always-on global rule) and **Endless Variety** (its compensation counter) — and the two capabilities they force: **passive arming** and a **structured targeting model** with drillthrough.

## Motivation

- **One Trick** — "reusing traits has diminishing returns." Every trait *used* (rolled) in a contest steps down one step for the beat. It is a standing table rule, not a player-triggered or move-triggered SFX.
- **Endless Variety** — a trait-attached SFX that *compensates* (steps the same trait back up), so a specific trait holds its rating through a contest.

These are the first concrete consumers of the deferred **recursive drillthrough** and **select-for-effect** tracks in [[Effect System Capabilities and Gaps]].

## Design (settled)

- **Trigger**: `on_session_start` — arms the rule once for the session (passive; no per-event trigger).
- **Effect timing**: `ON_ROLL` — fires at every roll.
- **Target**: every rolled trait die's owning **traitsetting** (trait instance), deduped — expressed as a structured target (see Work item 1), conceptually `all(rolled_dice[*].traitsetting, dedup=true)`.
- **Effect**: `modify_trait` / `step_down`, `steps: 1`, `duration: beat: 1`, condition `ENTITY_TYPE == character`.

"One Trick" therefore reads: *for the whole session, every time a character rolls, each trait instance they rolled steps down one step until end of beat.*

## Current state (blockers, grounded)

1. **Single-target, stringly-typed.** `_PLACEHOLDER_MODES = {"choose", "random"}`; `_resolve_target` returns one id (or one pending choice / one random candidate). There is no `all`/`any`, and the target is a flat string (`Effect.target: str`) that must be parsed. Multiplicity today is the per-die *loop* in `roll_deferral.fire_armed` — N single-target applications, not one N-target effect.
2. **`fire_armed("on_roll", …)` passes empty rolls.** `fire_roll_sfx` calls `fire_armed(entity_id, "on_roll", universe, {})`, so `rolls == []` and the per-die loop matches nothing. (`on_set`/`on_result` in `contest_pools.set_result` *do* pass rolls.)
3. **No die→traitsetting reference.** `_substitute_die_context` exposes `{triggered_die_tier/effect_die/result/die}` but not the die's `ts_id`; there is no `die.traitsetting` drillthrough.
4. **Passive arming conflicts with the stamp model.** `arm_sfx` always sets `source_sfx_id = sfx.id`, and `_selects_die` requires that id in each die's `armed_sfx_ids`. A session-armed rule never stamps dice; it must match by `die_filter` (`{source_kind: "trait"}`) alone.
5. **`roll_deferral` is entity-keyed** (`_armed[entity_id]`); a global rule needs a global armed set consulted on every entity's roll.
6. **`step_down` resolves by registry trait id, not instance.** `_apply_step_down` → `_resolve_target(kind="trait")` returns a `trait_id`, then `_trait_owner` + `_find_traitsetting` look up the **first** `ts` where `ts.trait_id == trait_id`. That's lossy (assumes one instance per owner+trait). Step up/down should target the **traitsetting instance** by `ts_id` (`repo.get_traitsetting(ts_id)` already exists); `die.traitsetting` yields that id directly.

## Work items

### 1. Targeting model — structured `TargetSpec` (build first)

Replace the parse-a-string approach with a structured target object, so the wizard builds it directly and the resolver validates it. Conceptually:

```
TargetSpec:
  mode        # literal | self | choose | random | any | all
  kind        # target kind: entity/trait/traitsetting/location/…
  collection  # context collection, e.g. "rolled_dice"
  path        # drillthrough hops, e.g. ["traitsetting"]  (die → traitsetting → entity → location)
  filter      # candidate predicate
  dedup       # bool — dedupe the resolved set by id
  scope       # narrowing (absorbs today's target_scope)
```

- **Resolver**: one function `evaluate(spec, context) → list[ids]`; `all`/`any` return a list (fan out), `choose` stays a pending single choice, `random` picks one.
- **Migration**: keep `Effect.target: str` as the legacy fast path (`self`, literal, `{choose:*}`/`{random:*}`) so existing SFX don't break; add a nullable `Effect.target_spec` for structured targets. Decide later whether to fold the legacy path in fully.

### 2. Traitsetting identity (instance, not registry trait)

- Targets resolve to `ts_id`; add a `traitsetting` target kind / direct-`ts_id` resolution path.
- `step_up`/`step_down` act on the instance via `repo.get_traitsetting(ts_id)` instead of `_find_traitsetting(owner, trait_id)`.
- This is a correctness fix independent of the grammar; `die.traitsetting` naturally resolves to `ts_id`.

### 3. Targeting wizard

The drillthrough picker that produces a `TargetSpec` (mode, collection, hops, dedup) rather than emitting a string. Built on top of items 1–2.

### 4. Roll context collection + `on_roll` fix

- `ON_ROLL` firing passes the enriched dice as `rolled_dice` (fix `fire_roll_sfx` → `fire_armed("on_roll", …, {"rolls": …})`, mirroring `set_result`). This is a latent bug independent of targeting.
- `_substitute_die_context` exposes the die as a navigable unit (minimally `ts_id`) so `collection=rolled_dice, path=[traitsetting]` resolves.

### 5. Passive arming

- New `on_session_start` trigger + fire site (session lifecycle; see open decisions).
- Global armed set (not entity-keyed) that `fire_armed` consults for every entity.
- Passive arming skips `source_sfx_id`; matches by `die_filter` only.

### 6. Endless Variety

Same targeting primitive (`rolled_dice[*].traitsetting`), `step_up` compensation firing *after* the step-down on the same instance. Ordering + the `beat:1` revert interaction are the risk points.

## Sequencing

1. **Targeting model** — `TargetSpec` + resolver + `all`/`any`/`dedup` (unit test: `all` fans out; `dedup` dedupes by id).
2. **Traitsetting identity** — target/step by `ts_id`, not `trait_id`.
3. **Wizard** — build a `TargetSpec` through drillthrough.
4. **Roll context + `on_roll` fix** — expose `rolled_dice` and pass real rolls to `fire_armed("on_roll")`.
5. **Passive arming** — `on_session_start` trigger, global armed set, no stamp.
6. Author One Trick end-to-end; add Endless Variety as the compensation counter.

## Open decisions

- **`TargetSpec` migration** — coexist with the legacy `target` string (recommended) vs full migration of existing authored SFX.
- **Dedup identity** — by `ts_id` (instance) vs `trait_id` (registry trait); instance is the safe default and matters for relationship traits.
- **Session-start fire site** — session *created* vs *first join*; and global armed set vs per-entity arming.
- **`any` semantics** — first-candidate vs deterministic pick (only needed if a future rule wants "any one", not for One Trick).

## Related

- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.
- [[Effect System Convergence Plan]] — build order and testing strategy.
- [[Effect Variables and Primitives]] — the reference/context primitive inventory.
- [[Unified Effects Plan]] — the layer that built the effect system.

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
  - Multi-Target Effects
status: planning
---

# Passive Rules and Multi-Target References

The plan for two SFX — **One Trick** (a passive, always-on global rule) and **Endless Variety** (its compensation counter) — and the two capabilities they force: **passive arming** and a **multi-target reference grammar** with drillthrough.

## Motivation

- **One Trick** — "reusing traits has diminishing returns." Every trait *used* (rolled) in a contest steps down one step for the beat. It is a standing table rule, not a player-triggered or move-triggered SFX.
- **Endless Variety** — a trait-attached SFX that *compensates* (steps the same trait back up), so a specific trait holds its rating through a contest.

These are the first concrete consumers of the deferred **recursive drillthrough** and **select-for-effect** tracks in [[Effect System Capabilities and Gaps]].

## Design (settled)

- **Trigger**: `on_session_start` — arms the rule once for the session (passive; no per-event trigger).
- **Effect timing**: `ON_ROLL` — fires at every roll (per-die loop).
- **Target**: `{all:deduped:rolled_dice[*].traitsetting}` — every rolled trait die's owning traitsetting, deduped.
- **Effect**: `modify_trait` / `step_down`, `steps: 1`, `duration: beat: 1`, condition `ENTITY_TYPE == character`.

"One Trick" therefore reads: *for the whole session, every time a character rolls, each trait they rolled steps down one step until end of beat.*

## Current state (blockers, grounded)

1. **Single-target only.** `_PLACEHOLDER_MODES = {"choose", "random"}`; `_resolve_target` returns one id (or one pending choice / one random candidate). There is no `all`/`any`. Multiplicity today is the per-die *loop* in `roll_deferral.fire_armed` — N single-target applications, not one N-target effect.
2. **`fire_armed("on_roll", …)` passes empty rolls.** `fire_roll_sfx` calls `fire_armed(entity_id, "on_roll", universe, {})`, so `rolls == []` and the per-die loop matches nothing. (`on_set`/`on_result` in `contest_pools.set_result` *do* pass rolls.)
3. **No die→traitsetting reference.** `_substitute_die_context` exposes `{triggered_die_tier/effect_die/result/die}` but not the die's `ts_id`; there is no `die.traitsetting` drillthrough.
4. **Passive arming conflicts with the stamp model.** `arm_sfx` always sets `source_sfx_id = sfx.id`, and `_selects_die` requires that id in each die's `armed_sfx_ids`. A session-armed rule never stamps dice; it must match by `die_filter` (`{source_kind: "trait"}`) alone.
5. **`roll_deferral` is entity-keyed** (`_armed[entity_id]`); a global rule needs a global armed set consulted on every entity's roll.
6. **Identifier mismatch (data-types).** A rolled die carries `ts_id` (traitsetting id, e.g. `kael-1:trait-martial-934c`), but `step_down` resolves its target by `trait_id` (e.g. `trait-martial-934c`) via `_find_traitsetting`. `die.traitsetting` must yield the identifier the action consumes — either add a `traitsetting`/direct-`ts_id` resolution path, or drill through to `trait_id`.

## Work items

### 1. Reference grammar — multi-target + drillthrough
Extend the placeholder grammar from `{mode:kind}` to `{mode[:flags][:collection][*].path}`.

- **Modes**: `choose` (user-picked single), `random` (random single), `any` (arbitrary single), `all` (every candidate).
- **Flags**: `deduped` (dedupe the candidate set by resolved id).
- **Collection**: `rolled_dice[*]` — the ON_ROLL context collection.
- **Drillthrough**: `.traitsetting` — first hop of `die → traitsetting → entity → location`.

`_resolve_target` returns a *list* for `all`/`any`; the apply loop fans out one application per candidate. `_parse_placeholder` and `_PLACEHOLDER_MODES` absorb the new modes; `find_choose_placeholder`/pending-choice stays single for `choose`.

### 2. Roll context collection
- `ON_ROLL` firing passes the enriched dice as `rolled_dice` (fix `fire_roll_sfx` → `fire_armed("on_roll", …, {"rolls": …})`, mirroring `set_result`).
- `_substitute_die_context` exposes the die as a navigable unit so `die.traitsetting` resolves (minimally, `ts_id`).

### 3. Passive arming
- New `on_session_start` trigger + fire site (session lifecycle; see open decisions).
- Global armed set (not entity-keyed) that `fire_armed` consults for every entity.
- Passive arming skips `source_sfx_id`; matches by `die_filter` only.

### 4. Fix the `on_roll` deferred fire
Pass the real rolls into `fire_armed("on_roll", …)` (work item 2's first bullet, called out separately because it is a latent bug independent of the new grammar).

### 5. Endless Variety
Same reference primitive (`die.traitsetting`), `step_up` compensation firing *after* the step-down on the same trait. Ordering + the `beat:1` revert interaction are the risk points.

## Sequencing

1. Multi-target grammar + list resolution (unit test: `{all:kind}` fans out; `{all:deduped:kind}` dedupes).
2. Roll context collection + `.traitsetting` drillthrough (with the identifier alignment from blocker 6).
3. Fix `fire_armed("on_roll")` rolls + passive arming (global set, no stamp).
4. `on_session_start` trigger + fire site.
5. Author One Trick end-to-end; add Endless Variety as the compensation counter.

## Open decisions

- **Dedup identity**: by traitsetting `ts_id` (assumed) vs trait `trait_id` — matters for relationship traits that can have multiple settings.
- **Identifier alignment**: `die.traitsetting` yields `ts_id` vs drills through to `trait_id` (blocker 6).
- **Session-start fire site**: session *created* vs *first join*; and global armed set vs per-entity arming at session start.
- **`any` semantics**: first-candidate vs deterministic pick (only needed if a future rule wants "any one", not for One Trick).

## Related

- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.
- [[Effect System Convergence Plan]] — build order and testing strategy.
- [[Effect Variables and Primitives]] — the reference/context primitive inventory.
- [[Unified Effects Plan]] — the layer that built the effect system.

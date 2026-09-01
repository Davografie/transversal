---
title: Challenge Rating Type
date: 2026-09-01
tags:
  - transversal
  - game-design
  - mechanics
  - technical
  - challenge
aliases:
  - Doom Pool
  - Progress Clock
  - Crisis Pool
  - Challenge Pools
status: draft
---

# Challenge Rating Type

> [!note] Supersedes
> This supersedes "Rolling Against Challenge Pools" in [[Inspired Mechanics]].
> The progress-clock resolution changed from *roll-against-to-shrink* to
> *count-up-to-a-target* (a spend-from pool).

## Mental model

A **challenge**-rated trait is a pool of dice that lives on a *scene/owner*
(individual, location, or faction) rather than on a character's personal
resources. It either **drains** (negative → doom/tension) or **fills**
(positive → progress). Under the hood it is resource-shaped — a `dice` ledger
plus a `capacity` — so maintenance is familiar; only the gameplay direction
differs.

## Orthogonal axes

A trait is the intersection of independent axes; none implies another:

| Axis | Values | Meaning |
|------|--------|---------|
| `rating_type` | static / resource / challenge / empty | *mechanics* — how dice behave |
| `polarity` | positive / negative | *direction* — fill vs drain |
| owner (`entity_id`) | individual / location / faction / GMC | *whose pool it is* |
| `traitset_id` + `known_to` | any | *grouping* + *fog-of-war scoping* |

"doom pool" and "crisis pool" are **not** rating types or trait sets — they are
concrete challenge-rated traits (typically negative, location-anchored). A
character can hold a challenge-rated "doom pool" inside their `complications`
trait set, and a location can hold one in a location trait set. The rating type
carries the mechanics; the trait set carries narrative grouping. Keep traits in
their narrative-domain trait set (a location's doom pool lives with that
location's traits), and use `rating_type` to group/filter all pools when needed.

## The model

### Negative — doom pool (pressure)

- Owned by the GM / the opposition (location, faction, or scene). Starts with
  dice.
- **Grows** on bought hitches/opportunities and player failures
  (`add_die` / `step_up`).
- **GM spends** a die to oppose: it leaves the pool and routes into the active
  GMC's pool (if the GM is acting as a GMC that already has dice) or the
  difficulty pool otherwise.
- **Player tempts fate**: on their own turn/contest, a player may spend a doom
  die into *their own* opposition to drain the pool.
- **Player decreases**: the success consequence menu keeps "Decrease the doom
  pool" (step down a doom die).
- Full = dangerous.

### Positive — progress clock (work)

- Owned by the party / a project (location, faction, or individual). Starts
  low/empty.
- **Fills** toward a **target** (e.g. `3d6`) as work happens
  (`add_die` / `step_up`).
- **Grows** via the *successful-test consequence menu* ("work on the project").
- **Partial use**: before the target is reached, spend a die → it enters a
  character's dice pool **as a resource die** (depletes the clock).
- **Complete**: reaching the target fires the project's completion SFX.
- Full = ready.

## Data model

### `TraitSetting` additions

| Field | Type | Meaning |
|-------|------|---------|
| `capacity` | `DieType[]?` | For challenge: the progress **target** (positive) or optional growth **ceiling** (negative). For resource: optional explicit original capacity (today derived as `dice + spent_dice`; leave resource behavior unchanged for now). |

### Challenge ledger semantics

Challenge pools use `dice` as the single current-pool ledger and **do not** use
the resource `spent_dice` recovery ledger (depletion is permanent; the pool
grows back via `add_die`/`step_up`, not recovery):

- **Negative (doom)**: `dice` = available doom dice. Spend → `remove_die`
  (leaves the pool). Grow → `add_die`/`step_up` (bounded by `capacity` when
  set).
- **Positive (progress)**: `dice` = accumulated progress. Fill →
  `add_die`/`step_up` (bounded by `capacity`). Partial use → `remove_die`
  (the die becomes a resource die in the spending character's pool).
  **Completion** = `dice` reaches `capacity`.

## Who builds what

**applied-mechanics (this session) — backend plumbing:**

- `capacity` field on `TraitSetting` (model + migration/fold + GraphQL/REST
  exposure).
- A `challenge_pools` domain service: `spend_challenge_die`,
  `check_challenge_completion`.
- REST `POST /api/v1/challenge-pool/{ts_id}/spend`.
- `capacity` enforcement on `modify_trait` `add_die`/`step_up` + completion
  check after growth.
- New trigger `on_challenge_completed` (positive pool reaches target).

**character-sheet session — rendering + click wiring:**

- Challenge trait rendering (die stack + target/ceiling indicator).
- Click behavior per actor/polarity (see the click matrix) → calls
  `spend_challenge_die`.
- Fog-of-war: hide a challenge trait behind `known_to`.

**SFX/effects session — effect + menu wiring:**

- Target challenge pools by owner/polarity in effects.
- Consequence-menu base moves (see below).
- Consume `on_challenge_completed` in SFX conditions.

The interface surface each consumer needs is in the next two sections.

## Backend interface (built by applied-mechanics)

### Domain service — `challenge_pools`

1. `spend_challenge_die(ts_id, die, destination)` — remove `die` from the
   pool's `dice` and route it:
   - `destination="opposition"` (negative): return the die for the caller to
     place in the GMC pool / difficulty pool.
   - `destination="pool"` (positive partial use): return the die flagged
     `resource=true` so it joins the spending character's pool as a resource
     die.
   - Returns `{ ts, die }`.
2. `check_challenge_completion(ts_id)` — for positive: if `dice == capacity`,
   fire the completion SFX (`on_challenge_completed`). Invoked after every
   `add_die`/`step_up` on a positive challenge trait.
3. `challenge_capacity(ts)` — expose target/ceiling for UI fill/remaining.

### Effect-system hooks

- `modify_trait` `add_die` / `step_up` respect `capacity` (positive: cannot
  exceed target; negative: capped at ceiling) and call
  `check_challenge_completion` afterwards.
- `modify_trait` `remove_die` / `step_down` remain the depletion primitives
  for both polarities. (`reduce_by_effect` exists as an apply primitive but is
  **not** the primary progress-clock mechanic anymore.)
- `modify_pool` `add_dice` / `add_trait_rating` already exist — reused for
  routing a spent die into a dice pool (`opposition` or `pool` destination).
- Registered `modify_trait` actions today: `step_up`, `step_down`, `set`,
  `gain`, `remove`, `gain_or_step_up`, `cortex_gain`, `reveal`, `disable`,
  `enable`, `toggle`, `add_die`, `remove_die`.

## Interface contract — character sheet

### Rendering

- A challenge trait renders as a **stack of dice** (like a resource), with:
  - **negative**: the spendable doom dice; optional ceiling shown if `capacity`
    is set.
  - **positive**: accumulated `dice` plus a **target indicator** (e.g. `2/3`
    dice against `capacity`).
- Respect `known_to`: a hidden challenge trait renders as `???` until revealed.

### Click behavior (calls `spend_challenge_die`)

| Actor | Polarity | Context | Click action |
|-------|----------|---------|--------------|
| GM | negative | acting as a GMC with dice in its pool | spend → route into that GMC's pool |
| GM | negative | otherwise (free-roam / no GMC dice) | spend → route into difficulty pool |
| Player | negative | own turn / contest | "tempt fate" → spend into own opposition |
| Player | positive | own / shared project | spend → resource die into own pool (partial use) |
| GM | positive | any | edit target/dice, or award progress |
| Anyone | either | viewing only | read-only; no roll |

- Positive "work on the project" is **not** a sheet click — it is a
  consequence-menu option on success.

## Interface contract — SFX/effects

### Consequence-menu base moves (`consequence_menu.py`)

- **Success menu (player)**: add "Work on a project" → `gain_or_step_up`
  targeting a positive challenge trait (scope: `rating_type: challenge`,
  `polarity: positive`).
- Keep "Decrease the doom pool" (step down a negative challenge trait) —
  re-scope it from the `ts-complications` placeholder to real challenge-pool
  targeting.
- **Failure/hitch menu (GM)**: keep "Increase the doom pool" (step up a
  negative challenge trait), likewise re-scoped.

### Triggers

- `on_hitch` (bought) → grow the doom pool (`add_die`/`step_up`).
- New `on_challenge_completed` → fire the project's completion SFX.

## Open items

- [ ] Exact wording/scope of the "Work on a project" base move.
- [ ] Whether `capacity` is one shared field for resource + challenge
      (recommended) or challenge-only.
- [ ] Doom-pool ceiling semantics: what fires when a *capped* negative pool
      reaches `capacity` ("the regime cracks down" event?).
- [ ] `on_challenge_completed` trigger registration + context shape.
- [ ] Confirm partial-use die lands in the dice pool as a **resource** die
      (current lean) vs a plain pool die.

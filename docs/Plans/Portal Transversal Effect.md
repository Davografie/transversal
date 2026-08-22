---
title: Portal Transversal Effect
tags:
  - transversal
  - technical
  - sfx
  - effects
  - travel
  - portal
  - plan
aliases:
  - Travel Effect
  - Portal Effect
status: working
---

# Portal Transversal Effect

> [!note] Status
> Agreed design, pre-implementation. Generalises the existing `travel` effect into a portal with five independently controllable axes. See [[SFX and Effects]], [[System Architecture]], and [[Data Model]].

## Goal

Let a single `travel` effect express "cross a universal boundary" with independently controllable axes, so portals can randomise or scope where a character ends up, how they get there, and which body they arrive in.

## Current state

- The `travel` effect (`effects_registry.py`, key `("travel", "move")`) exposes `entity` (subject) + `target` (location) + `context.transversal_type` (`inapposite` | `consciousness`).
- Its handler (`effects_applier.py::_travel`) bottoms out in two hardcoded `EntityManager` methods:
  - `inapposite_travel` — moves the **active** body (projection fixed).
  - `consciousness_travel` — reuses/spawns `{entity}:{universe}` (body fixed; location = that body's location).
- Target kinds today: `location`, `occupant`, `entity`, `trait`, `rating_die`, `life_path`, `roll_table`. No `universe` or `projection` kind.
- Scopes: `universe`, `location`, `subtree`, `faction`, `traitset` — the `prefix:value` value is a literal id; no placeholder/variable in the value position.
- `Effect.entity` (subject) exists; `{choose_*}` / `{random:*}` placeholders resolve through `resolve_candidates(kind, scope, entity, repo)`.

## The five axes

1. **Subject (who)** — `Effect.entity`. Type `entity`. Existing.
2. **Destination location (where)** — a portal's destination is expressed through a **portal-scoped variable** resolved from the edge's `_to` type (see locked decisions). For a free-standing SFX travel effect, `target` is a literal id, `{choose_location}`, or `{random:location}`, scoped via `target_scope`.
3. **Mechanism (how)** — `context.transversal_type`: `inapposite` | `consciousness`.
4. **Body / projection policy (which body)** — new `projection` kind:
   - `active` — default; the body itself travels (inapposite).
   - `{choose_projection}` — pick an existing body (deferred, see below).
   - `{random_projection}` — random existing body, scoped to the destination universe.
   - `{new_projection}` — spawn a fresh body at the destination (`add_projection` semantics: `origin_universe` = destination universe, `transversal_type` = `CONSCIOUSNESS`).
5. **Universe** — new `universe` kind, for `{random_universe}`; also usable as a scope value (`universe:{random_universe}`).

## New target kinds

- `universe` — resolves to universe entities (`repo.list_entities_by_type(UNIVERSE)`).
- `projection` — resolves to the subject entity's projections, optionally filtered by the destination universe.

## Scope value as a variable

`parse_scope` currently treats `prefix:value`'s `value` as a literal id. Extend so the `value` position accepts:

- `{random:*}` — resolved through the shared candidate machinery before the resolver runs (e.g. `universe:{random_universe}`).
- `{context_var}` — substituted via `_substitute_effect_context` (today covers `result`/`target`/`entity`; extend to `target_scope`/`entity_scope`).

## Locked decisions

- Body policy is **enforced in the editor** — the `projection` field is only offered when mechanism is `consciousness` (inapposite always implies `active`).
- `{random_universe}` is a first-class variable.
- The scope value can itself be a variable (extension above).
- `{new_projection}` = spawn a fresh body (clone), not reuse.
- `{random_projection}` = random among the entity's bodies in the destination universe.
- **Portal destination is a variable** — a travel effect on a transversal edge references the edge's `_to` through exactly one portal-scoped variable, matching the target's type: `{location:transversal_target}` (location `_to`) or `{universe:transversal_target}` (universe `_to`). `fire_portal` resolves the variable before applying. A location `_to` fixes the destination; a universe `_to` scopes a location picker to that universe.

## Examples

- `universe:three_realms` + `{choose_location}` + `inapposite` + `active` — body travels; the player picks the exit (tech lets them choose exactly where).
- `earth` + `{random_projection}` + `consciousness` — mind arrives in a random existing Earth body (the default consciousness transversal).
- `earth` + `krasnoyarsk` + `{new_projection}` + `consciousness` — spawn a fresh body at Krasnoyarsk (clone factory).

## Multi-step prompt — implemented

`{choose:*}` in the scope value (e.g. `universe:{choose_universe}`) resolves as a sequential `PendingChoice`: the scope choice is prompted first, then the effect re-applies and prompts for the now-scoped target. The SFX choice wizard forwards each round of `pendingChoices`, so back-to-back prompts work.

## Preview — blind vs previewed (planned)

A portal can run **blind** (resolve + move in one step) or **previewed** (resolve → show → confirm/refuse → move). Same effect pipeline; a single per-effect flag controls the pause.

- **Flag**: `context.preview` on the `travel` effect (`true` = previewed, default `false` = blind). Authorable per-SFX, consistent with `transversal_type` and `projection`.
- **Blind**: fire → resolve → commit atomically (current behaviour).
- **Previewed**: fire → resolve to a concrete destination → present name/image → player **confirms** (commit) or **walks away** (discard, no move).

Composes with the three destination modes:

- literal + preview — "see where the door goes before stepping through".
- random + preview — a **shifting gate**: the destination is re-rolled on each approach (never locked); the player previews the roll and may refuse.
- choose + preview — pick → see it → confirm.

Requires one new primitive: a **pending-confirmation** state that splits *resolve* from *commit* (the applier currently resolves-and-commits atomically). On refuse, the resolved move is discarded.

### Locked decisions

- `context.preview` flag on the travel effect.
- Refusal is allowed (confirm + walk-away).
- Previewed-random is a **shifting gate** — re-roll per approach.

## Remaining

- **Effect-driven portals** — wire LocationViewer portals to fire a `travel` effect rather than the hardcoded `transversal` edges calling `/move` / `/consciousness-travel`.
- **Preview phase** — the pending-confirmation state (resolve → preview → confirm/refuse) described above.
- **Consolidation** — merge `EntityManager.inapposite_travel` / `consciousness_travel` with the effect-applier travel path so there is one source of truth.

## Implementation steps

1. Add `universe` and `projection` target kinds to `_TARGET_KINDS` + `resolve_candidates`.
2. Extend scope-value resolution: `{random:*}` and `{context_var}` in the value position.
3. Rewrite `_travel` to honour the four axes (location, mechanism, body policy, universe).
4. Editor: `travel` effect gains the `projection` field (shown only for `consciousness`) and the `universe`/scope variable inputs.
5. Tests: universe/projection candidate resolution, scope-value substitution, `{new_projection}` / `{random_projection}` / `{random_universe}` behaviour, editor hiding of `projection` under `inapposite`.

## Relationship to multi-projection work

`inapposite_travel` / `consciousness_travel` are the hardcoded "reuse/spawn by `{entity}:{universe}`" paths. This effect's **body policy** is the mechanism through which multiple projections get applied — `{new_projection}` is what actually creates a second body — so this plan and the multi-projection support converge here.

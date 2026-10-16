---
title: Portal Transversal Effect
date: 2026-08-22
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
status: partly implemented
---

# Portal Transversal Effect

> [!warning] Read this before the body — the section that matters most is superseded
> **The portal-scoped destination variable does not exist.** `{location:transversal_target}` / `{universe:transversal_target}` and the whole `target_scope` / `{choose_*}` / `{random:*}` placeholder machinery were **deleted on 2026-09-17 by `6c1b03ae`** ("refactor(targeting): delete the flat target form"), which moved a runtime pick into a `choose` **step in the target path**. The variable is still described below under *Locked decisions* and *The five axes*, and **it cannot be authored**. Present-day facts this doc predates, all measured 2026-09-28:
>
> - **The replacement is unwired.** `Effect.targetSpec` exists and the `choose` step has real semantics ([[Choose and Random Resolution]]), but the edge's endpoint is bound to nothing — a portal effect cannot reference the edge it sits on, and **nothing stops an authored effect contradicting its own endpoint** (it happens: the only portal carrying effects offers two cities that are not its endpoint).
> - **No portal destination resolves.** Firing the one authored portal returns `status: pending` with a pending choice of kind `location` **and no candidates** — the low-level applier entry point cannot carry the pool, so the traveller does not move.
> - **`context.preview` was never built** — zero hits for `preview` in the effects layer, so *Remaining* below reads emptier than the truth.
> - **The feature is unexercised:** **343 `transversal` edges, 0 carrying effects.**
>
> For the intended product behaviour — the Floating Vagabond's stairs, the airport exit menu, and what a portal's endpoint means — see **[[Hubs and Exits]]**.

> [!note] Status
> Agreed design, pre-implementation. Generalises the existing `travel` effect into a portal with five independently controllable axes. See [[SFX and Effects]], [[System Architecture]], and [[Data Model]].

## Goal

Let a single `travel` effect express "cross a universal boundary" with independently controllable axes, so portals can randomise or scope where a character ends up, how they get there, and which body they arrive in.

## Current state

- The `travel` effect (`services/effects_registry/actions_world.py`, key `("travel", "move")`) exposes `entity` (subject) + `target` (location) + `context.transversal_type` (`inapposite` | `consciousness`).
- Its handler (`services/effects_applier/handlers_world.py::_apply_travel`) resolves the subject, destination location, mechanism, and body policy directly. `EntityManager.travel()` and `fire_portal`'s no-effects fallback both synthesize a travel effect and run it through `commit_effects`, so there is one travel path (no separate `inapposite_travel`/`consciousness_travel`).
- Target kinds today: `location`, `occupant`, `entity`, `trait`, `rating_die`, `life_path`, `roll_table`. No `universe` or `projection` kind.
- Scopes: `universe`, `location`, `subtree`, `faction`, `traitset` — the `prefix:value` value is a literal id; no placeholder/variable in the value position.
- `Effect.entity` (subject) exists; `{choose_*}` / `{random:*}` placeholders resolve through `resolve_candidates(kind, scope, entity, repo)`.

## The five axes

1. **Subject (who)** — `Effect.entity`. Type `entity`. Existing.
2. **Destination location (where)** — a portal's destination is a location picked **within a scope derived from the edge's `_to` type**: `{location:transversal_target}` (location `_to` → the location plus its zones) or `{universe:transversal_target}` (universe `_to` → any location in it). For a free-standing SFX travel effect, `target` is a literal id, `{choose_location}`, or `{random:location}`, scoped via `target_scope`.
3. **Mechanism (how)** — `context.transversal_type`: `inapposite` | `consciousness`.
4. **Body / projection policy (which body)** — new `projection` kind. Inapposite always uses `active` (the body travels). Consciousness picks a body **scoped to the destination scope** (a location scope → bodies currently in that location + its zones; a universe scope → bodies anywhere in it):
   - `{last_projection}` — the **most recently used** body in that scope (tracked via `Projection.last_used_at`); arrive where it is.
   - `{random_projection}` — a random body in that scope.
   - `{choose_projection}` — choose a body in that scope.
   - `{new_projection}` — always spawn a fresh body (`origin_universe` = destination universe, `transversal_type` = `CONSCIOUSNESS`).

   The reuse policies (`{last_projection}` / `{random_projection}` / `{choose_projection}`) fall back to spawning a fresh body **at the specific target location** when no body exists within the scope.
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
- ~~**Portal destination is a scope variable** (deleted 2026-09-17, `6c1b03ae` — see the note at the top)** — a travel effect on a transversal edge references the edge's `_to` through exactly one portal-scoped variable, matching the target's type: `{location:transversal_target}` (location `_to`, resolved to `location:<id>` — the location plus its zones) or `{universe:transversal_target}` (universe `_to`, resolved to `universe:<key>`). `fire_portal` resolves the variable in `target_scope` before applying; `target` is a location picked within that scope. **The intent survives and is still right — a portal effect should be able to reach the edge it sits on — but no present-day mechanism binds the edge.** The destination is now a `choose`/`random` step in `Effect.targetSpec`, whose candidate set the author supplies by hand; **whether a portal destination should even be a `choose` is open on [[Hubs and Exits]]**, which carries the product model.

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

- **Preview phase** — the pending-confirmation state (resolve → preview → confirm/refuse) described above. **Never built**, and the note below calls it planned; nothing in the effects layer reads a `preview` flag today.
- **The destination half, which this doc treats as solved and is not.** No present-day mechanism binds a portal effect to its own edge, no portal destination resolves (the fire stops at a `choose` whose candidate pool the low-level applier entry point cannot carry), and no portal effect is authorable through MCP. See [[Hubs and Exits]] and [[B242]].

## Done

- **Effect-driven portals** — LocationViewer portals fire a `travel` effect via `/portal/{to}/fire`. **Firing a portal always delivers the traveller to the edge's own `_to`**, and its effects happen as well; the `transversal_type` fallback routes the move through the same path, and an effect that moved the traveller itself wins so a portal whose effect travels *elsewhere* is not double-moved ([[B312]], 2026-10-17). Before that, travel happened only when the edge carried **no** effects, so any effect-carrying portal moved nobody unless one of its effects was a successful travel — which left Eindhoven Airport unusable as a hub (`status: pending`, `applied: []`, location unchanged, measured live).
- **Consolidation** — `EntityManager.inapposite_travel` / `consciousness_travel` merged into a single `EntityManager.travel()` that synthesizes a travel effect and runs `commit_effects`.

## Implementation steps

1. Add `universe` and `projection` target kinds to `_TARGET_KINDS` + `resolve_candidates`.
2. Extend scope-value resolution: `{random:*}` and `{context_var}` in the value position.
3. Rewrite `_travel` to honour the four axes (location, mechanism, body policy, universe).
4. Editor: `travel` effect gains the `projection` field (shown only for `consciousness`) and the `universe`/scope variable inputs.
5. Tests: universe/projection candidate resolution, scope-value substitution, `{new_projection}` / `{random_projection}` / `{random_universe}` behaviour, editor hiding of `projection` under `inapposite`.

## Relationship to multi-projection work

The body policy is the mechanism through which multiple projections get applied — `{new_projection}` is what actually creates a second body. Travel now goes through a single `EntityManager.travel()` → `commit_effects` path, so the portal effect and multi-projection support share one source of truth.

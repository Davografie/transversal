---
title: Effect Variables and Primitives
tags:
  - transversal
  - technical
  - sfx
  - effects
  - variables
  - triggers
  - architecture
  - plan
aliases:
  - Trigger Variables
  - Effect Primitives
  - Typed Variables
status: planned
---

# Effect Variables and Primitives

> [!note] Status
> Planned, not yet implemented. Follows on from [[Unified Effects Plan]] (the layer that built the effect system) and [[SFX and Effects]] (the current canonical reference). This plan is about making the effect layer *robust, durable, and widely applicable* by enriching the trigger-variable model and tightening the authoring experience.

## Goal

Transversal gets its depth the way *Magic: the Gathering* does: a **small set of primitives** composed into a large space of outcomes. The primitives are the dice pool, traits (with die ratings), razmerit, locations, and occupants; factions and roll tables give structure. **Effects are the card layer** — the thing that makes those primitives combine into interesting, unexpected behavior.

This plan makes the effect layer trustworthy to build on: typed variables that can't drift from their data, a trigger system that honestly exposes the context an author can use, and an editor that shows the author what an effect *means* before it runs.

## The five dimensions of an effect

Every effect is the composition of five small, closed vocabularies. Depth = the cross-product.

1. **WHEN** — trigger + conditions
2. **DO WHAT** — action
3. **TO WHAT** — target (kind + mode + scope + filter)
4. **WITH WHAT** — result/context, including `{variables}`
5. **WHEN IN THE LIFECYCLE** — timing + duration

The rule of thumb: **prefer a general primitive over a bespoke effect.** "Reveal a GMC when the party enters a room" should be `on_location_change` + `at_location` + a `reveal_entity` action — not a new hardcoded "reveal on enter" effect.

## Current primitive inventory (verified)

- **Triggers (18):** `manual`, `on_roll`, `on_result`, `on_complication`, `on_botch`, `on_success`, `on_failure`, `on_contest_win`, `on_contest_loss`, `on_give_in`, `on_push`, `on_taken_out`, `on_prevent_taken_out`, `on_location_change`, `on_trait_change`, `on_trait_learn`, `on_trait_offered`, `on_relationship_create`, `on_character_create`.
- **Menu contexts (5):** `test_success`, `simplified_roll`, `contest_win`, `contest_give_in`, `hitch` — a parallel activation vocabulary with its own variable list (`MENU_CONTEXT_VARIABLES`). To be merged into `TRIGGERS` (see [[#Trigger vs. menu context]]).
- **Conditions (9):** `always`, `at_location`, `has_trait`, `has_trait_in_traitset`, `trait_rating`, `has_relationship`, `unplaced`, `in_universe`, `narrative`.
- **Target kinds (9):** `location`, `occupant`, `trait`, `entity`, `universe`, `projection`, `rating_die`, `life_path`, `roll_table`.
- **Scopes:** `universe`, `location`, `subtree`, `faction`, `traitset`, bare/current-context.
- **Filters (1 field):** `starter_location`.
- **Actions (35):** dice-pool manipulation, outcome manipulation, trait step/set/gain/reveal, razmerit earn/spend/transfer, create asset, attune, travel, set location, life-path enroll/next/muster, relationship create, targeting ban.
- **Timings (6):** `immediate`, `end_of_beat`, `end_of_scene`, `end_of_session`, `after_beats`, `on_condition` — plus timers.

## The variable problem

Variables have **two halves that must agree**:

1. **Declaration** — `TRIGGERS` in `services/menu_contexts.py` lists the `{variable}` tokens each trigger exposes to the editor.
2. **Data** — the fire site passes a `context` dict; `_substitute_effect_context` does literal `{key}` → value replacement across `result`, `target`, `entity`, `target_scope`, `entity_scope`, and string `context` values.

Two failure modes:

- **Declared but not populated** — the token stays literal and silently breaks (a `{created_entity}` target becomes a bogus literal id).
- **Populated but not declared** — authors can't see the value, so it can't be used.

There is no mechanism today that keeps the two halves in sync. That is the durability risk.

### Flat strings vs. typed references

The current substitution is **flat string replacement**: `{entity_created}` becomes the entity *id string*, and nothing more. That is why it is tempting to add a separate `{entity_created_universe}` variable — but that is redundant.

The correct model is a **typed reference**: an `entity` variable *carries* its structure (id, universe, location, …), so its universe is **derivable**, not a separate variable. This plan moves variables from flat strings to typed references, and adds the minimal dereference syntax needed to pull a field out of one (e.g. `universe:{entity_created}` resolving through the entity's `current_universe`).

> [!note] Decision
> Expose **one** variable for a created entity — `{entity_created}` (type `entity`) — not a parallel `{entity_created_universe}`. The universe is part of the entity reference's payload.

## Trigger vs. menu context

`SFX` currently splits "how does this activate" across two fields:

- `trigger` — the auto-fire event (`on_success`, `on_character_create`, `manual`, …).
- `menu_context` — the post-roll menu this SFX is an *option* in (`test_success`, `contest_win`, `hitch`, …). When set, the SFX is offered as a choice; when `None`, it is trigger-driven.

This split is artificial. A consequence menu **is** a manual trigger: the player activates it by choosing it from that specific menu, with that menu's variables in scope. Every seeded menu SFX is authored `trigger="manual"` + `menu_context="…"` — the `trigger` field is a meaningless placeholder for them. And the two fields each carry their own parallel variable vocabulary (`TRIGGERS` vs `MENU_CONTEXT_VARIABLES`), which is the same two-halves drift problem, one level up.

### Direction: fold `menu_context` into `trigger`

1. Make the menu contexts first-class triggers (`test_success`, `contest_win`, `hitch`, …), declared in `TRIGGERS` with their variables — merging `MENU_CONTEXT_VARIABLES` into `TRIGGERS`.
2. Drop `SFX.menu_context`, migrating it to `trigger`; keep the legacy `on_consequence` shim during migration.
3. Collapse the editor's two activation selects into one.

> [!note] Ownership already encodes "who"
> No separate `side` field is needed. The owner buckets (`table` / `gm`) plus entity/projection/trait ownership already encode who an SFX is offered to — the hitch menu derives side from the bucket. The `players` bucket was folded into `table`; "player-character-only" is now an `ENTITY_TYPE` condition, not a grant surface.

> [!note] Side-sourcing wrinkle (orthogonal)
> The consequence menu (`test_success`/`contest_win`/…) currently hardcodes SFX moves as `side="player"` and sources from `get_available_sfx_ids`, while the hitch menu derives side from owner buckets. Reconciling the two is a separate ownership/sourcing ticket — not part of this trigger/menu unification.

## Conditions and their subject

Conditions are gates evaluated against an entity. They previously had a hardcoded
subject (the event's entity). Now a condition can declare its own subject:

```
Condition:
  type      (has_trait / has_trait_in_traitset / at_location / …)
  subject   "" | literal entity id | {variable}
  target    trait / location / entity id  (also {variable})
  value     (trait_rating threshold)
  narrative
```

- **Blank subject** → the *current entity*: the event's entity for auto-fire, the acting entity for the consequence menu. (No bare ``self`` keyword — it was ambiguous.)
- **`{variable}` subject** → the referenced entity, resolved from the trigger/menu context (e.g. `{buying_entity}`, `{contest_entity_opponent}`).
- **Literal subject** → a specific entity id.
- **`target`** is also variable-resolvable (e.g. `has_trait` with `target: {trait}`).

Where conditions are evaluated:

- **Auto-fire** — against the event's entity, with `event.context` in scope.
- **Consequence menu** — against the acting entity.
- **Hitch menu** — no default entity; conditions must reference `{hitch_entity}` or `{buying_entity}` explicitly (a blank subject skips the SFX).

## Design principles

1. **Declarative over procedural** — an effect is data; the engine interprets it.
2. **Backend is the single source of truth** — every vocabulary is served to the editor, never duplicated in the frontend.
3. **Drift-proof by mechanism, not discipline** — where two places must agree, make them agree *or fail loudly*.
4. **Typed everything** — a variable is a typed reference (`entity`, `universe`, `location`, `trait`, `die`, `number`, `string`, `boolean`), and the type drives the editor input and the engine's validation.

## Phased roadmap

### Phase 1 — Drift-proof the variable layer

1. Extend the `Variable` model's `type` to the full typed set above.
2. Co-locate each trigger's variables with its fire site (single source), so declaration and data cannot diverge.
3. Add a test that asserts, for every trigger, the fire-site context keys match the declared variables and their types.
4. Enrich the triggers that currently expose nothing:
   - `on_character_create` → `{entity_created}` (entity). **First.**
   - `on_location_change` → `{from_location}`, `{to_location}`, `{universe}`.
   - `on_relationship_create` → `{target_entity}`, `{relationship_type}`.
   - `on_trait_change` → `{trait_id}`, `{traitset_id}`.
   - Contest triggers → add the missing declared aliases (`opponent_id`, `high_stakes`, `taken_out`).
5. **Fold `menu_context` into `trigger`** — merge the two variable vocabularies, migrate `menu_context` → `trigger`, and collapse the editor's two activation selects into one (see [[#Trigger vs. menu context]]).

*Deliverable:* every trigger honestly advertises what it can give authors, it cannot rot, and there is a single activation axis instead of two.

### Phase 2 — Typed variables drive authoring

1. Use the variable's type to offer the right control per field (a `universe` variable becomes a universe picker, not a text box).
2. Fix the ambiguous **"Current context"** scope label: add an explicit **"Current universe"** option; keep "Current context" only as the clearly-labeled empty choice.
3. Extend the live preview into a **plain-English summary** of the whole SFX ("When a character is created, if unplaced and in Earth → set location to a random starter location"), and later a candidate-resolution preview.

> [!note] Clarification
> "Dry-run" here means *previewing what an effect would do to a specific entity before applying it* — it is **not** the MCP tool experience. Full mutation simulation is descoped for now; candidate-resolution preview is in scope.

### Phase 3 — Primitive-coverage audit *(deferred)*

Deferred until the current surface is verified. Candidates, for later:

- `faction` and `traitset` (i.e. `TraitSetSetting` instances) as **target kinds**, not just scopes — e.g. giving/changing a faction's traits, or changing a trait set's limits.
- Razmerit `set` (today delta-only: earn/spend/transfer).
- Relationship `remove`/`update` (today create-only).
- Fog-of-war actions (`reveal_entity`, `hide_entity`, …) — the `hidden`/`unpublished`/`known_to` fields have no effect action yet.
- Missing conditions: `taken_out`, `has_razmerit`, `occupant_count`, `is_faction_member`, `has_attunement`.

### Phase 4 — Authoring validation

Make illegal or silently-broken effects hard to write:

1. Validate on save: unknown `{variable}`, scope/filter incompatible with the target kind, missing required field, etc. Return clear errors.
2. Surface the same checks as inline editor warnings.

*Deliverable:* "foolproof" — it becomes difficult to write a broken effect, and impossible to write a silently-broken one.

## Delivery sequence

Each step lands independently and is verified before the next.

1. Write this plan (done).
2. `on_character_create` → `{entity_created}` (done).
3. Batch trigger enrichments + drift-proof test (done).
4. Variable naming normalized — `trait`/`traitset`/`trait_setting`/`contest_entity_opponent` (done).
5. Fold `menu_context` into `trigger` (done).
6. Variable-subject conditions + menu condition evaluation (done).
7. Typed-variable-driven authoring (Phase 2) — plain-English summary + `universe:current` scope done; typed inputs remaining.
8. Authoring validation (Phase 4) — unknown variables, filter/target-kind mismatch, missing required fields (done).

Phase 3 is explicitly **not** started until the above is green and the content needs surface.

## Open / deferred

- **Full mutation dry-run** — descoped; candidate-resolution preview only for now.
- **Field-dereference syntax breadth** — start with `universe:{entity_created}` (universe of an entity reference); generalize later if more fields are needed.
- **Consequence-menu condition variables** — `effect_die` / `contest_entity_opponent` are not yet plumbed into `consequence_options`; consequence-menu conditions currently see no `{variables}`.
- **Projection-level subjects** — conditions are entity-scoped; `{contest_projection_opponent}` cannot yet be a condition subject.
- **Faction / traitset targeting, razmerit `set`, relationship `remove`, fog-of-war** — deferred (Phase 3).
- **Side-sourcing consistency** — reconcile the consequence menu's hardcoded `side="player"` sourcing with the hitch menu's owner-bucket-derived side. Orthogonal to the trigger/menu unification.

## Related

- [[SFX and Effects]] — current canonical reference.
- [[Unified Effects Plan]] — the layer that built the effect system.
- [[Data Model]] — `Effect`, `Condition`, `Entity`, `Projection`, `TraitSetSetting`.
- [[System Architecture]] — where the effects engine and applier sit.

---
title: Effect Ownership and Dynamic Drillthrough
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
  - plan
aliases:
  - Owner Model
  - Drillthrough
  - Targeting Wizard
  - Entity-Type Condition
status: planned
---

# Effect Ownership and Dynamic Drillthrough

Follows on from [[Effect Variables and Primitives]] (parent) and [[Unified Effects Plan]]. Two converging changes, both decided in-session (2026-08-26):

1. The ownership model — replace the `players` bucket with an `entity_type` condition, keep `gm` as owner.
2. Dynamic drillthrough — generalise the hardcoded `self.*` fields into a target-type field schema that powers a recursive targeting wizard.

## 1. Owner model → `entity_type` condition + GM owner

### Decision

Drop the `players` owner bucket and express "player-character-only" as an `entity_type` **condition**. Keep `gm` as the GM-context bucket (already excluded from entity availability). This **supersedes** the "Ownership stays exactly as-is" note in [[Effect Variables and Primitives]].

### Rationale

Ownership answers *where an SFX is granted*; conditions answer *when it can fire*. A role is an entity property, so it belongs in conditions, not in the grant surface. `players` and `table` are otherwise identical (both mean "every entity"), so `players` collapses into `table` and its distinction moves to a condition.

### Current state (verified)

`get_available_sfx_ids` ([[SFX and Effects]] → `services/sfx_owner.py`) unions seven grant surfaces:

- buckets: `table`, `players`, `gm`
- entity: `Entity.sfx_ids`
- projection: `Projection.sfx_ids`
- trait: `TraitSetting.sfx_ids` + `Trait.default_sfx_ids`
- trait-set: `TraitSetSetting.sfx_ids`

It does **not** evaluate SFX conditions — conditions gate *firing* (in `effects_engine.process_event_outcome`) but not *listing*. So availability and fireability already diverge; `entity_type` will make that divergence visible unless listing also filters.

### Changes

1. Add `ConditionType.ENTITY_TYPE` (target = `character` / `gmc` / `asset`, …) + an evaluation branch in `conditions.py`.
2. Make `get_available_sfx_ids` evaluate cheap entity-state conditions (at least `ENTITY_TYPE`) so **listing matches fireability**.
3. Migrate `players`-bucket seeds to `table` + an `ENTITY_TYPE=character` condition; remove the `players` bucket.
4. In the "Manage SFX" panel ([[to-do]]), treat **"Owners" as one filter type** alongside the primitive filters (trigger, condition, action) — owners remain a grant axis, roles become conditions.

### Open question

Does `entity_type` gate listing, firing, or both? **Recommendation: both**, so the player's SFX list reflects what can actually fire. (This also fixes the existing listing/fireability divergence generally.)

## 2. Dynamic drillthrough → target-type field schema

### Decision

Replace the hardcoded `self.location` / `self.universe` / `self.projection` with a data-driven schema: each target *kind* declares its fields and their result kinds. That makes drillthrough **dynamic** and lets the targeting wizard offer **recursive** continuations instead of a fixed dropdown.

### Current state (verified)

`_SELF_FIELDS` in `services/effects_applier.py` hardcodes three fields. `self.location.owner` does not compose. [[Effect Variables and Primitives]] already introduced *typed references* and the `universe:{entity_created}` dereference; this is the "generalise field-dereference syntax" step it deferred.

### Target state

A `TARGET_FIELD_SCHEMA` in `services/effect_targets.py` mapping kind → `(field, result_kind, cardinality)`:

- `entity` → `location` (location), `universe` (universe), `projection` (projection), `owner` (entity), …
- `location` → `universe` (universe), `parent` (location), `occupants` (entity·many), …
- `trait` → `traitset` (traitset), `owner` (entity), …

Drillthrough walks the graph: `self.location.owner` resolves `entity → location → (location) → owner`. The targeting wizard renders each step's legal continuations from the same schema, so scope/targeting becomes recursive rather than a fixed dropdown.

### Changes

1. `TARGET_FIELD_SCHEMA` (kind → `(field, result_kind, cardinality)`), the single source of truth.
2. Replace `_SELF_FIELDS` / `_parse_self_field` with a path resolver that walks the schema.
3. Surface the schema via GraphQL so the wizard renders continuations from the backend (no frontend hardcoding).
4. Keep `{choose:*}` / `{random:*}` as the terminal step; drillthrough only selects the *starting* subject.

### Open questions

- **Cardinality**: `occupants` is a set — pick-one vs. iterate-all. Reuse `{choose:*}`/`{random:*}` for singular; a "scope step" for plural.
- **Naming**: `owner` (an entity's owning entity, e.g. asset→character) vs `occupants` (location→entities). Nail the field vocabulary once, since the schema is the contract.

## 3. Reconciliation with the parent plan

Since [[Effect Variables and Primitives]] was written, these have landed and are now stale there:

- `has_razmerit` condition (its Phase 3 listed it as missing).
- `traitset` as a target kind.
- `entity_type` (`type`) target filter — two filters now (`starter_location`, `type`).
- `self.*` drillthrough (first cut), action `group`, `dicepool` trigger group.

## 4. Sequencing

1. **Baseline test pass** — manual end-to-end of the editor + one firing scenario before building on it (see recommendation in-chat).
2. **Owner model** — condition + availability filtering + seed migration + panel filter.
3. **Drillthrough schema** — field schema + recursive resolver + wizard.

## Related

- [[Effect Variables and Primitives]] — parent plan (typed references, variable drift-proofing).
- [[Unified Effects Plan]] — the layer that built the effect system.
- [[SFX and Effects]] — current canonical reference.
- [[to-do]] — the running checklist (owner selection, Manage SFX panel).

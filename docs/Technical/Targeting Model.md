---
title: Targeting Model
tags:
  - transversal
  - technical
  - effects
  - sfx
  - targeting
aliases:
  - Target Spec
  - Target Drillthrough
  - Targeting Wizard
  - Multi-Target References
status: canonical
---

# Targeting Model

A structured, type-checked way to author **what an effect targets** — replacing the flat string `target` (`self`, a literal id, `{choose_*}`, `{random:*}`) with an ordered pipeline of steps that resolves to a typed value.

> [!note] Read alongside the code
> All modules live under `src/api/src/transversal/services/` and the frontend under `src/frontend/src/`. This page describes the implemented system, not design intent.

## Why

The legacy `Effect.target: str` could only express a single target or a runtime choice. It could not express **drillthrough** ("the traitsettings of every trait die I just rolled"), **multi-target fan-out**, or **typed values** ("an integer", "an entity"). The targeting model makes those authorable and, because it is catalog-driven and type-checked, the authoring wizard can only compose valid paths.

## The spec

A `TargetSpec` is an ordered list of **steps**. Each step carries its own config fields; the ordered list is the pipeline.

```python
class TargetSpec(BaseModel):
    steps: list[TargetStep]
```

`TargetStep` is a discriminated union on `kind`:

| Step | Fields | Meaning |
|------|--------|---------|
| `select` | `collection` | Seed from a context collection (`self`, `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`) |
| `filter` | `field`, `operator`, `value` | Narrow by a comparable scalar field |
| `navigate` | `edge`, `dedup` | Hop an edge to a related element; `dedup` collapses by identity |
| `aggregate` | `fn`, `field` | Collapse a collection to a scalar (`count`, `min`, `max`, `mean`, `avg_floor`, `avg_ceil`) |
| `literal` | `element`, `value` | Name one object by id directly |

**Type = element × cardinality.** Every step produces a `ValueType(element, cardinality)`, where `element` is a catalog element type or a scalar (`int`/`number`/`die`/`string`) and `cardinality` is `one` or `many`.

**The effect field declares the type.** A field that wants a target (`target`, `entity`, `result`, `steps`, condition operands) states the element + cardinality it expects; the spec must resolve to a matching type. That declared type is the "what am I selecting for" hint the wizard highlights against.

**Resolution modes are `all` / `choose` / `random`.** `choose` and `random` are the single-resolution forms; there is no `any`. Cardinality lives on the *field*, not on the spec grammar.

## The catalog

`target_catalog.py` is the single source of truth both the type-checker and the wizard read, so only valid steps compose.

- **Element types** (`ELEMENT_TYPES`): `die`, `traitsetting`, `trait`, `traitset`, `entity`, `projection`, `location`, `universe`.
- **Edges** (`EDGES`): named hops `(source → target, cardinality)`. Edges are union-capable (`target` is a tuple) but single-typed today — e.g. `die → traitsetting`, `traitsetting → entity`, `entity → location`, `location → occupants`.
- **Scalar fields** (`SCALAR_FIELDS`): comparable/aggregatable fields per element, each with a type (`int`/`number`/`die`/`string`). Enum-like string fields also carry an **`options` tuple** so the wizard renders a dropdown (`die.source_kind`, `die.tier`, `die.rating`, `traitsetting.rating_type`, `traitsetting.from_type`, `entity.type`, …).
- **Aggregations** (`AGGREGATIONS`): `count` (int), `min`/`max` (same-type), `mean`/`avg_floor`/`avg_ceil` (number).
- **Collections** (`COLLECTIONS`): the `select` seeds — `self` (singleton entity), `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`.

Adding a new element, edge, field, aggregation, or collection is a declaration here plus a repo read in the resolver.

## Type-checker and resolver

Two layers, one source of truth:

- **`target_spec.py::trace` / `check` / `final_type`** — a *pure*, catalog-driven walk that returns the `ValueType` after each step plus step-level errors, and whether the final type matches a destination. Used by the wizard for live highlighting.
- **`target_resolver.py::resolve`** — the *runtime* walk over actual game values. `navigate` consults a registry of edge resolvers (one per `(source, edge)`), each backed by the repository (e.g. `die → traitsetting` reads `repo.get_traitsetting(die["ts_id"])`).

A spec that type-checks is guaranteed to have resolvable steps; the resolver produces the concrete objects (or scalar).

### Filter operators

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in` (field value is a member of a list), `contains` (list field contains the value). Ordering compares numerically (a `die` field coerces `d8` → 8). **Values are typed at authoring time** (decision 4): an `int`/`number` field stores a number, `die`/`string` fields store strings — so downstream logic always has typed values.

## Effect fields

`Effect` (in `src/api/src/transversal/domain/__init__.py`) gained two structured fields alongside the legacy strings:

- `target_spec: Optional[TargetSpec]` — the object/target pipeline. `None` = still use the legacy `target` string.
- `entity_spec: Optional[TargetSpec]` — the **subject** pipeline (who the effect applies to). `None` = still use the legacy `entity` string.

When both a legacy string and a spec exist, the spec wins. `entity_spec` resolves in `effects_applier._effect_subject`; `target_spec` resolves per target in `roll_deferral._apply_spec_target` (the roll-deferred path), which fans the effect out once per resolved target.

### Legacy migration

`target_legacy.py::from_legacy_target(target, kind)` translates the *unambiguous* legacy string forms into trivial specs:

- `self` → `select self`
- `{choose:kind}` / `{random:kind}` → `select <collection>` (choose/random cardinality is the field's concern)
- a literal id → `literal <id>` (element from the action's `target_kind`)

Unmappable forms (variables like `{effect_die}`, kinds without a collection/element) return `None` and stay on the legacy string for the author to fix by hand.

## The wizard (frontend)

- `src/frontend/src/components/gm/TargetSpecBuilder.vue` — the step-by-step path builder: add/remove/reorder step rows, per-step config, catalog-driven affordances (only legal edges/fields/aggregations offered), and **live type highlighting** (each step's resolved type, green when it matches the field's declared destination).
- `src/frontend/src/composables/useTargetCatalog.js` — module-singleton that fetches the catalog and calls `traceTargetSpec` (debounced) for highlighting.
- Wired into `EffectForm.vue` as a **"Targeting path"** mode on both the `target` and `entity` fields (alongside Pick/Choose/Random/Named-exit).

The wizard is catalog-driven: it cannot compose an invalid path, and a field with declared enum options renders a dropdown rather than a free-text value.

## GraphQL surface

- `targetCatalog` — the full catalog (elements, edges, fields + options, aggregations, collections).
- `traceTargetSpec(input, destinationElement, destinationCardinality)` — walks a draft spec through the shared type-checker; returns the type after each step, step errors, and `valid` (does the final type match the destination).

`Effect` / `EffectInput` expose `targetSpec` and `entitySpec` as JSON (camelCase on the wire; `target_spec`/`entity_spec` in Python).

## Passive rules (the driver)

The targeting model exists to power **passive rules** like One Trick:

- New `on_session_start` trigger (`menu_contexts.py`).
- A **global armed set** in `roll_deferral.py` (`arm_passive`, not entity-keyed, no `source_sfx_id`) — passive rules apply to *every* entity's rolls, including late joiners.
- `state_events.fire_session_start()` scans `on_session_start` SFX and arms their roll-timing effects globally.
- `roll_deferral._apply_spec_target` resolves an effect's `target_spec` against `rolled_dice` and applies once per resolved target.

**One Trick** (`sfx-one-trick`, hand-authored in the effect editor) is the reference passive rule: `on_session_start` → `on_roll` `step_down` with `target_spec = select rolled_dice → filter source_kind == trait → navigate traitsetting (dedup) → filter rating_type == static`, effect `duration: beat:1` for the revert. **Endless Variety** is its author-facing compensation counter (same path, `step_up`).

## Where things live

| Concern | Module |
|---------|--------|
| Catalog (elements, edges, fields + options, aggregations, collections) | `services/target_catalog.py` |
| Spec model + step types + type-checker | `services/target_spec.py` |
| Runtime resolver + edge resolvers | `services/target_resolver.py` |
| Legacy string → trivial spec | `services/target_legacy.py` |
| `Effect.target_spec` / `entity_spec` fields | `domain/__init__.py` |
| `entity_spec` subject resolution | `services/effects_applier.py` (`_effect_subject`) |
| `target_spec` roll-deferred fan-out | `services/roll_deferral.py` (`_apply_spec_target`) |
| Passive arming + `on_session_start` | `services/state_events.py`, `services/roll_deferral.py`, `services/menu_contexts.py` |
| Wizard component / composable | `frontend/src/components/gm/TargetSpecBuilder.vue`, `frontend/src/composables/useTargetCatalog.js` |
| GraphQL (`targetCatalog`, `traceTargetSpec`) | `api/graphql/schema.py`, `api/graphql/types.py` |

## Related

- [[SFX and Effects]] — the effect model + registry this targets.
- [[Passive Rules and Multi-Target References]] — the design/plan this implements.
- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.

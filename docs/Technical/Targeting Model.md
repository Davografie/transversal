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
| `select` | `collection`, `variable` | Seed from a context collection (`self`, `rolled_dice`, `opposing_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`, `sfxs`), the SFX `source`, or a bound `variable` |
| `filter` | `field`, `operator`, `value` | Narrow by a comparable scalar field |
| `navigate` | `edge`, `dedup` | Hop an edge to a related element; `dedup` collapses by identity |
| `aggregate` | `fn`, `field` | Collapse a collection to a scalar (`count`, `min`, `max`, `mean`, `avg_floor`, `avg_ceil`) |
| `literal` | `element`, `value` | Name one object by id directly |
| `top` | `field`, `direction` | Keep the extreme element of a collection by a comparable field — the ordering the pipeline otherwise lacks (`desc` = highest / most recent). Collapses `many → one` |
| `evaluate` | `field`, `operator`, `value` | Terminal boolean test: `exists` (non-empty) or a comparison whose LHS is `field` — `"count"` (element count) or a scalar field name (e.g. `rating`) on a single object; produces `boolean/one` |

Every step also carries `output: Optional[str]` — the variable name the step exposes
once it resolves (see [[Effect Output Variables]]).

**Type = element × cardinality.** Every step produces a `ValueType(element, cardinality)`, where `element` is a catalog element type or a scalar (`int`/`number`/`die`/`string`/`boolean`) and `cardinality` is `one` or `many`. `boolean` is produced only by the terminal `evaluate` step (used by `TARGET_PATH` conditions).

**The effect field declares the type.** A field that wants a target (`target`, `entity`, `result`, `steps`, condition operands) states the element + cardinality it expects; the spec must resolve to a matching type. That declared type is the "what am I selecting for" hint the wizard highlights against.

**Resolution modes are `all` / `choose` / `random`.** `choose` and `random` are the single-resolution forms; there is no `any`. Cardinality lives on the *field*, not on the spec grammar. `choose` is **resumable** mid-path: the resolver emits a `PendingTargetChoice` (candidates + `step_index`) and later re-resolves the same spec with `answers` (a `step_index → ids` map), so a path can pause for user input and continue.

**Variables.** A step's `output` binds its resolved value into the per-activation
scope, typed by the step's resolved element *and* cardinality. A `many` step
binds the full ordered list (`Binding {value, values, element, cardinality}`); a
`one` step binds a single id. A later step references it with `select variable
{name}` (a `many` binding re-seeds a `many` collection and fans out); a later
effect references `{name}` in the flat `target`/`entity`/`result`/
`refs.<name>.value` fields (scalar `one` bindings only). See [[Effect Output Variables]].

**A step's value may itself be a name** — `filter universe == {chosen_universe}`,
where the right-hand side is resolved from the bound scope at resolution time
(`target_resolver._bound_value`). An unknown name matches nothing rather than
everything. This is what lets a path **join** to a decision made elsewhere in the
activation instead of comparing against a literal.

**References are variables too.** Each declared `EffectActionMeta.refs` entry is
resolved in order and published into the same scope (typed by its element), so a
reference declared *before* another is in scope for it: Attune decides the world
first, then draws the life from it (`filter universe == {universe}`).

## The catalog

`target_catalog.py` is the single source of truth both the type-checker and the wizard read, so only valid steps compose.

- **Element types** (`ELEMENT_TYPES`): `die`, `traitsetting`, `traitsetsetting`, `trait`, `traitset`, `entity`, `projection`, `location`, `universe`, `pool`.
- **Edges** (`EDGES`): named hops `(source → target, cardinality)`. Edges are union-capable (`target` is a tuple) but single-typed today — e.g. `die → traitsetting`, `traitsetting → subtraits`, `traitsetting → entity`, `entity → location`, `location → occupants`, plus the pool-assembly hops `entity → pool` and `location → difficulty_pool`, and `pool → dice` (a pool element is a handle; the dice themselves come from the scene store, which is why this one edge reads runtime state rather than the repo). A `traitsetting → subtraits` hop reaches the instances nested under a parent (elemental roots under Spiritual Power); they are deliberately absent from `entity → traitsettings`, which filters `from_type != 'traitsetting'`.
- **Scalar fields** (`SCALAR_FIELDS`): comparable/aggregatable fields per element, each with a type (`int`/`number`/`die`/`string`/`datetime`). Enum-like string fields also carry an **`options` tuple** so the wizard renders a dropdown (`die.source_kind`, `die.tier`, `die.rating`, `traitsetting.rating_type`, `traitsetting.from_type`, `entity.type`, …). Id-reference fields carry a **`references`** element hint (`traitset_id → traitset`, `trait_id → trait`, `entity_id → entity`, `projection_id → projection`, …) so the wizard renders a **TargetPicker** instead of a free-text id input. A free-form field whose values are *data* rather than schema carries a **`suggest`** value source instead (`traitsetting.tags` and `trait.tags` → `trait_tags`): the wizard autosuggests the values that exist (`<datalist>`), while typing a new one stays allowed. **`datetime`** orders by when it happened (naive and aware timestamps are normalised to UTC), which is what makes `projection.last_used_at` orderable — `is_orderable(field)` is the check a `top` step passes before it can rank.
- **Aggregations** (`AGGREGATIONS`): `count` (int), `min`/`max` (same-type), `mean`/`avg_floor`/`avg_ceil` (number).
- **Collections** (`COLLECTIONS`): the `select` seeds — `self` (singleton entity), `rolled_dice`, `opposing_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`, `sfxs`. Two special seeds live outside `COLLECTIONS` because their type varies: `select source` (typed by the SFX's `source_kind`) and `select variable` (typed by a bound output variable). **Dice collections come from the event context**, through one rule (`target_resolver.event_collections`): an event that carries `rolls` / `opposing_rolls` exposes them as `rolled_dice` / `opposing_dice` wherever the context is threaded (conditions, immediate effects, deferred effects). A collection's card phrase carries its **party** (`you rolled` / `they rolled`), so the other side's dice never read as the actor's.

Adding a new element, edge, field, aggregation, or collection is a declaration here plus a repo read in the resolver.

## Type-checker and resolver

Two layers, one source of truth:

- **`target_spec.py::trace` / `check` / `final_type` / `spec_variables`** — a *pure*, catalog-driven walk. `trace` returns the `ValueType` after each step plus step-level errors (and accumulates step `outputs` into the variable scope); `check`/`final_type` match the destination; `spec_variables` returns the typed scope a spec exposes (for cross-effect `select variable`).
- **`target_resolver.py::resolve`** — the *runtime* walk over actual game values. `navigate` consults a registry of edge resolvers (one per `(source, edge)`), each backed by the repository (e.g. `die → traitsetting` reads `repo.get_traitsetting(die["ts_id"])`). `resolve(spec, context, answers=…)` is resumable across mid-path `choose`, and binds step `outputs` into `context.bindings` (typed `Binding {value, values, element, cardinality}`).

A few fields are **derived** — not a single attribute of the element. A trait *instance*'s tags are a **union**: the labels set on the instance itself plus the ones on the registry trait it points at (B116), so matching sees both. Such a `(element, field)` pair is registered in a derived-field table (`register_derived_field`) and read through the repo, so the catalog stays a declaration and the resolver stays the one place that knows how a value is actually read. `filter` and `evaluate` both read through it; with no repo there are no tags (fail closed).

A spec that type-checks is guaranteed to have resolvable steps; the resolver produces the concrete objects (or scalar).

### Filter operators

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in` (field value is a member of a list), `contains` (list field contains the value — how a list-valued field is matched: `armed_sfx_ids`, and `tags` on a trait or trait instance). Ordering compares numerically (a `die` field coerces `d8` → 8). **Values are typed at authoring time** (decision 4): an `int`/`number` field stores a number, `die`/`string` fields store strings — so downstream logic always has typed values.

**An enum filter takes one value or several.** Several is written as a list with `in` and means *any of*, and a list-valued field follows the same rule: `tags contains [fire, wood]` means *tagged either*. (The tags editor in the wizard writes that list.) — `polarity in [positive, negative]` matches either, and the card reads *each positive or negative trait instance you rolled*. The wizard stores a single pick as a string with `==` (so nothing already authored changes shape) and a multi-pick as a list with `in`.

**A filter can prove a type.** `entity.type == location` establishes that the value *is* a location, so the path may take the steps only a location has (`occupants`, `difficulty_pool`) afterwards — the same rule the resolver and the card text read (`target_catalog.narrowed_element`, declared in `ELEMENT_NARROWING`). Only equality with a value that names a catalog element narrows; `!=`, the ordering operators, a bound `{name}` and non-element types (`character`, `gmc`, `asset`, `faction`) prove nothing. This is what makes a path writable that starts at a trait instance on a place and then reaches the room: *the trait → its owner → (proven a location) → occupants*.

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

The wizard is catalog-driven: it cannot compose an invalid path, and a field with declared enum options renders a dropdown, an id-reference field renders a picker, and a free-text value is the fallback.

## GraphQL surface

- `targetCatalog` — the full catalog (elements, edges, fields + options, aggregations, collections).
- `traceTargetSpec(input, destinationElement, destinationCardinality, sourceElement, variables)` — walks a draft spec through the shared type-checker; returns the type after each step, step errors, and `valid` (does the final type match the destination). `variables` seeds the bound-variable scope (name → element).
- `effectVariables(effects, sourceElement, conditions, trigger, sourceKind)` — the typed names a path may `select variable` from. It seeds the scope with the **activation's own names** first (`target_catalog.scope_seed_names`: the source token and the trigger's declared variables, typed by catalog element, non-walkable ones dropped), then traces the SFX's conditions, then each effect's specs and its declared references. The engine binds the same names from the live event (`effects_engine._activation_bindings`), so what the wizard offers is what resolves — and a deferred effect carries them, snapshotted with the rest of the activation.

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
| Runtime resolver + edge resolvers | `services/target_resolver.py` (`resolve`, `Binding`, `TargetContext.bindings`) |
| Step outputs → typed variables | `services/target_spec.py::spec_variables`, `services/effects_engine.py` |
| Legacy string → trivial spec | `services/target_legacy.py` |
| `Effect.target_spec` / `entity_spec` fields | `domain/__init__.py` |
| `entity_spec` subject resolution | `services/effects_applier.py` (`_effect_subject`) |
| `target_spec` roll-deferred fan-out | `services/roll_deferral.py` (`_apply_spec_target`) |
| Passive arming + `on_session_start` | `services/state_events.py`, `services/roll_deferral.py`, `services/menu_contexts.py` |
| Wizard component / composable | `frontend/src/components/gm/TargetSpecBuilder.vue`, `frontend/src/composables/useTargetCatalog.js` |
| GraphQL (`targetCatalog`, `traceTargetSpec`, `effectVariables`) | `api/graphql/schema.py`, `api/graphql/types.py` |

## Related

- [[SFX and Effects]] — the effect model + registry this targets.
- [[Effect Output Variables]] — step-level typed outputs + `select variable`.
- [[Passive Rules and Multi-Target References]] — the design/plan this implements.
- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.

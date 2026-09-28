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
| `select` | `collection`, `variable` | Seed from a context collection (`self`, `rolled_dice`, `opposing_dice`, `added_dice`, `occupants`, `locations`, `entities`, `traits`, `universes`, `self_traitsettings`, `sfxs`), the SFX `source`, or a bound `variable` |
| `filter` | `field`, `operator`, `value` | Narrow by a comparable scalar field |
| `navigate` | `edge`, `dedup` | Hop an edge to a related element; `dedup` collapses by identity |
| `aggregate` | `field`, `fn`, `count` | **Field first, then function** — the field's type decides which functions exist (`aggregations_for(field_type)` is the one rule the editor and the type-checker share). No field: `count`, or `random` (a sample — `count` 1 picks one element, more keeps a subset). Orderable field (`int`/`number`/`die`/`datetime`): `min`/`max` give the **value**, `top`/`bottom` give the **element** carrying the highest/lowest value. Numeric field adds `mean`/`avg_floor`/`avg_ceil`. A `datetime` is never offered an average |
| `literal` | `element`, `value` | Name one object by id directly |
| `evaluate` | `field`, `operator`, `value` | Terminal boolean test: `exists` (non-empty) or a comparison whose LHS is `field` — `"count"` (element count) or a scalar field name (e.g. `rating`) on a single object; produces `boolean/one` |

`random` and `top`/`bottom` were steps of their own and are **aggregate functions** now; a stored spec using the old spellings is folded on parse (`TargetSpec._fold_legacy_random_step`), so only one spelling survives.

Every step also carries `output: Optional[str]` — the variable name the step exposes
once it resolves (see [[Effect Output Variables]]).

**Type = element × cardinality.** Every step produces a `ValueType(element, cardinality)`, where `element` is a catalog element type or a scalar (`int`/`number`/`die`/`string`/`boolean`) and `cardinality` is `one` or `many`. `boolean` is produced only by the terminal `evaluate` step (used by `TARGET_PATH` conditions).

**The effect field declares the type.** A field that wants a target (`target`, `entity`, `result`, `steps`, condition operands) states the element + cardinality it expects; the spec must resolve to a matching type. That declared type is the "what am I selecting for" hint the wizard highlights against.

**Resolution modes are `all` / `choose` / `random`.** `choose` and `random` are the single-resolution forms; there is no `any`. Cardinality lives on the *field*, not on the spec grammar. **A `choose` carries one of two amounts, not a number:** `count = 1` is *choose one* and `count = null` is *choose multiple* — as many as the user likes. A number above 1 is never written (legacy content still reads as "more than one"), because the amount only ever decided single-pick vs multi-select while *looking* like a cap it never enforced: the wizard let you tick every candidate whatever the number said. The wizard renders the two as a toggle. `choose` is **resumable** mid-path: the resolver emits a `PendingTargetChoice` (candidates + `step_index`) and later re-resolves the same spec with `answers` (a `step_index → ids` map), so a path can pause for user input and continue. `choose` is **not offered in a condition path** — a condition is *evaluated*, with nobody to answer, so such a step would resolve to nothing and the gate would silently never pass (the editor disables it with that reason; `validate_sfx` warns on content that predates the rule). An effect's **subject** path (`entity_spec`) honours it too: a real decision is raised as a structured choice and the effect waits for the answer. **Nothing to choose between is not a question — and that means exactly one candidate**, taken silently; anything with two or more is put to the table, and the answer **fans the effect out over everyone picked**. Before 2026-09-27 the shortcut fired on *"no more candidates than the step asked for"*, so `choose 2` over exactly two people took the first and silently dropped the other; before 2026-09-26 a `choose` there resolved to nobody and the effect was dropped without ever asking ([[B228]]).

**Answering and cancelling are both decisions.** The question is raised while the activation is still open, so an effect that applied *before* it (a cost, say) is held rather than committed. **Cancelling the table ends the activation** — the same take-back the owner's own toggle-off makes, applying the undos it still owes — which is why the host that puts the question away must know the rule it belongs to (the choice carries `source_sfx_id`). Two things it is not: a question raised by a roll or a state change has no press behind it, so cancelling there only puts the question away; and declining a **loop** prompt is the loop ending, not a bargain being undone. A take-back is bounded twice over — by which actions declare an inverse (an effect with none cannot come back), and by the window itself, since a roll commits the activation and dissolves its holds.

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

- **Element types** (`ELEMENT_TYPES`): `die` (a die in a pool), `rating_die` (a die of a trait instance's rating), `traitsetting`, `traitsetsetting`, `trait`, `traitset`, `entity`, `projection`, `location`, `universe`, `relationship`, `sfx`, `pool`.
- **Edges** (`EDGES`): named hops `(source → target, cardinality)`. Edges are union-capable (`target` is a tuple) but single-typed in practice — a union target is refused by the trace rather than guessed at. Two hops reach a **die**, because a die has two homes: `pool → dice` (the dice currently assembled for a roll) and `traitsetting → rating_dice` (the dice that make up that trait's rating). A **relationship** is reachable from either end of what it joins: `entity → relationships` (outgoing only — what this entity holds *about* others) then `relationship → traitsettings`, which is the route to a trait instance anchored to a membership edge rather than to the entity; `relationship → entity` and `traitsetting → relationship` hop back. A **universe** reaches its own places with `universe → locations` (the reverse of `location → universe`), so a path ranges over a world instead of starting from an entity that happens to be in one. The rest: `die → traitsetting`, `traitsetting → subtraits`, `traitsetting → entity`, `entity → location`, `location → occupants`, `trait → traitsettings` (a definition's instances — sub-trait instances included — which is the step a registry-seeded reach selector needs, since a definition has no surface to own a rule; see [[Dynamic SFX Reach]]), plus the pool-assembly hops `entity → pool` and `location → difficulty_pool`. A `traitsetting → subtraits` hop reaches the instances nested under a parent (elemental roots under Spiritual Power); they are deliberately absent from `entity → traitsettings`, which filters `from_type != 'traitsetting'`.
- **Scalar fields** (`SCALAR_FIELDS`): comparable/aggregatable fields per element, each with a type (`int`/`number`/`die`/`string`/`datetime`). Enum-like string fields also carry an **`options` tuple** so the wizard renders a dropdown (`die.source_kind`, `die.tier`, `die.rating`, `traitsetting.rating_type`, `traitsetting.from_type`, `entity.type`, …). Id-reference fields carry a **`references`** element hint (`traitset_id → traitset`, `trait_id → trait`, `entity_id → entity`, `projection_id → projection`, `relationship.contact_id → entity`, …) so the wizard renders a **TargetPicker** instead of a free-text id input. A free-form field whose values are *data* rather than schema carries a **`suggest`** value source instead (`traitsetting.tags` and `trait.tags` → `trait_tags`): the wizard autosuggests the values that exist (`<datalist>`), while typing a new one stays allowed. **`datetime`** orders by when it happened (naive and aware timestamps are normalised to UTC), which is what makes `projection.last_used_at` orderable — a field like this is what `aggregate` offers `top`/`bottom` (`Highest/Lowest element`) and `min`/`max` (`Lowest/Highest value`) for, and it is never offered `mean`/`avg_*`.
- **Aggregations** (`AGGREGATIONS`): `count` (int), `min`/`max` (same-type), `mean`/`avg_floor`/`avg_ceil` (number).
- **Collections** (`COLLECTIONS`): the `select` seeds — `self` (singleton entity), `rolled_dice`, `opposing_dice`, `added_dice`, `occupants`, `locations`, `entities`, `traits` (every trait *definition* in the registry), `universes` (every world), `self_traitsettings`, `sfxs`. Two special seeds live outside `COLLECTIONS` because their type varies: `select source` (typed by the SFX's `source_kind`) and `select variable` (typed by a bound output variable). **Dice collections come from the event context**, through one rule (`target_resolver.event_collections`): an event that carries `rolls` / `opposing_rolls` exposes them as `rolled_dice` / `opposing_dice` wherever the context is threaded (conditions, immediate effects, deferred effects). A collection's card phrase carries its **party** (`you rolled` / `they rolled`), so the other side's dice never read as the actor's.

Adding a new element, edge, field, aggregation, or collection is a declaration here plus a repo read in the resolver.

## Type-checker and resolver

Two layers, one source of truth:

- **`target_spec.py::trace` / `check` / `final_type` / `spec_variables`** — a *pure*, catalog-driven walk. `trace` returns the `ValueType` after each step plus step-level errors (and accumulates step `outputs` into the variable scope); `check`/`final_type` match the destination; `spec_variables` returns the typed scope a spec exposes (for cross-effect `select variable`).
- **`target_resolver.py::resolve`** — the *runtime* walk over actual game values. `navigate` consults a registry of edge resolvers (one per `(source, edge)`), each backed by the repository (e.g. `die → traitsetting` reads `repo.get_traitsetting(die["ts_id"])`). `resolve(spec, context, answers=…)` is resumable across mid-path `choose`, and binds step `outputs` into `context.bindings` (typed `Binding {value, values, element, cardinality}`).

A few fields are **derived** — not a single attribute of the element. A trait *instance*'s tags are a **union**: the labels set on the instance itself plus the ones on the registry trait it points at (B116), so matching sees both. A location's `universe` is stored as `current_universe` on the Entity, so the reader bridges the two names — without it the picker's subtitle was blank and `filter universe == earth` matched nothing (the same shape as a pool die's `rating`, stored as `die`). Such a `(element, field)` pair is registered in a derived-field table (`register_derived_field`) and read through the repo, so the catalog stays a declaration and the resolver stays the one place that knows how a value is actually read. `filter` and `evaluate` both read through it; with no repo there are no tags (fail closed).

A spec that type-checks is guaranteed to have resolvable steps; the resolver produces the concrete objects (or scalar).

### Filter operators

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in` (field value is a member of a list), `not in` (the negation of `in`: none of the listed values — one value or several), `contains` (list field contains the value — how a list-valued field is matched: `armed_sfx_ids`, and `tags` on a trait or trait instance), `not contains` (its negation: several values mean *none of*, and an absent list contains nothing). **The two containment directions are not interchangeable and the wrong one fails silently:** `in` tests the field's *whole value* against a list, so on a list field it can never be true — and `not in` on a list field is therefore *always* true. A list field is matched with `contains`/`not contains` and declares neither `==` nor `in`. Ordering compares numerically (a `die` field coerces `d8` → 8). **Values are typed at authoring time** (decision 4): an `int`/`number` field stores a number, `die`/`string` fields store strings — so downstream logic always has typed values.

**An enum filter takes one value or several.** Several is written as a list with `in` and means *any of*, and a list-valued field follows the same rule: `tags contains [fire, wood]` means *tagged either*. (The tags editor in the wizard writes that list.) — `polarity in [positive, negative]` matches either, and the card reads *each positive or negative trait instance you rolled*. The wizard stores a single pick as a string with `==` (so nothing already authored changes shape) and a multi-pick as a list with `in`.

**A list-valued field is asked about with `contains`, and only that.** `["a"] == "a"` and `["a"] in ["a"]` are both false, so an id picker's habitual `==`/`in` would write a filter that reads as authored and matches nothing. A field is a list here when its declaration offers `contains` **and not** `in` (`known_to`, `tags`, `universes`) — which is what the wizard reads to choose the operator, so a single pick means *is on the list* and several mean *any of*. Such a field is declared with `contains` alone rather than offering operators that can never match. There is no `not contains`, so "on nobody's list" is not expressible.

**A filter can prove a type.** `entity.type == location` establishes that the value *is* a location, so the path may take the steps only a location has (`occupants`, `difficulty_pool`) afterwards — the same rule the resolver and the card text read (`target_catalog.narrowed_element`, declared in `ELEMENT_NARROWING`). Only equality with a value that names a catalog element narrows; `!=`, the ordering operators, a bound `{name}` and non-element types (`character`, `gmc`, `asset`, `faction`) prove nothing. This is what makes a path writable that starts at a trait instance on a place and then reaches the room: *the trait → its owner → (proven a location) → occupants*.

## Effect fields

`Effect` (in `src/api/src/transversal/domain/__init__.py`) gained two structured fields alongside the legacy strings:

- `target_spec: Optional[TargetSpec]` — the object/target pipeline. `None` = still use the legacy `target` string.
- `entity_spec: Optional[TargetSpec]` — the **subject** pipeline (who the effect applies to). `None` = still use the legacy `entity` string.

When both a legacy string and a spec exist, the spec wins. `entity_spec` resolves in `effects_applier._effect_subject`; `target_spec` resolves per target in `roll_deferral._apply_spec_target` (the roll-deferred path), which fans the effect out once per resolved target.

### Two homes for a die (the `Change a Die` family)

A die lives in one of two places, and which one decides what changing it *means*:

| | `die` (pool die) | `rating_die` (rating die) |
|---|---|---|
| What it is | a die the player assembled for a roll | part of a trait instance's definition |
| Reached by | `pool → dice` | `traitsetting → rating_dice` |
| Lifetime | rebuilt every roll — a change lasts the roll | a fact about the character — a change persists |
| Undo | nothing to revert (the pool is gone) | restores the recorded prior dice; may carry a duration |
| Reference | `die:<location>:<owner>:<index>` | `rating:<index>:<ts_id>` |

The index comes **first** in the rating reference because a traitsetting id contains colons (`kael:spiritual-power`), so the tail is the only unambiguous place for it.

An action declares the destinations it accepts as a **set** (`EffectActionMeta.path_element`, served as `pathElements`): the whole family accepts both, and `reroll_die` accepts only `die`, because rerolling a *result* needs a result and a rating die has none. The trace refuses a spec reaching neither, naming each type that would have worked ("not die/one or rating_die/one").

A duration is offered only where it means something (`duration_elements`): the editor reads the element the path resolved to and shows the timer builder only for a rating die. A timer on a pool die would be a field that lies — the pool it changed no longer exists. **The path reports that element itself** (`PathField` traces its own steps), rather than only from the builder inside the child edit panel: a locus that is merely *unknown* must not read as *inapplicable*, or a stored timer shows as left over and is dropped on save.

`aggregate` is how a *specific* die is chosen from either home: `bottom field=rating` is the lowest die of a rating, `top field=rating` the highest, and `random` samples. That is why `Reroll Highest` is expressed as `reroll_die` over `aggregate top field=rating`, and why the two must not be confused with `min`/`max`, which give the *value* rather than the die.

### Legacy migration

`target_legacy.py::from_legacy_target(target, kind)` translates the *unambiguous* legacy string forms into trivial specs:

- `self` → `select self`
- `{choose:kind}` / `{random:kind}` → the declared scope path for that kind plus a terminal `choose`/`random` step. **The placeholder form is deleted** — a stored rule carries the path, not the token.
- a literal id → `literal <id>` (element from the action's `target_kind`)

Unmappable forms (variables like `{effect_die}`, kinds without a collection/element) return `None` and stay on the legacy string for the author to fix by hand.

## The scope vocabulary

A **scope** is a compact way of saying *which targets* — `subtree:krasnoyarsk`, `faction:ru-maffia`, `traitset:ts-complications-a190`. It is not a second vocabulary: every `(prefix, kind)` pair is declared in `services/target_scopes.py` as the **path** it stands for, and `resolve_candidates` runs that path through the same resolver as any authored spec. One vocabulary (the catalog), one evaluator.

It is now a **picker** vocabulary. `Effect.target_scope` — the string stored on a rule — is **deleted**: a stored target choice is a path, with a `choose` or `random` step where the author wants the table to decide. The declarations remain because the picker needs them (and `choice_spec(kind, scope, mode, filter)` composes one, which is how a built-in says "a random starter location in Earth").

```
scope "traitset:ts-complications-a190", kind "trait"
  → literal traitset ts-complications-a190 → navigate traits
scope "subtree:loc-56720896", kind "occupant"
  → literal location loc-56720896 → navigate subtree → navigate occupants
    → filter id != <the acting entity's id>
```

- **Declared, not registered.** `register_scope(prefix, resolver)` is gone. Adding a scope means declaring a path. `targetScopes` returns each prefix with its label, description, and the kinds it can select, so a caller reads the vocabulary instead of extracting it from the source.
- **Kind vs element.** `kind` is the flat/editor word and `element` the catalog type the path ends on; they differ once, for `occupant` (an *entity at a place* — a scope question, not a type), declared in the selection row.
- **The acting entity is the only parameter.** A builder receives the scope's value and the acting entity — the only two things the flat form ever depended on. *Not me* is `filter id != <its id>`; *my universe* is `filter universe == <the universe it is in>`. Both are ordinary filter steps.
- **Unsupported pairs are errors.** `kind="occupant"` + `scope="faction:X"` used to answer `[]`, indistinguishable from an empty roster; it now raises an error naming the kinds that scope supports. An unknown prefix is an error too, rather than silently falling back to the default scope.
- **A candidate filter is a filter step.** `{"starter_location": true}` was stored beside the scope; it is appended as an ordinary filter step, so a narrowing is the same language as the path.
- **`universe:X` and a bare value** are the same selections — bare means "the acting entity's context", and a bare value is a universe (a place id for `occupant`).

The declarations, and what each scope can select:

| Prefix | Kinds | Means |
|--------|-------|-------|
| *(bare)* / `universe` | `rating_die`, `location`, `occupant`, `entity`, `trait`, `traitset`, `life_path`, `roll_table`, `universe`, `projection`, `scheduled_event` | The acting entity's own context; a bare value is a universe |
| `location:` | `occupant`, `entity`, `location`, `projection` | At that place (its occupants; the place and its zones; the actor's own bodies there) |
| `subtree:` | `occupant`, `entity`, `location`, `projection` | Everything inside that place, zones included |
| `faction:` | `entity`, `roll_table` | Its roster; the tables of the life paths it may start people on |
| `actor_faction:` | `entity`, `trait` | The orgs the acting entity is itself on the roster of (optionally narrowed to one by id) |
| `traitset:` | `trait` | The traits that set defines — or, for a mutate-only action, only the ones the entity already holds in it |
| `life_path:` | `roll_table` | The tables that follow that life path |

## The wizard (frontend)

- `src/frontend/src/components/gm/TargetSpecBuilder.vue` — the step-by-step path builder: add/remove/reorder step rows, per-step config, catalog-driven affordances (only legal edges/fields/aggregations offered), and **live type highlighting** (each step's resolved type, green when it matches one of the field's declared destinations). It also reports the element its path currently resolves to, which is what lets an action offer a duration only where one means something.
- `src/frontend/src/composables/useTargetCatalog.js` — module-singleton that fetches the catalog and calls `traceTargetSpec` (debounced) for highlighting.
- Wired into `EffectForm.vue` on the `target` field (a **"Targeting path"** mode) and the `entity` field (a **"Targeting path"** subject).

### A path is the only way to name a target

Every action's `target` is a **targeting path**. The older way — a picker kind (`target_kind`) choosing a thing, or a free-text *strategy keyword* naming a rule for choosing one — is gone, along with the `entity`/`relationship` fields that only existed to resolve a bare trait id and override its anchor.

- **The picker kind is no longer declared** for a target. `path_element` states what a path must resolve to (`("traitsetting",)`, `("die", "rating_die")`, `("trait",)` …), and that is what the trace checks and the editor highlights against.
- **A target that must be a path offers only the path.** When an action declares destinations and no picker kind, the mode row is not rendered at all — there is nothing to pick and no keyword to type, so a select with one option is not a UI.
- **A runtime pick is a `choose` step.** The `{choose_trait}` / `{random:location}` placeholder and the `target_scope`/`target_filter` fields beside it are **gone**; a rule that wants the table to choose carries the path and a terminal `choose`/`random` step. The engine resolves it and surfaces a structured choice carrying the exact candidate pool (see `resolveTargetSpec`), which is what the wizard renders.
- **The keywords have path equivalents**, and any step's `output` makes one reusable (`select variable`):
  - `highest_trait_die` → `select rolled_dice → filter source_kind == trait → aggregate Highest element field=rating` (or `select self → navigate pool → navigate dice → …` for the live pool rather than the event's dice);
  - `the_hitch_die` → the same path filtered to `tier == fail`.

`entity` remains a field where it is a genuine **subject** — who an effect lands on — and it has accepted a targeting spec (`entity_spec`) all along. `relationship` remains only where a *subject* cannot yet be a relationship: creating a trait on a membership edge (`gain_trait` and its siblings). That last one is the remaining work, not a design choice.

The wizard is catalog-driven: it cannot compose an invalid path, and a field with declared enum options renders a dropdown, an id-reference field renders a picker, and a free-text value is the fallback.

## GraphQL surface

- `targetCatalog` — the full catalog (elements, edges, fields + options, aggregations, collections).
- `traceTargetSpec(input, destinationElements, destinationCardinality, sourceElement, variables)` — walks a draft spec through the shared type-checker; returns the type after each step, step errors, and `valid` (does the final type match the destination). `destinationElements` is a **list**, because a field may accept more than one kind of thing. `variables` seeds the bound-variable scope (name → element).
- `targetScopes` — the declared scope vocabulary: every prefix with its label, description, and the kinds it can select. Read it instead of remembering it; the entries come from the same declaration the resolver uses.
- `targetCandidates(kind, entityId, scope, action, filter)` — the candidates a `(kind, scope, filter)` choice selects, resolved through the declared path. The **picker's** read (a path that wants a runtime pick carries a `choose` step instead). Raises for an unsupported pair rather than answering `[]`.
- `resolveTargetSpec(input, entityId, sourceKind, sourceId, bindings, valuesLimit)` — **execute** a spec against live data, read-only. The counterpart of `traceTargetSpec`: that one says what a draft *would* be, this one says what it *does*. Every step reports its values, its resulting type, and the exact count it produced (values are capped by `valuesLimit`, the count is not); a `choose` step reports `pending` with the element it is about plus the full candidate pool. Nothing is applied or committed, so a path can be inspected rather than guessed at — a single final list hides the step that collapsed.
- `targetLabels(ids: [ID!]!)` — display names for ids, resolved through the same repository resolver the card text uses, so a picker shows a **name** for a value whose candidate is not in the loaded page. The editor never shows raw ids; a raw id is the last resort.
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
| The scope vocabulary + candidate resolution | `services/target_scopes.py` (`TARGET_SCOPES`, `selection_spec`, `choice_spec`, `resolve_candidates`) |
| Step outputs → typed variables | `services/target_spec.py::spec_variables`, `services/effects_engine.py` |
| Legacy string → trivial spec | `services/target_legacy.py` |
| `Effect.target_spec` / `entity_spec` fields | `domain/__init__.py` |
| `entity_spec` subject resolution | `services/effects_applier.py` (`_effect_subject`) |
| `target_spec` roll-deferred fan-out | `services/roll_deferral.py` (`_apply_spec_target`) |
| Change-a-die handlers, both loci | `services/effects_applier/handlers_change_die.py` |
| Passive arming + `on_session_start` | `services/state_events.py`, `services/roll_deferral.py`, `services/menu_contexts.py` |
| Wizard component / composable | `frontend/src/components/gm/TargetSpecBuilder.vue`, `frontend/src/composables/useTargetCatalog.js` |
| GraphQL (`targetCatalog`, `traceTargetSpec`, `effectVariables`) | `api/graphql/schema.py`, `api/graphql/types.py` |

## Related

- [[SFX and Effects]] — the effect model + registry this targets.
- [[Effect Output Variables]] — step-level typed outputs + `select variable`.
- [[Passive Rules and Multi-Target References]] — the design/plan this implements.
- [[Effect System Capabilities and Gaps]] — the deferred drillthrough + selective-stamping tracks this resolves.

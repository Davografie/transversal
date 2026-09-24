---
title: Effect Output Variables
date: 2026-08-29
tags:
  - transversal
  - technical
  - sfx
  - effects
  - plan
aliases:
  - Effect Bindings
  - Output Variables
status: implemented
---

# Effect Output Variables

A value can be **exposed under a name** and read by later steps. There are two
declarations, and the difference is *when the name exists*:

- **A step's `output`** (the 💡 on a path step) binds a name as a **side effect** of
  a path authored for another purpose. It exists from that step onward, so it can
  be read by later steps in the same path and by later effects — but **not by a
  condition**, because the condition gate runs before any effect.
- **A `BoundVariable` on the SFX** (the *Bound variables* section) states the name
  and its path up front. It is resolved **before the condition gate**, so a
  condition's path may read it and a later declaration may start from an earlier
  one. This is the one to reach for when the rule *is about* a value; the 💡 is for
  "remember this while I walk".

Both write the **same per-activation scope**. One shared scope per activation holds
all of it — declared bound variables first (in declaration order), then written by
**conditions**, then by **effects** in order.

## Shape

- `TargetStep.output: Optional[str]` — the single variable name bound at that step.
- `SFX.bound_variables: list[BoundVariable]` — `{name, spec}`, resolved in order by
  `effects_engine.firing.bind_declared`, before the gate.
- The resolver binds a resolved value into the per-activation scope
  (`Binding {value, values, element, cardinality}`) through **one** function,
  `target_resolver.bind_named`: a `many` result binds the full list
  (`cardinality="many"`), a `one` result binds a single id (`cardinality="one"`).
  Both callers read it, so they cannot disagree about cardinality or about which id
  a value carries.
- Later steps reference `{name}` via `select variable` (typed); a `many` binding
  re-seeds a `many` collection and fans out. Later effects reference `{name}` in
  the flat `target`/`entity`/`result`/`refs.<name>.value` fields via string
  substitution (scalar `one` bindings only).
- An **unbound** name is the honest state for "resolved to nothing": it is never
  bound empty, so a downstream path resolves to nobody rather than to a blank id.

## Why this (vs resolve-once-by-identity)

Explicit authoring, general (any resolved value, not just identical chooses),
predictable. It composes with the existing `refs` + `{token}` substitution
machinery rather than adding a parallel system.

## What's implemented

1. **Step-level output** — `TargetStep.output: Optional[str]`; the resolver binds
   the step's resolved value(s) into `TargetContext.bindings`
   (`Binding {value, values, element, cardinality}`), typed by the step's
   resolved element.
2. **Typed `select variable`** — both the type-checker (`trace`) and the resolver
   support `select variable {name}`; `trace` accumulates intra-spec step outputs
   so later steps in the same path type-check.
3. **Cross-effect typing** — `target_spec.spec_variables` + the GraphQL
   `effectVariables` field trace prior effects' specs and return the typed
   `name → {element, cardinality}` scope; the wizard uses it so a later effect's
   `select variable` type-hints against earlier effects (including `many`).
4. **String substitution** — `_substitute_effect_context` merges the binding
   scope, so a scalar `one` binding resolves in `target` / `entity` / `result` /
   `refs.<name>.value` / `context.<key>`; a `many` binding is left untouched
   (array re-use is via `select variable`).
5. **Deferred + resume** — bindings thread through the immediate path, the
   deferred path (`ArmedSfx.bindings`), and the resume path (`bind_activation`),
   so a value picked once survives to later roll-timed effects.
6. **Ref fan-out** — `resolve_refs` returns a *list* of concrete effects: a ref
   whose `spec` resolves to `N` values fans the effect out `N` ways (the
   cartesian product across refs); a literal/token ref stays fixed, and a ref
   resolving to zero values produces no effects. Wired through the immediate
   path (`process_event_outcome`), the resume path
   (`resolve_effect_spec_choices`), and the roll-deferred path
   (`_apply_refs_roll`).
7. **List output variables** — a `many` step binds the full ordered list
   (`Binding.values` + `cardinality="many"`); `select variable` re-seeds a `many`
   collection and fans out (see [[List Output Variables]]).
8. **Conditions seed the scope** — a `Targeting path` condition runs *before* any
   effect, so its step `output` names are published into the activation scope and
   are in scope for every effect. The gate names *what it matched* (e.g. `the d4
   traits in this roll`), not just yes/no:
   - `evaluate_condition`'s `TARGET_PATH` branch resolves with the scope as
     `TargetContext.bindings`, then publishes the path's outputs into the
     caller's `out_bindings` (step outputs land on the resolution **context**, not
     on the `Resolution`, which carries only `values`/`errors`/`pending_choices`).
   - `process_event_outcome` seals one `bindings` dict *before* the condition gate
     and reuses it for the effect loop, so both halves share it.
   - The scope reaches the applier via `BINDINGS_CONTEXT_KEY` (`_bindings`) in the
     effect context — the same pattern as `_source`/`_source_element`.
   - `effectVariables` takes a `conditions` argument and traces conditions before
     effects, so the wizard offers those names in `select variable`.
9. **`entity_spec` resolves against the scope** — `resolve_effect_entity`
   (`apply_effects`, and the engine before dispatch) rewrites an effect's
   `entity_spec` into a concrete `entity` id and clears the spec, mirroring the
   engine's `target_spec` rewrite. The razmerit handlers (`earn`/`spend`/
   `transfer`) then act on that entity: a concrete `effect.entity` wins, and only
   blank / `self` / an unresolved placeholder falls back to the acting entity.
10. **Roll-scoped seeds for conditions** — roll-bearing triggers put the dice in
    the event context and `TARGET_PATH` seeds `collections["rolled_dice"]` from
    `context["rolls"]`. `fire_roll_sfx` and `fire_result_sfx` both supply it; a
    path selecting `rolled_dice` on a trigger without dice resolves empty and
    fails closed.
11. **Armed subjects resolve per die** — `_apply_armed` now resolves an armed
    effect's `entity_spec` before dispatch (`resolve_armed_subject`), on the
    per-die loop, the plain branch, and the `refs`/`target_spec` branches. It
    seeds `rolled_dice` with **the die being processed** in the per-die loop
    (the die *is* the roll that path should read) and with the whole roll
    otherwise. Before this, an armed effect's subject was silently dropped and
    the effect landed on the acting entity — e.g. a hazard authored for the
    die's owner's location landed on the roller.
12. **Declared bound variables** — `SFX.bound_variables` (a `BoundVariable`:
    `name` + `spec`), resolved by `firing.bind_declared` in declaration order,
    immediately after `_activation_bindings` and **before the condition gate**, so
    a condition's path may read them. The editor's *Bound variables* section
    authors them; `effectVariables` takes a `boundVariables` argument and traces
    them first, from the same seed the engine uses, so what the editor offers is
    what will bind. A declaration that would shadow a name the activation already
    owns is **refused** by the engine and warned about by `validate_sfx`; a
    declaration whose path resolves to nothing stays unbound.
13. **A numeric field can read a bound number** — an effect's *Amount* / *Steps*
    offers Number or Variable, because an `<input type="number">` cannot hold
    `{name}` at all. The **value carries the mode**; only `int`/`number` bindings
    are offered (a die would substitute as `d8`, which the handler cannot parse).
14. **The `tier` cast** — an `Aggregation` (`fn="tier"`, `accepts=("die",)`,
    `needs_single=True`) that reads a die-typed field as its **ladder position**
    (d4 → 1 … d12 → 5), distinct from the side-count reading `_to_number` already
    gives the ordering/mean functions. It lives in `AGGREGATIONS` rather than as
    its own step kind because reading a field off an element is what an aggregate
    does, and `min`/`max` would have converted the die before a later cast step
    could see it. `needs_single` refuses a collection rather than casting its first
    element.

## Open / deferred

- **`select source`-dependent types** — a step whose element comes from
  `select source` now resolves in the SFX editor (it threads `sourceElement`);
  noted for completeness.
- **`{name}` substitution vs `select variable`** — a `many` binding still can't
  be referenced from a flat field (array re-use goes through `select variable`).
- **Per-die effects resolve everything per die** — a `die_filter` runs an armed
  effect once per matching die, and its `target_spec`, `entity_spec` and `refs`
  are each resolved with **that die as the roll** (`{rolled_dice: [die]}`), so
  "for each unchosen die, take the trait it came from" lands per die. The die
  filter is checked first, before the spec/ref branches, precisely so a target
  path can't silently swallow the scope.

## Related

- [[Choose and Random Resolution]] — the `choose` machinery this feeds.
- [[Effect System Convergence Plan]] — umbrella effect-layer plan.
- [[Targeting Model]] — the spec/ref model outputs read from.

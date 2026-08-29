---
title: List Output Variables
tags:
  - transversal
  - technical
  - sfx
  - effects
  - targeting
  - plan
aliases:
  - Array Variables
  - Many-valued Bindings
status: proposed
---

# List Output Variables

Make an output variable that resolves to **many** survive as a *list*, so a
later effect can re-use it as an array and fan out once per element — instead of
the current behaviour of silently keeping only the first value.

> [!note] Relationship to [[Effect Output Variables]]
> Output variables live on targeting steps (`TargetStep.output`). Today a step
> binds only its **first** resolved id regardless of cardinality. This plan makes
> the binding cardinality-aware so `entity/many` → `friends` stays a list.

## Problem (verified)

`target_resolver._bind_step_outputs` binds `values[0]` only:

```python
rid = _candidate_id(current_type.element, values[0])
context.bindings[name] = Binding(value=rid, element=current_type.element)
```

`Binding` is a scalar (`value: str`, `element: str`), and `select variable`
resolves it back to `ValueType(element, "one")`. So a step resolving to 5
entities exposes only the first as `friends`; the other 4 are dropped and the
"many" is unrecoverable downstream.

## Goal

- A step with `output` that resolves to `many` binds the **full ordered list** of ids.
- A later effect re-uses it as an array via `select variable {name}`, which seeds
  a `many` collection and fans out through the already-built `target_spec` /
  `refs` fan-out.
- The type checker, cross-effect scope, GraphQL surface, and wizard all carry the
  cardinality so `select variable` is type-correct and self-explanatory.

## Decisions (proposed)

1. **Cardinality lives on the binding.** `Binding` gains `values: list[str]`
   (the full list) and `cardinality: "one" | "many"` (default `"one"`). `value`
   stays the scalar (first id) for the legacy `{name}` string substitution.
2. **`{name}` string substitution stays scalar-only.** `_substitute_effect_context`
   substitutes `{name}` only when the binding is `"one"` (never stringifies a
   list). Array re-use is via `select variable`, not the flat string fields. This
   keeps `target`/`entity`/`result`/`refs.<name>.value` unambiguous.
3. **`select variable` is the array re-use path.** A `"many"` binding seeds
   `values = [lookup each id]` and `current_type = ValueType(element, "many")`.
   Downstream `target_spec` / `refs` fan-out (already implemented) then applies
   once per element. No new fan-out machinery.
4. **Cardinality is carried through the typed scope.** `trace` / `spec_variables`
   switch their variable scope from `name → element` to `name → ValueType`, and
   the GraphQL `effectVariables` / `traceTargetSpec` + the wizard expose it.
5. **Backward-compatible inputs.** `traceTargetSpec.variables` keeps accepting
   `{name: element}` (cardinality defaults to `"one"`) and also accepts
   `{name: {element, cardinality}}`; both normalize to `dict[str, ValueType]`.

## Backend changes

1. **`target_resolver.py`**
   - `Binding`: add `values: list[str]` and `cardinality: str = "one"`.
   - `_bind_step_outputs`: when `current_type.cardinality == "many"`, collect
     `[_candidate_id(element, v) for v in values]` into `values`, set
     `cardinality="many"` (and `value` = first id); else the current single-id
     binding.
   - `select variable` branch: if the binding is `"many"`, seed
     `values = [_lookup_literal(element, id, context) for id in binding.values]`
     flattened and `current_type = ValueType(element, "many")`; else unchanged.
2. **`target_spec.py`**
   - `trace` / `check` / `final_type` / `spec_variables`: change `variables` from
     `dict[str, str]` to `dict[str, ValueType]` (with a normalizer accepting a
     bare element string). `scope[step.output] = t` (full `ValueType`, not just
     `t.element`). `select variable` reads both `element` and `cardinality`.
   - `spec_variables` returns `dict[str, ValueType]`.
3. **`effects_engine.py`**
   - `_substitute_effect_context`: `source.update({name: b.value ...})` → only
     include bindings whose `cardinality == "one"` (skip `"many"`).
4. **`roll_deferral.py`**
   - `bind_activation(entity_id, source_sfx_id, name, value, element="",
     values=None, cardinality="one")`: write the full binding (list + cardinality)
     into `armed.bindings`.
   - `ArmedSfx.bindings` already stores `Binding` objects — no shape change beyond
     `Binding` itself.

## GraphQL changes

- `types.py::EffectVariable`: add `cardinality: str = "one"`.
- `schema.py::effect_variables`: return `EffectVariable(name, element=v.element,
  cardinality=v.cardinality)` from the `dict[str, ValueType]` scope.
- `schema.py::traceTargetSpec`: normalize `variables` (`{name: element}` or
  `{name: {element, cardinality}}`) to `dict[str, ValueType]` before `trace`/`check`.
- `schema.py` resume mutation (`resolve_effect_targets`): pass `binding.values` +
  `binding.cardinality` to `bind_activation` instead of only `binding.value`.

## Frontend changes

- `useTargetCatalog.js::collectVariables`: return `{name: {element, cardinality}}`
  (query `effectVariables { name element cardinality }`).
- `useTargetCatalog.js::traceSpec`: pass the richer `variables` through.
- `TargetSpecBuilder.vue`: `variablesMap` becomes `{name: {element, cardinality}}`;
  the `select variable` dropdown shows element label plus a `· many` badge, and
  the live type highlight reflects `many` for a list binding.
- `EffectEditor.vue` / `GmEffectEditPanel.vue`: thread the richer `outputVariables`
  map unchanged (they just pass it through; the builder renders it).

## Tests

- `_bind_step_outputs` binds the full list when the step is `many` (and a single
  id when `one`).
- `select variable` on a `"many"` binding resolves to a `many` collection and fans
  out via `target_spec`/`refs` (immediate + roll-deferred).
- `{name}` string substitution ignores a `"many"` binding (no list stringification).
- `spec_variables` / `trace` carry cardinality through a two-effect chain; a later
  `select variable` type-checks as `many`.
- `bind_activation` round-trips `values` + `cardinality` into a deferred effect.

## Open / not in scope

- `{name}` in a flat string field fanning out over a list — deliberately deferred;
  array re-use is `select variable` only (decision 2).
- List bindings across `refs.<name>` already fan out via `resolve_refs`
  ([[Choose and Random Resolution]]); this plan is about the *output-variable*
  bindings, which are a separate mechanism.

## Related

- [[Effect Output Variables]] — the step-level scalar bindings this extends.
- [[Choose and Random Resolution]] — the `target_spec`/`refs` fan-out the list
  re-use leans on.
- [[Targeting Model]] — the spec/resolver/scope surfaces touched here.

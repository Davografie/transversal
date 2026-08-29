---
title: Effect Output Variables
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

An effect can **expose a resolved value as a named variable**, readable by
*subsequent* steps in the same path and *later* effects in the same SFX
activation. Outputs are declared **on a targeting step** (a list of names); the
step's resolved value is bound under each name, typed by the step's resolved
element (no manual element entry).

## Shape

- `TargetStep.output: Optional[str]` — the single variable name bound at that step.
- The resolver binds each step's first resolved value into the per-activation
  scope (`Binding {value, element}`), typed from the step's resolved type.
- Later steps reference `{name}` via `select variable` (typed); later effects
  reference `{name}` in the flat `target`/`entity`/`result`/`refs.<name>.value`
  fields via string substitution.

## Why this (vs resolve-once-by-identity)

Explicit authoring, general (any resolved value, not just identical chooses),
predictable. It composes with the existing `refs` + `{token}` substitution
machinery rather than adding a parallel system.

## What's implemented

1. **Step-level output** — `TargetStep.output: Optional[str]`; the resolver binds
   each step's first resolved value into `TargetContext.bindings`
   (`Binding {value, element}`), typed by the step's resolved element.
2. **Typed `select variable`** — both the type-checker (`trace`) and the resolver
   support `select variable {name}`; `trace` accumulates intra-spec step outputs
   so later steps in the same path type-check.
3. **Cross-effect typing** — `target_spec.spec_variables` + the GraphQL
   `effectVariables` field trace prior effects' specs and return the typed
   `name → element` scope; the wizard uses it so a later effect's
   `select variable` type-hints against earlier effects.
4. **String substitution** — `_substitute_effect_context` merges the binding
   scope, so `{name}` resolves in `target` / `entity` / `result` /
   `refs.<name>.value` / `context.<key>`.
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

## Open / deferred

- **`select source`-dependent types** — a step whose element comes from
  `select source` now resolves in the SFX editor (it threads `sourceElement`);
  noted for completeness.

## Related

- [[Choose and Random Resolution]] — the `choose` machinery this feeds.
- [[Effect System Convergence Plan]] — umbrella effect-layer plan.
- [[Targeting Model]] — the spec/ref model outputs read from.

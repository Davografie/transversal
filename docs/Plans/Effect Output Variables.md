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
status: in-progress
---

# Effect Output Variables

An effect can **expose a resolved value as a named variable**, readable by
*subsequent* steps in the same path and *later* effects in the same SFX
activation. Outputs are declared **on a targeting step** (a list of names); the
step's resolved value is bound under each name, typed by the step's resolved
element (no manual element entry).

## Shape

- `TargetStep.outputs: list[str]` — names bound at that step.
- The resolver binds each step's first resolved value into the per-activation
  scope (`Binding {value, element}`), typed from the step's resolved type.
- Later steps reference `{name}` via `select variable` (typed); later effects
  reference `{name}` in the flat `target`/`entity`/`result`/`refs.<name>.value`
  fields via string substitution.

## Why this (vs resolve-once-by-identity)

Explicit authoring, general (any resolved value, not just identical chooses),
predictable. It composes with the existing `refs` + `{token}` substitution
machinery rather than adding a parallel system.

## Execution plan (ordered)

1. **Domain** — `EffectOutput` + `Effect.outputs`.
2. **Substitution** — `_substitute_effect_context(effect, context, bindings=None)`
   merges the binding scope into the substitution source.
3. **Binding helper** — `_apply_outputs(effect, bindings)` reads `outputs` and
   binds each resolved field's id.
4. **Immediate path** — thread a `bindings` scope through `process_event_outcome`;
   bind after each applied effect.
5. **Deferred path** — `ArmedSfx.bindings` + thread through `_apply_armed`; bind
   after each applied effect (and, for a suspended `choose`, write the binding
   back into the armed entry on resume — the re-entrancy half).
6. **GraphQL** — expose `outputs` on `Effect` / `EffectInput`.
7. **Tests** — immediate binding, deferred binding, `{name}` substitution.

## Open / deferred

- **Typed variables** — ✅ done: `EffectOutput.element` carries the catalog element
  type; bindings are `Binding {value, element}`; the targeting wizard offers a
  typed `select variable` step and type-checks against the variable's element.
- **Suspended `choose` + deferred binding** — ✅ done (see above).
- **Authoring UX** — ✅ done: `EffectForm` output editor (name + field + element,
  auto-filled for `refs.<name>`/`entity`).
- **Remaining polish** — `field: "target"` outputs don't auto-fill `element` yet
  (the author types it); fan-out of a `refs` list binding is still first-value only.

## Related

- [[Choose and Random Resolution]] — the `choose` machinery this feeds.
- [[Effect System Convergence Plan]] — umbrella effect-layer plan.
- [[Targeting Model]] — the spec/ref model outputs read from.

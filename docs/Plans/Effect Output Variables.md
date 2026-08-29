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
*subsequent* effects in the same SFX activation. This is the "shared target
across effects" mechanism: instead of two effects each re-picking the same
complication, the first resolves it once and binds it; later effects reference
`{name}`.

## Shape

- `Effect.outputs: list[EffectOutput]` where `EffectOutput = { name, field }`.
  - `field` is which resolved field to bind: `target` | `entity` | `refs.<name>`.
- A per-activation **binding scope** (`dict[name -> id]`) is threaded through the
  effects. After an effect applies, its `outputs` read the resolved field's id
  and bind it into the scope.
- Later effects reference `{name}` in `target` / `entity` / `result` /
  `refs.<name>.value` / `context.<key>`; `_substitute_effect_context` consults
  the scope (in addition to the event context) and replaces the token.

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

- **Typed variables** — the binding currently carries only the id string; element
  type (for the wizard/type-checker) is future work.
- **Suspended `choose` + deferred binding** — ✅ done: `roll_deferral.bind_activation`
  writes the resolved binding into the armed SFX from the resume path
  (`resolveEffectTargets`); `source_sfx_id` threads through the structured choice
  so the write targets the right activation. A binding-referencing effect now
  fires once (die-scoping is keyed on `die_filter`, not `source_sfx_id`).
- **Authoring UX** — ✅ done: `EffectForm` exposes an output editor (name + field).

## Related

- [[Choose and Random Resolution]] — the `choose` machinery this feeds.
- [[Effect System Convergence Plan]] — umbrella effect-layer plan.
- [[Targeting Model]] — the spec/ref model outputs read from.

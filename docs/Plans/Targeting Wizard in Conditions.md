---
title: Targeting Wizard in Conditions
tags:
  - transversal
  - technical
  - sfx
  - effects
  - conditions
  - targeting
  - plan
aliases:
  - Path Conditions
  - TARGET_PATH
  - Conditions Use the Wizard
status: in-progress
---

# Targeting Wizard in Conditions

Let a condition's predicate be authored as a **targeting path** (a `TargetSpec`,
seeded by `select source`), instead of a flat `target` string. This makes
"the trait I'm on reached d8" authorable generically, and lets the flat
`TRAIT_RATING` / `SOURCE_RATING` predicates collapse into one path-based shape.

Follows on from [[Source-Aware Conditions]] (which threaded `source` into
condition evaluation) and the [[Targeting Model]] (the spec/resolver/catalog this
reuses).

## Goal

- A condition can hold a `TargetSpec` (`spec`) and evaluate "does this path
  resolve to anything?" — with all narrowing/comparison done by the spec's own
  `filter` / `navigate` / `aggregate` steps (already type-checked by the wizard).
- The path is seeded by `select source` (the SFX's activation/owner source), and
  `select self` / catalog collections remain available.
- Reuse the whole existing machinery — no parallel type system.

## Design (decided)

1. **New `ConditionType.TARGET_PATH`** (`"target_path"`), label "Targeting path".
2. **`Condition.spec: Optional[TargetSpec]`** — the path. `subject` / `target` /
   `value` / `operator` stay for the legacy flat conditions.
3. **Semantics**: resolve `spec` against a `TargetContext` seeded with
   `subject=entity`, `source=source`, `source_element=source_element`. The
   condition passes **iff the resolution is non-empty and error-free**. All
   comparison is expressed via `filter` steps (e.g. `filter rating >= d8`).
4. **`source_element` threading** — `evaluate_condition` / `evaluate_conditions`
   gain a `source_element` param; fire-time (`effects_engine`) and availability
   (`sfx_owner`) pass both the resolved source object and its catalog element.
5. **`TraitSetting.rating`** — a computed property (max die in `dice`), so the
   catalog's `traitsetting.rating` filter field actually resolves at runtime
   (today it's declared but `_get_field` reads no such attribute).
6. **Static classification** — `TARGET_PATH` is static unless its spec seeds
   `rolled_dice` or `select variable` (context/binding-gated), so availability
   (grey-out) can evaluate source/entity-state paths.

Non-goals (deferred): migrating existing flat conditions off `TRAIT_RATING` /
`SOURCE_RATING` (backward-compat: they keep working); scalar-predicate-on-resolved-
value (aggregate-then-compare); `select source` on effect-level conditions (the
applier path doesn't thread source yet).

## Concrete example (cultivation stage)

```
TARGET_PATH
  spec:
    - select source                # the trait-setting this SFX lives on
    - filter rating >= d8          # its current rating reached d8
```

## Touch points

| Concern | Module |
|---------|--------|
| `ConditionType.TARGET_PATH`, `Condition.spec`, `TraitSetting.rating` | `domain/__init__.py` |
| Evaluator branch + `static_conditions` + `CONDITION_TYPES` | `services/conditions.py` |
| `source_element` threading | `services/effects_engine.py`, `services/sfx_owner.py` |
| GraphQL `Condition.spec` / `ConditionInput.spec` + conversions | `api/graphql/types.py`, `api/graphql/schema.py` |
| Editor path mode (reuse `TargetSpecBuilder`) | `frontend/src/components/gm/ConditionEditor.vue` |
| `sourceElement` wiring + `spec` selection | `GmSfxEditPanel.vue`, `EffectForm.vue`, `useSfxEdit.js` |

## Related

- [[Source-Aware Conditions]] — the source-threading this builds on.
- [[Targeting Model]] — the spec/resolver/catalog reused wholesale.
- [[Effect Output Variables]] — `select source` / bindings.
- [[to-do]] — "SFX's need a source" / cultivation-stage unlock.

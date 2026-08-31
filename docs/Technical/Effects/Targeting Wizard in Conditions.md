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
status: implemented
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
   `subject=entity`, `source=source`, `source_element=source_element`. A path
   ending in an **`evaluate`** step returns that step's explicit boolean;
   otherwise the condition passes **iff the resolution is non-empty and
   error-free** (backward-compatible "existence" check).
4. **`source_element` threading** — `evaluate_condition` / `evaluate_conditions`
   gain a `source_element` param; fire-time (`effects_engine`) and availability
   (`sfx_owner`) pass both the resolved source object and its catalog element.
5. **`TraitSetting.rating`** — a computed property (max die in `dice`), so the
   catalog's `traitsetting.rating` filter field actually resolves at runtime
   (today it's declared but `_get_field` reads no such attribute).
6. **Static classification** — `TARGET_PATH` is static unless its spec seeds
   `rolled_dice` or `select variable` (context/binding-gated), so availability
   (grey-out) can evaluate source/entity-state paths.
7. **`evaluate` terminal step** — `exists` (non-empty) plus `==`/`!=`/`>`/`>=`/
   `<`/`<=` against a `many` collection's count or a scalar (`int`/`number`/`die`),
   producing `boolean/one`. This makes scalar predicates (`count >= 2`,
   `max rating >= d8`) expressible — the plain "non-empty" check couldn't.
8. **Automatic-trigger source** — `sfx_owner.resolve_sfx_source` resolves the
   SFX's source from ownership (the trait/trait-set setting granting it, or the
   entity/projection itself) when an automatic trigger (`on_roll`) carries no
   explicit `source_id`; `effects_engine` falls back to it at fire time.

Non-goals (deferred): migrating existing flat conditions off `TRAIT_RATING` /
`SOURCE_RATING` (backward-compat: they keep working); `select source` on
effect-level conditions (the applier path doesn't thread source yet).

## Concrete example (cultivation stage)

Two equivalent authorings — "non-empty" (filter) and "evaluate" (terminal):

```
TARGET_PATH
  spec:
    - select source                # the trait-setting this SFX lives on
    - filter rating >= d8          # narrow to matching rating…
    - evaluate exists              # …did it survive? (or omit evaluate → non-empty)

TARGET_PATH                        # scalar form
  spec:
    - select source
    - aggregate max rating         # collapse to a die scalar
    - evaluate >= d8               # terminal boolean comparison
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
| `EvaluateStep` (model + trace → `boolean/one`) | `services/target_spec.py` |
| `evaluate` resolution (`_evaluate_step`) | `services/target_resolver.py` |
| Automatic-trigger source resolution (`resolve_sfx_source`) | `services/sfx_owner.py`, `services/effects_engine.py` |

## Related

- [[Source-Aware Conditions]] — the source-threading this builds on.
- [[Targeting Model]] — the spec/resolver/catalog reused wholesale.
- [[Effect Output Variables]] — `select source` / bindings.
- [[to-do]] — "SFX's need a source" / cultivation-stage unlock.

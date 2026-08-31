---
title: Source-Aware Conditions
tags:
  - transversal
  - technical
  - sfx
  - effects
  - conditions
  - plan
aliases:
  - Conditions Refer to Source
  - Source Rating Condition
status: implemented
---

# Source-Aware Conditions

Let a condition evaluate against the SFX's **source** (the trait-setting that
owns/activates it), so a trait-linked SFX can gate on "the trait I'm on reached
rating X" without hardcoding a trait id. This is the conditions half of the
cultivation-stage unlock and the "conditions refer to the source" item.

## Problem

Today `evaluate_conditions` sees only the entity + a flat `target` string. A
`TRAIT_RATING` condition must hardcode a trait id; it cannot say "the source
trait's rating". That makes trait-linked SFX non-generic and forces the
cultivation-stage unlock to be five hand-hardcoded SFX.

## Two source moments

- **Availability** (grey-out, before firing): source = the trait-setting that
  owns the SFX (`TraitSetting.sfx_ids` / `Trait.default_sfx_ids`).
- **Fire-time** (trigger gate): source = the activation origin
  (`source_kind` / `source_id` in the event context).

Both already flow through the targeting system's `resolve_source`; the condition
evaluator just doesn't receive them.

## Scope (implemented)

1. ✅ **`ConditionType.SOURCE_RATING`** — a source trait-setting's rating (its
   `dice`) compared to a die threshold with an operator (`>=` default). Static
   (entity-state only), so it works for availability.
2. ✅ **Thread `source`** into `evaluate_condition` / `evaluate_conditions`, from
   both the fire-time gate (`effects_engine.process_event_outcome`) and the
   availability filter (`sfx_owner.get_available_sfx_ids`).
3. ✅ **Fix `static_conditions`** to classify by *type* (context-dependent types
   are never static) instead of token presence.
4. ✅ **Honor `operator` in `TRAIT_RATING`** (ordered-die comparison) — reusable,
   matches `SOURCE_RATING`.
5. ✅ **Expose `availableSfxIds(entityId, universe)`** GraphQL field so the sheet
   can consume availability.

## Remaining (not this pass)

- Frontend grey-out consumption (the "live SFX conditional assessment" UI half).
- "Pickable conditions limited by source" (editor filtering by `source_kind`).

## Related

- [[Effect Output Variables]] — the `select source` / `resolve_source` seam this builds on.
- [[Targeting Model]] — `source_kind` / `resolve_source` / `bind_source`.

---
title: Effects Inventory
date: 2026-08-28
tags:
  - transversal
  - technical
  - sfx
  - effects
  - targeting
  - architecture
  - plan
aliases:
  - Effect Checklist
  - Effect Migration Status
  - Effects Audit
status: working
---

# Effects Inventory

> [!note] Status
> Working tracking doc. Generated from `effects_registry.EFFECT_ACTION_REGISTRY` (43 actions). Re-run the generator after registry changes.

Checklist for the **named-references** migration (multi-target refs — see [[Passive Rules and Multi-Target References]]). One row per effect action; `status` tracks migration progress and the opportunistic audit verdict.

## Legend

- `pending` — not yet migrated to named `refs`
- `migrated` — uses `refs` (model + editor + fire-time resolution)
- `review` — migrated but behavior needs a design/fix pass
- `broken` — no-op, dead branch, or label-doesn't-match-behavior (audit finding)

## By group

### Dice Pool

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | play_as_rating | modify_roll/play_as_rating | cost | result:die_select (implicit target: {source_trait}) | — | TBD | |
| pending | step_up_die | modify_roll/step_up_die | benefit | target:text | — | TBD | |
| pending | step_down_die | modify_roll/step_down_die | cost | target:text | — | TBD | |
| pending | double_die | modify_roll/double_die | benefit | target:text | — | TBD | |
| pending | reroll_die | modify_roll/reroll_die | benefit | target:text | — | TBD | |
| pending | add_dice | modify_pool/add_dice | benefit | target:text | pool | TBD | |
| migrated | add_trait_rating_dice | modify_pool/add_trait_rating | either | refs (trait, pool) | — | trait→traitsetting, pool→pool | destination no longer implicit |
| pending | remove_die | modify_roll/remove_die | cost | target:text | — | TBD | |
| pending | split_die | modify_roll/split_die | benefit | target:text | — | TBD | |

### Outcome

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | increase_dice_limit | modify_dice_limit/increase | benefit | result:number | — | TBD | |
| pending | decrease_dice_limit | modify_dice_limit/decrease | cost | result:number | — | TBD | |
| pending | step_up_effect | modify_outcome/step_up_effect | benefit | — | — | TBD | |
| pending | step_up_outcome | modify_outcome/step_up_outcome | benefit | — | — | TBD | |
| pending | negate_complication | modify_outcome/negate_complication | benefit | — | — | TBD | |
| pending | convert_complication | modify_outcome/convert_complication | benefit | target:text | — | TBD | |
| pending | reroll_highest | modify_outcome/reroll_highest | either | — | — | TBD | |

### Trait

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | step_up_trait | modify_trait/step_up | benefit | target:text, entity:entity | trait | TBD | |
| pending | step_down_trait | modify_trait/step_down | cost | target:text, entity:entity | trait | TBD | |
| pending | set_trait | modify_trait/set | either | target:text, entity:entity, result:die_select | trait | TBD | |
| pending | disable_trait | modify_trait/disable | cost | target:text, entity:entity | trait | TBD | |
| pending | toggle_trait | modify_trait/toggle | either | target:text, entity:entity | trait | TBD | |
| pending | set_traitset_limit | modify_traitset/set_limit | either | entity:entity, target:text, result:number | traitset | TBD | |
| pending | gain_trait | modify_trait/gain | either | target:text, entity:entity, result:die_select | trait | TBD | |
| pending | gain_or_step_up_trait | modify_trait/gain_or_step_up | either | target:text, entity:entity, result:die_select | trait | TBD | |
| pending | cortex_gain_trait | modify_trait/cortex_gain | either | target:text, entity:entity, result:die_select | trait | TBD | |
| pending | reveal_trait | modify_trait/reveal | benefit | target:text, entity:entity | trait | TBD | |

### Razmerit

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | earn_razmerit | transfer_razmerit/earn | benefit | result:number, entity:entity (implicit target: self) | — | TBD | |
| pending | spend_razmerit | transfer_razmerit/spend | cost | result:number, entity:entity (implicit target: self) | — | TBD | |
| pending | transfer_razmerit | transfer_razmerit/transfer | either | result:number, target:text | — | TBD | |

### Entity

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | create_asset | create_entity/create_asset | benefit | target:text | — | TBD | |
| pending | end_active_effect | entity/cancel_scheduled_event | either | entity:entity, target:text | scheduled_event | TBD | |
| pending | create_projection | projection/create | benefit | entity:entity, target:text | — | TBD | |

### Attunement

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | attune | attune/enable | benefit | result:select, target:text | — | TBD | |

### Travel

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | travel | travel/move | benefit | entity:entity, target:text | location | TBD | |
| pending | set_location | location/set | either | entity:entity, target:text | location | TBD | |

### Life Path

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | discover_life_path | life_path/discover | benefit | target:text | life_path | TBD | |
| pending | next_step | life_path/next_step | either | target:text | roll_table | TBD | |
| pending | draft_life_path | life_path/draft | either | target:text | life_path | TBD | |
| pending | force_muster | life_path/force_muster | cost | — | — | TBD | |
| pending | muster | life_path/muster | either | — | — | TBD | |
| pending | enroll_life_path | life_path/enroll | either | — | — | TBD | |

### Relationship

| Status | Action | type/action | Cat | Fields | target_kind | Migration refs | Notes |
|---|---|---|---|---|---|---|---|
| pending | create_relationship | relationship/create | either | target:text, result:text | entity | TBD | |
| pending | entity_targeting_ban | entity/targeting_ban | cost | target:text | entity | TBD | |

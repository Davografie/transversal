---
title: SFX and Effects
tags:
  - transversal
  - game-design
  - sfx
  - effects
  - automation
  - technical
aliases:
  - SFX
  - Special Effects
  - Effects System
status: canonical
---

# SFX and Effects

> [!note] This is a technical reference
> This page describes how SFX and effects are *implemented* in the current codebase, not just the design intent. It references the actual modules, model fields, and trigger/action identifiers so it can be read alongside `src/api/src/transversal/`.

**SFX** (Special Effects) are rule exceptions attached to entities, traits, and projections. The **Effects System** is the backend automation layer that matches SFX against game events and applies structured `Effect` records to the gamestate.

## Where everything lives

| Concern | Module |
|---------|--------|
| Domain models (`SFX`, `Effect`, `EffectTiming`, `ConsequenceOption`, `SfxOwner`, `Attunement`, `TargetingBan`, `Condition`) | `src/api/src/transversal/domain/__init__.py` |
| Effect action registry (what actions exist, their fields, category, valid timings) | `src/api/src/transversal/services/effects_registry.py` |
| Effects engine (trigger matching, scheduling, event → applied/pending effects) | `src/api/src/transversal/services/effects_engine.py` |
| Effect applier (dispatch + mutation handlers, `{choose_*}` target resolution) | `src/api/src/transversal/services/effects_applier.py` |
| SFX ownership resolution + seeding of table/contest SFX | `src/api/src/transversal/services/sfx_owner.py` |
| State-change event wiring (takeout, contest win/loss, give-in, push) | `src/api/src/transversal/services/state_events.py` |
| Consequence menu assembly (base + entity + SFX moves) | `src/api/src/transversal/services/consequence_menu.py` |
| Contest lifecycle endpoints (challenge, set, give-in, push, prevent-taken-out) | `src/api/src/transversal/api/rest/contest_pools.py` |
| Targeting bans + takeout clearing on scene advance | `src/api/src/transversal/services/targeting_bans.py` |

## Domain model

All definitions are in `src/api/src/transversal/domain/__init__.py`.

### `EffectTiming` (line 618)

```python
class EffectTiming(str, Enum):
    IMMEDIATE       = "immediate"
    END_OF_BEAT     = "end_of_beat"
    END_OF_SCENE    = "end_of_scene"
    END_OF_SESSION  = "end_of_session"
    AFTER_BEATS     = "after_beats"
    ON_CONDITION    = "on_condition"
```

### `Effect` (line 646)

One canonical, operational effect record shared by SFX and life-path consequences.

| Field | Type | Meaning |
|-------|------|---------|
| `timing` | `EffectTiming` | When the effect fires (default `IMMEDIATE`) |
| `type` | `str` | Effect family: `modify_roll`, `modify_outcome`, `modify_trait`, `transfer_razmerit`, `create_entity`, `attune`, `travel`, `life_path`, `relationship`, `entity` |
| `action` | `str` | Operation within the family (see registry below) |
| `target` | `str` | Literal id, `"self"`, or a `{choose_*}` / `{random:*}` placeholder |
| `result` | `Optional[str]` | Die rating, integer amount, relationship type, or `{context_key}` placeholder |
| `target_scope` | `Optional[str]` | Narrowing hint for runtime target choice (e.g. `traitset:ts-complications-a190`) |
| `context` | `dict` | Extra data (e.g. relationship description) |

There is **no `polarity` field** — cost vs. benefit is derived from the `(type, action)` pair via the registry's `category`.

### `SFX` (line 673)

```python
class SFX(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger: str
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
```

- `trigger` names the event (see trigger semantics below).
- `conditions` gate which instance of that event applies.
- A legacy `limit` string is folded into a `NARRATIVE` condition by the `@model_validator` `_fold_legacy_limit`.

### `SfxOwner` (line 709)

Ownership lives on the *owner* side, not the SFX. An owner bucket is a named set of SFX ids:

```python
class SfxOwner(BaseModel):
    id: str            # "table" | "gm" | "players"
    sfx_ids: list[str]
```

### `ConsequenceOption` (line 660)

A selectable post-roll consequence entry. Authored directly on entities (location/lair moves), registered as base moves, or derived from `on_consequence` SFX.

| Field | Meaning |
|-------|---------|
| `id` | Stable option id; SFX moves use `sfx:{sfx_id}` |
| `label` | Display text |
| `side` | `"player"` \| `"gm"` \| `"either"` |
| `effects` | `list[Effect]` applied when chosen |
| `source` | `"base"` \| `"entity"` \| `"sfx"` |

### Entity state touched by effects (`Entity`, line 525)

- `razmerit` — spend/earn/transfer balance.
- `current_universe`, `current_location`, `current_projection`.
- `attunements: list[Attunement]` — active temporary universe grants (effect-managed).
- `targeting_bans: list[TargetingBan]` — directional, scene-counted contest-target bans (`TargetingBan`, line 517).
- `taken_out: bool = False` — scene-scoped; a high-stakes contest removed this entity from the scene.
- `sfx_ids: list[str]` — SFX owned directly by this entity.
- `consequence_options: list[ConsequenceOption]` — location/lair moves.

### `Attunement` (line 633) and `AttunementScope` (line 627)

```python
class AttunementScope(str, Enum):
    SELF   = "self"     # only the entity carrying the attunement
    DOMAIN = "domain"   # occupants in the entity's location subtree

class Attunement(BaseModel):
    universe: str
    scope: AttunementScope = AttunementScope.SELF
    until: Optional[EffectTiming] = None
    source_sfx_id: Optional[str] = None
```

### `Condition` (line 734) and `ConditionType` (line 723)

Conditions are authored alongside effects and evaluated against entity state (`at_location`, `has_trait`, `has_trait_in_traitset`, `has_relationship`, `trait_rating`, `narrative`). `NARRATIVE` is human-readable only and never auto-blocks. See `src/api/src/transversal/services/conditions.py`.

## Effect action registry

`src/api/src/transversal/services/effects_registry.py` is the single source of truth for every action the editor can author (`EFFECT_ACTION_REGISTRY`, line 52). Each entry is an `EffectActionMeta` with `action_id`, `category` (`cost` | `benefit` | `either`), `effect_type`, `effect_action`, `valid_timings`, field definitions, and `target_kind`.

| Family (`effect_type`) | `action_id` → `effect_action` | Category |
|------------------------|-------------------------------|----------|
| `modify_roll` | `play_as_rating` → `play_as_rating` | cost |
| | `step_up_die` → `step_up_die` | benefit |
| | `step_down_die` → `step_down_die` | cost |
| | `double_die` → `double_die` | benefit |
| | `reroll_die` → `reroll_die` | benefit |
| | `add_die` → `add_die` | benefit |
| | `remove_die` → `remove_die` | cost |
| | `split_die` → `split_die` | benefit |
| `modify_outcome` | `step_up_effect` → `step_up_effect` | benefit |
| | `step_up_outcome` → `step_up_outcome` | benefit |
| | `negate_complication` → `negate_complication` | benefit |
| | `convert_complication` → `convert_complication` | benefit |
| | `reroll_highest` → `reroll_highest` | either |
| `modify_trait` | `step_up_trait` → `step_up` | benefit |
| | `step_down_trait` → `step_down` | cost |
| | `set_trait` → `set` | either |
| | `gain_trait` → `gain` | benefit |
| | `gain_or_step_up_trait` → `gain_or_step_up` | benefit |
| | `gain_complication` → `gain_complication` | cost |
| | `gain_or_step_up_complication` → `gain_or_step_up_complication` | cost |
| `transfer_razmerit` | `earn_razmerit` → `earn` | benefit |
| | `spend_razmerit` → `spend` | cost |
| | `transfer_razmerit` → `transfer` | either |
| `create_entity` | `create_asset` → `create_asset` | benefit |
| `attune` | `attune` → `enable` | benefit |
| `travel` | `travel` → `move` | benefit |
| `life_path` | `discover_life_path` → `discover` | benefit |
| | `next_step` → `next_step` | either |
| | `draft_life_path` → `draft` | either |
| | `force_muster` → `force_muster` | cost |
| | `muster` → `muster` | either |
| | `enroll_life_path` → `enroll` | either |
| `relationship` | `create_relationship` → `create` | either |
| `entity` | `entity_targeting_ban` → `targeting_ban` | cost |

## Effects engine

`src/api/src/transversal/services/effects_engine.py`.

### Event and outcome types

- `GameEvent` (line 33): `type`, `entity_id`, `universe`, `context`, plus optional `dice_request` / `roll_result`.
- `EventOutcome`: splits results into `applied` (immediate effects that were executed) and `pending` (`PendingSfxEffect` — immediate effects with a `{choose_*}` target that were skipped and need user resolution).

### Processing (`EffectsEngine.process_event_outcome`, line 127)

For each available SFX id:

1. Look up the SFX in the registry.
2. `_trigger_matches` (line 219) checks the trigger.
3. If `conditions` exist and a repo is provided, `evaluate_conditions` gates on current entity state.
4. A razmerit cost check sums `transfer_razmerit`/`spend` effect results and skips the SFX if it exceeds the balance.
5. `_substitute_effect_context` replaces `{context_key}` placeholders in each effect's `result` from the event context (this is how `{effect_die}` becomes a concrete die rating).
6. `IMMEDIATE` effects with a `{choose_*}` target are returned as `pending`; otherwise they are applied via `effects_applier.effect_registry.apply`. Non-`IMMEDIATE` effects are queued on the internal schedule.

`attune`/`enable` is special-cased: it applies immediately and also schedules a matching `attune`/`disable` at the effect's timing.

### Scheduling

| Method | Fires |
|--------|-------|
| `tick_beat` (line 310) | `END_OF_BEAT` effects; decrements `AFTER_BEATS` counters and fires them at zero |
| `tick_scene` (line 334) | `END_OF_SCENE` effects |
| `tick_session` (line 350) | everything remaining on the schedule |

`AFTER_BEATS` defaults to 3 beats (`_beats_for_timing`).

### Trigger semantics (`_trigger_matches`, line 219)

| SFX `trigger` | Fires when |
|---------------|------------|
| `== event.type` | Direct match on the event name |
| `on_activate` | Legacy alias for event type `manual` |
| `on_complication` | `on_roll` / `on_result` whose `roll_result.hitches` is non-empty |
| `on_botch` | `roll_result.botch` is true |
| `on_location_change` | event type `location_changed` |
| `on_trait_change` | event type `trait_updated` |
| `on_relationship_create` | event type `relationship_created` |
| `on_contest_loss` | `event.context["contest_winner"] == "opponent"` |
| `on_contest_win` | `event.context["contest_winner"] == "player"` |
| `on_success` | `roll_result.tier` is present and not `FAIL` |
| `on_failure` | `roll_result.tier == FAIL` |

`contest_to_events` (line 390) and `fire_contest_sfx` (line 437) generate per-side events from a `ContestResult`, with `contest_winner` set from each side's perspective (ties favor the initiator — there is no separate tie outcome).

## Effect applier

`src/api/src/transversal/services/effects_applier.py`.

- `EffectRegistry` (line 23) dispatches by `(type, action)`, falling back to `(*, action)` → `(type, *)` → `(*, *)`.
- Core mutation handlers are registered at import time (lines 71–166). `modify_roll` and `modify_outcome` are registered as `("*", ...)` pass-throughs (roll/outcome math happens in the resolver, not here).
- `apply_effects` (line 569) mutates the entity in place for entity-level fields (razmerit, discovered paths, rank) and collects `TraitSetting` changes, relationship edges, cross-entity mutations, pending choices, and passthrough effects into an `EffectsResult`. **Persistence and SSE broadcast are the caller's responsibility.**

### Target placeholders

- `_parse_placeholder` (line 304) parses `{mode:kind}` and `{mode_kind}` targets. Recognised modes are `choose` and `random`; recognised kinds are `location`, `occupant`, `trait`, `entity`, `rating_die`, `life_path`, `roll_table`.
- `is_choose_target` (line 324) and `choose_kind` (line 330) are what the engine uses to decide whether an effect needs user resolution.
- `_resolve_target` (line 348): `"self"` → the entity's id; `{choose_*}` / empty-when-required → a `PendingChoice`; `{random:*}` → a random in-scope candidate via `effect_targets.resolve_candidates`; anything else → a literal target id.
- `resolve_choice` (line 377) re-applies a `PendingChoice` with a concrete target.

### `target_scope`

A `target_scope` like `traitset:ts-complications-a190` narrows the candidate set the picker/random resolver presents (see `effect_targets.resolve_candidates`). This is how the contest complication SFX restrict the "pick a complication" choice to the complications trait set.

### Complication trait set id

The complications trait set is **`ts-complications-a190`**. The negative-trait fallback in `_new_traitsetting` (line 268) and the contest complication SFX both use it. See [[#Known mismatch]] below for the one place that still references the old id.

## SFX ownership and seeding

`src/api/src/transversal/services/sfx_owner.py`.

### Owner buckets

`ensure_sfx_owners` (line 22) seeds three owner buckets: `table` (everyone), `gm` (GM-context only, not entity-derived), `players` (reserved, currently empty). The `gm` bucket is intentionally excluded from entity-derived resolution.

### Available SFX resolution (`get_available_sfx_ids`, line 181)

The SFX ids available to an entity in a universe are the sorted union of:

1. `Entity.sfx_ids` (direct ownership).
2. The active projection's `Projection.sfx_ids` (`entity.current_projection`).
3. The `table` owner bucket.
4. Trait-level grants from effective `TraitSetting.sfx_ids` plus the trait's `Trait.default_sfx_ids`.
5. Trait-set-as-unit grants from effective `TraitSetSetting.sfx_ids`.

### Seeded table/contest SFX

| SFX id | Trigger | Effect(s) | Purpose |
|--------|---------|-----------|---------|
| `sfx-give-in-get-razmerit` | `on_give_in` | `transfer_razmerit`/`earn`/`self`/`1` | Conceder gains 1 razmerit |
| `sfx-give-in-targeting-ban` | `on_give_in` | `entity`/`targeting_ban`/`""`/`1` | Conceder can't target that opponent for the scene |
| `apply-complication` | `on_consequence` | `modify_trait`/`gain_complication`/`{choose_trait}` @ `{effect_die}`, scope `traitset:ts-complications-a190` | Winner applies a complication to the opponent |
| `take-complication` | `on_consequence` | same effect as `apply-complication` | Conceder takes a complication on their own projection |
| `prevent-taken-out` | `on_prevent_taken_out` | `transfer_razmerit`/`spend`/`self`/`1` | Spend 1 razmerit to avoid being taken out |

`ensure_contest_complication_sfx` (line 98) intentionally creates **two** SFX (`apply-complication`, `take-complication`) with identical effects but different labels, so the frontend can surface the correct one at each end of a contest. Both are `on_consequence` and owned by `table` (players + GM).

`remove_legacy_contest_complication_sfx` (line 164) deletes the retired `sfx-contest-loss-complication` row and its `table` reference so a stale DB doesn't keep auto-firing it on `on_contest_loss` (P2.10d moved contest-loss complications into the manual consequence menu).

## State events and takeout

`src/api/src/transversal/services/state_events.py` centralises automatic SFX firing for state changes (entity moves, trait gains, relationship creation, contest outcomes) that don't happen in the roll/contest endpoint layer.

### `fire_state_sfx` (line 16)

Fires matching condition-gated SFX for a single state event. A re-entrancy guard (`_firing` set of `(entity_id, event_type)`) prevents an SFX-triggered mutation from re-entering the same event. Pending `{choose_*}` effects are emitted via `roll_orchestrator._emit_pending_choices`.

### Contest outcome (`fire_contest_outcome_sfx`, line 54)

Fires `on_contest_win` / `on_contest_loss` for both sides of a resolved manual contest. The event context carries `contest_winner`, `opponent_id`, `effect_die`, `high_stakes`, and `taken_out`; `{effect_die}` in an SFX result is substituted from this context. If `taken_out` is true, `_mark_taken_out` is called for the loser.

### Takeout (`_mark_taken_out`, line 103)

Sets `loser.taken_out = True`, persists it, and fires `on_taken_out` with `{taken_out: True, opponent_id}`.

### Prevent takeout (`prevent_taken_out`, line 116)

Server-enforced:

1. Returns `{"prevented": False, "reason": "insufficient razmerit"}` if `razmerit < 1`.
2. Returns `{"prevented": False, "reason": "not taken out"}` if not `taken_out`.
3. Otherwise fires `on_prevent_taken_out` with `{prevented: True, effect_die}` (the seeded `prevent-taken-out` SFX spends 1 razmerit).
4. Re-fetches the entity, clears `taken_out`, and returns `{"prevented": True}`.

> [!note] The complication on prevent is **not** applied by the prevent SFX itself
> `prevent-taken-out` only spends the razmerit. The winner applies the complication at the effect die through the consequence menu (`apply-complication`).

### Endpoints (`src/api/src/transversal/api/rest/contest_pools.py`)

| Path | Behavior |
|------|----------|
| `POST /locations/{location_id}/pools/{entity_id}/set-opposition` | Challenge; blocked by `has_targeting_ban` |
| `POST .../set` | Commit one side's result; on final resolution fires `fire_contest_outcome_sfx` |
| `POST .../stakes` | Toggle high stakes |
| `POST .../give-in` | Concede; fires `on_give_in` (razmerit + ban SFX) |
| `POST .../push` | Start a push; fires `on_push` |
| `POST .../prevent-taken-out` | `PreventTakenOutRequest { effect_die }` → `prevent_taken_out`, broadcasts `contest_prevent_taken_out` |
| `GET .../contest` | Re-sync perspective (challenger/defendant, committed results, high stakes) |

### Scene-advance clearing (`src/api/src/transversal/services/targeting_bans.py`)

- `decrement_scene_bans` (line 42) advances every entity's `targeting_bans` by one scene, removing expired bans.
- `clear_taken_out` (line 68) clears `taken_out` from every entity.

Both are wired into scene advance (see `src/api/src/transversal/api/rest/targeting_bans.py`), so a scene boundary expires challenge bans and re-admits taken-out entities.

## Consequence menu

`src/api/src/transversal/services/consequence_menu.py`.

`assemble_consequence_menu` (line 90) builds the post-roll consequence options from three sources:

1. **Base moves** (`BASE_CONSEQUENCE_OPTIONS`) — always available, keyed by `"player"` / `"gm"`.
2. **Entity moves** — `Entity.consequence_options` on the acting entity's current location and its ancestors (lair moves), filtered by `side`.
3. **SFX moves** — `on_consequence` SFX available to the acting entity, wrapped as `ConsequenceOption(id="sfx:{sfx_id}", source="sfx")`.

Choosing an option applies its effects through the shared applier, resolving any `{choose_*}` targets via the wizard.

### Known mismatch

The base doom-pool options (`decrease_doom`, `increase_doom` in `consequence_menu.py` lines 53 and 67) still declare `target_scope="traitset:ts-complications"`, while the correct complications trait set id is **`ts-complications-a190`** (used by `sfx_owner._complication_effect` and the `effects_applier` negative-trait fallback). The precise doom-pool scoping is deferred to Phase 3's challenge-pool work; the contest complication SFX already use the correct id.

## Design principle

> [!quote] Declarative over procedural
> SFX and consequences are authored declaratively as `Effect` records. The engine interprets the declaration against the current event and gamestate. This separation means new SFX can be added without changing core code, effect chains can be reasoned about, and `{choose_*}` targets surface as user-resolvable choices instead of being hardcoded.

## Next

- [[Core Mechanics]] — The fundamentals these exceptions modify
- [[Dice Mechanics]] — Where SFX intercept the rolling procedure
- [[Character Growth]] — Life paths execute the same `Effect` records

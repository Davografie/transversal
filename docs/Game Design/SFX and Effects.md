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
| Domain models (`SFX`, `Effect`, `EffectTiming`, `EffectDuration`, `Timer`, `TimerCombine`, `ScheduledEvent`, `ConsequenceOption`, `SfxOwner`, `Attunement`, `TargetingBan`, `Condition`) | `src/api/src/transversal/domain/__init__.py` |
| Effect action registry (what actions exist, their fields, category, valid timings, inverse, supports-duration) | `src/api/src/transversal/services/effects_registry.py` |
| Effects engine (trigger matching, scheduling, event → applied/pending effects) | `src/api/src/transversal/services/effects_engine.py` |
| Effect applier (dispatch + mutation handlers, `{choose_*}` target resolution) | `src/api/src/transversal/services/effects_applier.py` |
| Target-candidate resolution (scope resolvers, `resolve_candidates`, `FILTER_FIELDS`) | `src/api/src/transversal/services/effect_targets.py` |
| Condition evaluation + condition-type vocabulary (`CONDITION_TYPES`) | `src/api/src/transversal/services/conditions.py` |
| Scheduled events / duration (timers, combine, central `dispatch_event`, `advance_events`) | `src/api/src/transversal/services/scheduled_events.py` |
| SFX ownership resolution + seeding of table/contest SFX | `src/api/src/transversal/services/sfx_owner.py` |
| State-change event wiring (takeout, contest win/loss, give-in, push) | `src/api/src/transversal/services/state_events.py` |
| Consequence menu assembly (base + entity + SFX moves) | `src/api/src/transversal/services/consequence_menu.py` |
| Menu-context / trigger / filter-field vocabularies (`TRIGGERS`, `MENU_CONTEXT_VARIABLES`) | `src/api/src/transversal/services/menu_contexts.py` |
| Contest lifecycle endpoints (challenge, set, give-in, push, prevent-taken-out) | `src/api/src/transversal/api/rest/contest_pools.py` |
| Targeting bans (membership) + takeout clearing | `src/api/src/transversal/services/targeting_bans.py` |

## Domain model

All definitions are in `src/api/src/transversal/domain/__init__.py`.

### `EffectTiming` (line 621)

```python
class EffectTiming(str, Enum):
    IMMEDIATE       = "immediate"
    END_OF_BEAT     = "end_of_beat"
    END_OF_SCENE    = "end_of_scene"
    END_OF_SESSION  = "end_of_session"
    AFTER_BEATS     = "after_beats"
    ON_CONDITION    = "on_condition"
```

### `Effect` (line 649)

One canonical, operational effect record shared by SFX and life-path consequences.

| Field | Type | Meaning |
|-------|------|---------|
| `timing` | `EffectTiming` | When the effect fires (default `IMMEDIATE`) |
| `type` | `str` | Effect family: `modify_roll`, `modify_outcome`, `modify_trait`, `transfer_razmerit`, `create_entity`, `attune`, `travel`, `location`, `life_path`, `relationship`, `entity` |
| `action` | `str` | Operation within the family (see registry below) |
| `target` | `str` | Literal id, `"self"`, or a `{choose_*}` / `{random:*}` placeholder |
| `entity` | `str` | Explicit subject entity; `""` or `"self"` = the entity the effect is applied to |
| `result` | `Optional[str]` | Die rating, integer amount, relationship type, or `{context_key}` placeholder |
| `target_scope` | `Optional[str]` | Narrowing hint for runtime target choice (e.g. `traitset:ts-complications-a190`) |
| `entity_scope` | `Optional[str]` | Narrowing hint for runtime entity choice |
| `target_filter` | `dict` | Candidate field predicates for the target (e.g. `{"starter_location": true}`), AND-ed and applied across every scope |
| `negative` | `bool` | Trait-grant effects only: bake the created trait as `polarity=NEGATIVE` (complication) |
| `context` | `dict` | Extra data (e.g. relationship description, `transversal_type`, faction `relationship`, `learner`, `steps`) |
| `duration` | `Optional[EffectDuration]` | When set, the inverse effect is scheduled to fire on expiry (see below) |

Cost vs. benefit (sign) is still derived from the `(type, action)` pair via the registry's `category`; `negative` is the *polarity* flag that marks a trait as a complication, separate from sign.

### `Timer`, `TimerCombine`, `EffectDuration`, `ScheduledEvent` (lines 664–695)

These implement the **duration** model: an effect can be temporary, and its inverse
fires later.

```python
class Timer(BaseModel):
    event: str = "scene"      # "beat" | "scene" | "session" | "location_changed" | "trait_updated" | …
    remaining: int = 0        # countdown; 0 fires on the next advance pass

class TimerCombine(str, Enum):
    FIRST_TO_FIRE = "first_to_fire"   # expire when ANY timer reaches 0
    ALL_TRANSPIRED = "all_transpired" # expire when ALL timers reach 0

class EffectDuration(BaseModel):
    timers: list[Timer]
    combine: TimerCombine = TimerCombine.FIRST_TO_FIRE

class ScheduledEvent(BaseModel):
    id: str
    effect: Effect        # the REVERT effect to fire on expiry
    timers: list[Timer]
    combine: TimerCombine
    source_sfx_id: Optional[str] = None
```

The owner holds the scheduled events: `Entity.scheduled_events` (line 527) and
`TraitSetting.scheduled_events` (line 424). The forward effect is applied
immediately (mutating the owner's concrete state); only the *revert* is
scheduled. See [[#Duration / scheduled events]] below.

### `SFX` (line 710)

```python
class SFX(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger: str
    menu_context: Optional[str] = None
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
```

- `trigger` names the auto-fire event (see trigger semantics below).
- `menu_context` names the consequence menu this SFX appears in (`test_success`, `simplified_roll`, `contest_win`, `contest_give_in`); `None` = not a menu option. Distinct from `trigger`.
- `conditions` gate which instance of that event applies.
- A legacy `limit` string is folded into a `NARRATIVE` condition by the `@model_validator` `_fold_legacy_limit`.

### `SfxOwner` (line 746)

Ownership lives on the *owner* side, not the SFX. An owner bucket is a named set of SFX ids:

```python
class SfxOwner(BaseModel):
    id: str            # "table" | "gm" | "players"
    sfx_ids: list[str]
```

### `ConsequenceOption` (line 660)

A selectable post-roll consequence entry. Authored directly on entities (location/lair moves), registered as base moves, or derived from `menu_context` SFX.

| Field | Meaning |
|-------|---------|
| `id` | Stable option id; SFX moves use `sfx:{sfx_id}` |
| `label` | Display text |
| `side` | `"player"` \| `"gm"` \| `"either"` |
| `effects` | `list[Effect]` applied when chosen |
| `source` | `"base"` \| `"entity"` \| `"sfx"` |

### Entity state touched by effects (`Entity`, line 527)

- `razmerit` — spend/earn/transfer balance.
- `current_universe`, `current_location`, `current_projection`.
- `attunements: list[Attunement]` — active temporary universe grants (effect-managed).
- `targeting_bans: list[TargetingBan]` — directional bans, membership only; expiry via scheduled events (`TargetingBan`, line 518).
- `taken_out: bool = False` — scene-scoped; a high-stakes contest removed this entity from the scene.
- `scheduled_events: list[ScheduledEvent]` — pending timed reverts.
- `sfx_ids: list[str]` — SFX owned directly by this entity.
- `consequence_options: list[ConsequenceOption]` — location/lair moves.

### `Attunement` (line 636) and `AttunementScope` (line 630)

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

### `Condition` and `ConditionType`

Conditions are authored alongside effects and evaluated against entity state (`at_location`, `has_trait`, `has_trait_in_traitset`, `has_relationship`, `trait_rating`, `unplaced`, `in_universe`, `narrative`). `NARRATIVE` is human-readable only and never auto-blocks; `UNPLACED` is true when the entity has no current location; `IN_UNIVERSE` compares `current_universe` to the condition's `target`. The editor's condition-type list is served from `CONDITION_TYPES` in `src/api/src/transversal/services/conditions.py` (value + label + needs-target + placeholder).

## Effect action registry

`src/api/src/transversal/services/effects_registry.py` is the single source of truth for every action the editor can author (`EFFECT_ACTION_REGISTRY`, line 52). Each entry is an `EffectActionMeta` with `action_id`, `category` (`cost` | `benefit` | `either`), `effect_type`, `effect_action`, `valid_timings`, `fields`, `context_fields`, `target_kind`, `supports_duration`, `supports_polarity`, and an optional `inverse` + `inverse_captures_prior` (used by the scheduler to undo a temporary effect).

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
| | `gain_trait` → `gain` | either (polarity) |
| | `gain_or_step_up_trait` → `gain_or_step_up` | either (polarity) |
| | `cortex_gain_trait` → `cortex_gain` | either (polarity) |
| `transfer_razmerit` | `earn_razmerit` → `earn` | benefit |
| | `spend_razmerit` → `spend` | cost |
| | `transfer_razmerit` → `transfer` | either |
| `create_entity` | `create_asset` → `create_asset` | benefit |
| `attune` | `attune` → `enable` | benefit |
| `travel` | `travel` → `move` | benefit |
| `location` | `set_location` → `set` | either |
| `life_path` | `discover_life_path` → `discover` | benefit |
| | `next_step` → `next_step` | either |
| | `draft_life_path` → `draft` | either |
| | `force_muster` → `force_muster` | cost |
| | `muster` → `muster` | either |
| | `enroll_life_path` → `enroll` | either |
| `relationship` | `create_relationship` → `create` | either |
| `entity` | `entity_targeting_ban` → `targeting_ban` | cost |

`gain_trait` / `gain_or_step_up_trait` / `cortex_gain_trait` all declare `supports_polarity`, so the editor shows a "Negative (complication)" toggle that sets `Effect.negative`. `cortex_gain` is the Cortex create-or-step-up rule: create at the effect die if absent; if present, jump to the effect die when higher, else step up one step.

### Internal inverse actions (not editor-authored)

These are registered directly on the effect registry (`effects_applier._register_core_handlers`) and are used by the scheduler to revert temporary effects:

- `modify_trait` / `remove` — delete a trait setting (inverse of `gain`).
- `entity` / `remove_targeting_ban` — inverse of `targeting_ban`.
- `entity` / `clear_taken_out` — inverse of the `taken_out` status.
- `entity` / `delete_entity` — inverse of `create_asset`.
- `attune` / `disable` — inverse of `attune` / `enable`.

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
6. `IMMEDIATE` effects with a `{choose_*}` target are returned as `pending`; otherwise they are applied via `effects_applier.effect_registry.apply`. Non-`IMMEDIATE` effects are persisted as `ScheduledEvent`s on the entity when a repo is available (see [[#Duration / scheduled events]]); an in-memory schedule remains only as a fallback for the no-repo, life-path, and `ON_CONDITION` cases.

`attune`/`enable` no longer special-cases the schedule: the `_attune` handler applies the enable now and `schedule_revert` schedules the `disable` via the same duration model.

### Scheduling

The in-memory `ScheduledEffect` schedule backs `tick_beat`/`tick_scene`/`tick_session` for deferred life-path and `ON_CONDITION` effects. Ordinary timed reverts are persisted and driven by `scheduled_events.dispatch_event` (see [[#Duration / scheduled events]]).

| Method | Fires |
|--------|-------|
| `tick_beat` (line 296) | in-memory `END_OF_BEAT` / `AFTER_BEATS` effects |
| `tick_scene` (line 320) | in-memory `END_OF_SCENE` effects |
| `tick_session` (line 336) | everything remaining on the in-memory schedule |

`AFTER_BEATS` defaults to 3 beats (`_beats_for_timing`).

### Trigger semantics (`_trigger_matches`, line 205)

| SFX `trigger` | Fires when |
|---------------|------------|
| `== event.type` | Direct match on the event name |
| `on_activate` | Legacy alias for event type `manual` |
| `on_complication` | `on_roll` / `on_result` whose `roll_result.hitches` is non-empty |
| `on_botch` | `roll_result.botch` is true |
| `on_location_change` | event type `location_changed` |
| `on_trait_change` | event type `trait_updated` |
| `on_relationship_create` | event type `relationship_created` |
| `on_character_create` | event type `character_created` |
| `on_contest_loss` | `event.context["contest_winner"] == "opponent"` |
| `on_contest_win` | `event.context["contest_winner"] == "player"` |
| `on_success` | `roll_result.tier` is present and not `FAIL` |
| `on_failure` | `roll_result.tier == FAIL` |
| `on_give_in` | event type `on_give_in` |
| `on_push` | event type `on_push` |
| `on_taken_out` | event type `on_taken_out` |
| `on_prevent_taken_out` | event type `on_prevent_taken_out` |
| `on_trait_learn` | event type `trait_learned` |
| `on_trait_offered` | event type `trait_offered` |

`contest_to_events` (line 376) generates per-side events from a `ContestResult`, with `contest_winner` set from each side's perspective (ties favor the initiator — there is no separate tie outcome). The legacy `fire_contest_sfx` no-repo helper was removed; contest outcomes fire through `fire_contest_outcome_sfx` (see [[#State events and takeout]]).

## Effect applier

`src/api/src/transversal/services/effects_applier.py`.

- `EffectRegistry` (line 23) dispatches by `(type, action)`, falling back to `(*, action)` → `(type, *)` → `(*, *)`.
- Core mutation handlers are registered at import time (lines 71–166). `modify_roll` and `modify_outcome` are registered as `("*", ...)` pass-throughs (roll/outcome math happens in the resolver, not here).
- `apply_effects` (line 569) mutates the entity in place for entity-level fields (razmerit, discovered paths, rank) and collects `TraitSetting` changes, relationship edges, cross-entity mutations, pending choices, and passthrough effects into an `EffectsResult`. **Persistence and SSE broadcast are the caller's responsibility.**

### Target placeholders

- `_parse_placeholder` parses `{mode:kind}` and `{mode_kind}` targets. Recognised modes are `choose` and `random`; recognised kinds are `location`, `occupant`, `trait`, `entity`, `rating_die`, `life_path`, `roll_table`, `universe`, `projection` (the `_TARGET_KINDS` map).
- `is_choose_target` / `choose_kind` decide whether an effect needs user resolution.
- `_resolve_target`: `"self"` → the entity's id; `{choose_*}` / empty-when-required → a `PendingChoice`; `{random:*}` → a random in-scope candidate via `effect_targets.resolve_candidates`; anything else → a literal target id.
- `resolve_choice` re-applies a `PendingChoice` with a concrete target.
- **Candidate filters**: `Effect.target_filter` (e.g. `{"starter_location": true}`) further narrows `choose`/`random` candidates — `_random_candidate`/`_resolve_target` pass it into `resolve_candidates`, which ANDs the field predicates across every scope resolver. This replaces the retired `starter_location` target kind.

### `target_scope` and `target_filter`

A `target_scope` like `traitset:ts-complications-a190` or `universe:earth` narrows the candidate set the picker/random resolver presents (see `effect_targets.resolve_candidates`). Scope grammar is `prefix:value` — prefixes `universe`, `location`, `subtree`, `faction`, `traitset`; a bare value defaults to universe (or current location for occupants); empty means current context. `target_filter` (e.g. `{"starter_location": true}`) adds candidate field predicates that compose with any scope. The GraphQL `targetCandidates` query resolves both for the runtime picker and the editor's live preview (`entityId` is optional; when omitted the resolver uses a synthetic universe context derived from `scope`).

### Complication trait set id

The complications trait set is **`ts-complications-a190`**. The negative-trait fallback in `_new_traitsetting` (line 268) and the contest complication SFX both use it. See [[#Known mismatch]] below for the one place that still references the old id.

## Duration / scheduled events

`src/api/src/transversal/services/scheduled_events.py`.

A temporary effect is modeled as **apply now + schedule a revert**:

1. The forward effect mutates the owner's concrete state immediately (a trait's `dice`, an entity's `targeting_bans` / `taken_out` / `attunements`, a created asset).
2. `schedule_revert` / `schedule_traitsetting_revert` / `queue_revert` / `queue_event` append a `ScheduledEvent` holding the inverse effect and its `timers`.
3. `dispatch_event(repo, event_type, entity_id, …)` advances timers on the boundary and applies the stored revert when they expire.

### Advancement (central point)

- **Global boundaries** (`beat` / `scene` / `session`, no entity): `dispatch_event` advances every entity + trait setting's scheduled events.
- **Entity-scoped events** (`location_changed`, `trait_updated`, `relationship_created`): advance that entity + its trait settings, then fire state SFX.
- `next_beat` → `dispatch_event(repo, "beat")`; `advance_scene` → `dispatch_event(repo, "scene")`; `entity_manager._publish_location_changed` and `effects_commit` publish through `dispatch_event`.

### Inverse mappings (registry)

`EffectActionMeta.inverse` + `inverse_captures_prior` declare the undo for reversible actions. `scheduled_events.build_revert(effect, prior_result=…)` builds the inverse effect, substituting `prior_result` for `inverse_captures_prior` actions (e.g. `set` reverts to the pre-apply die rating).

| Forward | Inverse |
|---------|---------|
| `modify_trait` / `step_up` | `step_down` |
| `modify_trait` / `step_down` | `step_up` |
| `modify_trait` / `set` | `set` (prior value captured) |
| `modify_trait` / `gain` | `remove` |
| `modify_trait` / `gain_or_step_up` | `step_down` (if stepped) or `remove` (if created) |
| `entity` / `targeting_ban` | `remove_targeting_ban` |
| `taken_out` (status) | `clear_taken_out` |
| `create_entity` / `create_asset` | `delete_entity` |
| `attune` / `enable` | `disable` |

`gain_or_step_up` is compound — it queues the explicit branch-specific revert (`_queue_explicit`) rather than a single registry inverse.

### Deferred SFX effects

Non-`IMMEDIATE` effects from the effects engine are persisted as scheduled events when a repo is available (`scheduled_events.schedule_deferred` → `timing_to_timer` maps `END_OF_BEAT` / `END_OF_SCENE` / `END_OF_SESSION` / `AFTER_BEATS` to a timer). The in-memory `ScheduledEffect` schedule remains only for life-path deferrals and `ON_CONDITION`.

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
| `apply-complication` | `manual` → menu `contest_win` | `modify_trait`/`cortex_gain`/`{choose_trait}` @ `{effect_die}` (negative), scope `traitset:ts-complications-a190` | Winner applies a complication to the opponent |
| `take-complication` | `manual` → menu `contest_give_in` | same effect as `apply-complication` | Conceder takes a complication on their own projection |
| `prevent-taken-out` | `on_prevent_taken_out` | `transfer_razmerit`/`spend`/`self`/`1` | Spend 1 razmerit to avoid being taken out |
| `sfx-starter-location` | `on_character_create` | `location`/`set`/`{random:location}` @ scope `universe:earth`, filter `{starter_location: true}`; conditions `UNPLACED` + `IN_UNIVERSE(earth)` | New unplaced Earth characters arrive at a random starter location |

`ensure_contest_complication_sfx` creates/migrates **two** SFX (`apply-complication`, `take-complication`) with identical `cortex_gain` + negative effects but different `menu_context` (`contest_win` vs `contest_give_in`), so the frontend surfaces the right one at each end of a contest. The migration also rewrites stale `gain_complication` effects in place.

`remove_legacy_contest_complication_sfx` (line 164) deletes the retired `sfx-contest-loss-complication` row and its `table` reference so a stale DB doesn't keep auto-firing it on `on_contest_loss` (P2.10d moved contest-loss complications into the manual consequence menu).

### Editor vocabularies (backend-served)

The SFX editor renders three vocabularies from GraphQL rather than hardcoding them: `triggers` (from `TRIGGERS` in `menu_contexts.py` — value + label + variables), `conditionTypes` (from `CONDITION_TYPES` in `conditions.py`), and `targetFilterFields` (from `FILTER_FIELDS` in `effect_targets.py` — field + label + valueType + applicable kinds). Adding an entry to the backend registry makes it appear in the editor without frontend edits.

## State events and takeout

`src/api/src/transversal/services/state_events.py` centralises automatic SFX firing for state changes (entity moves, trait gains, relationship creation, contest outcomes) that don't happen in the roll/contest endpoint layer.

### `fire_state_sfx` (line 16)

Fires matching condition-gated SFX for a single state event. A re-entrancy guard (`_firing` set of `(entity_id, event_type)`) prevents an SFX-triggered mutation from re-entering the same event. Pending `{choose_*}` effects are emitted via `roll_orchestrator._emit_pending_choices`.

### Contest outcome (`fire_contest_outcome_sfx`, line 54)

Fires `on_contest_win` / `on_contest_loss` for both sides of a resolved manual contest. The event context carries `contest_winner`, `opponent_id`, `effect_die`, `high_stakes`, and `taken_out`; `{effect_die}` in an SFX result is substituted from this context. If `taken_out` is true, `_mark_taken_out` is called for the loser.

### Takeout (`_mark_taken_out`, line 103)

Sets `loser.taken_out = True`, schedules a `clear_taken_out` revert (one scene) via `scheduled_events.schedule_effect`, persists it, and fires `on_taken_out` with `{taken_out: True, opponent_id}`.

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

### Scene-advance clearing

Scene advance (`advance_scene` in `src/api/src/transversal/api/rest/targeting_bans.py`) now routes through `scheduled_events.dispatch_event(repo, "scene")`, which expires ban and takeout timers by applying their `remove_targeting_ban` / `clear_taken_out` reverts. `targeting_bans.py` keeps `apply_targeting_ban` / `remove_targeting_ban` / `has_targeting_ban` (membership) and the `clear_taken_out` sweep utility; the old `decrement_scene_bans` scene countdown was removed.

## Consequence menu

`src/api/src/transversal/services/consequence_menu.py`.

`assemble_consequence_menu(entity, repo, side, menu_context)` builds the post-roll consequence options from three sources:

1. **Base moves** (`BASE_CONSEQUENCE_OPTIONS`) — always available, keyed by `"player"` / `"gm"`.
2. **Entity moves** — `Entity.consequence_options` on the acting entity's current location and its ancestors (lair moves), filtered by `side`.
3. **SFX moves** — SFX whose `menu_context` matches the requested menu context, wrapped as `ConsequenceOption(id="sfx:{sfx_id}", source="sfx")`. Legacy SFX with no `menu_context` but `trigger="on_consequence"` are included in all contexts for backward compatibility.

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

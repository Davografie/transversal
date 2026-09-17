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
| Effect applier (dispatch + mutation handlers; a target arrives already resolved) | `src/api/src/transversal/services/effects_applier/` (package: `entry.py` dispatches, `registry.py` registers, `handlers_*.py` mutate) |
| Changing a die, in either home (rating or pool) | `src/api/src/transversal/services/effects_applier/handlers_change_die.py` |
| Target-candidate resolution (declared scopes, `resolve_candidates`, `FILTER_FIELDS`) | `src/api/src/transversal/services/target_scopes.py` |
| Structured targeting catalog (elements, edges, fields + options, aggregations, collections) | `src/api/src/transversal/services/target_catalog.py` |
| Target spec model + step types + type-checker | `src/api/src/transversal/services/target_spec.py` |
| Target spec runtime resolver + edge resolvers | `src/api/src/transversal/services/target_resolver.py` |
| Legacy string target → trivial spec migration | `src/api/src/transversal/services/target_legacy.py` |
| Targeting wizard (frontend) | `src/frontend/src/components/gm/TargetSpecBuilder.vue`, `src/frontend/src/composables/useTargetCatalog.js` |
| Condition evaluation + condition-type vocabulary (`CONDITION_TYPES`) | `src/api/src/transversal/services/conditions.py` |
| Authoring validation (`validate_sfx` — unknown variables, filter/target-kind, missing required fields) | `src/api/src/transversal/services/sfx_validation.py` |
| Scheduled events / duration (timers, combine, central `dispatch_event`, `advance_scheduled_events`) | `src/api/src/transversal/services/scheduled_events.py` |
| SFX ownership resolution + seeding of table/contest SFX | `src/api/src/transversal/services/sfx_owner.py` |
| State-change event wiring (takeout, contest win/loss, give-in, push) | `src/api/src/transversal/services/state_events.py` |
| Consequence menu assembly (base + entity + SFX moves) | `src/api/src/transversal/services/consequence_menu.py` |
| Trigger vocabulary (`TRIGGERS` — auto-fire + manual, each with `group` + `{variables}`) + menu-context outcome signals (`MENU_CONTEXT_IDS`/`MENU_CONTEXT_VARIABLES`) | `src/api/src/transversal/services/menu_contexts.py` |
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
    ON_ROLL         = "on_roll"
    ON_SET          = "on_set"
    ON_RESULT       = "on_result"
    ON_CONTEST_WIN  = "on_contest_win"   # deferred; fires on the next contest the entity wins
    ON_CONTEST_LOSS = "on_contest_loss"  # deferred; fires on the next contest the entity loses
    ON_SUCCESS      = "on_success"       # deferred; fires on the next roll result with tier != fail
    ON_FAILURE      = "on_failure"       # deferred; fires on the next roll result with tier == fail
```

### `Effect` (line 649)

One canonical, operational effect record shared by SFX and life-path consequences.

| Field | Type | Meaning |
|-------|------|---------|
| `timing` | `EffectTiming` | When the effect fires (default `IMMEDIATE`) |
| `type` | `str` | Effect family: `modify_roll`, `modify_outcome`, `modify_trait`, `transfer_razmerit`, `create_entity`, `attune`, `travel`, `location`, `life_path`, `relationship`, `entity` |
| `action` | `str` | Operation within the family (see registry below) |
| `target` | `str` | Literal id, `"self"`, or a `{variable}` token — a runtime pick is a `choose` step in `target_spec` |
| `entity` | `str` | Explicit subject entity; `""` or `"self"` = the entity the effect is applied to |
| `result` | `Optional[str]` | Die rating, integer amount, relationship type, or `{context_key}` placeholder |
| ~~`target_scope`~~ | — | **Deleted.** A narrowing is a step in `target_spec`; the scope vocabulary survives as the *picker's* declaration (`targetScopes`), see [[Targeting Model]] |
| `entity_scope` | `Optional[str]` | Narrowing hint for runtime entity choice |
| ~~`target_filter`~~ | — | **Deleted.** A candidate filter is an ordinary `filter` step in the path |
| `target_spec` | `Optional[TargetSpec]` | Structured targeting pipeline (the new model); wins over `target` when set. See [[Targeting Model]] |
| `entity_spec` | `Optional[TargetSpec]` | Structured subject pipeline; wins over `entity` when set. See [[Targeting Model]] |
| `refs` | `dict[str, TargetRef]` | Named references (multi-target model); each key is a declared ref name → `{value, spec, scope}` |
| `output` | `Optional[str]` | The author's name for *this step's result*. Bound into the activation scope when the action declares an `output_element` (gain/copy/move → `traitsetting`, disguise → `projection`), so a later step targets the just-made thing with `select variable {name}` (`effects_applier.publish_effect_output`) |
| `conditions` | `list[Condition]` | Per-effect gate; the effect is skipped unless all conditions pass against the fire-time context (reuses the SFX condition model) |
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
    target_type: str = "entity"   # "entity" | "trait_setting"
    target_id: str = ""           # entity id or trait-setting id
    effect: Effect                # the REVERT effect to fire on expiry
    timers: list[Timer]
    combine: TimerCombine
    source_sfx_id: Optional[str] = None
```

Scheduled events live in one persisted `scheduled_events` collection, not on the
owner documents. `target_type` + `target_id` reconnect each event to the owner
(entity or trait setting) it will fire against, resolved at fire time so a
deleted target is a no-op. The forward effect is applied immediately (mutating
the owner's concrete state); only the *revert* is scheduled. See
[[#Duration / scheduled events]] below.

### `SFX` (line 710)

```python
class SFX(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger: str
    source_kind: Optional[str] = None
    placement: Optional[str] = None
    arming_scope: Optional[str] = None       # "self" | "global" | "listener_spec"
    listener_spec: Optional[TargetSpec] = None
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
```

- `trigger` is the event axis: an auto-fire event (`on_*`) or `manual`.
- `source_kind` declares the owner surface**s** — a *set*, because one source can be provisioned onto more than one thing. `trait_setting` covers both the trait **instance** it fires from and the trait **definition** that provisions its instances (`Trait.possible_sfx_ids` / `default_sfx_ids`) — which is how a rule becomes available to every instance of a trait, and why `backfill_source_kinds` reads either surface as "carried by a trait". The rest are single: `traitset_setting`/`entity`/`projection`, plus the non-resolving bucket sources `table`/`gm` (empty element/variable; no `select source`/`source_rating`). Ownership is the concrete instances of the declared kind (see [[#Ownership & source resolution]]).
- `placement` is the activation surface (`auto`/`sheet`/`menu`), derived from `trigger` when unset (`on_*` → auto, `manual` → sheet, anything else → menu). It is **no longer authored**: the menu is a trigger (`menu`), because a separate field could disagree with the trigger it sat beside. Menu rules are gated by role/outcome conditions (`USER_ROLE` / `CONTEST_OUTCOME` / `TEST_OUTCOME` / `HITCH`) rather than a legacy menu-context trigger.
- `arming_scope` is the listener scope — who the armed SFX listens to once it fires its roll/outcome-timed effects. `None` = derive from trigger (`on_session_start` → `global`, else `self`); `listener_spec` resolves the listener set from a `TargetSpec`. See [[#Arming scope]].
- `conditions` gate which instance of that activation applies.
- Legacy `menu_context` and `limit` strings are folded into `trigger` / a `NARRATIVE` condition by `@model_validator`s (`_fold_legacy_menu_context`, `_fold_legacy_limit`).

### `SfxOwner` (line 746)

Ownership lives on the *owner* side, not the SFX. An owner bucket is a named set of SFX ids:

```python
class SfxOwner(BaseModel):
    id: str            # "table" | "gm"
    sfx_ids: list[str]
```

### `ConsequenceOption` (line 660)

A selectable post-roll consequence entry. Authored directly on entities (location/lair moves) or derived from `trigger="menu"` SFX gated by role/outcome conditions (the base moves are seeded as such SFX, not hard-coded).

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
- `scheduled_events: list[ScheduledEvent]` — legacy owner-scoped field, no longer used (timers live in the central `scheduled_events` collection).
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

```python
class Condition(BaseModel):
    type: ConditionType = ConditionType.ALWAYS
    subject: str = ""       # "" = current entity; literal id; or {variable}
    target: str = ""        # trait / location / entity id (or {variable})
    value: Optional[str] = None
    narrative: str = ""
```

Conditions are authored alongside effects and evaluated against an entity's state (`at_location`, `has_trait`, `has_trait_in_traitset`, `has_relationship`, `trait_rating`, `has_razmerit`, `entity_type`, `unplaced`, `in_universe`, `phase`, `narrative`) plus three fire-time outcome gates: `contest_outcome` (target `player`/`opponent`, reads `context["contest_winner"]`), `roll_tier` (operator + value against `OutcomeTier`, reads `context["tier"]`), and `test_outcome` (target `success`/`fail` — binary; `success` = any non-fail tier). `high_stakes` (target `high`/`low`) reads `context["high_stakes"]` — filled from the contest tracker on a manual activation and from the roll context at resolve, and already present on contest outcome events. `arrival_kind` (target `transversal`/`hierarchy`/`move`/`effect`) reads `context["arrival_kind"]` — carried on every location-change event (`ArrivalKind` in the domain) so a rule can tell a portal crossing from a step up the hierarchy, a GM placement, or an effect-driven move. Every arrival path populates it: `EntityManager.move_to` (default `move`; the caller may say `hierarchy`), `EntityManager.travel`, the portal fire and the travel mutation (`transversal`), and a move an effect performed (`effect`, via `effects_commit.commit_effects`). The same field rides the `location_changed` SSE payload, so the viewer can react to *how* the viewer's entity arrived without asking. `NARRATIVE` is human-readable only and never auto-blocks; `UNPLACED` is true when the entity has no current location; `IN_UNIVERSE` compares `current_universe` to the condition's `target`. Conditions live at **both** the SFX level (`SFX.conditions`, gates the whole activation) and the **effect** level (`Effect.conditions`, gates that one effect — skipped at fire time if any condition fails).

`subject` selects **which entity** the condition tests: blank = the current entity (the event's entity for auto-fire, the acting entity for a consequence menu), a literal entity id, or a `{variable}` resolved from the trigger/menu context (e.g. `{buying_entity}`). The hitch menu has no default entity, so its conditions must reference `{hitch_entity}` / `{buying_entity}` explicitly. `target` is also `{variable}`-resolvable. The editor's condition-type list is served from `CONDITION_TYPES` in `src/api/src/transversal/services/conditions.py` (value + label + needs-target + placeholder + **target-kind**); the target kind (`universe` / `location` / `trait` / `entity`) drives a picker in `ConditionEditor.vue` instead of a text field (`IN_UNIVERSE` uses a universe-*key* picker, not a universe entity id).

## Effect action registry

`src/api/src/transversal/services/effects_registry.py` is the single source of truth for every action the editor can author (`EFFECT_ACTION_REGISTRY`, line 52). Each entry is an `EffectActionMeta` with `action_id`, `category` (`cost` | `benefit` | `either`), `effect_type`, `effect_action`, `valid_timings`, `fields`, `context_fields`, `target_kind`, `supports_duration`, `supports_polarity`, and an optional `inverse` + `inverse_captures_prior` (used by the scheduler to undo a temporary effect).

| Family (`effect_type`) | `action_id` → `effect_action` | Category |
|------------------------|-------------------------------|----------|
| `modify_roll` | `play_as_rating` → `play_as_rating` | cost |
| | `set_die` → `set_die` | either (change a die) |
| | `step_up_die` → `step_up_die` | benefit (change a die) |
| | `step_down_die` → `step_down_die` | cost (change a die) |
| | `double_die` → `double_die` | benefit (change a die) |
| | `split_die` → `split_die` | benefit (change a die) |
| | `remove_die` → `remove_die` | cost (change a die) |
| | `reroll_die` → `reroll_die` | benefit (pool die only) |
| `modify_outcome` | `step_up_effect` → `step_up_effect` | benefit |
| | `step_up_outcome` → `step_up_outcome` | benefit |
| | `negate_complication` → `negate_complication` | benefit |
| | `convert_complication` → `convert_complication` | benefit |
| | `reroll_highest` → `reroll_highest` | either |
| `modify_dice_limit` | `increase_dice_limit` → `increase` | benefit |
| | `decrease_dice_limit` → `decrease` | cost |
| `modify_pool` | `add_dice` → `add_dice` | benefit |
| | `add_trait_rating_dice` → `add_trait_rating` | either |
| `modify_trait` | `step_up_trait` → `step_up` | benefit |
| | `step_down_trait` → `step_down` | cost |
| | `reduce_by_effect_die` → `reduce_by_effect` | benefit (effect die vs rating: remove if larger, else step down) |
| | `increase_by_effect_die` → `increase_by_effect` | benefit (effect die vs rating: set to the effect die if larger, else step up) |
| | `set_trait` → `set` | either |
| | `gain_trait` → `gain` | either (polarity) |
| | `gain_or_step_up_trait` → `gain_or_step_up` | either (polarity) |
| | `cortex_gain_trait` → `cortex_gain` | either (polarity) |
| | `copy_trait` → `copy` | either (reference: the trait instance to copy) |
| | `move_trait` → `move` | cost (reference: the trait instance to take) |
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

`gain_trait` / `gain_or_step_up_trait` / `cortex_gain_trait` all declare `supports_polarity`, so the editor shows a "Negative (complication)" toggle that sets `Effect.negative`. `cortex_gain` is the Cortex create-or-step-up rule: create at the effect die if absent; if present, jump to the effect die when higher, else step up one step. (`gain_trait` already no-ops when the trait is present, so "if not exists" is its existing behaviour.)

### The `Change a Die` family

Six `modify_roll` actions are one family, because they are one question: *which
die, and what happens to it*. The targeting path answers the first half, and it
may land on **either** of a die's two homes — a die in the assembled pool
(`pool → dice`) or a die of a trait instance's rating
(`traitsetting → rating_dice`). The family declares both as its
`path_element`, so one action serves both; `reroll_die` declares only the pool,
because a rating die has no result to reroll.

Where the change lands decides what it *means*, and nothing is authored twice:

- a **rating die** is part of the character, so the change persists and the form
  offers a duration, whose undo restores the rating's whole prior dice list;
- a **pool die** is rebuilt every roll, so the change lasts the roll and no
  duration is offered (`duration_elements` gates the control on the element the
  path resolved to).

`effects_applier/handlers_change_die.py` holds one rule
(`_plan_change`: the die resized, the die gone, or N copies) and two appliers —
the rating list and the pool list — so the two homes cannot drift. The ladder
itself is `domain.dice.step_die`: d12 saturates, a **d4 stepped down is gone**,
and stepping up from nothing restores a d4 (an empty rating is a valid trait).

`step_up_trait`, `step_down_trait`, `remove_rating_die` and
`negate_complication` are **retired from authoring** in this family's favour —
`EffectActionMeta.retired` keeps them in the registry (where their inverse, card
and dispatch live) while the editor stops offering them, so stored content keeps
working and keeps reverting.

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
- `EventOutcome`: splits results into `applied` (immediate effects that were executed), `pending` (`PendingSfxEffect` — a **context-policy** pick like a travel effect's `{choose_projection}` that needs user resolution), and `structured` (a `choose` step in a path, carrying its candidate pool).

### Processing (`EffectsEngine.process_event_outcome`, line 127)

For each available SFX id:

1. Look up the SFX in the registry.
2. `_trigger_matches` (line 219) checks the trigger.
3. If `conditions` exist and a repo is provided, `evaluate_conditions` gates on current entity state.
4. A razmerit cost check sums `transfer_razmerit`/`spend` effect results and skips the SFX if it exceeds the balance.
5. `_substitute_effect_context` replaces `{context_key}` placeholders in each effect's `result` from the event context (this is how `{effect_die}` becomes a concrete die rating).
6. `IMMEDIATE` effects whose path stops at a `choose` step are returned as `structured` (or, for a context-policy pick, as `pending`); otherwise they are applied via `effects_applier.effect_registry.apply`. Non-`IMMEDIATE` effects are persisted as `ScheduledEvent`s in the central store (see [[#Duration / scheduled events]]).

`attune`/`enable` no longer special-cases the schedule: the `_attune` handler applies the enable now and `schedule_revert` schedules the `disable` via the same duration model.

### Scheduling

There is a single persisted timer store — no in-memory schedule. The old in-memory `ScheduledEffect` schedule and its `tick_beat`/`tick_scene`/`tick_session` methods were removed; every deferred/life-path/duration effect with a mappable timing routes through `scheduled_events.dispatch_event` (see [[#Duration / scheduled events]]).

`AFTER_BEATS` maps to a 3-beat timer (`timing_to_timer`).

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
| `on_projection_create` | event type `projection_created` |
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
- `_resolve_target`: `"self"` → the entity's id; `self.<field>` → one of its own id fields; anything else → a literal target id. (A target spec is resolved *before* the applier, so what arrives here is concrete.)
- `resolve_choice` re-applies a `PendingChoice` with a concrete target.
- **Candidate filters** are filter steps in the path (`filter starter_location == true`), so a narrowing composes with everything else a path can say. The `starter_location` target kind stays retired.

> [!note] Structured targeting
> The legacy string targets above are being superseded by a structured, type-checked **[[Targeting Model]]** (`target_spec` / `entity_spec`). When a spec is present it takes precedence over the string form.

### `target_scope` and `target_filter`

A `target_scope` like `traitset:ts-complications-a190` or `universe:earth` narrows the candidate set the picker/random resolver presents. It is **not a second vocabulary**: each `(prefix, kind)` pair is declared in `services/target_scopes.py` as the catalog **path** it stands for, and `resolve_candidates` runs that path through the same resolver as any authored spec (see [[Targeting Model]] → *The scope vocabulary*). Grammar is `prefix:value` — prefixes `universe`, `location`, `subtree`, `faction`, `actor_faction`, `traitset`, `life_path`; a bare value is a universe (a place id for occupants); empty means the acting entity's own context; `universe:current` explicitly means its current universe. `target_filter` (e.g. `{"starter_location": true}`) is appended as ordinary filter steps, so a candidate narrowing is the same language as the path. The GraphQL `targetCandidates` query resolves both for the runtime picker and the editor's live preview (`entityId` is optional; with no entity the universe narrowing is dropped, so the whole registry stays reachable while authoring), `targetScopes` reads the declared vocabulary, and `resolveTargetSpec` executes a spec read-only and reports every step.

An unsupported `(kind, scope)` pair is an **error** naming the kinds that scope supports, not `[]` — an empty list is indistinguishable from "nothing matched" (an `occupant` picker on a faction once read as an empty 30-member roster). An unknown prefix is an error too.

`roll_table` targets honour `universe:` (bare = current universe), `life_path:` (tables in one life path) and `faction:` (tables whose owning life path is in the faction's `suitable_life_path_ids`). A `trait` target with an empty scope resolves to the full trait registry in authoring (no concrete universe); with a universe it resolves to that universe's traits, and with `traitset:` to that trait set's traits.

### Complication trait set id

The complications trait set is **`ts-complications-a190`**. The negative-trait fallback in `_new_traitsetting` (line 268) and the contest complication SFX both use it. See [[#Known mismatch]] below for the one place that still references the old id.

## Duration / scheduled events

`src/api/src/transversal/services/scheduled_events.py`.

A temporary effect is modeled as **apply now + schedule a revert**:

1. The forward effect mutates the owner's concrete state immediately (a trait's `dice`, an entity's `targeting_bans` / `taken_out` / `attunements`, a created asset).
2. `schedule_revert` / `schedule_effect` / `schedule_event` / `schedule_deferred` append a `ScheduledEvent` holding the inverse effect and its `timers`.
3. `dispatch_event(repo, event_type, entity_id, …)` advances timers on the boundary and applies the stored revert when they expire.

### Advancement (central point)

- **Global boundaries** (`beat` / `scene` / `session`, no entity): `dispatch_event` advances every scheduled event in the central store.
- **Entity-scoped events** (`location_changed`, `trait_updated`, `relationship_created`): advance only that entity's and its trait-settings' events, then fire state SFX.
- `next_beat` → `dispatch_event(repo, "beat")`; `advance_scene` → `dispatch_event(repo, "scene")`; `entity_manager._publish_location_changed` and `effects_commit` publish through `dispatch_event`.

### Querying (GraphQL + UI)

Running timers are exposed so the UI can reconnect a timer to its owner:

- `scheduledEvents(targetType, targetId, targetIds)` — `targetType` is `"entity"` or `"trait_setting"`; `targetId` scopes to one owner, `targetIds` to a set (e.g. a sheet's trait-setting ids). All filters combine; omitting all returns the full store.
- Frontend `useScheduledEvents` (`fetchFor`) fetches them and `formatTimers` renders a game-boundary countdown (`"2 scenes"`, `"1 beat"`) — never wall-clock. The character sheet shows a `⏳` line on the entity header (GM) and a per-trait badge when a trait has a pending revert.

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

Non-`IMMEDIATE` effects from the effects engine are persisted as scheduled events (`scheduled_events.schedule_deferred` → `timing_to_timer` maps `END_OF_BEAT` / `END_OF_SCENE` / `END_OF_SESSION` / `AFTER_BEATS` to a timer). There is no in-memory fallback — life-path deferrals and duration reverts share the same central store.

A row's `kind` says what it is for: a **`revert`** (an undo timer) applies its
effect when the timers expire, a **`pending`** row is a deferred forward effect,
and a **`hold`** is the undo of an effect that had no timer — it never fires on
its own. Holds exist so a *manual* activation can be taken back until it commits:
ended early, its holds are applied (and its pending parts dropped); committed — a
delayed part fired, or the entity's dice were rolled — its holds are dissolved.
That window, and what it can and cannot undo, is [[Activation Flight Window]].

### Arming scope

Roll/outcome-timed effects (`on_roll`/`on_set`/`on_result`/`on_contest_*`/`on_success`/`on_failure`) arm in `roll_deferral.py` (`_armed[entity_id]` + `_global_armed`). An armed entry's **listener scope** says *who it listens to*:

- `self` — the triggering entity (default; the `_armed[entity_id]` register).
- `global` — every entity's rolls (the `_global_armed` register).
- `listener_spec` — a `TargetSpec` resolving the listener entity set, **at arm time** (D3, resolved 2026-09-12): the path is resolved once against the activating entity, and the rule is armed on each entity it names. An empty set arms nobody.

`SFX.arming_scope` declares this; `None` derives it from trigger (`on_session_start` → `global`, else `self`). `fire_armed` honors the `rolls` budget for **both** registers — a `rolls:N` entry fires N times then drops; `rolls=None` stays armed until a boundary expires it. This makes session-scoped passives (e.g. `sfx-one-trick`) *declare* their lifetime instead of relying on the global path silently ignoring the roll budget.

### Activation variable scope

Each SFX activation carries one shared **variable scope** — a dict of typed `Binding`s threaded through the whole run. Two things write to it, in order:

1. **Conditions.** `evaluate_condition`'s `TARGET_PATH` branch resolves its path with the scope as `TargetContext.bindings`, then publishes the path's `output` names into the caller's `out_bindings`. So a gate can *name what it matched* (e.g. `d4_traits` = the d4 trait instances in this roll), not just answer yes/no. Step outputs live on the resolution **context**, not the `Resolution` (which carries only `values`/`errors`/`pending_choices`).
2. **Effects.** Effect step outputs extend the same dict, so later effects see both.

The scope reaches the applier via `BINDINGS_CONTEXT_KEY` (`_bindings`) in the effect context — the same pattern as `_source`/`_source_element`. `apply_effects` and `resolve_effect_entity` resolve an effect's `entity_spec` against it before dispatch, so by the time a handler runs it sees a concrete `entity` id with `entity_spec` cleared (mirroring the engine's `target_spec` rewrite).

Roll data reaches conditions the same way it reaches armed effects: roll-bearing triggers put the dice in the event context, and `TARGET_PATH` seeds `collections["rolled_dice"]` from `context["rolls"]`. `fire_roll_sfx` and `fire_result_sfx` both do this; a path selecting `rolled_dice` on any other trigger resolves empty and fails closed.

`effectVariables(effects, sourceElement, conditions)` mirrors this for the editor: it traces the SFX's conditions first, then the effects, and returns the accumulated typed scope so the targeting wizard can offer the names in `select variable`.

### Razmerit effects honour their entity

`earn`/`spend`/`transfer` act on `_razmerit_entity(effect, acting_id)`: a concrete `effect.entity` (a literal, a substituted `{variable}`, or one the engine resolved from an `entity_spec`) wins; blank / `self` / an unresolved placeholder falls back to the acting entity. Before this the razmerit handlers credited the passed-in entity id unconditionally, so an authored `entity`/`entity_spec` on a razmerit effect was silently ignored.

### Session boundaries

`state_events.fire_session_start()` / `fire_session_end()` are the two global boundaries.

**Session start** splits an `on_session_start` SFX by effect timing, and the two halves fan out differently:

- **Deferred effects** (`DEFERRED_TIMINGS` = roll + outcome timings) arm **once, globally** via `arm_passive`, in a pass that iterates *SFX, not entities*. This is deliberately ownership-independent, so a passive armed for the session still covers characters who join mid-session.
- **Non-deferred effects** (`immediate`, `end_of_beat`/`scene`/`session`, `after_beats`) fire **per entity** through `fire_global_state_sfx("on_session_start", arm_deferred=False)` — each entity applies its own immediate effect or schedules its own persisted timer.

`arm_deferred=False` keeps the two passes non-overlapping: the walk applies non-deferred effects and never arms, while the single global pass owns arming. (It is no longer load-bearing for correctness — see **Arming is idempotent** below — but it avoids N redundant re-arms and keeps each half with one clear owner.)

### Arming is idempotent

Both registers dedupe on `source_sfx_id` (`roll_deferral._drop_existing`): arming is a **state, not a counter**. Re-arming a named SFX replaces its entry (refreshing the `rolls` budget / expiry) instead of appending a second copy.

This is what makes the per-entity fan-outs safe. `fire_global_state_sfx` visits every entity, and each visit re-arms an SFX the entity carries; before the dedupe, a `global`-scope boundary SFX (`on_beat`/`on_scene`/`on_session_end`) carried by N entities left **N armed copies**, and its roll effect fired N times per roll event. Anonymous entries (`source_sfx_id is None`) are never deduped — with no name to key on they are separate rules by construction, which also preserves the existing multi-duration stacking case.

Regression-guarded by `test_global_boundary_fanout_arms_once_for_n_entities` (three owning entities must leave one armed copy) and the two `*_is_idempotent_per_sfx_id` tests.

Scope note: the **persisted** timer store (`scheduled_events`) is deliberately *not* deduped. Identical rows there are legitimate — two step-downs each need their own step-up revert — and fan-outs never produce duplicates anyway, because each row is keyed to a distinct `target_id`.

**Session end** (`fire_session_end`) drops the session's armed passives (`clear_global_armed`) and then fires `on_session_end` per entity — a global boundary like `on_beat`/`on_scene`, so its effects fire for every entity that has the SFX available.

## SFX ownership and seeding

`src/api/src/transversal/services/sfx_owner.py`.

### Owner buckets

`ensure_sfx_owners` (line 22) seeds two owner buckets: `table` (everyone) and `gm` (GM-context only, not entity-derived). The `gm` bucket is intentionally excluded from entity-derived resolution. There is no `players` bucket — "player-character-only" is expressed as an `ENTITY_TYPE` condition (target `character`) on the SFX, not a grant surface. The legacy `players` bucket is migrated into `table` and dropped on seed.

### Ownership & source resolution

Ownership is the **concrete instances** of an SFX's declared `source_kind`: an `entity`-kind SFX lives on `Entity.sfx_ids`, a `trait_setting`-kind SFX on a `TraitSetting.sfx_ids`, a `table`/`gm`-kind SFX in the matching owner bucket. `source_kind` is the single axis that names *what shape of thing carries the SFX*; `resolve_sfx_source` reads it to resolve the activation source for `select source` / `source_rating`.

`owned_surfaces(repo, sfx_id)` reverse-indexes which owner surfaces actively carry an SFX (used by validation). `backfill_source_kinds(repo)` idempotently backfills `source_kind` from ownership — folding the `table`/`gm` buckets into `source_kind=table`/`gm` and trait-instance grants into `trait_setting` — and marks `on_session_start` rules `arming_scope=global`.

### Available SFX resolution (`get_available_sfx_ids`, line 181)

The SFX ids available to an entity in a universe are the sorted union of:

1. `Entity.sfx_ids` (direct ownership).
2. The active projection's `Projection.sfx_ids` (`entity.current_projection`).
3. The `table` owner bucket.
4. Trait-level grants from effective `TraitSetting.sfx_ids` plus the trait's `Trait.default_sfx_ids` — **and a disabled instance grants nothing**. "Landed", "suppressed", "spent" are states of the owner, so the rule it carries stops being offered with it; this is implicit rather than authored, and no condition can stand in (`HAS_EFFECTIVE_TRAIT` matches by *registry trait* and returns the first match's `enabled`, so several instances of one generic trait — an agenda's steps — answer arbitrarily).
5. Trait-set-as-unit grants from effective `TraitSetSetting.sfx_ids`.

Then context-free conditions are evaluated (`static_conditions`) so listing matches fireability: an SFX whose `entity_type` / `in_universe` condition doesn't hold for this entity is dropped from the available list; variable-gated conditions are left to fire-time.

### Seeded table/contest SFX

| SFX id | Trigger | Effect(s) | Purpose |
|--------|---------|-----------|---------|
| `sfx-give-in-get-razmerit` | `on_give_in` | `transfer_razmerit`/`earn`/`self`/`1` | Conceder gains 1 razmerit |
| `sfx-give-in-targeting-ban` | `on_give_in` | `entity`/`targeting_ban`/`""`/`1` | Conceder can't target that opponent for the scene |
| `apply-complication` | trigger `contest_win` (menu) | `modify_trait`/`cortex_gain`/`{choose_trait}` @ `{effect_die}` (negative), scope `traitset:ts-complications-a190` | Winner applies a complication to the opponent |
| `take-complication` | trigger `contest_give_in` (menu) | same effect as `apply-complication` | Conceder takes a complication on their own projection |
| `prevent-taken-out` | `on_prevent_taken_out` | `transfer_razmerit`/`spend`/`self`/`1` | Spend 1 razmerit to avoid being taken out |
| `sfx-starter-location` | `on_character_create` | `location`/`set`/`{random:location}` @ scope `universe:earth`, filter `{starter_location: true}`; conditions `UNPLACED` + `IN_UNIVERSE(earth)` | New unplaced Earth characters arrive at a random starter location |

`ensure_contest_complication_sfx` creates/migrates **two** SFX (`apply-complication`, `take-complication`) with identical `cortex_gain` + negative effects but different `trigger` (`contest_win` vs `contest_give_in`), so the frontend surfaces the right one at each end of a contest. The migration also rewrites stale `gain_complication` effects in place.

`remove_legacy_contest_complication_sfx` (line 164) deletes the retired `sfx-contest-loss-complication` row and its `table` reference so a stale DB doesn't keep auto-firing it on `on_contest_loss` (P2.10d moved contest-loss complications into the manual consequence menu).

### Editor vocabularies (backend-served)

The SFX editor renders three vocabularies from GraphQL rather than hardcoding them: `triggers` (from `TRIGGERS` in `menu_contexts.py` — value + label + variables + `group` (`manual`/`dicepool`/`auto`); the activation surface is derived from the trigger (`manual` → sheet, `on_*` → auto, `menu` → the post-roll menu)), `conditionTypes` (from `CONDITION_TYPES` in `conditions.py` — value + label + needs-target + placeholder + target-kind), and `targetFilterFields` (from `FILTER_FIELDS` in `target_scopes.py` — field + label + valueType + applicable kinds), and `targetScopes` (the declared scope vocabulary). Adding an entry to the backend registry makes it appear in the editor without frontend edits.

The editor also validates a draft on save (and live, debounced) via the `validateSfx` GraphQL field backed by `sfx_validation.validate_sfx`, which warns on unknown `{variables}`, a `target_filter` field that doesn't apply to the action's target kind, missing required fields, a declared `source_kind` that matches no actual owner (a silent `select source` / `source_rating` no-op), a `listener_spec` arming scope without a listener path, a condition whose **source** can't supply what it reads, and a condition whose **moment** doesn't supply a context key it reads. Warnings are advisory, not a save gate.

**The context capability map** (`conditions.py`) answers the last one. Every condition declares the context keys it reads (`condition_context_keys`) and every evaluation point the keys it supplies (`context_keys_for`) — site keys are read off the fire sites themselves (roll/outcome timings bring the roll, boundary timings and boundary triggers bring nothing, a manual activation brings `phase` + `high_stakes`, a menu rule (`trigger="menu"`, or a legacy `placement="menu"`) is gated by the menu assembly's outcome keys). An unmodelled site supplies `null` = unrestricted: the map only ever *forbids*, because hiding a working gate is worse than offering a dead one. `conditionContextKeys(trigger, placement, timing)` serves one point to the editor; the per-condition exactness stays here, where the live warnings surface.

### Target pickers (frontend)

Every target picker in the GM panel routes through one component, `src/frontend/src/components/gm/TargetPicker.vue`, which renders the backend `targetCandidates` resolver's result via the shared `SearchDropdown`. The bespoke `GmTraitPicker` / `GmLocationPicker` / `GmRollTablePicker` / `ScopedTargetPicker` were retired, so the authoring picker and the runtime `{random:*}` resolver share the same candidate source and cannot drift. In the effect editor, `literal` / `choose` / `random` target modes all use the same `scope` + `filter`; `literal` merely picks one of those candidates now, and its scope/filter are persisted so re-opening an effect keeps its context.

## State events and takeout

`src/api/src/transversal/services/state_events.py` centralises automatic SFX firing for state changes (entity moves, trait gains, relationship creation, contest outcomes) that don't happen in the roll/contest endpoint layer.

### `fire_state_sfx` (line 16)

Fires matching condition-gated SFX for a single state event. A re-entrancy guard (`_firing` set of `(entity_id, event_type)`) prevents an SFX-triggered mutation from re-entering the same event. Pending `{choose_*}` effects are emitted via `roll_orchestrator._emit_pending_choices`.

### Projection creation (`fire_projection_created`)

`fire_projection_created(entity_id, universe, projection_id)` is the single fire site for `on_projection_create`, called from every runtime path that produces a new Projection record: character/GMC/asset creation (the initial NATIVE body, in `create_entity`), `add_projection`, a universe move that spawns a fallback body (`move_to`), and travel-spawned bodies (`effects_commit`). Seed-time `create` / `create_projection` deliberately do not fire it.

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

1. **Entity moves** — `Entity.consequence_options` on the acting entity's current location and its ancestors (lair moves), filtered by `side`.
2. **SFX moves** — `trigger="menu"` SFX gated by their conditions (role via `USER_ROLE`, outcome via `CONTEST_OUTCOME`/`TEST_OUTCOME`/`HITCH`), wrapped as `ConsequenceOption(id="sfx:{sfx_id}", source="sfx")`. Legacy `trigger="on_consequence"` SFX still appear in every menu for backward compatibility.

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

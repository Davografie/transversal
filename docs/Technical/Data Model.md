---
title: Data Model
tags:
  - transversal
  - technical
  - data-model
  - schema
  - arangodb
aliases:
  - Data Model
  - Schema
  - Database Schema
  - Collections
status: canonical
---

# Data Model

The Transversal backend uses **ArangoDB 3.12** — a graph + document database. The data model is a property graph: entities, traits, SFXs, and players live in separate collections connected by edges. This is the single source of truth for all collection schemas, field definitions, edge patterns, and ID conventions.

> [!tip] Where's the code?
> Pydantic models: `src/api/src/transversal/domain/__init__.py`
> Database setup: `src/api/src/transversal/db/arango.py`
> Repository: `src/api/src/transversal/db/repository.py`

## Collections

| Collection | Type | Purpose | Edge `_from` → `_to` |
|-----------|------|---------|----------------------|
| `entities` | Document | Core entity metadata | — |
| `entity_images` | Document | Entity/projection images (background, sheet, navdot) | — |
| `historical_records` | Document | Blue Book — change log and history | — |
| `life_paths` | Document | Life-path catalog (sect, guild, career terms) | — |
| `messages` | Document | In-fiction messages / log entries | — |
| `players` | Document | Player identity for session persistence | — |
| `projections` | Document | Per-universe body — name, image, location, morph traits | — |
| `relationships` | **Edge** | Entity → Entity connections (also anchors relation traits) | `entities/{from}` → `entities/{to}` |
| `roll_tables` | Document | Reusable roll tables; entries execute effects | — |
| `sfxs` | Document | SFX registry — trigger, conditions, effects, duration | — |
| `sfx_owners` | Document | Named SFX-owner buckets (`table`, `gm`) | — |
| `traits` | Document | Trait registry — what traits exist per universe | — |
| `traitsets` | Document | Trait grouping registry (attributes, skills, cultivation, etc.) | — |
| `traitsettings` | **Edge** | Trait assignment — anchor by `from_type` (entity/projection/relationship/traitsetting) | entity / projection / relationship / traitsetting → trait |
| `traitsetsettings` | **Edge** | Per-entity traitset config (SFX + limit override) | entity / projection → traitset |
| `plan_entities` | Document | GM draft staging — entities not yet published | — |
| `plan_relationships` | **Edge** | GM draft staging — relationships in a plan | `plan_entities/{from}` → `plan_entities/{to}` |
| `scheduled_events` | Document | Persisted timed reverts fired when their timers expire | — |

**Graph traversal path:** `entity →(traitsetting)→ trait → traitset →(possible_sfx_ids)→ sfx`

---

## Enums

### EntityType

| Value | Description |
|-------|-------------|
| `character` | Player character |
| `location` | Place in a universe |
| `faction` | Organization or group |
| `asset` | Ownable item or resource |
| `gmc` | GM character / NPC |
| `universe` | Universe metadata entity |
| `subtrait` | Sub-trait nested under a parent trait |
| `relation` | Relationship edge trait (e.g. "friend of", "debt to") |

### TransversalType

| Value | Meaning |
|-------|---------|
| `native` | Permanent body — the return target for consciousness travel |
| `consciousness` | Transient projection — consciousness inhabits a foreign body |
| `inapposite` | Physically relocated body — full physical transport, position mutates in place |

### DieType

| Value | Sides |
|-------|-------|
| `d4` | 4 |
| `d6` | 6 |
| `d8` | 8 |
| `d10` | 10 |
| `d12` | 12 |

### RatingType

| Value | Behaviour |
|-------|-----------|
| `static` | Fixed die — always available at this value |
| `resource` | Pool of dice — spend moves a die to `spent_dice`, recovery moves it back (bounded by the ledger). Capacity = `dice + spent_dice`; depletion possible. |
| `challenge` | Opposition pool — GM spends dice against players. See [[#Polarity]]. |
| `empty` | No die — trait is present but unrated (flavor, narrative only) |

### Polarity

Every trait has a sign, independent of its rating type.

| Value | Meaning |
|-------|---------|
| `positive` | Benefit / asset the character wields |
| `negative` | Harm / complication the opposition can use against them |

Polarity is **baked** onto a trait setting at creation (non-null), resolved from the most specific override: `traitsetting` → `trait` → `traitset` → global `positive`. Changing a `trait` or `traitset` default propagates down to the settings that were inheriting it.

### EffectTiming

| Value | Fires |
|-------|-------|
| `immediate` | Right now, during resolution |
| `end_of_beat` | At beat end |
| `end_of_scene` | At scene end |
| `end_of_session` | At session end |
| `after_beats` | After N beats (parameterized) |
| `on_condition` | When a runtime condition is met |
| `on_roll` | At the next matching roll event (per-roll deferral) |
| `on_set` | At the next matching die-set event (per-roll deferral) |
| `on_result` | At the next matching roll-result event (per-roll deferral) |
| `on_contest_win` | At the next contest win |
| `on_contest_loss` | At the next contest loss |
| `on_success` | At the next successful test (tier != fail) |
| `on_failure` | At the next failed test (tier == fail) |

### OutcomeTier

| Value | Effect Die |
|-------|-----------|
| `fail` | None |
| `marginal` | d4 |
| `success` | d6 |
| `exceptional` | d8 |
| `perfect` | d10 |

### Relationship Types

| Type | Direction | Meaning |
|------|-----------|---------|
| `super` | child → parent | Location hierarchy (sub-location of) |
| `transversal` | bidirectional | Portal / traversal connection between locations |
| `relation` | arbitrary | Generic relationship between entities (legacy) |
| `associate` | entity → entity | Named association; resolves relationship descriptions in `messages` |
| `commands` | faction → entity | Command/control hierarchy |
| `membership` | entity → faction | Entity is a member of a faction |
| `agency` | player → entity | Player ownership / control of an entity |

---

## Collection Schemas

### `entities`

Core entity metadata. Every significant thing in Transversal is an entity. Traits live in separate collections — the entity is the hub that trait settings connect to.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Entity ID (e.g. `kael-1`, `loc-krasnoyarsk`, `universe-earth`) |
| `type` | EntityType | ✅ | `character`, `location`, `faction`, `asset`, `gmc`, `universe`, `subtrait`, `relation` |
| `name` | string | ✅ | Display name |
| `razmerit` | int | ✅ | Global hyper-dimensional currency (default `0`) |
| `current_universe` | string | ✅ | Universe key (e.g. `earth`, `three_realms`) |
| `current_location` | string? | | Entity ID of current location (`null` for universes and root locations) |
| `current_projection` | string? | | Active projection id (occupant types) |
| `hidden` | bool | | Visibility flag (default `false`) |
| `unpublished` | bool | | GM draft: real in-world but not yet revealed to players |
| `known_to` | string[] | | Entity IDs that know about this entity (faction conspyramid) |
| `background_image` | string? | | URL path to location background (e.g. `/media/loc-krasnoyarsk.webp`) |
| `starter_location` | bool | | Location is a valid random-spawn destination |
| `zones` | Zone[] | | Sub-areas within a location (see [[#Zone]]) |
| `map_x` | float? | | Percentage X position on location background (0–100) |
| `map_y` | float? | | Percentage Y position on location background (0–100) |
| `overlay` | string? | | Visual overlay preset: `mist`, `fire`, `rain`, `snow`, `sparkles`, `fog` |
| `nav_positions` | dict | | Navigation dot positions per edge type (e.g. `{"parent": {"x": 90, "y": 15}}`) |
| `node_ids` | string[] | | Faction conspyramid node entity IDs |
| `owned_by` | string? | | Owner entity ID (for assets) |
| `attunements` | Attunement[] | | Active temporary universe additions (effect-managed) |
| `targeting_bans` | TargetingBan[] | | Directional contest-target bans |
| `taken_out` | bool | | Scene-scoped: high-stakes contest removed this entity from the scene |
| `total_dice_bonus` | int | | Delta over the base total-dice keep limit (2); adjusted by `modify_dice_limit` effects (default `0`) |
| `effect_dice_bonus` | int | | Delta over the base effect-die keep limit (1); adjusted by `modify_dice_limit` effects (default `0`) |
| `sfx_ids` | string[] | | SFX owned directly by this entity |
| `scheduled_events` | ScheduledEvent[] | | Pending timed reverts |
| `lora_config` | dict? | | Per-entity-type LoRA config (e.g. `{"CHARACTER": ["lora1"]}`) |
| `life_paths` | Enrollment[] | | Life-path memberships (faction + path) |
| `active_universes` | string[] | | Faction-only: where active |
| `suitable_life_path_ids` | string[] | | Faction-only: offered paths |
| `discovered_life_paths` | string[] | | `_key`s of discovered paths |
| `pending_term` | PendingTerm? | | In-progress term state (checkpoint) |
| `consequence_options` | ConsequenceOption[] | | Post-roll consequence menu authored on the entity |

**ID conventions:**
- Characters: `{name_slug}-{n}` (e.g. `kael-1`, `elena-1`)
- Locations: `loc-{old_numeric_key}` (e.g. `loc-74560187`)
- Factions: `faction-{slug}`
- Assets: `asset-{slug}`
- GMCs: `gmc-{slug}`
- Universes: `universe-{universe_key}` (e.g. `universe-earth`)

### `projections`

Per-universe body record. An entity has one projection per universe they have visited.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Projection ID (e.g. `kael-1:three_realms`; `:2`, `:3` suffixes for extra bodies in one universe) |
| `entity_id` | string | ✅ | Entity this projection belongs to |
| `origin_universe` | string | | Native/home universe (immutable) |
| `universe` | string | ✅ | Current universe (mutable; inapposite travel mutates in place) |
| `name` | string | | Display name; falls back to entity name |
| `background_image` | string? | | Falls back to entity `background_image` |
| `current_location` | string? | | Where this body currently is |
| `transversal_type` | TransversalType | | `native`, `consciousness`, or `inapposite` (default `native`) |
| `sfx_ids` | string[] | | SFX owned by this body |
| `last_used_at` | string? | | ISO timestamp of when this body was last active |

### `traitsets`

Registry of trait groupings. Defines named sets of traits available to entity types in specific universes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `ts-attributes-8f3a`, `ts-cultivation-9d4e` |
| `name` | string | ✅ | Display name (e.g. `attributes`, `skills`, `cultivation`) |
| `universes` | string[] | ✅ | Universe keys where this traitset applies |
| `description` | string | | Explainer text |
| `entity_types` | EntityType[] | | Which entity types can use this set |
| `order` | int | | Display sort order (default `0`) |
| `limit` | int | | Max traits an entity can select from this set (default `1`) |
| `location_restricted` | bool | | Whether universe-specific laws are required (default `false`) |
| `polarity` | Polarity? | | Default polarity override for traits in this set (null = global positive) |
| `default_rating_type` | RatingType | | Default rating behaviour for new traits in this set (default `static`) |
| `default_die_type` | DieType | | Default die for new traits in this set (default `d4`) |
| `transfer_flags` | TransferFlags? | | teachable/giftable/takable flags |

**ID convention:** `ts-{slug}-{hash4}` — slug is a human-readable name variant (e.g. `attributes`, `cultivation`). The 4-char hex hash is `md5(slug + ":" + joined_universes)[:4]`, ensuring keys are unique even when the same name appears in different universes. Examples: `ts-attributes-8f3a` (Earth), `ts-attributes-9d4e` (Three Realms).

### `traits`

Registry of all possible traits per universe. Shared definitions — not per-entity.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `trait-hacking-7f2a`, `trait-qi-reserves-1e5b` |
| `name` | string | ✅ | Display name (e.g. `Hacking`, `Qi Reserves`) |
| `universes` | string[] | ✅ | Universe keys where this trait exists |
| `traitset_id` | string | ✅ | `_key` of parent traitset |
| `default_die_type` | DieType | | Die for untrained/new entities (default `d6`) |
| `default_rating_type` | RatingType | | Rating behaviour (default `static`) |
| `polarity` | Polarity? | | Default polarity override (null = inherit traitset) |
| `required_trait_ids` | string[] | | Prerequisite trait IDs |
| `possible_subtrait_ids` | string[] | | Sub-traits that can be nested under this trait |
| `possible_sfx_ids` | string[] | | SFX IDs unlockable for this trait |
| `location_restricted` | bool | | Whether universe-specific laws are required (default `false`) |
| `default_ego` | bool | | Grant default: true = entity (ego/persists), false = projection (morph/gated) |
| `explanation` | string | | Flavor or rules explanation text |
| `random_weight` | int | | Weight for random trait generation (default `0`) |
| `display_names` | TraitDisplayName[] | | Dynamic display names keyed by dice rating + universe |
| `transfer_flags` | TransferFlags? | | teachable/giftable/takable flags |
| `possible_subtraitset_ids` | string[] | | Whole traitsets that can be nested as sub-traits |
| `default_sfx_ids` | string[] | | SFX granted by default when this trait is taken |

**ID convention:** `trait-{slug}-{hash4}` — same pattern as traitsets. The 4-char hex hash is `md5(slug + ":" + joined_universes)[:4]`. Examples: `trait-hacking-7f2a` (Earth), `trait-qi-reserves-1e5b` (Three Realms).

### `traitsettings` (edge)

Per-entity trait configuration. The edge connects an anchor (entity, projection, relationship, or another trait setting) to a registry trait, carrying the anchor's specific dice, statement, SFX unlocks, and location restrictions.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `kael-1:trait-hacking-7f2a` (suffix for sub/relation anchors) |
| `_from` | string | ✅ | Anchor handle: `entities/{id}`, `projections/{id}`, `relationships/{id}`, or `traitsettings/{id}` |
| `_to` | string | ✅ | `traits/{trait_id}` |
| `from_type` | string | ✅ | Anchor kind: `entity` (ego) \| `projection` (morph) \| `relationship` (relation trait) \| `traitsetting` (sub-trait) |
| `entity_id` | string | ✅ | Denormalized owning entity |
| `trait_id` | string | ✅ | Denormalized |
| `traitset_id` | string | ✅ | Denormalized |
| `projection_id` | string? | | Projection anchor id when `from_type == "projection"` |
| `parent_traitsetting_id` | string? | | Parent TraitSetting id when `from_type == "traitsetting"` (sub-trait) |
| `rating_type` | RatingType | | `static`, `resource`, `challenge`, `empty` (default `static`) |
| `dice` | DieType[] | | Currently-available dice this trait contributes (e.g. `[d4, d4, d4, d4]` for a full 4d4 resource). For a resource this is the unspent remainder |
| `spent_dice` | DieType[] | | Spent-but-recoverable dice (resource pools). Capacity = `dice + spent_dice`; recovery moves a die back into `dice` |
| `capacity` | DieType[]? | | Challenge target (positive) / ceiling (negative); optional for resource pools |
| `polarity` | Polarity | ✅ | Baked sign: `positive` (benefit/asset) or `negative` (complication). Resolved from trait/traitset defaults at creation |
| `statement` | string | | Distinction statement or flavor text |
| `notes` | string | | Longer freeform notes |
| `enabled` | bool | | `false` = disabled; contributes no dice until re-enabled (default `true`) |
| `sfx_ids` | string[] | | SFX IDs unlocked for this anchor on this trait |
| `locations_enabled` | string[] | | Location entity IDs where this trait is active |
| `locations_disabled` | string[] | | Location entity IDs where this trait is suppressed |
| `known_to` | string[] | | Entity IDs that know about this trait setting |
| `source_type` | string? | | Provenance: `taught` \| `gifted` \| `taken` \| `life_path_term` \| `event` \| null |
| `source_entity_id` | string? | | Who taught/gifted it, or who it was taken from |
| `source_trait_setting_id` | string? | | Original TraitSetting this derived from (teach) |
| `source_life_path_id` | string? | | Which life path generated this (life_path_term) |
| `source_term_number` | int? | | Which term in that path (life_path_term) |
| `stolen` | bool | | Trait was taken — may have narrative consequences (default `false`) |
| `scheduled_events` | ScheduledEvent[] | | Pending timed reverts |

**ID convention:** `{entity_id}:{trait_id}` for entity/projection anchors; `{anchor_id}:{trait_id}` for relationship anchors; parent + suffix for sub-traits.

> [!note] Legacy fold
> Old docs may carry `negative`/`polarity=None`; the model folds `negative: true` into `polarity: negative` at load, and defaults a null polarity to `positive`.

### `traitsetsettings` (edge)

Per-entity (or per-projection) traitset configuration — the set-level sibling of `TraitSetting`. Carries SFX that apply to the set *as a unit* and an optional `limit` override.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `{entity_id}:{traitset_id}` |
| `_from` | string | ✅ | `entities/{id}` or `projections/{id}` |
| `_to` | string | ✅ | `traitsets/{traitset_id}` |
| `from_type` | string | ✅ | `entity` \| `projection` |
| `entity_id` | string | ✅ | Denormalized owning entity |
| `traitset_id` | string | ✅ | Denormalized |
| `projection_id` | string? | | Projection anchor id when `from_type == "projection"` |
| `sfx_ids` | string[] | | SFX that apply to the set as a unit |
| `limit` | int? | | Per-anchor override of the set's registry limit (null = registry default) |

### `sfxs`

SFX (Special Effect) registry. Defines named abilities with triggers, costs, and declarative effects.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `sfx-law-bridge`, `sfx-overcharge` |
| `name` | string | ✅ | Display name |
| `description` | string | | Flavor text and usage notes |
| `trigger` | string | ✅ | Single activation axis — an auto-fire event, `manual`, or a consequence menu (e.g. `manual`, `on_roll`, `on_result`, `on_complication`, `test_success`, `contest_win`) |
| `source_kind` | string? | | Declarative owner type this SFX carries — `trait_setting` / `traitset_setting` / `entity` / `projection`; null = bucket/passive (no meaningful origin) |
| `placement` | string? | | Activation surface: `auto` (event-driven), `sheet` (owner card), `menu` (post-roll consequence menu); null = derived from `trigger` |
| `conditions` | Condition[] | | Optional gates evaluated against the entity before firing |
| `effects` | Effect[] | | List of declarative effects |
| `duration` | EffectDuration? | | How long the SFX stays in effect once triggered; default one roll, null = indefinite (until cleared) |

**ID convention:** `sfx-{slug}` (e.g. `sfx-hinder`, `sfx-law-bridge`)

> [!note] Legacy folds
> `menu_context` is folded into `trigger` on load; `limit` (string) is folded into a `NARRATIVE` condition.

### Effect (sub-document of SFX and life-path entries)

Declarative effect — describes *what* changes, not *how*. Shared by SFX and life-path consequences. The canonical spec and full `type`/`action` vocabulary are in [[SFX and Effects#Unified Effect Model]].

| Field | Type | Description |
|-------|------|-------------|
| `timing` | EffectTiming | When it fires (see [[#EffectTiming]]; default `immediate`) |
| `type` | string | Effect type (e.g. `modify_trait`, `transfer_razmerit`, `life_path`, `relationship`) |
| `action` | string | What to do (e.g. `gain`, `step_up`, `gain_or_step_up`, `step_down`, `set`, `earn`, `spend`, `next_step`) |
| `target` | string | Legacy single-reference fallback: an id, `"self"`, or a `{choose_*}` / `{random:*}` token |
| `entity` | string | Explicit subject entity; `""` or `"self"` = the applying entity |
| `result` | string? | Die, integer, relationship type, or "" |
| `target_scope` | string? | Optional narrowing for runtime target choice |
| `entity_scope` | string? | Optional narrowing for runtime entity choice |
| `target_filter` | dict | Candidate field predicates (e.g. `{"starter_location": true}`) |
| `die_filter` | dict | Roll-die predicates for roll-deferred effects (e.g. `{"role": null}`) |
| `conditions` | Condition[] | Per-effect gate (reuses the SFX condition model) |
| `negative` | bool | Trait-grant effects only: bake the created trait as negative polarity |
| `context` | object? | Optional dict (e.g. relationship description, `learner`, `steps`) |
| `duration` | EffectDuration? | When set, schedules the inverse effect on expiry |
| `target_spec` | TargetSpec? | Structured targeting pipeline (the new model); null = legacy `target` string, lazily migrated |
| `entity_spec` | TargetSpec? | Structured subject resolution (who the effect applies to) |
| `refs` | dict[str, TargetRef] | Named multi-target references; `target`/`entity` are the legacy single-reference fallback |

### `relationships` (edge)

Entity-to-entity connections.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Deterministic: `edge:{from}:{to}:{type}` |
| `_from` | string | ✅ | `entities/{from_id}` |
| `_to` | string | ✅ | `entities/{to_id}` |
| `type` | string | ✅ | `super`, `transversal`, `relation`, `associate`, `commands`, `membership`, `agency`, `support` |
| `description` | string | | Optional description (e.g. relationship narrative) |
| `main` | bool | | On `agency` edges only: whether the entity is one of the player's mains (see [[Troupe Play]]) |

### `sfx_owners`

Named SFX-owner buckets — collect SFX ids available by category rather than by a single entity/trait/projection.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `table`, `gm` |
| `sfx_ids` | string[] | | SFX ids available to this owner bucket |

### `plan_entities` (GM draft staging)

Draft entities staged before publication — writes go here, not to `entities`, until a plan is published.

| Field | Type | Description |
|-------|------|-------------|
| `_key` | string | `{plan_id}:{draft_ref}` (e.g. `emberline:u-emberline`) |
| `plan_id` | string | Owning plan |
| `draft_ref` | string | Plan-local reference id |
| `name` / `type` / `universe` / `location` / `razmerit` / `owned_by` / `unpublished` | — | Mirrors `entities` fields |

### `plan_relationships` (GM draft staging, edge)

| Field | Type | Description |
|-------|------|-------------|
| `_from` / `_to` | string | `plan_entities/{from}` → `plan_entities/{to}` |
| `plan_id` | string | Owning plan |
| `type` | string | Relationship type (e.g. `super`) |
| `description` | string | Optional |

### `scheduled_events`

Persisted timed reverts fired centrally when their timers expire.

| Field | Type | Description |
|-------|------|-------------|
| `_key` | string | Unique id |
| `target_type` | string | `entity` \| `trait_setting` |
| `target_id` | string | Entity id or trait-setting id |
| `effect` | Effect | The revert effect to apply |
| `timers` | Timer[] | Countdowns that drive expiry |
| `combine` | TimerCombine | `first_to_fire` \| `all_transpired` |
| `source_sfx_id` | string? | Originating SFX |

### `players`

Player identity for session persistence.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | `player-{hex6}` (e.g. `player-bc80b9`) |
| `name` | string | ✅ | Player display name |
| `role` | string | | `player` or `architect` (default `player`) |
| `last_spotlight_at` | string? | | ISO timestamp of when this player last took control of a main (spotlight recency sort key) |
| `last_main_entity_id` | string? | | The main entity the player last took control of (stored, not derived) |


### `entity_images`

Metadata for a generated image stored per-entity, per-universe. Files live at `media/imagen/{entity_id}/{universe}/{image_id}_{variant}.{ext}`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | UUID |
| `entity_id` | string | ✅ | Owning entity |
| `projection_id` | string? | | Owning body; empty = entity-level default (fallback for any body) |
| `universe` | string | ✅ | Universe key |
| `image_type` | ImageType | ✅ | `uploaded`, `imagen`, or `animated` |
| `roles` | string[] | | `background`, `sheet`, `navdot` |
| `prompt` / `negative_prompt` | string | | Generation prompts |
| `loras` | string[] | | LoRA tags |
| `width` / `height` / `seed` / `steps` | int | | Generation parameters |
| `filename` | string | | Base filename without variant suffix/extension |
| `extension` | string | | `png` (or `webp`, etc.) |
| `created_at` | string | | ISO 8601 |

### `historical_records`

Append-only historical events (Blue Book / change log).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Record id |
| `entity_id` | string | | Owning entity |
| `record_type` | HistoricalRecordType | | `roll_table`, `contest`, or `transversal` |
| `universe` | string | | Universe key |
| `session_id` | string | | Session the event happened in |
| `data` | dict | | Type-specific payload |
| `created_at` | string | | ISO 8601 |

### `life_paths`

Life-path definitions — an entry point into a graph of linked roll tables. Discovery gating is optional.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `lp-...` |
| `name` | string | ✅ | Display name |
| `universe` | string | ✅ | Universe key |
| `description` | string | | Explainer text |
| `entry_table_id` | string | | `_key` of the first RollTable in the flow |
| `discovery` | DiscoveryBlock? | | Discovery conditions; null = always visible |

### `messages`

Persistent in-fiction messages between entities.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Message id |
| `sender_entity_id` | string | ✅ | Sending entity |
| `recipient_entity_id` | string | ✅ | Receiving entity |
| `kind` | MessageKind | | `letter`, `journal`, `report`, or `gm_note` |
| `title` / `body` | string | | Content |
| `images` | string[] | | Media paths |
| `after_ids` | string[] | | Ordering: message ids this follows |
| `threads` | string[] | | Thread tags |
| `created_at` | string | | ISO 8601 |

### `roll_tables`

Reusable roll tables whose entries execute effects when selected.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `rt-...` |
| `name` | string | ✅ | Display name |
| `universe` | string | | Universe key |
| `life_path` | string? | | Owning life-path id; null = shared/general |
| `scheme` | RollTableScheme | | `range`, `weight`, `tier`, or `index` (default `range`) |
| `roll_source` | RollSource | | `fixed_die` or `trait_dice` |
| `trait_dice_count` | int | | Number of trait dice to roll (`trait_dice`; N=1 for now) |
| `die` | DieType | | Die size for range/index rolls |
| `check` | RollTableCheck? | | Legacy dice-pool check; unused |
| `entries` | RollTableEntry[] | | Ordered entries |
| `canvas_x` / `canvas_y` | float? | | Canvas layout persistence |


## Sub-Models

### Zone

Sub-area within a location, embedded in `entities.zones`.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name |
| `x` | float | Percentage X position on background image (0–100, default `50`) |
| `y` | float | Percentage Y position on background image (0–100, default `50`) |
| `background_image` | string? | Optional zone-specific image |


### TraitDisplayName

Dynamic display name for a trait.  When an entity's dice rating matches a
``ratings`` entry in the matching ``universe``, this name replaces the trait's
base ``name`` in the UI.  First match wins; fallback is the base name.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name (e.g. `Dao Sliver`, `Divine Consciousness`) |
| `universe` | string | Universe key (e.g. `earth`, `three_realms`) or `*` for any |
| `ratings` | DieType[][] | Dice-combination alternatives that trigger this name (order-independent) |

### Die Roll Models

| Model | Purpose |
|-------|---------|
| `DieRoll` | Single die result: `die` (DieType), `result` (int), `source` (string) |
| `Opposition` | Challenge specification: `type`, `dice` array, `challenge_die`, `static_difficulty` |
| `DicePoolRequest` | Roll request: `entity_id`, `universe`, `dice` array, `opposition`, `razmerit_spent` |
| `SimplifiedResult` | 1–2 die pipeline result: `rolls`, `highest`, `tier`, `effect_die`, `hitches`, `botch` |
| `PoolResult` | 3+ die pipeline result: `rolls`, `kept`, `total`, `effect_die`, `unused`, `hitches`, `botch` |
| `ChallengeResult` | Challenge pool outcome: `targeted_die`, `effect_die`, `outcome`, `new_challenge_rating` |
| `ContestResult` | Head-to-head result: `winner`, `player_result`, `opponent_result`, `pushed`, `push_cost` |
| `PoolAssembly` | Per-location dice pool tracking: `entity_id`, `location_id`, `dice` array, `opposition_entity_id`, `pushed_this_beat` |

### Condition

A configurable, automatically-evaluated gate or limit (parallel to `Effect`).

| Field | Type | Description |
|-------|------|-------------|
| `type` | ConditionType | Which predicate to evaluate (default `always`) |
| `subject` | string | `""` = current entity; else literal id or `{variable}` |
| `target` | string | trait / location / entity id (or `{variable}`) |
| `value` | string? | Threshold (e.g. rank number) |
| `operator` | string | Numeric comparator for `has_razmerit` (`<`, `<=`, `==`, `!=`, `>=`, `>`) |
| `narrative` | string | Human-readable fallback text |
| `spec` | TargetSpec? | `target_path`: a targeting path resolved non-empty |

`ConditionType` values: `always`, `at_location`, `has_trait`, `has_effective_trait`, `has_trait_in_traitset`, `has_relationship`, `trait_rating`, `has_razmerit`, `entity_type`, `user_role`, `narrative`, `unplaced`, `in_universe`, `phase`, `contest_outcome`, `hitch`, `roll_tier`, `test_outcome`, `source_rating`, `target_path`.

### Attunement

Active temporary addition of a universe to an entity's effective universes (stored on `Entity.attunements`).

| Field | Type | Description |
|-------|------|-------------|
| `universe` | string | Universe key |
| `scope` | AttunementScope | `self` (entity only) or `domain` (occupants in its location subtree) |
| `until` | EffectTiming? | Expiry timing (driven by the effects system) |
| `source_sfx_id` | string? | Originating SFX |

### TargetingBan

Directional ban: the owning entity may not target `target_id`. Expiry is driven by a scheduled event.

| Field | Type | Description |
|-------|------|-------------|
| `target_id` | string | The entity id that is banned as a target |

### Timer / EffectDuration

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Advancement signal: `beat`, `scene`, `session`, or a state-change event (e.g. `location_changed`) |
| `remaining` | int | Countdown; `0` (or event `immediate`) fires on the next pass |

`EffectDuration` = `{ timers: Timer[], combine: TimerCombine }` where `TimerCombine` is `first_to_fire` or `all_transpired`. Turns a forward effect into a temporary one (schedules the inverse on expiry).

### TargetRef / TargetSpec

| Field | Type | Description |
|-------|------|-------------|
| `value` | string | Concrete id after resolution — or, before resolution, a literal id / `self` / `{choose_*}` / `{random:*}` token |
| `spec` | TargetSpec? | Structured pipeline resolving `value` at fire time (null = literal) |
| `scope` | string? | Narrows runtime choice for `{choose_*}` / `{random:*}` |

`TargetSpec` is an ordered `steps` list of `select` / `filter` / `navigate` / `aggregate` / `literal` / `random` / `choose` / `evaluate` steps (the structured, type-checked targeting pipeline; see [[Targeting Model]]).

### ConsequenceOption

Selectable entry in the post-roll consequence menu.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Option id |
| `label` | string | Display label |
| `side` | string | `player`, `gm`, or `either` |
| `effects` | Effect[] | Effects to apply |
| `source` | string | `base`, `entity`, or `sfx` |

### RollTableEntry / RollTableCheck

`RollTableEntry` (per entry; which fields are meaningful depends on the table `scheme`):

| Field | Type | Description |
|-------|------|-------------|
| `label` / `description` | string | Display / flavor |
| `min_value` / `max_value` | int? | range scheme |
| `weight` | int? | weight scheme |
| `tier` | OutcomeTier? | tier scheme |
| `conditions` | Condition[] | Entry gates |
| `effects` | Effect[] | Effects executed on selection |

`RollTableCheck` (legacy dice-pool check metadata): `trait_ids`, `difficulty` (DieType, default d6), `free_choice` (bool).

`RollTableScheme`: `range`, `weight`, `tier`, `index`. `RollSource`: `fixed_die`, `trait_dice`.

### Life-path sub-models

`DiscoveryBlock` (discovery conditions — any one met → discovered): `at_location` (string[]), `knows_entity` (string[]), `possesses_trait` (string[]), `has_trait_rating` (dict[trait→DieType]), `has_relationship` (string[]).

`Enrollment` (a character's membership in a faction's life path): `faction_id`, `path_id`, `mustered` (bool), `mishap_muster` (bool).

`PendingTerm` (in-progress term checkpoint): `faction_id`, `path_id`, `current_table_id`, `continuation` (string[]), `return_map` (dict).

### Small enums

- `ImageType`: `uploaded`, `imagen`, `animated`
- `MessageKind`: `letter`, `journal`, `report`, `gm_note`
- `HistoricalRecordType`: `roll_table`, `contest`, `transversal`

---

## Assembled Views

### CharacterView

Built by the repository, not stored. Assembles entity + projections + trait settings into a single response.

| Field | Source |
|-------|--------|
| `entity` | `entities` collection |
| `projections` | `projections` collection (keyed by universe) |
| `trait_settings` | `traitsettings` edges (filtered by effective universe) |

---

## Indexes

| Collection | Index | Type | Purpose |
|-----------|-------|------|---------|
| `entities` | `type` | hash | Filter by entity type |
| `entities` | `current_universe` | hash | Filter by universe |
| `entities` | `current_location` | hash | Find entities at a location |
| `entities` | `known_to[*]` | persistent | Array membership queries |
| `projections` | `entity_id` | hash | Find projections for entity |
| `projections` | `universe` | hash | Filter by universe |
| `traits` | `[name, universe]` | hash (unique) | Lookup trait by name in universe |
| `traits` | `traitset_id` | hash | Find traits in a set |
| `traits` | `universe` | hash | Filter by universe |
| `traitsets` | `[name, universe]` | hash (unique) | Lookup traitset by name in universe |
| `traitsets` | `universe` | hash | Filter by universe |
| `traitsettings` | `entity_id` | hash | Find all trait settings for entity |
| `traitsettings` | `trait_id` | hash | Find entities with a given trait |
| `traitsettings` | `traitset_id` | hash | Find settings in a traitset |
| `sfxs` | `name` | hash (unique) | Lookup SFX by name |
| `relationships` | `type` | hash | Filter edges by relationship type |

---

## ID Conventions Summary

| Entity type | Prefix | Example |
|-------------|--------|---------|
| Character | `{slug}-{n}` | `kael-1` |
| Location | `loc-{key}` | `loc-74560187` |
| Faction | `faction-{key}` | `faction-895820` |
| Asset | `asset-{key}` | `asset-12345` |
| GMC | `gmc-{key}` | `gmc-67890` |
| Universe | `universe-{key}` | `universe-earth` |
| TraitSet | `ts-{slug}-{hash4}` | `ts-attributes-8f3a` |
| Trait | `trait-{slug}-{hash4}` | `trait-hacking-7f2a` |
| TraitSetting | `{entity}:{trait}` | `kael-1:trait-hacking-7f2a` |
| SFX | `sfx-{slug}` | `sfx-hinder` |
| Relationship | `edge:{from}:{to}:{type}` | `edge:loc-platform:loc-valley:super` |
| Projection | `{entity}:{origin_universe}` | `kael-1:three_realms` |

---

## Effective Trait Resolution

Traits resolve from `effective_universes` — the active projection's universe plus any unexpired attunements:

1. **Ego traits** — always available (`from_type = entity`)
2. **Morph traits** — available iff the trait's `origin_universe` is in `effective_universes` (`from_type = projection`)

See [[Projections and Transversal]] for the canonical model and [[Entities and Traits#Ego and Morph]] for the ego/morph split.

---

## Next

- [[System Architecture]] — Service layer and data flow
- [[API Contract]] — GraphQL and REST endpoints
- [[Entities and Traits]] — Game design: how entities, ego/morph, and projections work in play

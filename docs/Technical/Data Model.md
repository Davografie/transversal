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
| `relationships` | **Edge** | Entity → Entity connections | `entities/{from}` → `entities/{to}` |
| `roll_tables` | Document | Reusable roll tables; entries execute effects | — |
| `sfxs` | Document | SFX registry — trigger, timing, cost, effects | — |
| `traits` | Document | Trait registry — what traits exist per universe | — |
| `traitsets` | Document | Trait grouping registry (attributes, skills, cultivation, etc.) | — |
| `traitsettings` | **Edge** | Trait assignment (ego→entity, morph→projection, relation→relationship) | entity / projection / relationship → trait |

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
| `relation` | arbitrary | Generic relationship between entities |
| `archetype` | instance → archetype | Entity inherits from archetype template |
| `agency` | player → entity | Player ownership / control of an entity |

---

## Collection Schemas

### `entities`

Core entity metadata. Every significant thing in Transversal is an entity. Traits live in separate collections — the entity is the hub that trait settings connect to.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Entity ID (e.g. `kael-1`, `loc-krasnoyarsk`, `universe-earth`) |
| `type` | EntityType | ✅ | `character`, `location`, `faction`, `asset`, `gmc`, `universe` |
| `name` | string | ✅ | Display name |
| `razmerit` | int | ✅ | Global hyper-dimensional currency (default `0`) |
| `current_universe` | string | ✅ | Universe key (e.g. `earth`, `three_realms`) |
| `current_location` | string? | | Entity ID of current location (`null` for universes and root locations) |
| `hidden` | bool | | Visibility flag (default `false`) |
| `known_to` | string[] | | Entity IDs that know about this entity (faction conspyramid) |
| `background_image` | string? | | URL path to location background (e.g. `/media/loc-krasnoyarsk.webp`) |
| `zones` | Zone[] | | Sub-areas within a location (see [[#Zone]]) |
| `map_x` | float? | | Percentage X position on location background (0–100) |
| `map_y` | float? | | Percentage Y position on location background (0–100) |
| `overlay` | string? | | Visual overlay preset: `mist`, `fire`, `rain`, `snow`, `sparkles`, `fog` |
| `nav_positions` | dict | | Navigation dot positions per edge type (e.g. `{"parent": {"x": 90, "y": 15}}`) |
| `node_ids` | string[] | | Faction conspyramid node entity IDs |
| `owned_by` | string? | | Owner entity ID (for assets) |

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
| `_key` | string | ✅ | Projection ID (e.g. `kael-1:three_realms`) |
| `entity_id` | string | ✅ | Entity this projection belongs to |
| `universe` | string | ✅ | Universe key |
| `transversal_type` | TransversalType | | `native`, `consciousness`, or `inapposite` (default `native`) |

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
| `default_rating_type` | RatingType | | Default rating behaviour for new traits in this set (default `static`) |
| `default_die_type` | DieType | | Default die for new traits in this set (default `d4`) |
| `polarity` | Polarity? | | Default polarity override for traits in this set (null = global positive) |

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
| `explanation` | string | | Flavor or rules explanation text |
| `random_weight` | int | | Weight for random trait generation (default `0`) |

**ID convention:** `trait-{slug}-{hash4}` — same pattern as traitsets. The 4-char hex hash is `md5(slug + ":" + joined_universes)[:4]`. Examples: `trait-hacking-7f2a` (Earth), `trait-qi-reserves-1e5b` (Three Realms).

### `traitsettings` (edge)

Per-entity trait configuration. The edge connects an entity to a registry trait, carrying the entity's specific dice, statement, SFX unlocks, and location restrictions.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `kael-1:trait-hacking-7f2a` |
| `_from` | string | ✅ | `entities/{entity_id}` |
| `_to` | string | ✅ | `traits/{trait_id}` |
| `entity_id` | string | ✅ | Denormalized for query convenience |
| `trait_id` | string | ✅ | Denormalized |
| `traitset_id` | string | ✅ | Denormalized |
| `rating_type` | RatingType | | `static`, `resource`, `challenge`, `empty` (default `static`) |
| `dice` | DieType[] | | Currently-available dice this trait contributes (e.g. `[d4, d4, d4, d4]` for a full 4d4 resource). For a resource this is the unspent remainder |
| `spent_dice` | DieType[] | | Spent-but-recoverable dice (resource pools). Capacity = `dice + spent_dice`; recovery moves a die back into `dice` |
| `polarity` | Polarity | ✅ | Baked sign: `positive` (benefit/asset) or `negative` (complication). Resolved from trait/traitset defaults at creation |
| `statement` | string | | Distinction statement or flavor text |
| `ego` | bool | | If `true`, persists across all universes/projections |
| `sub_trait_settings` | TraitSetting[] | | Nested sub-trait configurations |
| `sfx_ids` | string[] | | SFX IDs unlocked for this entity on this trait |
| `locations_enabled` | string[] | | Location entity IDs where this trait is active |
| `locations_disabled` | string[] | | Location entity IDs where this trait is suppressed |
| `known_to` | string[] | | Entity IDs that know about this trait setting |

**ID convention:** `{entity_id}:{trait_id}` (e.g. `kael-1:trait-hacking-7f2a`)

**Key pattern** — `_key` uses deterministic format: `entity_id + ":" + trait_id` for direct entity traits. Ego trait keys may include `:ego:` segment. Multi-universe traits for the same entity use distinct keys per registry trait.

### `sfxs`

SFX (Special Effect) registry. Defines named abilities with triggers, costs, and declarative effects.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `sfx-law-bridge`, `sfx-overcharge` |
| `name` | string | ✅ | Display name |
| `description` | string | | Flavor text and usage notes |
| `trigger` | string | ✅ | When the SFX auto-fires (or `manual` for player-activated): `manual`, `on_roll`, `on_result`, `on_complication`, `on_botch`, `on_success`, `on_failure`, `on_contest_win`, `on_contest_loss`, `on_give_in`, `on_push`, `on_taken_out`, `on_prevent_taken_out`, `on_location_change`, `on_trait_change`, `on_trait_learn`, `on_trait_offered`, `on_relationship_create` |
| `menu_context` | string? | | Consequence menu this SFX appears in (e.g. `test_success`, `contest_win`, `contest_give_in`, `hitch`); null = trigger-driven |
| `conditions` | Condition[] | | Optional gates evaluated against the entity before firing |
| `effects` | Effect[] | | List of declarative effects |

**ID convention:** `sfx-{slug}` (e.g. `sfx-hinder`, `sfx-law-bridge`)

### Effect (sub-document of SFX and life-path entries)

Declarative effect — describes *what* changes, not *how*. Shared by SFX and life-path consequences. The canonical spec and full `type`/`action` vocabulary are in [[SFX and Effects#Unified Effect Model]].

| Field | Type | Description |
|-------|------|-------------|
| `timing` | string | `immediate`, `end_of_beat`, `end_of_scene`, `end_of_session`, `after_beats`, `on_condition` |
| `type` | string | Effect type (e.g. `modify_trait`, `transfer_razmerit`, `life_path`, `relationship`) |
| `action` | string | What to do (e.g. `gain`, `step_up`, `gain_or_step_up`, `step_down`, `set`, `earn`, `spend`, `next_step`) |
| `target` | string | An id, `"self"`, or a `{choose_*}` placeholder |
| `entity` | string? | Explicit subject entity; `""` or `"self"` = the applying entity |
| `result` | string? | Die, integer, relationship type, or "" |
| `target_scope` | string? | Optional narrowing for target choice |
| `entity_scope` | string? | Optional narrowing for entity choice |
| `negative` | bool | Trait-grant effects only: bake the created trait as negative polarity |
| `context` | object? | Optional dict (e.g. relationship description, `learner`, `steps`) |
| `duration` | EffectDuration? | When set, schedules the inverse effect on expiry |

### `relationships` (edge)

Entity-to-entity connections.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | Deterministic: `edge:{from}:{to}:{type}` |
| `_from` | string | ✅ | `entities/{from_id}` |
| `_to` | string | ✅ | `entities/{to_id}` |
| `type` | string | ✅ | `super`, `transversal`, `relation`, `archetype`, `agency` |

### `players`

Player identity for session persistence.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | `player-{hex6}` (e.g. `player-bc80b9`) |
| `name` | string | ✅ | Player display name |
| `role` | string | | `player` or `architect` (default `player`) |


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

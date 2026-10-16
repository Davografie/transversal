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
| `historical_records` | Document | Blue Book — change log and history | — |
| `images` | Document | Image metadata, owned by an entity, a projection **or a trait** ([[B200]]) | — |
| `join_tokens` | Document | Campaign admission token *liveness* (SEC-3) — id, minted/expires/closed. The token itself is signed and self-describing; this exists so a window can be closed early | — |
| `life_paths` | Document | Life-path catalog (sect, guild, career terms) | — |
| `messages` | Document | In-fiction messages / log entries | — |
| `players` | Document | Player identity for session persistence | — |
| `projections` | Document | Per-universe body — name, image, location, morph traits | — |
| `relationships` | **Edge** | Connections between entities, **bodies and players** (also anchors relation traits) | `entities` / `projections` / `players` → `entities` / `projections` |
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

> [!warning] `entity_images` is dead — `images` is the live collection
> `migrate_images_owner.py` **copied** `entity_images` to `images` (Arango has no
> rename) and left the old collection in place, so both exist and only one is read:
> measured 2026-09-29, `entity_images` holds **1,134** rows that nothing reads and
> `images` holds **1,023** that everything does (`db/arango.py` registers `images`
> alone). This table named the dead one until 2026-09-29. A reader that enumerates
> collections, or an export that copies documents, must use `images`.


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

Edges split into **structural** wiring (the graph traverses these for hierarchy,
ownership, membership, travel, authority, cast) and one **personal** type
(`relation`) that carries narrative posture as relationship traits.

| Type | Direction | Meaning |
|------|-----------|---------|
| `super` | child → parent | Location hierarchy — *a sub-place of* when both ends are locations, ***carried by*** when the parent is not (see below) |
| `transversal` | bidirectional | Portal / traversal connection between locations |
| `membership` | member → faction | Entity is on a faction's **roster** (rank/role hang here) |
| `agency` | player → entity | Player ownership / control (carries the `main` flag) |
| `commands` | GMC → GMC | Command chain within a conspiracy (conspyramid authority) |
| `support` | SC → main | Support character belongs to a main's cast |
| `relation` | entity → entity | The single personal type — narrative posture lives as relationship traits |

Retired: `associate`, `gifted`, `suspects`, `hostile_to` collapse onto `relation`
(their meaning lives in the trait / `description` / trait-setting `source_type`).
See `STRUCTURAL_RELATIONSHIP_TYPES` in `domain/__init__.py` for the source of truth.

> [!important] Carried locations — one edge, two meanings, told apart by the parent's kind ([[B308]])
> A `super` edge whose **parent is not a location** means the child location is **carried
> by** that entity, not contained in it. A cultivator's inner world; a pocket realm; a
> formation anchored to its caster. Nothing distinguishes them in storage — the endpoint's
> *type* is the whole of it — so the reads must filter on it, and there are two:
>
> - `EntityRepository.get_locations_carried_by(entity_ids)` → `{carrier_id: [location, …]}`
> - `get_location_carriers(location_ids)` → `{location_id: carrier}`
>
> surfaced as **`Entity.carriedLocations`** and **`Entity.carrier`** (batched through
> request-scoped DataLoaders). Live example: `loc-345978606` *Phaos Tyish Qihai* (universe
> `earth`) is carried by `character-20809` *Phaos Tyish* (universe `three_realms`) — note
> the two universes **disagree**, which is why a carried location is never re-homed by
> walking the tree and why a carrier is not filed among a universe's places.
>
> **The asymmetry is enforced, and only one way:**
> `validate_relationship` refuses a `super` edge whose **child** is not a location, and
> permits one whose parent is not. A non-location child is the same corruption from the far
> side — a character rendered as a leaf inside the location tree — and 0 live edges have
> ever been one.
>
> `location_tree()` reports a carrier as `node_type: "carrier"` with its own name and
> universe (it used to be gap-filled as `{name: <the id>, universe: ""}`, which made it a
> top-level node *beside the universes* named by its key), marks the node below it
> `carried: true`, and reports an edge endpoint that no longer exists as
> `node_type: "unknown"`. Read [[B308]] for the reasoning; a travel/entry mechanic and a
> `create_location` action are [[B309]] and do **not** exist yet.


> [!important] Roster vs association — the direction rule
> Two reads ask different questions of the same edges, and the difference is
> direction plus traits:
>
> - **Roster** (`get_faction_roster` → `factionMembers`): a slot is a `membership`
>   edge **or** a `relation` tie carrying `role`/`rank` — the shape the migrated
>   sect rosters are in, which is why the read matches those traits by **name**
>   (the registry holds two traits called `role`). Only **member → faction**
>   counts. The reverse tie is the organisation's *posture* toward someone
>   (Azure Dawn's "outer sect disciple") and is never a slot.
> - **Association** (`get_factions_for_entities` → `entityFactions`): *any* tie to
>   a faction, **either direction** — a posture is an association. One pair can
>   hold both (measured live 2026-09-16: **333 mirrored pairs**), so it reports the
>   two directions' tie types separately; `outTieType` is the edge a role write
>   belongs on.
>
> `membership` may be held by a character, GMC or asset
> (`MEMBERSHIP_HOLDER_TYPES`); a location may not.

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
| `support_eligible` | bool | | GMC may be taken over as a support character (default `false`) |
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
| `attunements` | Attunement[] | | Projection grants — bodies made live (`attune`) or cut off (`suppress`); see [[#Attunement (projection grant)]] |
| `targeting_bans` | TargetingBan[] | | Directional contest-target bans |
| `taken_out` | bool | | Scene-scoped: high-stakes contest removed this entity from the scene |
| `total_dice_bonus` | int | | Delta over the base total-dice keep limit (2); adjusted by `modify_dice_limit` effects (default `0`) |
| `effect_dice_bonus` | int | | Delta over the base effect-die keep limit (1); adjusted by `modify_dice_limit` effects (default `0`) |
| `sfx_ids` | string[] | | SFX owned directly by this entity |
| `scheduled_events` | ScheduledEvent[] | | Pending timed reverts |
| `lora_config` | dict? | | Per-entity-type LoRA config (e.g. `{"CHARACTER": ["lora1"]}`) |
| `prompt_steering` | string | | Universe-only: free-text style steering appended to every prompt generated there |
| `naming_theme` | string | | Universe-only: which naming theme names here should sound like — a key from `services/name_generator` (`chinese`, `fantasy`, `alien`, …). `""` and an unknown key both mean the default, so a world may name a theme this build does not carry yet ([[Name Generation]], [[B82]]) |
| `palette` | dict? | | Universe-only: the universe's look — `dark`/`light` colour groups plus `font` and `radius`, applied by the frontend as `:root` overrides ([[UI-UX Design#The universe palette]]) |
| `life_paths` | Enrollment[] | | Life-path memberships (faction + path) |
| `active_universes` | string[] | | Faction-only: where active |
| `suitable_life_path_ids` | string[] | | Faction-only: offered paths |
| `discovered_life_paths` | string[] | | `_key`s of discovered paths |
| `pending_terms` | dict[str, PendingTerm] | | In-progress terms, keyed by `{entity_id}:{universe}` — one checkpoint per body |
| `pending_term` | PendingTerm? | | **Legacy** singular term state; the model still reads it (a checkpoint whose key could not be resolved) and the migration moves it into `pending_terms` |
| `destination_location` | string? | | Guided route: the objective a character has been given directions to (`next_hop` is measured from the location being viewed, not from this) |
| `trait_positions` | dict | | Sheet layout: `{traitsetting_id: {x, y}}`. The **key is a reference** — the only place a reference is stored as a map key rather than a value |
| `hitch_threshold` | int | | Dice-limit dial: the value a die must roll at or below to be a hitch (default `1`) |
| `prompt_include_ancestors` | bool | | Universe-only: whether an ancestor location's prompt material is folded into a descendant's |
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
| `explanation` | string | | What the set is for, in the author's words — the old app's `explainer`. Read through a legacy fold: documents the migration stored under `description` still answer, and the stale key leaves on the next write |
| `entity_types` | EntityType[] | | Which entity types can use this set |
| `order` | int | | Display sort order (default `0`) |
| `limit` | int | | Max traits an entity can select from this set (default `1`) |
| `allow_duplicates` | bool | | Allow multiple instances of the same trait definition. The **set** decides, not the text: a duplicate needs no `statement`, and each instance gets a key of its own (default `false`) |
| `sheet_tab` | SheetTab | | Which character-sheet tab this set's traits render on: `traits` (default) or `profile`. A deliberate authoring choice — the sheet does not infer it from the rating type, because a container trait carries no rating either |
| `polarity` | Polarity? | | Default polarity override for traits in this set (null = global positive) |
| `default_rating_type` | RatingType | | Default rating behaviour for new traits in this set (default `static`) |
| `default_die_type` | DieType | | Default die for new traits in this set (default `d4`) |

**ID convention:** `ts-{slug}-{hash4}` — slug is a human-readable name variant (e.g. `attributes`, `cultivation`). The 4-char hex hash is `md5(slug + ":" + joined_universes)[:4]`, ensuring keys are unique even when the same name appears in different universes. Examples: `ts-attributes-8f3a` (Earth), `ts-attributes-9d4e` (Three Realms).

> [!important] Two questions, one flag (B216)
> `allow_duplicates` is the **set's** rule — *may this set hold more than one instance of a definition?* —
> and it is **not** the same question as *is this specific instance already here?*, which keys on the
> instance's `statement`. They were conflated while a statement was also what made a duplicate's `_key`
> unique, so a duplicate-allowing set still refused a second instance whose statement happened to match.
> As of [[B216]]: the create path (`add_trait_setting`) and the repoint path
> (`trait_change._refuse_collision`) ask `may_hold_another` — the set's rule, and a duplicate needs **no**
> statement — while the effects **gain** path keeps asking `find_traitsetting_collision` (the instance's
> rule), because a repeated grant there is a no-op rather than a second copy. Read the caller before
> changing either.

### `traits`

Registry of all possible traits per universe. Shared definitions — not per-entity.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | e.g. `trait-hacking-7f2a`, `trait-qi-reserves-1e5b` |
| `name` | string | ✅ | Display name (e.g. `Hacking`, `Qi Reserves`) |
| `universes` | string[] | ✅ | Universe keys where this trait exists |
| `traitset_id` | string | ✅ | `_key` of parent traitset |
| `tags` | string[] | | Free-form labels a condition or targeting path can match on (e.g. `violent`) |
| `default_die_type` | DieType | | Die for untrained/new entities (default `d6`) |
| `default_rating_type` | RatingType | | Rating behaviour (default `static`) |
| `polarity` | Polarity? | | Default polarity override (null = inherit traitset) |
| `required_trait_ids` | string[] | | Prerequisite trait IDs |
| `possible_subtrait_ids` | string[] | | Sub-traits that can be nested under this trait |
| `possible_sfx_ids` | string[] | | SFX IDs unlockable for this trait |
| `default_ego` | bool | | Grant default: true = entity (ego/persists), false = projection (morph/gated) |
| `explanation` | string | | What the trait is, in the author's words — the old app's `explanation`, which the migration has carried since the registry landed |
| `random_weight` | int | | Weight for random trait generation (default `0`) |
| `display_names` | TraitDisplayName[] | | Dynamic display names keyed by dice rating + universe |
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
| `projection_id` | string? | | Projection anchor id when `from_type == "projection"` |
| `parent_traitsetting_id` | string? | | Parent TraitSetting id when `from_type == "traitsetting"` (sub-trait) |
| `rating_type` | RatingType | | `static`, `resource`, `challenge`, `empty` (default `static`) |
| `dice` | DieType[] | | Currently-available dice this trait contributes (e.g. `[d4, d4, d4, d4]` for a full 4d4 resource). For a resource this is the unspent remainder |
| `spent_dice` | DieType[] | | Spent-but-recoverable dice (resource pools). Capacity = `dice + spent_dice`; recovery moves a die back into `dice` |
| `capacity` | DieType[]? | | Challenge target (positive) / ceiling (negative); optional for resource pools |
| `polarity` | Polarity | ✅ | Baked sign: `positive` (benefit/asset) or `negative` (complication). Resolved from trait/traitset defaults at creation |
| `statement` | string | | Distinction statement or flavor text |
| `notes` | string | | Longer freeform notes |
| `order` | int? | | Author's position among siblings — the children of one parent container. `null` means unordered: those sort after the ordered ones, by trait set, trait id, then key (a total order, so reads are stable) |
| `tags` | string[] | | Labels set on this *instance*. Matching sees these **plus** the registry trait's own `tags` (B116) |
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
| `scheduled_events` | ScheduledEvent[] | | Pending timed reverts |

**ID convention:** `{entity_id}:{trait_id}` for entity/projection anchors; `{anchor_id}:{trait_id}` for relationship anchors; parent + suffix for sub-traits. A duplicate-allowing set seeds the suffix from the instance's `statement` when it has one and adds a taken-key suffix when it doesn't — see [[#ID Conventions Summary]].

> [!note] The set is not recorded here (B209)
> A setting carries **no** `traitset_id`: which set it belongs to is a fact about its registry trait (`_to`),
> reached through `trait_id`. The field used to be stored and could only ever drift, since a trait moving
> between sets had nothing to propagate the copy. 10,752 live documents still carry the dead key; nothing
> reads it. Detail: [[B209]].

> [!note] Sub-trait chains
> A sub-trait (`from_type: "traitsetting"`) has no anchor of its own — it is anchored to its parent,
> so **`ego` follows the root of the chain** rather than the immediate parent: a child of an
> entity-anchored trait is ego too. The chain must be a **path**; `create_traitsetting` and
> `update_traitsetting` refuse a re-parent that would put a setting under its own descendant
> (`_would_cycle`), because a loop would make every ancestor walk spin or lie. Neither rule is
> enforced by a schema — both live in code.

> [!tip] Containment is not reference
> A sub-trait is *contained*: it does not exist outside its parent and is deleted with it. A trait
> that only *points at* another trait — two guns sharing one ammunition pool — is a different thing
> and does **not** exist yet; see [[Shortcut Traits Design Log]].

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

> [!note] The pair is addressable before it exists (B228)
> A trait-set setting is an **override**, not a relationship: `limit = null` means *the set's
> registry default* and `sfx_ids = []` means *no set-level rules*, so an absent document says
> "nothing has been overridden", **not** "this pair is invalid". Its `_key` is therefore a pure
> function of the pair — `{entity_id}:{traitset_id}`, the shape both writers that have ever minted
> one already use (`migrate_traitsetsettings`, `effects_applier._apply_set_traitset_limit`) — read
> through `services/traitset_settings.py`, which resolves **stored-or-default** and **upserts on
> write** (the first write is what creates the document).
>
> Three measured consequences. **92 live rows**, of which **75 carry no information** (their limit
> equalled the registry default) and **0 carry an SFX**. A set-level rule attaches sparsely, and
> until this landed nothing could create the row it needed — `set_sfx_for_owner` refused every
> set-level attach for an entity without one. And enumerating the *defaults* instead would be
> **7,260 universe-aware (entity, set) pairs** whose entire content is "nothing", which is why the
> `entity → traitsetsettings` and `traitset → traitsetsettings` hops return **stored rows only**
> while a **named** pair resolves either way.

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
| `duration` | EffectDuration? | | How long the SFX stays **armed** once triggered; **null = nothing authored**, which for a roll-timing effect means no roll limit. Read only when arming those effects, so it does nothing for an all-immediate rule. It used to default to one roll — and because the editor round-tripped it, that default was written into 42 rules nobody had set (removed 2026-09-26) |

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

Connections between the things a connection can join: **entities, bodies and players**.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | `edge:{from}:{to}:{type}` **when minted by the canonical writer**, else an opaque id |
| `_from` | string | ✅ | `entities/{id}`, `projections/{id}` or `players/{id}` |
| `_to` | string | ✅ | `entities/{id}` or `projections/{id}` |
| `type` | string | ✅ | `super`, `membership`, `agency`, `transversal`, `commands`, `support`, `relation` |
| `description` | string | | Optional description (e.g. relationship narrative) |
| `main` | bool | | On `agency` edges only: whether the entity is one of the player's mains (see [[Troupe Play]]) |
| `transversal_type` | string? | | On `transversal` edges: the body policy the crossing used |
| `effects` | Effect[] | | A crossing may carry effects (`travel`), read on arrival |

> [!note] There are **two** key conventions live, and neither is enforced
> Measured 2026-09-29 over 1,532 edges: **1,301 carry an opaque numeric key** and 231
> carry the deterministic `edge:{from}:{to}:{type}`. Nothing in the model requires
> either, so an edge's key is not a fact to parse — resolve an edge by its
> `(_from, _to, type)` or read it by key, never by splitting the key.
>
> The endpoints are broader than "entity to entity": live today are
> `entities → entities` (1,448), `projections → projections` (41),
> `players → entities` (39, all `agency`) and `projections → entities` (4). A
> `projections → projections` tie is how one body holds a posture toward another;
> conflating the collection would have made `agency` a claim about an entity.


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

> [!note] Player presence (not persisted)
> "Online" state is in-memory only (`services/presence.py`): a player is online
> while they hold an SSE connection, plus a 10-minute grace window after the last
> connection drops. It is never written to Arango — the `onlinePlayers` GraphQL
> field reads this in-memory set.


### `images`

Metadata for an image stored per-owner, per-universe. The **owner is not always an
entity**: [[B200]] generalised it, so a trait or a trait instance can carry a picture
too, and the row says which with `owner_kind`. Files live at
`media/imagen/{entity_id}/{universe}/{image_id}_{variant}.{ext}`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_key` | string | ✅ | UUID |
| `owner_kind` | string | ✅ | `entity` or `trait` ([[B200]]) |
| `owner_id` | string | ✅ | The owning entity / trait / trait instance — **not** named `entity_id` |
| `entity_id` | string | ✅ | Denormalized owning entity, kept so the entity-facing reads stay one clause |
| `projection_id` | string? | | Owning body; empty = entity-level default (fallback for any body) |
| `universe` | string | ✅ | Universe key |
| `image_type` | ImageType | ✅ | `uploaded`, `imagen`, or `animated` |
| `roles` | string[] | | `background`, `sheet`, `navdot` |
| `prompt` / `negative_prompt` | string | | Generation prompts |
| `loras` | string[] | | LoRA tags |
| `width` / `height` / `seed` / `steps` | int | | Generation parameters |
| `filename` | string | | Base filename without variant suffix/extension. **The bytes are a file under `media/`, not a row** — a reference to an image is a reference to a filename |
| `extension` | string | | `png` (or `webp`, etc.) |
| `animated_extension` | string | | Set when an animation exists alongside the still |
| `variant_id` | string? | | Groups a cutout/variant set |
| `renders` | string[] | | Derived renders that exist (e.g. `cutout`) |
| `transparent` | bool | | Whether the still has an alpha channel |
| `flags` | string[] | | e.g. `ai_generated` |
| `credits` | object[] | | `{role, name, url}` — provenance for a sourced image |
| `credit_text` / `license` | string | | Attribution, rendered and stored |
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

Sub-area within a location, embedded in `entities.zones`. A zone is a **link to a
child location** — it carries no name of its own; the dot's label is derived from
the linked child, so a rename can never leave a stale pin behind.

| Field | Type | Description |
|-------|------|-------------|
| `location_id` | string | **Required.** `_key` of the child location this pin opens |
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

### Attunement (projection grant)

A **projection grant**: a body made live, or cut off. Stored on `Entity.attunements`. The entity's *active projection set* is **derived** from these on read (see [[Active Projections Design Log]]).

| Field | Type | Description |
|-------|------|-------------|
| `op` | AttunementOp | `add` (attune — bring live) or `remove` (suppress — cut off); default `add` |
| `universe` | string? | Target form 1: every one of the carrier's bodies from this universe (used by `domain` grants, which cannot name one occupant's body) |
| `projection_id` | string? | Target form 2: one specific body (the `suppress` form) |
| `scope` | AttunementScope | `self` (entity only) or `domain` (occupants in its location subtree) |
| `until` | EffectTiming? | Expiry timing (driven by the effects system) |
| `source_sfx_id` | string? | Originating SFX |

Targets are resolved **read-time**, so a universe grant tracks bodies gained while the grant is live. Both forms generalise to a resolved targeting path (an `omni` grant is `navigate` along the **All projections** edge — not a flag).

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
| `cost_effects` | Effect[] | Effects that **pay** for the row — read before `effects`, and carrying the same reference shapes as any other effect list. On **169** live rows; documented since 2026-09-29 (an export that walked only `effects` would have dropped a row's cost) |
| `effects` | Effect[] | Effects executed on selection |
| `bound_variables` | BoundVariable[] | Names this row supplies to the effects above |

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

**Read as live, not as declared** — measured over the running database on 2026-09-29.
`_add_hash_index` swallows a creation failure, so the difference between these two is
not academic (see the warning below).

| Collection | Index | Type | Purpose |
|-----------|-------|------|---------|
| `entities` | `type` | hash | Filter by entity type |
| `entities` | `current_universe` | hash | Filter by universe |
| `entities` | `current_location` | hash | Find entities at a location |
| `entities` | `known_to[*]` | persistent | Array membership queries |
| `projections` | `entity_id` | hash | Find projections for entity |
| `projections` | `universe` | hash | Filter by universe |
| `traits` | `traitset_id` | hash | Find traits in a set |
| `traits` | `universe` | hash | Filter by universe |
| `traitsets` | `[name, universe]` | hash (unique) | Lookup traitset by name in universe |
| `traitsets` | `universe` | hash | Filter by universe |
| `traitsettings` | `entity_id` | hash | Find all trait settings for entity |
| `traitsettings` | `trait_id` | hash | Find entities with a given trait |
| `traitsettings` | `traitset_id` | hash | Legacy: the stored copy [[B209]] removed. Kept because 10,752 documents still carry the key |
| `traitsetsettings` | `entity_id` | hash | Find an entity's set-level overrides |
| `traitsetsettings` | `traitset_id` | hash | Find who has overridden a set |
| `images` | `owner_id` | hash | Find an owner's images (entity, trait or instance) |
| `images` | `[owner_id, universe]` | hash | The same, scoped to a world |
| `life_paths` | `universe` | hash | Filter by universe |
| `roll_tables` | `life_path` | hash | Find a life path's tables |
| `roll_tables` | `universe` | hash | Filter by universe |
| `plan_entities` | `plan_id` | hash | List a plan's drafts |
| `sfxs` | `name` | hash (unique) | Lookup SFX by name |
| `relationships` | `type` | hash | Filter edges by relationship type |

> [!warning] `traits (name, universe)` unique has **never existed**
> `db/arango.py` declares it; the live collection does not have it — verified
> 2026-09-29, and flagged by [[B88]] the same way. **57 duplicate groups / 64
> documents** share a name within one universe (e.g. `ablative armor`, `age`,
> `analyse`, all with `universe: null`), which is why the creation failed and why
> the failure was invisible: `_add_hash_index` catches and logs. Two live traits
> called `role` is the consequence, and it is not cosmetic — a lookup by name
> silently picks one, which is how the faction roster read returned `members: 0`
> for every faction ([[B88]], and the `8880e6cf` fix that matched by name anyway).


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
| TraitSetting | `{entity}:{trait}` (default) / `{entity}:{trait}:{hash8}` when `allow_duplicates` and the instance has a statement (the statement only *seeds* the key; the first instance under it keeps it) / `…-{hex6}` when a key is already taken — two instances are two instances however alike their text / `{parent}:{trait}[:{hash8}]` for a **nested** setting (keyed to its parent, so many settings of one generic trait can share a container, with the same taken-key suffix) | `kael-1:trait-hacking-7f2a` |
| SFX | `sfx-{slug}` | `sfx-hinder` |
| Relationship | `edge:{from}:{to}:{type}` **or an opaque id** — 1,301 of 1,532 live edges are opaque, so a key is never parsed (see [[#`relationships` (edge)]]) | `edge:loc-platform:loc-valley:super` |
| Projection | `{entity}:{origin_universe}` | `kael-1:three_realms` |

---

## Effective Trait Resolution

An entity's **active projection set** is the source of truth: `{current_projection}` plus `add` grants minus `remove` grants (self- and domain-scoped). `effective_universes` is a compatibility view over it — the universes of the active bodies.

Traits resolve from the active set:

1. **Ego traits** — always available (`from_type = entity`)
2. **Morph traits** — available iff the trait's anchoring projection is live (`from_type = projection`); the active-bodies path (`entity_manager.get_effective_traitsettings` with no explicit scope) gates **projection-native** (`ts._from ∈ active projections`), so two bodies in one universe do not share availability. An explicit `universes` scope still asks the coarser universe-scoped question.

`transversal_type` is provenance and is **never** read for availability; having several NATIVE bodies does not make them all live (see [[Projections and Transversal]]).

See [[Projections and Transversal]] for the canonical model and [[Entities and Traits#Ego and Morph]] for the ego/morph split.

---

## Next

- [[System Architecture]] — Service layer and data flow
- [[API Contract]] — GraphQL and REST endpoints
- [[Entities and Traits]] — Game design: how entities, ego/morph, and projections work in play

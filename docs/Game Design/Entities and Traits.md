---
title: Entities and Traits
tags:
  - transversal
  - game-design
  - entities
  - data-model
  - universes
aliases:
  - Entities
  - Entity System
---

# Entities and Traits

The Transversal backend manages the multiverse through **entities** spread across multiple collections — a graph of documents and edges that together represent the full game state.

## Data Model Overview

Seven ArangoDB collections power the entity system:

| Collection | Type | Stores |
|-----------|------|--------|
| `entities` | document | Name, type, razmerit, current universe/location, visibility |
| `projections` | document | Per-universe body grouping (entity_id, universe, body type) |
| `traits` | document | **Registry** — what traits exist per universe (shared definitions) |
| `traitsets` | document | **Registry** — named groupings of traits (attributes, skills, cultivation) |
| `traitsettings` | **edge** | **Per-entity** — entity → trait, carries dice: [DieType], type, statement, SFX unlocks |
| `sfxs` | document | SFX registry — trigger, timing, cost, effects |
| `relationships` | **edge** | Entity-to-entity connections (located_at, owns, allegiance) |

The graph path: `entity → traitsetting → trait → traitset → sfx`. This means "find all entities with qi_reserves d8+" is a graph traversal, not a nested array scan.

## Entity Model

Every significant thing in Transversal is an entity. Each entity has:

- **Type**: character, location, faction, asset, or GMC
- **Razmerit**: Global hyper-dimensional material balance — follows the entity across universes
- **Current universe and location**: Where the entity is right now
- **Visibility**: `hidden` flag and `known_to` list (for conspyramid faction nodes)

Entities carry **metadata only**. Traits live in separate collections — the entity is the hub that trait settings connect to.

```yaml
type: character
name: "Kael Drift"
razmerit: 3
current_universe: earth
current_location: "Krasnoyarsk-45"
```

## Universe Laws

Each universe defines its own trait registry — what traits exist and what actions are possible.

| Universe | Laws | Registry Traits | Example |
|----------|------|----------------|---------|
| **Earth** | Standard physics | hacking, shooting, persuasion, strength, agility | `trait-earth-hacking` |
| **The Three Realms** | Xianxia — dao, qi, cultivation | qi_reserves, dao_comprehension, sword_intent, footwork | `trait-3r-qi-reserves` |

Traits in the registry are shared — `qi_reserves` is defined once for the Three Realms, not duplicated per cultivator. Each trait declares:
- `default_die_type`: What an untrained entity starts with
- `default_rating_type`: Static, resource, challenge, or empty
- `possible_sfx_ids`: Which SFXs can be unlocked for this trait
- `location_restricted`: Whether the trait requires universe-specific laws

## Entity Types

### Locations

A **location** is a place in a specific universe. It carries zone definitions and a background image for the UI.

```yaml
type: location
name: "Krasnoyarsk-45"
current_universe: earth
background_image: "krasnoyarsk_winter.png"
zones:
  - name: "Town Square"
  - name: "Mountain Road"
```

```yaml
type: location
name: "Valley of Ascension"
current_universe: three_realms
background_image: "valley_of_ascension.png"
zones:
  - name: "The Arrival Platform"
  - name: "Verdant Steps Sect Grounds"
  - name: "The Mistwood"
```

### Characters

A **character** stores only metadata. Their traits are `TraitSetting` edges pointing into the trait registry, connected by `entity_id`.

```yaml
# Entity document
type: character
name: "Kael Drift"
razmerit: 3
current_universe: three_realms
current_location: "Valley of Ascension"
```

```yaml
# Projection documents (one per universe)
- id: "kael-1:earth"
  entity_id: "kael-1"
  universe: earth
  transversal_type: native

- id: "kael-1:three_realms"
  entity_id: "kael-1"
  universe: three_realms
  transversal_type: consciousness
```

```yaml
# TraitSetting edges (entity → trait registry)
- id: "kael-1:hacking"
  entity_id: "kael-1"
  trait_id: "trait-earth-hacking"       # → Earth hacking trait
  dice: [d10]
  rating_type: static

- id: "kael-1:qi-reserves"
  entity_id: "kael-1"
  trait_id: "trait-3r-qi-reserves"      # → Three Realms qi trait
  dice: [d4, d4, d4, d4]
  rating_type: resource

- id: "kael-1:curious"
  entity_id: "kael-1"
  trait_id: "trait-earth-curious"
  dice: [d8]
  rating_type: static
  ego: true                              # persists across all universes
  statement: "Can't leave a mystery alone"
```

### Factions

A **faction** is an organization. It can have conspyramid nodes — sub-entities at different hierarchy levels.

```yaml
type: faction
name: "Argent Meridian Sect"
razmerit: 80
current_universe: three_realms
node_ids: ["arg-merc-level1-ops", "arg-merc-level2-cell"]
```

### Assets

An **asset** is a significant item. It can be a signature item (fully statted) or an item package (single trait representing bundled gear).

```yaml
# Signature asset
type: asset
name: "The Jian of Still Waters"
current_universe: three_realms
current_location: "Krasnoyarsk-45"   # currently on Earth
owned_by: "Russian Federation — ARD"
```

Assets carry their own TraitSettings — the jian has `cutting_power d12` and `qi_resonance d10` as trait settings linked to its entity.

### GMCs

**GMCs** (Game Master Characters) are simplified entities — one distinction, one trait set, no razmerit pool. Used for troupe play companions and minor NPCs.

```yaml
type: gmc
name: "Elder Yun"
current_universe: three_realms
current_location: "Valley of Ascension"
```

## Trait Registry vs. Trait Settings

**Registry traits** define what can exist. **Trait settings** define what an entity actually has.

| Registry (`traits` collection) | Setting (`traitsettings` edge) |
|-------------------------------|-------------------------------|
| "Hacking exists on Earth, starts at d6" | "Kael has hacking at d10" |
| "Qi reserves is a resource trait, possible SFX: [Overcharge]" | "Kael has qi reserves at 4d4+7d6, unlocked SFX: [Overcharge]" |
| Shared by all entities | Unique per entity |

The separation means:
- Adding a new universe just means populating its trait registry — existing entities automatically gain access when they create a projection there
- SFX unlocking is per-entity — Kael's Overcharge is his; another cultivator might not have unlocked it
- Queries like "find all entities with qi_reserves ≥ d8" use graph traversal on the `traitsettings` edge collection

## Ego and Morph

Not all traits are universe-gated. **Ego traits** represent personality, core identity, and learned understanding that persists regardless of which body or universe the character inhabits.

| Tag | Persists across universes? | Example |
|-----|---------------------------|---------|
| **Ego** (`ego: true`) | Yes — always available | Curious d8, Antisocial d6, "Answered Antonov's Call" d8 |
| **Morph** (`ego: false`) | No — only in the trait's native universe | Hacking d10 (Earth only), qi_reserves d6 (Three Realms only) |

When the dice resolver assembles a pool for Kael in the Three Realms, it calls `get_effective_traitsettings(kael-1, "three_realms")`, which returns:
- All morph traits whose registry trait has `universe: three_realms` (cultivation, combat)
- All ego traits regardless of universe (curious, antisocial, distinctions)

Kael's hacking stays on Earth. His curiosity follows him everywhere.

## Projections

A **projection** is a per-universe body record — not a container for traits, but a marker that the entity has a presence in that universe.

| Field | Meaning |
|-------|---------|
| `entity_id` | Which entity this projection belongs to |
| `universe` | Which universe |
| `transversal_type` | native, consciousness, or inapposite |

Projections are separate documents in the `projections` collection. An entity has one projection per universe they've visited. Creating a new projection (via consciousness transversal to a new universe) creates a projection document and a set of baseline trait settings from that universe's registry.

## Location Spoofing (Attunement)

Attunement is not a persistent entity field. It is a **temporary SFX-triggered effect** that makes the entity's current location pretend to be in another universe for trait availability purposes.

**How it works:**
1. Kael is on Earth, holding the jian
2. He activates the jian's SFX "Law Bridge" (cost: 1 razmerit)
3. The effects system applies a **location spoof**: Kael's effective universe becomes `three_realms` for the duration
4. `get_effective_traitsettings` now returns Three Realms morph traits + ego traits
5. Kael can use qi_reserves and sword_intent on Earth
6. When the SFX expires (end of scene), the spoof ends — cultivation traits go dormant

The jian doesn't permanently attune Kael to the Three Realms. It gives him a temporary window. Want cultivation to work longer? Find more razmerit, maintain the SFX, or develop inapposite technology that doesn't require spoofing.

## Razmerit

Razmerit is **global** — one balance per entity, not per universe. It follows the entity's consciousness across universal boundaries. Spend it on SFX in the Three Realms; the balance drops. Earn it from a complication on Earth; it rises. The same pool, everywhere.

See [[Inspired Mechanics]] for razmerit spend/earn rates and the effects system integration.

## Relationships Between Entities

Entities connect through the `relationships` edge collection:

- **located_at**: Entity → Location (where something is)
- **owns**: Entity → Asset (who possesses what)
- **allegiance**: Entity → Faction (who belongs to whom)
- **contains**: Location → Location (zone hierarchy)
- **conspyramid_node**: Faction → Entity (faction node structure)

Relationships can carry their own trait settings — a relationship edge can have traits attached (e.g., "debt: 4d6 razmerit owed").

## Design Principle

> [!quote] Graph-Native Entities
> Transversal's data model is a property graph, not a document tree. Entities, traits, settings, and SFXs live in separate collections connected by edges. This means:
> - You can traverse from any entity to any trait, following the graph
> - The trait registry is a shared namespace — consistent across all characters
> - SFX unlocks are per-entity, not per-trait
> - Adding a universe is adding registry entries, not modifying entity schemas

## Next

- [[Core Mechanics]] — How trait settings become dice pools and action resolution
- [[Dice Mechanics]] — The rolling procedure
- [[SFX and Effects]] — How SFX unlock from the registry and fire through the effects system
- [[Setting and Narrative]] — The story of Earth, the Three Realms, and the jian
- [[System Architecture]] — ArangoDB collections, graph queries, and service layer

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
status: canonical
---

# Entities and Traits

The Transversal backend manages the multiverse through **entities** spread across multiple collections — a graph of documents and edges that together represent the full game state.

## Data Model Overview

Transversal's data model uses thirteen ArangoDB collections in a property graph — entities, traits, settings, and SFXs live in separate collections connected by edges. The full schema, field definitions, edge patterns, enums, and ID conventions are documented in [[Data Model]].

The graph path: `entity → traitsetting → trait → traitset → sfx`. "Find all entities with qi_reserves d8+" is a graph traversal, not a nested array scan.

## Entity Model

Every significant thing in Transversal is an entity. Each entity carries **metadata only** — traits live in separate collections connected by edges. See [[Data Model#entities]] for the full entity schema.

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
# Entity document (occupant — universe/location derive from the active projection)
type: character
name: "Kael Drift"
razmerit: 3
current_projection: "kael-1:three_realms"
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

## Fog of War

Trait knowledge is tracked per entity. Each `TraitSetting` carries a `known_to` list of entity IDs that know about that specific trait instance (see [[Data Model#traitsettings]]).

- **Players** are affected by fog of war; the GM sees every trait, and an entity always sees its own sheet.
- On a foreign sheet, a trait whose `known_to` doesn't include the viewer is rendered as `???`.
- Knowledge is **monotonic** — once learned, a trait is never un-learned.

Trait knowledge changes through three reveal paths:

1. **Using a trait in a dice pool** — when a trait enters a pool at a location, everyone currently at that location learns it. The server persists the `known_to` entries and broadcasts `traits_revealed` so live clients re-fetch the sheet.
2. **Offering a negative trait** — routing one of your negative traits to an opponent's pool during a contest reveals it to everyone present. If the opponent hadn't learned it yet, `on_trait_offered` fires.
3. **Reveal effect** — a `modify_trait`/`reveal` effect (e.g. a spying SFX) adds a specific learner to `known_to`.

The `on_trait_learn` trigger fires whenever an entity newly learns a trait, regardless of which path caused it. See [[SFX and Effects#Trigger semantics]] for the trigger vocabulary.

## Ego and Morph

Not all traits are universe-gated. **Ego traits** represent personality, core identity, and learned understanding that persists regardless of which body or universe the character inhabits.

Ego vs morph is **derived from the trait setting's anchor** (`from_type`), not stored as a separate flag:

| Anchor (`from_type`) | Kind | Persists across universes? | Example |
|-----|------|---------------------------|---------|
| `entity` | **Ego** | Yes — always available | Curious d8, Antisocial d6, "Answered Antonov's Call" d8 |
| `projection` | **Morph** | No — gated by that projection's origin universe | Hacking d10 (Earth only), qi_reserves d6 (Three Realms only) |

When the resolver assembles a pool for Kael, it returns:
- All ego (entity-anchored) traits, always (curious, antisocial, distinctions)
- Morph (projection-anchored) traits whose projection's `origin_universe` is in Kael's `effective_universes` — his active projection's universe plus any unexpired attunements

Kael's hacking stays on Earth. His curiosity follows him everywhere. See [[Projections and Transversal]] for the gating rule.

## Projections

A **projection** is a per-universe body — a first-class container for name, image, location, and morph traits. Projections, consciousness/inapposite travel, attunement, and the Earth-bond are documented in [[Projections and Transversal]]. See [[Data Model#projections]] for the field schema.

## Attunement

Attunement is a **temporary SFX-triggered effect** that adds a universe to a character's `effective_universes` — letting morph traits from that universe become available without moving the body. It is never a passive state; it always has a cost and duration. See [[Projections and Transversal#Attunement]] for the canonical model.

## Razmerit

Razmerit is **global** — one balance per entity, not per universe. It follows the entity's consciousness across universal boundaries. Spend it on SFX in the Three Realms; the balance drops. Earn it from a complication on Earth; it rises. The same pool, everywhere.

See [[Inspired Mechanics]] for razmerit spend/earn rates and the effects system integration.

## Relationships Between Entities

Entities connect through the `relationships` edge collection. See [[Data Model#relationships]] for the edge schema and [[Data Model#Relationship Types]] for the type enum.

Relationships can carry their own trait settings — a relationship edge can have traits attached (e.g., "debt: 4d6 razmerit owed").

> [!note] Relationship anchor (planned)
> Today relationships are entity → entity. The planned model mirrors trait settings: `_from` is always an entity, but `_to` may be either an **entity** (a soul-level relationship — you know *who they are*) or a **projection** (a looks-level relationship — you know *what they look like*). A projection-anchored relationship can be **promoted** to an entity-anchored one as it deepens. Deferred relationship work — not yet implemented.

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

---
title: API Contract
tags:
  - transversal
  - technical
  - api
  - contract
aliases:
  - API
  - Endpoints
  - GraphQL Schema
---

# API Contract

The Transversal backend exposes a unified API over HTTP/2 with three interfaces: a GraphQL endpoint for entity CRUD and complex queries, REST endpoints for stateless operations, and an SSE stream for real-time state push.

Base URL: `/api/v1`

---

## GraphQL (Strawberry)

Available at `/api/v1/graphql`. All entity operations flow through GraphQL. Strawberry generates the schema from Python types; the contract below describes the logical shape.

### Entity Types

```graphql
type Entity {
  id: ID!
  type: EntityType!
  name: String!
  razmerit: Int!
  currentUniverse: String!
  currentLocation: String
  hidden: Boolean!
  knownTo: [ID!]!
  # Location
  backgroundImage: String
  zones: [Zone!]!
  # Map positioning (percentage, per-location)
  mapX: Float
  mapY: Float
  # Faction
  nodeIds: [ID!]!
  # Asset
  ownedBy: String
  # Computed
  projections: [Projection!]!
  traitSettings: [TraitSetting!]!
}

enum EntityType {
  CHARACTER
  LOCATION
  FACTION
  ASSET
  GMC
  UNIVERSE
}

type Projection {
  id: ID!
  entityId: ID!
  universe: String!
  transversalType: TransversalType!
}

enum TransversalType {
  NATIVE
  CONSCIOUSNESS
  INAPPOSITE
}

# Trait Registry — shared definitions
type TraitRef {
  id: ID!
  name: String!
  universe: String!
  traitsetId: ID!
  defaultDieType: DieType!
  defaultRatingType: RatingType!
  possibleSfxIds: [ID!]!
  locationRestricted: Boolean!
}

type TraitSetRef {
  id: ID!
  name: String!
  universe: String!
  entityTypes: [EntityType!]!
}

# Per-entity trait configuration (edge: entity → trait registry)
type TraitSetting {
  id: ID!
  entityId: ID!
  traitId: ID!
  traitsetId: ID!
  dieType: DieType!
  ratingType: RatingType!
  rating: String!          # e.g. "d8", "4d4+7d6"
  statement: String
  negative: Boolean!
  ego: Boolean!            # true = persists across all universes
  sfxIds: [ID!]!           # unlocked SFXs
  name: String!            # resolved from trait registry
  traitsetName: String!    # resolved from traitset registry
  universe: String!        # resolved from trait registry
}

enum DieType {
  D4  D6  D8  D10  D12
}

enum RatingType {
  STATIC
  RESOURCE
  CHALLENGE
  EMPTY
}

type Zone {
  name: String!
  backgroundImage: String
  x: Float!   # percentage position on background (0–100)
  y: Float!   # percentage position on background (0–100)
}

type CharacterView {
  entity: Entity!
  projections: [Projection!]!
  traitSettings: [TraitSetting!]!
}
```

### Queries

```graphql
type Query {
  # Entity lookup
  entity(id: ID!): Entity
  entities(type: EntityType, universe: String): [Entity!]!
  character(id: ID!): CharacterView

  # Trait registry
  traitsByUniverse(universe: String!): [TraitRef!]!
  traitsetsByUniverse(universe: String!): [TraitSetRef!]!
}
```

### Mutations

```graphql
type Mutation {
  # Entity CRUD
  createEntity(input: CreateEntityInput!): Entity!
  updateEntity(input: UpdateEntityInput!): Entity!
  deleteEntity(id: ID!): Boolean!

  # Trait settings
  addTraitSetting(entityId: ID!, input: TraitSettingInput!): TraitSetting!
  updateTraitSetting(id: ID!, input: TraitSettingUpdateInput!): TraitSetting!
  removeTraitSetting(id: ID!): Boolean!
  stepUpTrait(traitSettingId: ID!): TraitSetting!
  stepDownTrait(traitSettingId: ID!): TraitSetting!

  # Razmerit
  spendRazmerit(entityId: ID!, amount: Int!, reason: String): RazmeritResult!
  earnRazmerit(entityId: ID!, amount: Int!, reason: String): RazmeritResult!
  transferRazmerit(fromId: ID!, toId: ID!, amount: Int!, reason: String): RazmeritResult!

  # Projection
  addProjection(entityId: ID!, universe: String!, type: TransversalType): Entity!
}

input CreateEntityInput {
  name: String!
  type: EntityType!
  universe: String!
  location: String
  razmerit: Int
}

input UpdateEntityInput {
  id: ID!
  name: String
  razmerit: Int
  currentUniverse: String
  currentLocation: String
  hidden: Boolean
  knownTo: [String!]
  backgroundImage: String
  ownedBy: String
}

input TraitSettingInput {
  traitId: ID!
  traitsetId: ID!
  dieType: DieType!
  ratingType: RatingType
  rating: String
  statement: String
  negative: Boolean
  ego: Boolean
  sfxIds: [ID!]
}

input TraitSettingUpdateInput {
  dieType: DieType
  ratingType: RatingType
  rating: String
  statement: String
  negative: Boolean
  ego: Boolean
  sfxIds: [ID!]
}

type RazmeritResult {
  fromId: ID!
  fromBalance: Int!
  toId: ID
  toBalance: Int
  amount: Int!
  reason: String!
}
```

---

## REST Endpoints

REST is used for stateless operations that don't fit the entity graph model.

### Dice Resolution

**`POST /api/v1/roll`**

Request:

```json
{
  "entity_id": "kael-1",
  "universe": "three_realms",
  "dice": [["d8", "sword_intent"], ["d6", "qi_reserves"]],
  "opposition": {
    "type": "challenge",
    "challenge_die": "d8"
  },
  "razmerit_spent": 0
}
```

Response:

```json
{
  "pipeline": "simplified",
  "rolls": [
    {"die": "d8", "result": 7, "source": "sword_intent"},
    {"die": "d6", "result": 4, "source": "qi_reserves"}
  ],
  "highest": 7,
  "tier": "success",
  "effect_die": "d6",
  "hitches": [],
  "botch": false,
  "opposition_roll": {"die": "d8", "result": 5},
  "challenge_result": {
    "targeted_die": "d8",
    "effect_die": "d6",
    "outcome": "step_down",
    "new_challenge_rating": "1d6 + 1d8"
  },
  "razmerit_earned": 0
}
```

For Dice Pool pipeline, the response includes `total` (sum of kept dice) and `effect_die` (chosen from unused dice).

The resolver is stateless — it does not apply state changes. The caller (UI or effects system) reads the result and decides what to persist.

### SFX Trigger

**`POST /api/v1/effects/trigger`**

Request:

```json
{
  "entity_id": "kael-1",
  "sfx_name": "Law Bridge",
  "universe": "earth",
  "trigger": "on_activate",
  "context": {}
}
```

Response:

```json
{
  "applied": true,
  "cost": 1,
  "effects": [{ "type": "spoof_location", "action": "enable", "target": "wielder", "result": "three_realms:d8" }],
  "scheduled": [],
  "new_razmerit_balance": 4
}
```

Supports `reverse: true` in context for deactivating SFXs and refunding costs.

### Location Navigation

**`GET /api/v1/locations/{location_id}/navigate`**

Returns parent (up), children (down), transversal destinations (lateral), zones, and occupants.

```json
{
  "location": { "name": "Valley of Ascension", "zones": [{"name": "Verdant Dominion", "x": 30, "y": 40}, ...] },
  "parent": { "name": "...", "_key": "..." },
  "children": [{ "name": "Verdant Dominion", "_key": "loc-40646134", "current_universe": "three_realms" }],
  "transversal": [{ "name": "The Arrival Platform", "_key": "loc-platform", "current_universe": "three_realms" }],
  "occupants": [{ "name": "Kael Drift", "type": "character", "id": "kael-1", "image": "/media/kael-1.png", "map_x": 45, "map_y": 60 }]
}
```

### Entity Movement

**`POST /api/v1/entities/{entity_id}/move`**

```json
{ "location": "loc-40642106", "universe": "three_realms" }
```

Response: `{ "entity_id": "...", "name": "...", "location": "Valley of Ascension", "location_id": "loc-40642106", "universe": "three_realms" }`

### Location Edges

**`POST /api/v1/locations/{from_id}/edges/{to_id}`**
```json
{ "type": "super" }
```
Creates a super (parent-child) or transversal (inter-universe) edge. Transversal edges are created bidirectionally.

**`DELETE /api/v1/locations/{from_id}/edges/{to_id}?type=super`**
Removes a location edge. Transversal edges are removed bidirectionally.

### Zone Management

**`PUT /api/v1/locations/{location_id}/zones`**

Replaces all zones on a location. Used by the GM zone editor to persist drag-and-drop repositioning.

```json
[
  { "name": "Verdant Dominion", "x": 30, "y": 40 },
  { "name": "Gilded Basin", "x": 70, "y": 40 }
]
```

### Entity Map Position

**`PATCH /api/v1/entities/{entity_id}/map-position`**

Updates an entity's position on the current location's map. Used by drag-and-drop occupant positioning.

```json
{ "map_x": 45, "map_y": 60 }
```

### Media Upload

**`POST /api/v1/media/upload?entity_id={id}`**

Accepts multipart file upload (PNG, JPG, GIF, WebP, SVG). Files are renamed to `{entity_id}_{uuid}.{ext}` and stored in the `media/` directory. Max 10 MB.

Response: `{ "filename": "loc-sect_a1b2c3d4.png", "path": "/media/loc-sect_a1b2c3d4.png", "size": 12345 }`

Uploaded files are served at `GET /media/{filename}` via StaticFiles.

### Player Identity

**`POST /api/v1/players`** — find or create player by name. Returns player ID for localStorage.

---

## SSE Stream

**`GET /api/v1/stream?session_id=<id>&entity_id=<id>`**

The stream delivers state-change events as `text/event-stream`. The client opens one connection per session and receives push events for all entities in the session.

### Event Types

| Event | Payload | Triggers |
|-------|---------|----------|
| `location_changed` | `{"entity_id": "...", "from": "...", "to": "..."}` | Entity moves to a new location |
| `trait_updated` | `{"entity_id": "...", "trait_id": "...", "old_rating": "...", "new_rating": "..."}` | Any trait change on any entity in the session |
| `razmerit_changed` | `{"entity_id": "...", "old_balance": 5, "new_balance": 4, "reason": "sfx_cost"}` | Razmerit balance changes |
| `entity_updated` | `{"entity_id": "...", "name": "...", "background_image": "...", "current_universe": "...", "current_location": "..."}` | Entity metadata changed (name, background image, etc.) |
| `entity_created` | `{"entity_id": "...", "name": "...", "type": "..."}` | New entity created in session |
| `roll_result` | Full roll response (see `POST /roll`) | A dice roll completes |
| `pool_updated` | `{"player_id": "...", "entity_id": "...", "dice": [...], "phase": "..."}` | Dice pool contents change |
| `scene_change` | `{"to_location": "..."}` | The scene changes; UI transitions |
| `error` | `{"code": "...", "message": "..."}` | An error occurred server-side |

### Reconnection

The SSE client auto-reconnects on disconnect. The `Last-Event-ID` header enables replay of missed events from the event log (Redis-backed in future).

---

## Seed Data CLI

Seed data is no longer loaded on startup. Run it explicitly:

```bash
# Inside Docker
docker compose run seed

# Or directly
docker compose exec api python -m transversal seed
```

The command is idempotent — it checks for existing records before inserting. See `code/api/src/transversal/__main__.py`.

## MCP Server

Available over stdio transport. Provides 5 tools for entity CRUD, dice resolution, and session management. See `code/api/src/transversal/mcp/server.py`.

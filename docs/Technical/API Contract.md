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
status: canonical
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
  # Navigation dot positions (JSON)
  navPositions: String
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
  polarity: Polarity
  possibleSfxIds: [ID!]!
  locationRestricted: Boolean!
}

type TraitSetRef {
  id: ID!
  name: String!
  universe: String!
  entityTypes: [EntityType!]!
  order: Int!
  limit: Int!
  allowDuplicates: Boolean!
  polarity: Polarity
}

# Per-entity trait configuration (edge: entity → trait registry)
type TraitSetting {
  id: ID!
  entityId: ID!
  traitId: ID!
  traitsetId: ID!
  dice: [DieType!]!        # currently-available dice, e.g. [D8] or [D4, D4, D4, D4]
  spentDice: [DieType!]!   # spent-but-recoverable dice (resource pools); capacity = dice + spentDice
  ratingType: RatingType!  # STATIC | RESOURCE | CHALLENGE | EMPTY
  dieType: DieType!        # computed: first die in dice, or D6 if empty
  rating: String!          # computed: human-readable, e.g. "d8" or "4d4"
  statement: String
  polarity: Polarity!
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

enum Polarity {
  POSITIVE
  NEGATIVE
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

  # Effect authoring (served vocabularies + candidate resolution)
  effectActions: [EffectActionMeta!]!
  triggers: [TriggerOption!]!
  conditionTypes: [ConditionTypeOption!]!
  targetFilterFields: [FilterFieldOption!]!
  scopeVariables(trigger: String, menuContext: String): [ScopeVariable!]!
  targetCandidates(kind: String!, entityId: ID, scope: String, action: String, filter: JSON): [TargetCandidate!]!

  # Scheduled timers (central store)
  scheduledEvents(targetType: String, targetId: ID, targetIds: [ID!]): [ScheduledEvent!]!
}
```

> [!note] Scheduled timers
> `scheduledEvents` lists running centrally-scheduled timers. `targetType` is `"entity"` or `"trait_setting"`; `targetId` scopes to one owner, `targetIds` to a set of owners (all filters combine; omitting all returns the full store). Each `ScheduledEvent` carries `id`, `targetType`, `targetId`, the revert `effect`, `timers` (`{event, remaining}`), `combine`, and `sourceSfxId`.

> [!note] Effect target fields
> `Effect` and `EffectInput` carry a `targetFilter` map (candidate field predicates, e.g. `{"starter_location": true}`) that composes with `targetScope`. `targetCandidates` accepts the same `filter` and an optional `entityId` (omitted → authoring preview against a synthetic universe context derived from `scope`).

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
  navPositions: String
  ownedBy: String
}

input TraitSettingInput {
  traitId: ID!
  traitsetId: ID!
  dice: [DieType!]!
  ratingType: RatingType
  statement: String
  polarity: Polarity
  ego: Boolean
  sfxIds: [ID!]
}

input TraitSettingUpdateInput {
  dice: [DieType!]
  ratingType: RatingType
  statement: String
  polarity: Polarity
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
  "effects": [{ "type": "attune", "action": "enable", "target": "wielder", "result": "three_realms:d8" }],
  "scheduled": [],
  "new_razmerit_balance": 4
}
```

Supports `reverse: true` in context for deactivating SFXs and refunding costs.

### Location Navigation

**`GET /api/v1/locations/tree`**

Returns the full location hierarchy as a nested tree from super edges.

```json
[
  {
    "id": "loc-40642106",
    "name": "Valley of Ascension",
    "universe": "three_realms",
    "children": [
      { "id": "loc-40646134", "name": "Verdant Dominion", "universe": "three_realms", "children": [...] }
    ]
  }
]
```

**`GET /api/v1/locations/{location_id}/navigate`**

Returns parent (up), children (down), transversal destinations (lateral), zones, and occupants.

```json
{
  "location": { "name": "Valley of Ascension", "zones": [{"name": "Verdant Dominion", "x": 30, "y": 40}, ...], "nav_positions": {"parent": {"x": 90, "y": 15}, "portal": {"x": 90, "y": 50}} },
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

### Resource Pool

**`POST /api/v1/resource-pool/{traitsetting_id}/spend`**

Spend dice from a resource trait's pool.  Moves one die of the given type
from `dice` to `spent_dice` and persists.  Fails (400) if fewer dice of that
type are available than `count`.

Request: `{"die": "d4", "count": 1}`

Response: `{"traitsetting_id": "...", "die_type": "d4", "rating": "3d4", "dice": ["d4","d4","d4"], "spent": ["d4"], "max_rating": "4d4", "total": 3, "max_total": 4}`

**`POST /api/v1/resource-pool/{traitsetting_id}/recover`**

Recover spent dice back to the pool.  Moves one die of the given type from
`spent_dice` back to `dice` and persists.  Recovery is bounded by the ledger:
fails (400) if fewer dice of that type are in `spent_dice` than `count`.

Request: `{"die": "d4", "count": 1}`

Response: same shape as spend.

### Contest Pool Assembly

Per-location contest dice pools. Players assemble dice at a location; other
players see them via SSE (`pool_updated`) and the radial `PoolDiceRing` UI.
Pools persist across location switches — build at one scene, navigate away,
return, and your dice are still there.

**`GET /api/v1/locations/{location_id}/pools`**

Return all pool assemblies at a location. Used on navigation to hydrate
existing pools for the radial display.

Response: `{"location_id": "...", "pools": {"entity-1": {...}, "entity-2": {...}}}`

**`GET /api/v1/locations/{location_id}/pools/{entity_id}`**

Return one entity's pool.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/add-die`**

Add a die to an entity's pool. Broadcasts `pool_updated` via SSE.

Request: `{"die": "d8", "source": "shooting", "universe": "earth"}`

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/remove-die`**

Remove a die by index.

Request: `{"index": 0}`

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/set-opposition`**

Designate an opponent — creates the other side of a contest.

Request: `{"opponent_id": "guard-1", "universe": "earth"}`

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/clear`**

Reset an entity's pool (end of beat). Broadcasts empty `pool_updated`.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/resolve`**

Resolve a contest between the entity and its designated opponent.
Both sides must have dice. Returns `{"winner": "player"|"opponent"|"tie_defender", "pipeline": "...", "pushed": false}`.
Broadcasts `roll_result` via SSE. Returns 409 if pools aren't ready.

### Player Identity

**`POST /api/v1/players`** — find or create player by name. Returns player ID for localStorage.

Request: `{"name": "Kael"}`

Response:
```json
{
  "id": "player-a1b2c3",
  "name": "Kael",
  "entity_ids": ["kael-1"],
  "role": "player",
  "last_spotlight_at": null,
  "last_main_entity_id": null,
  "found": true
}
```

**`GET /api/v1/players`** — list all players, or search by partial name.

`GET /api/v1/players?q=dav` → returns all players whose names contain "dav" (case-insensitive).

Response: `[{"id": "...", "name": "dave", "entity_ids": [...], "role": "player"}, ...]`

**`GET /api/v1/players/{player_id}`** — get a single player by ID.

**`PATCH /api/v1/players/{player_id}/role`** — set player role.

Request: `{"role": "architect"}`

Response: `{"player_id": "...", "role": "architect", "updated": true}`

Valid roles: `"player"`, `"architect"`. The role controls which UI elements are visible (architect sees location labels, overlay switcher, arrange tools, and the GmPanel).

**`POST /api/v1/players/{player_id}/claim/{entity_id}`** — claim an entity (adds to player's entity_ids).

**`POST /api/v1/players/{player_id}/release/{entity_id}`** — release an entity.

**`POST /api/v1/players/{player_id}/main/{entity_id}`** — flag (or un-flag) an owned entity as a main. Request `{"main": true}` (default `true`); response `{"player_id": "...", "entity_id": "...", "main": true, "updated": true}`. A player can only flag entities they already own via an `agency` edge.

**`POST /api/v1/players/{player_id}/spotlight`** — stamp the player's spotlight recency (actor-keyed; B55 wires this to "took control of a main"). Request `{"last_main_entity_id": "...", "timestamp": "ISO"}`; `timestamp` defaults to now.

**`POST /api/v1/players/{player_id}/control/{entity_id}`** — the character-switch signal (B55). Stamps `last_spotlight_at` + `last_main_entity_id` only when `entity_id` is one of the player's mains; broadcasts `main_active` via SSE in both directions (a main becoming active on take, inactive on switch-away). Response `{"player_id": "...", "entity_id": "...", "main": true|false}`.

### Player Persistence

Players are stored in the ArangoDB `players` collection. Player→entity ownership is tracked via `relationships` edges (type: `agency`, `_from`: `players/{id}`, `_to`: `entities/{id}`), carrying a `main` flag for the player's mains. Support characters link to their main via a directional `support` edge (`entity → entity`). See [[Data Model#players]] and [[Data Model#relationships]].

### Session Management

Session CRUD and lifecycle. Each session carries a universe, a GM id, and the set of joined entity ids.

**`POST /api/v1/sessions`** — create a session.

Request: `{"name": "New Session", "gm_id": "", "universe": "earth"}`

Response: `{ "id": "...", "name": "...", "gm_id": "...", "universe": "...", "entity_ids": [...], "player_entities": {...}, "active": true }`

**`GET /api/v1/sessions`** — list active sessions.

**`GET /api/v1/sessions/{session_id}`** — get one session.

**`POST /api/v1/sessions/{session_id}/join`** — join a session (register an entity). Request `{"entity_id": "...", "player_id": ""}`.

**`POST /api/v1/sessions/{session_id}/leave`** — leave a session. Same request shape as `join`.

**`POST /api/v1/sessions/{session_id}/start`** — arm passive `on_session_start` rules; publishes `session_started`. Idempotent.

**`POST /api/v1/sessions/{session_id}/end`** — drop passive rules and clear armed roll-deferrals; publishes `session_ended`.

**`POST /api/v1/sessions/{session_id}/publish`** — publish a custom event to all subscribers of a session (clients share dice pools / roll results without server persistence). Request `{"event": "...", "data": {...}}`.

### Scene State

In-memory dice-pool + difficulty state keyed by `(location_id, entity_id)`; cleared at beat end.

**`GET /api/v1/locations/{location_id}/pools`** — every saved pool at a location.

**`GET /api/v1/locations/{location_id}/pools/{entity_id}`** — one entity's saved pool.

**`PUT /api/v1/locations/{location_id}/pools/{entity_id}`** — persist (in-memory) an entity's assembled pool.

**`DELETE /api/v1/locations/{location_id}/pools/{entity_id}`** — clear one entity's pool.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/offer-negative`** — offer a negative trait to an opponent's pool during a contest.

**`PUT /api/v1/locations/{location_id}/difficulty`** — set the current test difficulty for a location.

**`GET /api/v1/locations/{location_id}/difficulty`** — current difficulty (null if unset).

**`POST /api/v1/locations/{location_id}/next-beat`** — end the beat: clear every pool and the difficulty at the location.

### Contest Flow

The manual (concurrent) contest state machine, continuing the pool-assembly endpoints above.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/set`** — commit one side's rolled + picked result.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/stakes`** — set whether the contest is high-stakes (default low).

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/give-in`** — concede; the other side wins.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/prevent-taken-out`** — spend 1 razmerit to prevent a pending high-stakes takeout.

**`POST /api/v1/locations/{location_id}/pools/{entity_id}/push`** — start a push: rebuild and reroll (free, once).

**`GET /api/v1/locations/{location_id}/pools/{entity_id}/contest`** — current contest state (perspective re-sync).

### Challenge Pool

**`POST /api/v1/challenge-pool/{traitsetting_id}/spend`** — spend one die from a challenge pool.

Request: `{"die": "d8", "destination": "opposition"}` where `destination` is `opposition` (doom die the GM spends) or `pool` (progress die for partial use, returned flagged `resource`).

Response: `{ "traitsetting_id": "...", "die": "d8", "resource": false, "dice": [...], "capacity": [...], "completed": false }`

### Targeting Bans

**`GET /api/v1/entities/{entity_id}/targeting-bans`** — active directional contest-target bans for an entity. Response `{"bans": [{"target_id": "..."}]}`.

**`POST /api/v1/scenes/advance`** — advance the scene: fire scheduled scene effects, decrement bans, clear scene pools + contest trackers; publishes `scene_change`.

### Plans (GM staging)

Drafts live in `plan_entities` / `plan_relationships` staging collections; `apply` promotes them into live collections (fresh ids), `discard` deletes staging only.

**`POST /api/v1/plans/{plan_id}/entities`** — stage a draft entity (upsert by `draft_ref`).

**`POST /api/v1/plans/{plan_id}/relationships`** — stage a draft relationship edge (`from_ref`/`to_ref` accept `draft:<ref>`, `entity:<id>`, or a bare id).

**`GET /api/v1/plans/{plan_id}`** — read a plan (its entities + relationships).

**`POST /api/v1/plans/{plan_id}/apply`** — promote the staged plan into live `entities` / `relationships`.

**`DELETE /api/v1/plans/{plan_id}`** — discard staging (staging only; live data untouched).

### Image Generation

Flux image generation and animation, queued and reported via SSE.

**`POST /api/v1/imagen/{entity_id}`** — trigger async image generation.

**`POST /api/v1/animate/{entity_id}`** — trigger async video-loop animation.

**`POST /api/v1/imagen/{entity_id}/cancel`** — interrupt an active imagen/animate job.

**`GET /api/v1/imagen/jobs`** — active generation/animation jobs with status + queue position.

**`GET /api/v1/imagen/loras`** — available Flux LoRA files.

**`GET /api/v1/imagen/{entity_id}?universe=`** — list generated images for an entity (optionally filtered by universe).

**`PATCH /api/v1/imagen/{image_id}`** — update an image's roles, universe, and/or owning projection.

**`DELETE /api/v1/imagen/{image_id}`** — delete a generated image and its variants.

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
| `pool_updated` | `{"player_id": "...", "entity_id": "...", "dice": [...], "phase": "...", "location_id": "..."}` | Dice pool changes. Dice are `[{die, label}]` objects in adding phase, die-type strings from backend. |
| `main_active` | `{"player_id": "...", "entity_id": "...", "active": true|false}` | A player took control of a main (or switched to a non-main). Drives the troupe availability grey-out. |
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

The command is idempotent — it checks for existing records before inserting. See `src/api/src/transversal/__main__.py`.

## MCP Server

Available over stdio transport. Provides 5 tools for entity CRUD, dice resolution, and session management. See `src/api/src/transversal/mcp/server.py`.

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
  supportEligible: Boolean!
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
  coMembers: [FactionMember!]!  # the other roster members of this entity's factions
  # Agency — who holds this entity (the persistent player → entity `agency` edge)
  agency: AgencyRef
  # Asset
  ownedBy: String
  # Computed
  projections: [Projection!]!
  traitSettings: [TraitSetting!]!
  attunements: [Attunement!]!
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

# Projection grants — which bodies are currently live
# (see Data Model → "Attunement (projection grant)")
type Attunement {
  op: String!               # "add" (attune) | "remove" (suppress)
  universe: String          # target form 1: every body of mine from this universe
  projectionId: ID          # target form 2: one specific body
  scope: String!            # "self" | "domain" (location subtree)
  until: EffectTimingEnum
  sourceSfxId: String
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
  tags: [String!]!
  explanation: String!     # the definition's own text (registry only, never per instance)
}

type TraitSetRef {
  id: ID!
  name: String!
  universe: String!
  entityTypes: [EntityType!]!
  order: Int!
  limit: Int!
  allowDuplicates: Boolean!
  sheetTab: SheetTab!      # which sheet tab the set's traits render on (TRAITS | PROFILE)
  polarity: Polarity
  explanation: String!     # the set's own text; legacy documents stored it as `description`
}

enum SheetTab {
  TRAITS   # mechanical — the traits tab, grouped by set
  PROFILE  # descriptive (name, gender, appearance) — the profile tab
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
  tags: [String!]!         # labels set on this trait *instance* (B116)
  registryTags: [String!]! # labels inherited from the registry trait; matching sees tags + registryTags
  name: String!            # resolved from trait registry
  traitsetName: String!    # resolved from traitset registry
  traitsetTab: SheetTab!   # resolved from traitset registry — the tab this trait renders on
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
  locationId: ID!   # the child location this pin opens — a zone is always a link
  backgroundImage: String
  x: Float!   # percentage position on background (0–100)
  y: Float!   # percentage position on background (0–100)
}

type CharacterView {
  entity: Entity!
  projections: [Projection!]!
  traitSettings: [TraitSetting!]!
}

# Players & troupe (B54–B66)
type Player {
  id: ID!
  name: String!
  role: String!
  lastSpotlightAt: String
  lastMainEntityId: ID
  agency: [AgencyEdge!]!
  mainEntity: Entity        # recency main, else designated main (B63)
}

type AgencyEdge {
  entityId: ID!
  main: Boolean!
}

type SupportCharacter {
  entity: Entity!
  main: Entity!
  mainOwnerId: ID
  ownerId: ID
  mainActive: Boolean!
}

type ActiveMain {
  playerId: ID!
  playerName: String!
  main: Entity!
}

type PlayerBody {
  playerId: ID!
  playerName: String!
  entity: Entity!
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
  traitTags(universe: String!): [String!]!  # distinct tags across the universe's traits, deduped + sorted
  traitsetsByUniverse(universe: String!): [TraitSetRef!]!

  # Players & troupe
  players: [Player!]!
  spotlightRecency: [Player!]!
  supportCharacters: [SupportCharacter!]!
  activeMains: [ActiveMain!]!
  playerBodies: [PlayerBody!]!
  onlinePlayers: [ID!]!

  # Factions — the roster, the bulk association read, and distance ranking
  factionMembers(factionId: ID!): [FactionMember!]!
  entityFactions(entityIds: [ID!]!): [EntityFactionRef!]!
  factionDistances(locationId: ID!): [FactionDistance!]!

  # Locations — the whole distance map from one origin
  locationDistances(locationId: ID!): [LocationDistance!]!

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

> [!note] Faction reads — roster vs association
> Two shapes, deliberately different:
>
> - **`factionMembers(factionId)`** — the roster: `FactionMember { id name type role rank }`. A roster slot is a `membership` edge (member → faction) **or** a `relation` tie carrying `role`/`rank`, and only in the **member → faction** direction. The reverse (`faction → entity`) is the organisation's posture toward someone, not a slot.
> - **`entityFactions(entityIds)`** — the bulk association read: `EntityFactionRef { entityId factionId name outTieType inTieType }`, **one row per `(entity, faction)` pair for the whole list in one query**. Broader on purpose: *any* tie to a faction counts, either direction, so a posture is an association. `outTieType` is the `entity → faction` edge's type — the edge a **role write belongs on**, and the only direction `factionMembers` counts. It is `""` when only the faction's posture exists, which is the signal that no edge can be written and a `membership` must be created. A pair can hold both directions (measured live 2026-09-16: **333 mirrored pairs**), so the two types are reported separately rather than collapsed into one "the tie's type".
>
> `Entity.coMembers` is the "who else is in my sect?" view: the other members across every faction this entity is on the roster of, deduped, self excluded.

> [!note] `factionDistances(locationId)` — ranking factions by distance to their ground
> Returns **every** faction as `FactionDistance { factionId name distance nearestLocationId }`, sorted **nearest first**: a faction controlling this very location is `0`, a faction with no reachable ground is `null` and sorts last. This is the read behind a distance-sorted faction list ([[B134]]).
>
> Distance is a **weighted step count along the location graph** — `super` **and** `transversal` edges, walked **undirected**. Each step costs 1, except a `transversal` that **crosses a universe boundary**, which costs `CROSS_UNIVERSE_WEIGHT` (10, a named constant in `db/repository_mixins/canvas.py` — a dial, not a finding). A `super` edge always costs 1: measured live, **0** of them cross a universe boundary, while **14** portals do.
>
> Values were measured before the design was fixed, and they shape what a surface should render: **195 of 410** locations are unreachable from the single authored control point (47 components), so `null` is common and must read as *"none known"*, not as a number. The read is **computed per request, not materialized** — a full recompute for all 74 factions is ~2.4 ms — with the scale trigger to revisit recorded in [[Factions and Organizations Design Log]] §6.6.

> [!note] `locationDistances(locationId)` — the whole distance map from one origin
> `LocationDistance { locationId distance }`, **nearest first, ties on id**, over the same graph and weights `factionDistances` uses. The origin scores `0`. The point-to-point sibling: one Dijkstra from the origin for the whole map, so a caller orders hundreds of candidates by joining entity → place → distance rather than asking a query each. Built for the GM panel filter's *nearest* ordering ([[GM Panel Development]] § *Ordering*), and additive — nothing else consumes it.
>
> **Unreachable locations are absent**, exactly as `get_location_distances_from` returns them: no sentinel, no `null`. That is the contract's own rule about reading an absence as a number, and it is not hypothetical — measured live 2026-10-13 from the app's default origin (`loc-krasnoyarsk`): **272 of 466 places reachable, 194 with no route**, which leaves **417 of 998 placed entities** without a distance. A caller sorting by it must give the tail its own bucket and its own order.

### Mutations

```graphql
type Mutation {
  # Entity CRUD
  createEntity(input: CreateEntityInput!): Entity!
  updateEntity(input: UpdateEntityInput!): Entity!
  deleteEntity(id: ID!): Boolean!

  # Trait settings
  addTraitSetting(entityId: ID!, input: TraitSettingInput!): TraitSetting!
  addSubTrait(parentTraitsettingId: ID!, traitId: ID!, die: DieType, statement: String, order: Int): TraitSetting!
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

  # Trait-set registry (GM authoring)
  createTraitSet(id: String!, name: String!, universes: [String!]!, entityTypes: [EntityType!], explanation: String, description: String, order: Int, limit: Int, allowDuplicates: Boolean, polarity: Polarity): TraitSetRef!
  updateTraitSet(id: ID!, name: String, universes: [String!], entityTypes: [EntityType!], explanation: String, description: String, order: Int, limit: Int, allowDuplicates: Boolean, polarity: Polarity, clearPolarity: Boolean): TraitSetRef!
  deleteTraitSet(id: ID!): String!
  reorderTraitsets(ids: [ID!]!): Boolean!

  # Troupe / support cast
  setAgencyMain(input: SetAgencyMainInput!): Player!
  createSupportCharacter(playerId: ID!, mainEntityId: ID!, tableId: ID!, index: Int!): Entity!
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
  supportEligible: Boolean
  backgroundImage: String
  navPositions: String
  ownedBy: String
}

input TraitSettingInput {
  traitId: ID!
  traitsetId: ID!
  dice: [DieType!]!  ratingType: RatingType
  statement: String
  tags: [String!]          # instance-level labels (B116)
  polarity: Polarity
  ego: Boolean
  sfxIds: [ID!]
}

input TraitSettingUpdateInput {
  dice: [DieType!]
  ratingType: RatingType
  statement: String
  tags: [String!]          # instance-level labels (B116)
  polarity: Polarity
  ego: Boolean
  sfxIds: [ID!]
}

input SetAgencyMainInput {
  playerId: ID!
  entityId: ID!
  main: Boolean!
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

**`GET /api/v1/locations/{location_id}/navigate?entity_id={entity_id}`**

Returns parent (up), children (down), transversal destinations (lateral), zones, and occupants.

```json
{
  "location": { "name": "Valley of Ascension", "zones": [{"location_id": "loc-40646134", "x": 30, "y": 40}, ...], "nav_positions": {"parent": {"x": 90, "y": 15}, "portal": {"x": 90, "y": 50}} },
  "parent": { "name": "...", "_key": "..." },
  "children": [{ "name": "Verdant Dominion", "_key": "loc-40646134", "current_universe": "three_realms" }],
  "transversal": [{ "name": "The Arrival Platform", "_key": "loc-platform", "current_universe": "three_realms" }],
  "occupants": [{ "name": "Kael Drift", "type": "character", "id": "kael-1", "image": "/media/kael-1.png", "map_x": 45, "map_y": 60 }],
  "destination": { "location_id": "loc-40646505", "name": "The Whispering Forest" },
  "next_hop": "loc-40646505"
}
```

Optional query param **`entity_id`** — the acting character, and the switch for the
**guided route**. When that character carries a `destination_location` (written by the
effects system's "set destination" action, which an SFX grants in the fiction) the
response adds:

- **`destination`** — the objective, `{location_id, name}`. Absent when the character
  has no directions at all.
- **`next_hop`** — the single neighbouring location that is the first step toward the
  objective; `null` when the character is already there or nothing connects the two.
  This is the navdot the viewer pulses ([[Location Viewer]], [[Guided Route]]).

The hop is measured **from the location being viewed**, not from the character's own
`current_location` — so a character standing mid-route asks each location what its own
next step is. That is what makes *every* location on the route light the way onward.

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

A zone is a **link**, not a label: `location_id` is required, and the dot's label
is the linked child's *current* name — derived, never stored, so renaming a child
can never leave a pin stale.

```json
[
  { "location_id": "loc-40646134", "x": 30, "y": 40 },
  { "location_id": "loc-40646505", "x": 70, "y": 40 }
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

**`POST /api/v1/players/{player_id}/claim/{entity_id}`** — claim an entity (adds to player's entity_ids). **B117:** the claim auto-designates the entity as the player's main when the player has no `main`-flagged `agency` edge yet, so a fresh player's first (or only) character becomes their main with no manual GM flag. A player who already has a main keeps it, and the flag is only ever set on the claim that *creates* the edge — the re-claim the client makes on every character switch cannot move it. Support-character creation opts out (it claims with `main: false`).

**`POST /api/v1/players/{player_id}/release/{entity_id}`** — release an entity.

**`POST /api/v1/players/{player_id}/main/{entity_id}`** — flag (or un-flag) an owned entity as a main. Request `{"main": true}` (default `true`); response `{"player_id": "...", "entity_id": "...", "main": true, "updated": true}`. A player can only flag entities they already own via an `agency` edge.

**`POST /api/v1/players/{player_id}/spotlight`** — stamp the player's spotlight recency (actor-keyed; B55 wires this to "took control of a main"). Request `{"last_main_entity_id": "...", "timestamp": "ISO"}`; `timestamp` defaults to now.

**`POST /api/v1/players/{player_id}/control/{entity_id}`** — the character-switch signal (B55). Stamps `last_spotlight_at` + `last_main_entity_id` only when `entity_id` is one of the player's mains; broadcasts `main_active` via SSE in both directions (a main becoming active on take, inactive on switch-away). Response `{"player_id": "...", "entity_id": "...", "main": true|false}`.

Optional query param **`stamp=false`** — records the body **without** touching spotlight recency: presence only, no `last_spotlight_at` and no main active/inactive flip. This is the GM's own path for taking a GMC (it must show up in `playerBodies` and size its map dot, but a GM's possession must never stamp another player's spotlight — see [[Troupe Play]]).

**`DELETE /api/v1/players/{player_id}/control`** — the player has stopped driving anything (the GM going to free-roam). Response `{"player_id": "...", "entity_id": null}`.

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

**`POST /api/v1/sessions/{session_id}/start`** — arm passive `on_session_start` rules (their deferred effects, once and globally) and fire their non-deferred effects per entity; publishes `session_started`. Idempotent.

**`POST /api/v1/sessions/{session_id}/end`** — drop passive rules and clear armed roll-deferrals, then fire `on_session_end` for every entity; publishes `session_ended`.

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

### Content Bundles ([[B301]])

A **bundle** is a portable JSON file of whole documents for a set of authored
elements — the export half of *"share authored content between worlds"*. Two phases
by design: `plan` is a **read** that reports what the selection would carry and what
it would leave behind, `export` writes the file. Full model in [[Content Bundles]].

Request body for both: `{ "selection": [{"kind": "...", "id": "..."}], "depth": 1 }`.
`depth` = how many closure rounds to walk — `1` reports the frontier so the caller
widens and asks again, `0` walks to a fixpoint. **Owner-gated**: a bundle reaches the
whole authored surface of the campaign.

**`GET /api/v1/bundles/kinds`** — the vocabulary: the selectable kinds
(`traitset`, `trait`, `sfx`, `life_path`, `roll_table`, `entity`, `projection`) and
the **anchored** kinds (`traitsetting`, `traitsetsetting`, `relationship`) that
arrive with their owner rather than being asked for. Served so a picker cannot
drift from the map the exporter walks.

**`POST /api/v1/bundles/plan`** — the report, no documents:

| field | is |
|---|---|
| `included`, `counts` | what the bundle would contain |
| `required[]` | references that **leave** the selection, each with the exact document path that named it (`entries[].effects[].refs.trait.value`), its kind, and whether the target exists |
| `invited[]` | relationships whose far endpoint is outside the bundle |
| `incidental[]` | placement and play state that will not travel (`current_location`, `known_to`, attunements, in-progress terms) |
| `expects` | `{universes, media}` — a world handle and an image filename are not documents, so they are *declarations* |
| `unruled[]` | an id-shaped path with no rule in the map — a map gap, surfaced rather than dropped |

**`POST /api/v1/bundles/export`** — the same walk, serialised, returned as
`Content-Disposition: attachment`. The report is embedded (`unresolved`,
`leftBehind`, `invited`, `unruled`) so an importer can refuse a bundle that expects
something it does not carry instead of discovering it at the table.

An **unknown kind is a 400** naming the vocabulary, not an empty bundle: a bundle
that silently exports nothing is indistinguishable from a bundle of nothing.

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

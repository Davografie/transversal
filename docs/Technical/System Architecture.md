---
title: System Architecture
tags:
  - transversal
  - technical
  - architecture
  - backend
  - ui
aliases:
  - Architecture
  - Tech Design
---

# System Architecture

The Transversal backend manages the multiverse — locations, characters, factions, and assets — as entities with traits, razmerit, and relationships. The UI renders the player's current location as an immersive background image with interactive zone hotspots and occupant markers.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Vue3 PWA Frontend                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ Location     │ │ Character    │ │ Dice Roller  │ │
│  │ Viewer       │ │ Sheet        │ │ (retractable)│ │
│  │ (hotspots,   │ │ (GraphQL)    │ │ (REST, swipe)│ │
│  │  occupants,  │ │              │ │              │ │
│  │  drag-drop)  │ │              │ │              │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ │
│         │                │                │         │
│  ┌──────┴────────────────┴────────────────┴───────┐ │
│  │  GmPanel — entity CRUD, trait mgmt, upload,    │ │
│  │  zone editing toggle, universe/location picker │ │
│  └───────────────────────────────────────────────┘ │
├─────────┼────────────────┼────────────────┼─────────┤
│         │     Vite Proxy (dev) — /api, /media        │
│         ▼                ▼                ▼          │
│  ┌────────────────────────────────────────────────┐  │
│  │              FastAPI (unified)                  │  │
│  │  ┌─────────┐ ┌───────────┐ ┌───────────────┐  │  │
│  │  │ REST    │ │ GraphQL   │ │ SSE           │  │  │
│  │  │ /roll   │ │ Strawberry│ │ /stream       │  │  │
│  │  │ /media  │ │           │ │               │  │  │
│  │  │ /loc..  │ │           │ │               │  │  │
│  │  └────┬────┘ └─────┬─────┘ └───────┬───────┘  │  │
│  │       └────────────┴───────────────┘          │  │
│  │                     │                          │  │
│  │  ┌──────────────────▼───────────────────────┐  │  │
│  │  │           Service Layer                   │  │  │
│  │  │  EntityManager / DiceResolver /           │  │  │
│  │  │  EffectsEngine / RazmeritService          │  │  │
│  │  └──────────────────┬───────────────────────┘  │  │
│  └─────────────────────┼──────────────────────────┘  │
│                        │                             │
│  ┌─────────────────────┼──────────────────────────┐  │
│  │               Data Layer                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐    │  │
│  │  │ ArangoDB │  │  Redis   │  │  media/   │    │  │
│  │  │ (8 coll) │  │ (cache)  │  │ (uploads) │    │  │
│  │  └──────────┘  └──────────┘  └───────────┘    │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## Core Services

### Entity Manager

Manages the CRUD lifecycle across 8 ArangoDB collections (plus `players`). Responsibilities:

- Create, read, update, and delete entities, projections, and trait settings
- Assemble `CharacterView` from multiple collections (entity + projections + trait settings)
- Query effective traitsettings per universe (morph + ego)
- Manage razmerit transactions with atomicity guarantees
- Enforce validation (non-negative razmerit)
- Publish SSE events on mutations (`entity_updated`, `entity_created`, `location_changed`, `trait_updated`)
- Move entities between locations

### Dice Resolver

Implements both resolution pipelines described in [[Dice Mechanics]]. Responsibilities:

- Accept a dice pool specification (set of dice with sources)
- Determine pipeline based on pool size (1–2 = Simplified, 3+ = Dice Pool)
- Roll dice, detect hitches (1s) and botches (all 1s)
- Resolve challenge pools (effect die vs challenge die)
- Compute outcome tiers (fail/marginal/success/exceptional/perfect) with effect dice
- For pool pipeline: return all rolls for manual keep-two selection

### Effects Engine

Manages SFX definitions, trigger matching, and effect execution. Responsibilities:

- Register SFX definitions with declarative effects
- Match triggers (on_roll, on_complication, on_botch, on_activate, on_location_change) to SFX
- Execute immediate effects and schedule deferred effects
- Support reverse/deactivation of SFXs
- Tick system: advance beats, scenes, sessions to fire scheduled effects

### Razmerit Service

Handles hyper-dimensional currency transactions. Responsibilities:

- Atomic earn/spend/transfer operations
- Balance validation (no negative razmerit)
- Transaction logging for undo support

## Data Model

### Collections

| Collection | Type | Purpose |
|-----------|------|---------|
| `entities` | Document | Core entity metadata (name, type, razmerit, universe, location, background_image, zones, map_x/y) |
| `projections` | Document | Per-universe body grouping |
| `traits` | Document | Trait registry per universe |
| `traitsets` | Document | Trait grouping registry |
| `traitsettings` | Edge | Entity → trait, carries rating/type/statement |
| `sfxs` | Document | SFX definitions |
| `relationships` | Edge | Entity → entity (super, transversal) |
| `players` | Document | Player identity for session persistence |

### Entity Types

| Type | Description |
|------|-------------|
| `CHARACTER` | Player character |
| `LOCATION` | Place in a universe |
| `FACTION` | Organization or group |
| `ASSET` | Ownable item or resource |
| `GMC` | GM character / NPC |
| `UNIVERSE` | Universe metadata entity |

### Zone Model

Zones are sub-areas within a location, rendered as interactive hotspots on the background image.

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Display name (matches child location name for navigation) |
| `x` | Float | Percentage position (0–100) on background image |
| `y` | Float | Percentage position (0–100) on background image |
| `background_image` | String? | Optional zone-specific image |

### Map Positioning

Entities at a location have optional `map_x`/`map_y` percentage coordinates for positioning on the background. Characters always see their own marker and can drag it. GMs in edit mode can drag all occupants.

## Frontend

The frontend is a Vue3 PWA served by Vite in development.

### Components

| Component | Transport | Function |
|-----------|-----------|----------|
| `LocationViewer` | REST + SSE | Full-screen background image with zone hotspots (navigable), occupant circles (draggable), and navigation arrows (▲ parent, ◎ portal). Zones and occupants support drag-and-drop repositioning. |
| `CharacterSheet` | GraphQL | Slide-out panel showing entity traits grouped by trait set. Filters by current universe (morph traits) and always shows ego traits. Clicking a trait toggles it in the dice pool. SFX buttons appear next to traits. |
| `DiceRoller` | REST `POST /roll` | Retractable bottom panel. **Closed**: only the phase bar is visible as a drag handle at the bottom edge. **Desktop**: hover reveals. **Touch**: swipe up on the handle to open, swipe down or tap outside to dismiss. Four-phase lifecycle (adding/rolling/picking/resolved). |
| `GmPanel` | GraphQL + REST | Slide-in panel from the right. Entity list with type filters, create/edit/delete entities, trait assignment, background image upload (with auto-persist), universe/location dropdowns, and "Edit Zones" toggle for drag-and-drop zone repositioning. |
| `DieIcon` | — | SVG dice renderer (d4–d12), color-coded. Shows result value and hitch/botch highlighting. |

### State Management

State is lifted to `App.vue`: universe, phase, keepCount/effectCount, locationId, locationBgImage, editZones toggle, and pool source tracking are shared between components. SSE events trigger reactive updates across all components.

### Dice Pool Phases

| Phase | Allowed actions | Character sheet |
|-------|----------------|-----------------|
| `adding` | Add/remove dice, toggle SFXs, roll | Traits clickable, SFX active |
| `rolling` | API call in flight | Locked |
| `picking` | Click dice to assign total/effect slots, commit | Locked |
| `resolved` | View result, start new pool | Locked |

### Multiplayer and Sessions

Session management groups players into shared game sessions. The SSE bus broadcasts state changes to all session members.

| Feature | Implementation |
|---------|---------------|
| **Sessions** | In-memory store (`SessionManager`). Create, join, leave. Each session tracks entity→player mapping. |
| **Player identity** | Server-generated player IDs, stored in `localStorage`. Name-based recovery. |
| **Shared state** | Razmerit, trait updates, entity updates, dice pools, and roll results broadcast via SSE. |
| **Entity switcher** | Top-center pill buttons (Kael / Elena). Remote pools and results appear as chips beneath each character name. |

### Image Asset Management

- Location background images managed through GM panel's file upload → auto-persist to entity's `background_image` field
- Files stored in `media/` directory, served via StaticFiles at `/media/{filename}`
- Upload renames files to `{entity_id}_{uuid}.{ext}` for collision safety
- Zone hotspots can display zone-specific images
- Occupant circles show entity images when available, fall back to colored initials

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| **Backend framework** | FastAPI | Unified REST + GraphQL (Strawberry) + SSE. Native async, auto OpenAPI docs. |
| **GraphQL** | Strawberry | Type-first, code-first schema from Python types. FastAPI-native integration. |
| **Real-time** | SSE (Server-Sent Events) | One-directional state push (server → client). Auto-reconnects, simpler than WebSocket. |
| **Frontend** | Vue3 + Vite + PWA | One codebase for mobile, tablet, and desktop. Vite PWA plugin for installable apps. |
| **Database** | ArangoDB 3.12 | Graph + document model. AQL traversal for entity relationships. |
| **Cache / session** | Redis 7 | Session state, future event log for SSE replay. |
| **MCP transport** | stdio | CodeWhale spawns the server as a child process. Same service layer as the HTTP API. |
| **Container** | Docker Compose | All services orchestrated together. |

## Docker Compose Setup

```yaml
services:
  seed:           # one-shot, runs `python -m transversal seed` (profiles: tools)
  api:            # FastAPI on :8085, reload in dev, depends_on arango (healthy) + redis
  arango:         # ArangoDB 3.12 on :8531, health check with auth
  redis:          # Redis 7 on :6380
  frontend:       # Vue3 Vite dev server on :3000, proxies /api and /media

volumes:
  arango_data:    # persistent DB
  redis_data:     # persistent cache
  # media/ is a bind mount from project root → /app/media in api and frontend containers
```

## Data Flow: A Turn Example

1. **Player action**: "Kael hacks the terminal on Krasnoyarsk-45"
2. **UI** builds dice pool from character sheet traits
3. **Dice Resolver** rolls the pool, returns results (successes, hitches, botches)
4. **Effects System** checks for triggered SFX (e.g., "Hinder" on a distinction), applies modifications
5. **Razmerit Service** adjusts currency
6. **SSE bus** broadcasts roll results, trait changes, and razmerit updates to all session members
7. **UI** animates the roll, displays outcome, updates character sheet if traits changed

## Design Principles

> [!quote] Three Design Pillars
> 1. **Entities are the single source of truth.** There is no split between character sheet data and world data. A character's hacking skill and a space station's atmosphere are both entity traits in the same store.
> 2. **The UI is a projection of state.** The frontend reads entity state and renders it. When a character's location changes, the background image changes — the UI doesn't maintain separate state.
> 3. **Effects are declarative, not procedural.** SFX describe what changes, not how to apply them. The effects system resolves the "how" — enabling automation, undo, and replay.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Zone hotspots on background image | Immersive — navigation is part of the scene, not a separate panel |
| Drag-and-drop zone editing | GM can visually position zones to match the background art |
| Occupant map positioning (map_x/map_y) | Characters/GMCs remember where they are on each location's map |
| Retractable dice roller | Minimizes UI clutter; player-focused view shows only the background |
| Seed data as CLI command | Clean separation of concerns; no startup overhead on restarts |
| Universe as entity type | First-class data with names, images; dropdowns show human-readable names |
| Media upload with auto-persist | Instant feedback — upload a background image, it saves and appears immediately |

## Next

- [[API Contract]] — Detailed endpoint and mutation reference
- [[Project Roadmap]] — Phased milestones
- [[Transversal Hub]] — Documentation hub

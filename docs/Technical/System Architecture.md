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
status: canonical
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
│  │  │  EffectsEngine / RazmeritService /          │  │  │
│  │  │  ContestTracker / ResourcePool               │  │  │
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
- Resolve head-to-head contests via `resolve_contest()` — compare two pools,
  declare winner per Cortex Prime tie-breaking rules (higher tier/total wins, ties to defender)

### Effects Engine

Manages SFX definitions, trigger matching, and effect execution. Responsibilities:

- Register SFX definitions with declarative effects
- Match triggers (on_roll, on_complication, on_botch, on_activate, on_location_change,
  on_trait_change, on_contest_win, on_contest_loss, on_success, on_failure) to SFX
- Execute immediate effects and schedule deferred effects
- Support reverse/deactivation of SFXs
- Tick system: advance beats, scenes, sessions to fire scheduled effects

### Razmerit Service

Handles hyper-dimensional currency transactions. Responsibilities:

- Atomic earn/spend/transfer operations
- Balance validation (no negative razmerit)
- Transaction logging for undo support

### Dice Resolver — Contests

Beyond the stateless `resolve()` for single-pool tests, the resolver now supports
head-to-head contests via `resolve_contest(player, opponent)`.  Two pools go in;
both sides are rolled independently (each using their own pipeline), and a winner
is declared per Cortex Prime rules:

- **Simplified vs Simplified**: compare outcome tiers, then highest die values.
  Ties go to the defender (opponent).
- **Pool vs Pool**: compare totals (sum of two highest). Ties to defender.
- **Mixed pipelines**: the pool side's total is compared to the simplified side's
  highest die.

The resolver returns a `ContestResult` with both sides' full roll data, the winner,
and push metadata.

### Contest Tracker

Per-location, session-scoped dice pool assembly tracker. Responsibilities:

- Maintain `PoolAssembly` objects keyed by `(location_id, entity_id)`
- Add/remove dice, designate opposition, track SFX push state (one per beat)
- Resolve contests via the dice resolver when both sides have dice
- Broadcast `pool_updated` SSE events on every mutation so all players see
  dice appearing around occupant dots on the background
- Clear pools at beat or scene boundaries
- Pools survive location switches — build at one scene, return later, dice persist

The `PoolDiceRing` frontend component reads `pool_updated` events and renders
die icons radially around character avatars, with phase-aware display:
adding → die types, picking → rolled results, resolved → total + effect dice.

### Effects Engine — Automated SFX

The effects engine now supports automated triggers that fire during gameplay
without manual activation:

| Trigger | Fires when |
|---------|------------|
| `on_location_change` | Entity moves to a new location |
| `on_trait_change` | Any trait value changes |
| `on_contest_win` | Entity wins a contest |
| `on_contest_loss` | Entity loses or ties a contest |
| `on_success` | A roll achieves any tier above FAIL |
| `on_failure` | A roll results in FAIL tier |

The `fire_contest_sfx()` function takes a `ContestResult` and processes both
sides through the engine with their available SFXs.  The `contest_to_events()`
helper converts a contest result into `GameEvent` objects for the pipeline.

### SFX Push Mechanic

After a failed or tied contest, a player may spend 1 razmerit to **push** —
reassemble their dice pool (same or different traits) and reroll against the
same opposition.  Only one push per beat is enforced by the `ContestTracker`.
The new result replaces the original.  The razmerit cost is handled by the
effects engine; the tracker checks availability and marks the push consumed.

## Data Model

The complete data model — collection schemas, field definitions, edge patterns, enums, ID conventions, and indexes — is documented in [[Data Model]].

## Frontend

The frontend is a Vue3 PWA served by Vite in development.

### Components

| Component | Transport | Function |
|-----------|-----------|----------|
| `LocationViewer` | REST + SSE | Full-screen background image with interactive dots: **zone dots** (green portal), **occupant dots** (blue=PC, orange=GMC, always expanded), **nav dots** (gold=parent, purple=portal). Two-phase interaction: tap to pop (zone/nav), tap to navigate. **Unified overlay system**: CSS backdrop-filter presets (mist, fire, rain, snow, fog) + canvas particle engine (embers, flakes, streaks) activate simultaneously. All positions **image-relative**, responsive bubble sizing (`clamp` + vw). **Portal travel**: pre-fetches destination nav, clip-path expansion, opaque curtain, instant reveal. Portal-style inset box-shadow on location bubbles (no border). SSE cross-device position sync with lerp animation. Character `arrivePop` on arrival. **Role-gated**: labels, overlay presets, Arrange Map are Architect-only; players see ✨/🌑 toggle. |
| `CharacterSheet` | GraphQL | Slide-out panel showing entity traits grouped by trait set. Filters by current universe (morph traits) and always shows ego traits. Clicking a trait toggles it in the dice pool. SFX buttons appear next to traits. Supports `embedded` prop for inline rendering without the panel wrapper (used by GmPanel for entity inspection). |
| `DiceRoller` | REST `POST /roll` | Retractable bottom panel. Desktop: hover reveals. Touch: swipe up/down on drag handle (40px threshold), tap outside to dismiss. Four-phase lifecycle (adding/rolling/picking/resolved). Picking phase: drag-and-drop (mouse + touch with ghost clone) die-to-slot assignment; clicking Total:/Effect: labels auto-assigns Best Total or Best Effect. Resolved phase: large total number + effect die icon. |
| `GmPanel` | GraphQL + REST | Panel to the right of screen, opened by a fixed toggle button. Only visible in Architect mode (`gmMode === true`). Two modes: **Play** (session shortcuts — Next Beat clears all pools, Scene toggle shows characters/GMCs, Start/End Session) and **Prep** (searchable location tree with occupants nested under locations, faction list, entity create/edit/delete with trait management and image upload). Clicking a scene entity in Play mode opens the inspected entity's CharacterSheet (embedded) in a fixed panel to the left. Edit panels also open left of the entity list. A close button appears between the GM panel and secondary panels. Location tree uses Vue TransitionGroup for expand/collapse animations. |
| `DieIcon` | — | SVG dice renderer (d4–d12), color-coded. Shows result value with white text and dark stroke for legibility on transparent backgrounds. |

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
| **Player identity** | Server-generated player IDs, stored in `localStorage`. Name-based recovery with search-driven input (debounced partial-match suggestions, "New transverser" create option). Each player has a **role** — `"player"` or `"architect"` — stored in the ArangoDB `players` collection. Player→entity ownership via `relationships` edges (type: `agency`). Role controls UI visibility (GmPanel, location labels, overlay tools). Settings panel (↩ button) provides business-card-style name display, Player/Architect mode toggle, switch-player with live suggestions, and character selection with confirmation. |
| **Shared state** | Razmerit, trait updates, entity updates, dice pools, and roll results broadcast via SSE. |
| **Entity switcher** | Top-center pill buttons (Kael / Elena). Remote pools and results appear as chips beneath each character name. |

### Image Asset Management

- Location background images managed through GM panel's file upload → auto-persist to entity's `background_image` field
- Files stored in `media/` directory, served via StaticFiles at `/media/{filename}`
- **Uploads auto-converted to WebP** (Pillow, quality 85) for 85-90% size reduction. SVG/GIF pass through.
- `convert_media.py` script can batch-convert existing media: `python -m transversal.convert_media`
- Upload renames files to `{entity_id}_{uuid}.webp` for collision safety
- Zone hotspots display zone-specific images (sourced from child entity, single-source-of-truth)
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
  api_data:       # persistent data (seed migration, backups)
  # media/ is a bind mount from project root → /app/media in api and frontend containers
```

## Data Flow: A Turn Example

1. **Player action**: "Kael hacks the terminal on Krasnoyarsk-45"
2. **UI** builds dice pool from character sheet traits, adds dice via `ContestTracker`
3. **SSE** broadcasts `pool_updated` — other players see dice ring appear around Kael's dot
4. **Dice Resolver** rolls the pool (or resolves a contest if opposition is set), returns results (successes, hitches, botches, winner)
5. **Effects System** checks for triggered SFX (e.g., "Hinder" on a distinction, `on_contest_win` for the victor), applies modifications
6. **Razmerit Service** adjusts currency (SFX costs, complication earnings)
7. **SSE bus** broadcasts roll results, trait changes, and razmerit updates to all session members
8. **UI** animates the roll, displays outcome, updates character sheet if traits changed. Pool dice ring updates to resolved phase (total + effect dice).

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
| Player / Architect role split | Two roles with different UI surfaces. Architect sees GmPanel, location labels, overlay switcher, and arrange tools. Players see a minimal UI with only an effects toggle. Role stored server-side on Player model, synced on login. |
| Effects toggle per-device | Players on lower-powered devices can disable CSS/particle effects for performance. Stored in `localStorage`, only shown on locations that have effects. |
| Player persistence in ArangoDB | Players stored in `players` collection. Player→entity ownership via `relationships` edges (type: `agency`). Survives restarts via persistent Docker volume. |

## Next

- [[API Contract]] — Detailed endpoint and mutation reference
- [[Project Roadmap]] — Phased milestones
- [[Transversal Hub]] — Documentation hub

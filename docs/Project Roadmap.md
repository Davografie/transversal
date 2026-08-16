---
title: Project Roadmap
tags:
  - transversal
  - project-management
  - roadmap
aliases:
  - Roadmap
  - Milestones
status: canonical
---

# Project Roadmap

> [!note] Current Phase
> **Phase 4 — Full Integration** (nearly complete)

## Phase 0: Foundation & Design ✅

- [x] Define game mechanics (Cortex Prime with dual-pipeline resolution)
- [x] Design entity model (locations, characters, factions, assets)
- [x] Design dice resolution system (dual-pipeline: simplified 1-2 dice + Cortex Prime pool 3+ dice)
- [x] Design SFX / effects system (declarative triggers, automated application)
- [x] Draft system architecture (services, data flow, UI concept)
- [x] Create documentation hub with Obsidian wikilinking
- [x] Design the API contract (GraphQL, REST, SSE, MCP)
- [x] Choose tech stack (FastAPI, Strawberry, ArangoDB, Redis, Vue3 PWA)
- [ ] Finalize trait set definitions per entity type *(deferred — content work)*
- [ ] Specify razmerit economy rules in detail *(deferred — content work)*

## Phase 1: Core Backend ✅

- [x] Implement entity CRUD with schema validation (7 collections, EntityRepository)
- [x] Implement trait validation (d4–d12 die ratings, rating types)
- [x] Implement razmerit transactions (atomic earn/spend/transfer)
- [x] Build the stateless dice resolver (dual-pipeline, challenge pools, hitches/botches)
- [x] Add complication detection (hitches per die, botch on all-1s)
- [x] GraphQL API (Strawberry: queries, mutations, character assembly)
- [x] SSE stream endpoint (EventBus, session-scoped subscriptions)
- [x] MCP server (stdio, 5 tools)
- [x] Seed data (Earth + Three Realms trait registries)
- [x] Set up database with auto-init (ArangoDB collections, indexes)
- [x] Write unit and integration tests (84 tests, all passing)

## Phase 2: Effects System ✅

- [x] Implement the effect registry (SFX definitions, register/get)
- [x] Build the trigger monitor (event → SFX matching, on_complication, on_botch, on_activate)
- [x] Implement effect execution engine (immediate + deferred, tick_beat/scene/session)
- [x] Wire effects applier (connects engine to EntityManager + RazmeritService)
- [x] REST trigger endpoint (`POST /api/v1/effects/trigger`) with reverse support
- [x] SFX registry populated (Law Bridge, Overcharge, Lucky Break, Catastrophe Insurance, Dimensional Anchor, Hinder, Spray 'n' Pray)
- [ ] Location spoofing resolver integration (effective traits during spoof)
- [ ] Conflict resolution for chained effects
- [ ] Build the change log / undo system

## Phase 3: UI Prototype ✅

- [x] Build a web-based UI skeleton (Vue3 + Vite PWA)
- [x] Implement location-driven background images (with gradient fallback)
- [x] Build the dice pool visualizer and roller (manual + sheet-click; simplified + pool pipelines; die selection for Cortex keep-two; four-phase lifecycle; dynamic keep/effect counts)
- [x] Create character sheet overlay (GraphQL, universe-filtered, trait-to-pool toggling, SFX buttons with phase gating and frequency tracking)
- [x] Add location transition animations (crossfade)
- [x] Test on desktop and tablet viewports (PWA manifest, mobile layout)
- [x] SFX integration (Hinder, Spray 'n' Pray with toggle, reverse, and phase gating)
- [x] Wire SSE stream to live-update character sheet and location viewer
- [x] Session management (create/join/leave, session-scoped SSE)
- [x] Player identity (server-generated IDs, name-based recovery)
- [x] Shared dice pools and roll results across devices
- [x] Location navigation panel (super/transversal edges, move endpoint)
- [x] Location persistence (entity location survives refreshes)

## Phase 4: Full Integration (in progress)

- [x] Connect UI to backend API (GraphQL + REST + SSE)
- [x] Real-time state sync (SSE with session-scoped event bus)
- [x] Player session management (create/join/leave, entity claiming)
- [x] Foundation for GM tools (MCP server, seed data, location CRUD)
- [x] GM entity editor (GmPanel — create/edit/delete entities, trait assignment)
- [x] Location hotspot system (zone overlays with percentage positioning, drag-and-drop editing)
- [x] Occupant presence on location backgrounds (PC/GMC circles with drag-and-drop)
- [x] Media upload system (file upload, UUID-based renaming, `/media/` serving)
- [x] Seed data separated from startup (`python -m transversal seed` as CLI command)
- [x] Universe entity type with seeded universe entities (Earth, Three Realms)
- [x] Retractable dice roller panel (hover to reveal on desktop, swipe on touch)
- [x] Zone coordinate editing via GM toggle (drag-and-drop on background)
- [x] Dot-based location UI (zones, occupants, nav dots as interactive map markers)
- [x] Two-phase interaction (tap to pop, tap to navigate)
- [x] Portal expansion travel animation (dot → viewport)
- [x] Navigation dots (parent/portal) with persistable positions
- [x] Drag-and-drop die-to-slot assignment in dice pool picking
- [x] Best Total / Best Effect auto-assign for dice picking
- [x] Self-character always popped with proximity-based dot expansion
- [x] Character arrival positioning at source location dot
- [x] Character arrival pop animation (scale+brightness)
- [x] Image-relative coordinate system (dots bound to image, not viewport)
- [x] Seamless portal travel (pre-fetch destination, opaque curtain, instant reveal)
- [x] Background panning with aspect-ratio-aware single-axis scrolling
- [x] Media auto-conversion to WebP (88% size reduction)
- [x] Touch drag-and-drop for dice picking
- [x] Character sheet auto-closes on location change
- [x] Player / Architect role split (server-side role, GmPanel gated, architect-only top-left UI)
- [x] Player settings panel (↩ button — business-card name display, mode toggle, switch-player with live search, character selection with confirmation)
- [x] Search-driven login (debounced partial-match suggestions, "New transverser" create option, narrative Transversal-themed messages)
- [x] Player ArangoDB persistence (`players` collection + `agency` relationships edges, survives restarts)
- [x] Effects toggle per-device (✨/🌑 in localStorage, only on locations with effects)
- [x] CSS overlay presets (mist, fire, rain, snow, fog) with backdrop-filters
- [x] Canvas particle system (fire embers, snow flakes, rain streaks) per overlay preset
- [x] Overlay preset switcher on LocationViewer (propagates via SSE)
- [x] SSE cross-device position sync (entity_moved event, lerp animation on remote updates)
- [x] Responsive bubble sizing (clamp + viewport units)
- [x] Portal-style location bubbles (inset box-shadow, no border, background-attachment: fixed)
- [x] All occupants always expanded (portraits always visible)
- [x] Two-phase tap restored (pointer-events gating on collapsed overlays)
- [ ] Relational Canvas — GM interactive node graph for locations, factions, and GMC relationships ([[Relational Canvas]])
- [ ] End-to-end playtest of a full scene

## Phase 5: Polish & Launch

- [ ] Performance optimization
- [ ] Accessibility review
- [ ] Asset pipeline for location images
- [ ] Documentation finalization
- [ ] Public beta

## Design Decisions Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Dual-pipeline resolution (simplified + Cortex Prime pool) | Simplified for speed on minor checks; Cortex Prime pool for bell-curve reliability on high-stakes rolls | 2026-06-04 |
| Entities as single source of truth | No split between character sheet and world state — simpler backend, cleaner UI | 2026-06-04 |
| Declarative SFX over procedural | Enables automation, undo, replay, and GM-created SFX at runtime | 2026-06-04 |
| Location-driven background UI | Core immersion mechanic — changing locations = changing the visual scene | 2026-06-04 |
| Obsidian-based documentation | Wikilinks, graph view, and backlinks make the design docs navigable and living | 2026-06-04 |
| Multi-collection data model (7 ArangoDB collections) | Traits registry, TraitSetting edges, graph traversal for queries | 2026-06-04 |
| Ego/morph trait tagging | Personality traits persist across universes; body traits are universe-gated | 2026-06-04 |
| Global razmerit (not per-universe) | Hyper-dimensional material follows the entity across boundaries | 2026-06-04 |
| Attunement as SFX-triggered location spoofing | No permanent attunement state; SFX temporarily change effective universe | 2026-06-04 |
| SSE over HTTP/2 (not WebSocket) | Simpler, auto-reconnects, sufficient for state push | 2026-06-04 |
| Strawberry GraphQL (code-first) | Schema generated from Python types, FastAPI native | 2026-06-04 |
| Seed data as CLI command, not startup | One-time initialization; avoids wasteful no-op DB queries on every restart | 2026-06-05 |
| Zone hotspots with percentage coordinates | Scalable positioning on background images; drag-and-drop GM editing | 2026-06-05 |
| Occupant map positioning (map_x/map_y) | Characters/GMCs remember their position on each location's map | 2026-06-05 |
| Universe as entity type | Universe metadata (name, image) is first-class data, not magic strings | 2026-06-05 |
| Dot-based navigation UI | Zones, occupants, and nav destinations rendered as interactive dots on the background image; two-phase tap-to-pop interaction | 2026-06-05 |
| Portal expansion travel animation | Clip-path circle expanding from zone dot to full viewport creates immersive location transitions | 2026-06-05 |
| Nav dot positioning per location | Parent/portal dot positions stored on the location entity; persist across drag-and-drop editing | 2026-06-05 |
| Image-relative coordinate system | All dot positions stored as image percentages; background pans to character position; dots move in lockstep with image — no parallax layers needed | 2026-06-05 |
| Seamless portal travel | Pre-fetch destination nav data for exact arrival position; opaque portal curtain hides background switch; position lock prevents cross-frame animation | 2026-06-05 |
| WebP media conversion | All uploads auto-converted to WebP (Pillow, quality 85); 88% size reduction on existing 232MB library | 2026-06-05 |
| Unified overlay system | CSS backdrop-filters + canvas particle system activate simultaneously per preset; fire=glow+embers, rain=darken+streaks, etc. | 2026-06-06 |
| SSE position sync | entity_moved events broadcast map_x/map_y changes to all connected clients; receiving end applies lerp animation for smooth remote updates | 2026-06-06 |
| Portal-style bubbles | Inset box-shadow with no border creates organic "window into another location" feel rather than UI widget | 2026-06-06 |
| Player / Architect role split | Two roles, two UI surfaces. Architect sees GmPanel + location management tools; players see minimal UI. Role stored server-side, synced on login — not just a localStorage toggle. | 2026-06-06 |
| JSON file player persistence | Simple file-backed store with Docker volume. Survives restarts without adding an ArangoDB collection. Every mutation triggers synchronous save. | 2026-06-06 |
| Search-driven login with debounced suggestions | Players type their name; partial-match results appear as you type. "New transverser" option visible when no exact match exists — creation is discoverable without a separate button. | 2026-06-06 |
| Effects toggle per-device in localStorage | Performance escape hatch for lower-powered devices. Only shown on locations that actually have effects set. No server round-trip needed. | 2026-06-06 |
| Relational Canvas (D3 + Vue Flow) | D3-hierarchy for tree layout, Vue Flow for canvas UX. Lazy-load on expand, auto-layout, focus-aware collapse. GM-only. | 2026-08-12 |

## Next

- [[Transversal Hub]] — Return to the documentation hub
- [[System Architecture]] — Technical implementation plan
- [[Core Mechanics]] — Game design details

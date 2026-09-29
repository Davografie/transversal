---
title: Transversal Hub
tags:
  - transversal
  - hub
  - vttrpg
aliases:
  - Hub
  - Main
status: canonical
---

# Transversal Hub

**Transversal** is a VTTRPG where players travel across a multiverse, using the applications on a common backend. The rules are based on [[Cortex Prime]], with a dual-pipeline resolution system.

> [!abstract] At a Glance
> - **System**: Cortex Prime foundation, dual-pipeline dice resolution (simplified + pool)
> - **World**: Multiverse traversal via a common backend
> - **Entities**: Locations, characters, factions, and major assets
> - **Economy**: Razmerit — hyper-dimensional material that fuels SFX and traversal
> - **UI**: Location-driven background imagery for immersive play

## Navigation

### 📖 Game Design

- [[Setting and Narrative]] — The story: Earth, the Three Realms, the jian, Antonov, and the multiverse
- [[Core Mechanics]] — Cortex Prime foundation, trait rating types, dice pools, and the resolution engine
- [[Dice Mechanics]] — Dual-pipeline resolution: simplified (1–2 dice) and dice pool (3+), hitches, botches, challenge pools
- [[Entities and Traits]] — The entity system: trait registry, ego/morph traits, entity types
- [[Character Growth]] — life paths, trait transfer, and relationship ratings
- [[Projections and Transversal]] — Projections, consciousness/inapposite travel, attunement, and the Earth-bond
- [[SFX and Effects]] — SFX as rule exceptions, the automated effects system
- [[Inspired Mechanics]] — Conspyramid, Entanglements, zones, troupe play, career paths, random generation
- [[Razmerit Resonance]] — the signal model behind projection switching and its visualization *(draft)*

### 📘 Manual

- [[User Manual]] — how to play and run the game (start here if you're new)
- [[Getting Started]] — log in, claim a character, roll your first pool

### ⚙️ Technical

- [[System Architecture]] — Tech stack, core services, UI design, and Docker Compose setup
- [[Data Model]] — ArangoDB collections, schemas, edges, and ID conventions
- [[API Contract]] — GraphQL schema, REST endpoints, SSE stream, and MCP tools
- [[Targeting Model]] — the structured, type-checked target spec + catalog + wizard behind effect targeting
- [[Location Viewer]] — the full-screen location renderer: dots, drag-drop travel, and animations
- [[Relational Canvas]] — GM-only interactive node graph for locations, factions, and relationships
- [[GM Panel Development]] — the Architect's entity/trait editor: panels, composables, conventions
- [[Life Path Flow and Shared Roll Tables]] — how `next_step` links tables and how shared/unaffiliated tables return control
- [[UI-UX Design]] — interaction conventions, touch gestures, and tunable feel constants
- **Security & the way online** (all in `Technical/`): [[Security Posture]] — the SEC-1…SEC-12 register, what is fixed and what is open · [[Identity Programme]] — the **campaign** tenant, admission, accounts and recovery (SEC-3/6/8) · [[Content Registry]] — the cross-campaign catalog, sandbox and GPU entitlement · [[Public Exposure Plan]] — the priced route to the public internet · [[Private Access Runbook]] — the private lane (complete)
- **Effect system** (in `Technical/Effects/`): [[SFX Source Model]], [[Effect Output Variables]], [[Effect Holders and Owners]], [[Passive Rules and Multi-Target References]], [[Portal Transversal Effect]], and the other SFX/effects design specs

### 🗂️ Process

- [[Sessions]] — the session roster and cross-session coordination layer
- [[Division of Labor]] — who owns what: role scope + ticket ownership + deferral
- [[Release Plan]] — scope, decisions, and the 6-phase **build order** (start here for "what to build next")
- [[Tickets]] — the ticket-level breakdown (per-ticket dependencies + context to load)
- [[Pressure-Test Log]] — scenario-by-scenario gap analysis: what's built vs missing, per-feature findings
- [[Effect System Convergence Plan]] — the SFX/effects build sequence
- [[Performance and Resilience Plan]] — client caching, draft persistence, backend latency, multi-worker
- [[Life Path Editor and Wizard Plan]], [[Unified Effects Plan]] — feature plans
- [[Content Completeness Checklist]], [[MCP Tool Experience]] — authoring guidelines and worklog
- **Design logs** *(draft — decisions recorded before they are built)*: [[UN Scenario Design Log]], [[Time and Flashbacks Design Log]], [[AI GM Design Log]], [[Appearance Authoring Guide]]

### 📚 Reference

- [[Cortex Rules Library]] — **local, searchable copy of the Cortex RAW** (Game Handbook, Cortex Lite, Smallville, Marvel Heroic, Tales of Xadia, …) with a topic→page map
- [[TTRPG Library]] — the external reference library (~16 GB, merged and indexed), plus Transversal's own early design material

## Getting Started

> [!tip] New here? Start with the [[User Manual]].

1. Read [[Setting and Narrative]] for the world and story
2. Read [[Core Mechanics]] for the foundational rules
3. Read [[Entities and Traits]] to understand the data model
4. Read [[Dice Mechanics]] for the rolling procedure
5. Read [[SFX and Effects]] for the exception and automation layer
6. Read [[System Architecture]] for the technical plan
7. Read [[API Contract]] for the API design

> [!tip] This documentation is designed for Obsidian
> All internal links use `[[wikilinks]]`. Open this vault in Obsidian for full navigation, graph view, and backlinks.

## Project Status

See the [[Project Roadmap]] for current development phase and milestones. For what to build next, read the [[Release Plan]] (build order) with the evidence in the [[Pressure-Test Log]].

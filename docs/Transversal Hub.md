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
- [[Entities and Traits]] — The entity system: trait registry, ego/morph traits, entity types
- [[Projections and Transversal]] — Projections, consciousness/inapposite travel, attunement, and the Earth-bond
- [[Dice Mechanics]] — Dual-pipeline resolution: simplified (1–2 dice) and dice pool (3+), hitches, botches, challenge pools
- [[SFX and Effects]] — SFX as rule exceptions, the automated effects system
- [[Inspired Mechanics]] — Conspyramid, Entanglements, zones, troupe play, career paths, random generation

### ⚙️ Technical

- [[System Architecture]] — Tech stack, core services, UI design, and Docker Compose setup
- [[API Contract]] — GraphQL schema, REST endpoints, SSE stream, and MCP tools
- [[Relational Canvas]] — GM-only interactive node graph for locations, factions, and relationships
- [[Location Viewer]] — the full-screen location renderer: dots, drag-drop travel, and animations
- [[Life Path Flow and Shared Roll Tables]] — how `next_step` links tables and how shared/unaffiliated tables return control
- [[Targeting Model]] — the structured, type-checked target spec + catalog + wizard behind effect targeting

### 📋 Plans

- [[Release Plan]] — scope, decisions, and the 6-phase **build order** (start here for "what to build next")
- [[Pressure-Test Log]] — scenario-by-scenario gap analysis: what's built vs missing, per-feature findings
- [[Tickets]] — the ticket-level breakdown (per-ticket dependencies + context to load)
- [[Performance and Resilience Plan]] — client caching, draft persistence, backend latency, multi-worker

### 🎨 Design

- [[UI-UX Design]] — interaction conventions, touch gestures, and tunable feel constants

## Getting Started

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

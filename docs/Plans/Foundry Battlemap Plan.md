---
title: Foundry Battlemap Plan
date: 2026-09-13
tags:
  - transversal
  - technical
  - foundry
  - battlemap
  - locations
  - integration
  - plan
aliases:
  - Battlemap Mode
  - Map Mode
  - Foundry Integration
  - FoundrySurface
status: working
---

# Foundry Battlemap Plan

> [!note] Status
> Design agreed 2026-09-13, pre-implementation, **not yet ticketed**. The item is currently parked — "Foundry integration" is `#deferred` in [[to-do]] and "out of this release" in [[Tickets]]. Ticket id + owning role to be assigned by the [[Overseer]]; do not merge implementation work under this plan until then.

> [!abstract] One line
> A **location** decides which surface the table is looking at: concept art ([[Location Viewer]]) for theatre of the mind, a **Foundry VTT battlemap** for tactical encounters. Transversal stays authoritative for world, rules, characters and authoring; Foundry owns the grid.

## Goal

Run tactical, dungeon-delving play on a real battlemap without moving the game's rules, characters, or world graph into Foundry — and without a second, competing world model.

Two play configurations must work:

- **Physical table** — a flat-laying central monitor showing the shared battlemap, players on their own devices (mobile/tablet/laptop) showing sheet, dice, and a small map viewport centered on their own character.
- **Online** — the same, with every participant in their own browser window; the shared screen is optional.

## Principles (invariants)

These are the rules that keep the system from drifting. They are cheap to keep and expensive to retrofit.

1. **The surface is a pure function of the current location.** No mode flag to toggle, no state machine to get out of sync: `location.render` decides which surface renders. Derived state cannot oscillate.
2. **Every transition is a move.** A Transversal nav dot, a fired portal, a Foundry door region — all of them do exactly one thing: `POST /api/v1/entities/{id}/move`. Nothing else changes a location. This is what makes door portals in both directions safe.
3. **Transversal is authoritative** for entities, traits, dice, SFX, razmerit, the world graph, sessions and identity. **Foundry is authoritative** for tactical position *within a scene*: tokens, walls, lighting, terrain.
4. **No coordinate sync.** `map_x`/`map_y` are percentages on a concept image; Foundry positions are grid coordinates. They are different spaces; never map between them. Concept-image positions simply stand still while a scene is tactical.
5. **One dice authority.** No rolls in Foundry. If rolls ever need to appear there, mirror the *result* as a display-only chat card.
6. **Concept art is the base renderer; the battlemap is an enhancement.** Foundry down, module absent, scene missing → fall back to the concept image with a visible "battlemap unavailable" state. Never a blank screen at a physical table.
7. **The world graph stays in Transversal.** Foundry regions *reference* Transversal locations; they never own connectivity.
8. **`render` is explicit, not derived** from "a battlemap is bound". Two reasons: a tactical location can be run narratively on a given night, and a binding with Foundry offline needs an honest fallback path.

## Facts this plan rests on (verified 2026-09-13)

Checked against the Foundry v14 API docs (`foundryvtt.com/api`), the official module-development article, and this repo:

- **Foundry v14 is the current stable** line (v14 stable April 2026).
- **The camera is per-client.** `canvas.animatePan({x, y, scale})` animates a client's view to a coordinate and zoom; each client tracks its own viewed position per scene, in memory. A `canvasPan` hook exists. This is what makes "device shows a slice centered on my character" native rather than custom.
- **Per-user scene views are core.** `Scene#activate({pullAll})`, `Scene#pullUsers(users)`, `Scene#view()`. Practitioners confirm players can sit on *different* scenes without activating for everyone — so the multiverse split is representable.
- **Programmatic token movement exists**: `scene.moveTokens({...})` (destinations, waypoints, wall/terrain constraints); hooks `moveToken` and `updateDocument`.
- **Regions exist in v14** (region surfaces, `TokenDocument#testInsideRegion`, `Scene#updateTokenRegions`) — door/stairs triggers on the map are viable.
- **The module is client-side JavaScript.** `module.json` manifest (`id`, `title`, `version`, `compatibility.{minimum,verified,maximum}`, `esmodules`, `styles`), loaded per client. `"socket": true` provides a server-relayed `module.{id}` socket namespace for client-to-client messages. **Authoritative actions (scene activate, pulls) require a GM session in a browser** — there is no headless Foundry.
- **Touch and chrome-hiding are community layers, not core.** Pinch/pan and mobile ergonomics come from modules (TouchVTT, Swipe, Mobile Improvements); hiding UI for a table screen likewise (Display Mode, Hide UI, Stream View).

Repo anchors used below:

- `Entity`'s Location block — `src/api/src/transversal/domain/entities.py` (`background_image`, `starter_location`, `zones`, `map_x/map_y`, `overlay`, `nav_positions`). New fields go here.
- SSE bus — `src/api/src/transversal/api/sse/bus.py` (session-scoped, Redis fan-out). Existing events: `location_changed`, `entity_moved`, `beat_end`, `presence_changed`, …
- In-memory scene state patterns — `src/api/src/transversal/api/rest/scene_state.py`.
- Movement + graph — `POST /api/v1/entities/{id}/move`, `POST /api/v1/locations/{from}/portal/{to}/fire`, `POST /api/v1/locations/{from}/edges/{to}` (`super` | `transversal`, reverse edge auto-created for `transversal`), `GET /api/v1/locations/{id}/navigate`.
- Auth — magic-link cookie at the nginx edge (`api/auth.py`); CORS is `allow_origins=["*"]` (`main.py`).

### Still unverified (checks listed in M0)

- **Foundry's own frame headers** (`X-Frame-Options` / CSP `frame-ancestors`) — decide whether an in-app `<iframe>` is possible at all. 10-second check: `curl -I` against the running server.
- **Path-prefix hosting** — Foundry's route-prefix server config, so it can sit on the *same origin* as the app (see Hosting).
- **Region behavior list in v14** vs. a module hooking region/token events.
- **Touch feel** on the actual tablet, with the actual chrome-hidden configuration.
- **Which game system** hosts the world (minimal/generic system) — needed the moment a world is created.

## Architecture

### Surfaces (app shell)

`App.vue` already swaps its main band (`fullCanvas`) and keeps the sheet and dice roller as overlays — the surface swap is idiomatic there, not a rewrite:

```
surface = location.render === 'tactical' ? <FoundrySurface> : <LocationViewer>
```

- **[[Location Viewer]]** — unchanged for concept locations. It remains the world-graph renderer: concept art, zones, occupant dots, nav dots, portal animation, overlays.
- **`FoundrySurface.vue` (new)** — a *handoff* component, not a map renderer. It shows bridge status ("battlemap live" / "Foundry offline"), hosts the iframe if hosting allows (else an "Open battlemap" affordance), runs the enter/exit transition by reusing the existing portal curtain, and renders the fallback state. It never draws a map itself.
- **Sheet, dice, SFX, razmerit** — remain Transversal overlays on every surface, in both modes.
- **Tactical locations** hide the concept-image editors (zones, dot dragging, overlay presets); those semantics are Foundry's now. **Occupancy stays meaningful** — it drives scene membership and pulls.

### Data model

On the `Entity` Location block:

```python
render: Literal["concept", "tactical"] = "concept"
battlemap: Optional[BattlemapBinding] = None   # {scene_id, name, thumbnail}
```

- Scene content (background, grid, walls, lights, tokens) lives **entirely in Foundry**. Transversal stores the link and nothing else.
- No new entity type, no new edge type.
- Identity mapping: `foundry_user_id` on the player record (players collection), managed from the existing GM-only player settings panel.
- Exposure follows the existing pattern: GraphQL `Location` type, REST entity endpoints, MCP `create_location`/update tools, GM panel fields gated by `render`.

### Server (Transversal)

- **SSE**: extend the `location_changed` payload (or add a sibling event) with `{render, scene_id}` so a client can swap surfaces without an extra round-trip. Small, follows existing patterns.
- **Bridge auth**: the module needs to read the SSE stream and post status/moves. The app's gate is an nginx-edge magic-link cookie and `EventSource` cannot set headers — so add a scoped bridge token (query parameter or fetch-based stream), accepted for: SSE read, bridge status, and region-issued moves. Keep it least-privilege and per-session.
- **Bridge status** (optional but recommended): let the module report `bridge_online` / `active_scene_id` so the app can show the truth instead of assuming it. Reuse the presence pattern (`services/presence.py`) for the "display client online" grace window.

### Foundry side (module)

A module, `transversal-bridge`, lives in its own folder/repo (not in this repo's build). It loads on **every** client; only the **GM client** performs authoritative actions.

- **v1**: subscribe to SSE (GM client); on `location_changed` to a `render: tactical` location → activate the bound scene and pull its occupants (`Scene#activate` / `pullUsers`); player clients center their camera on their owned token (`canvas.animatePan`) on scene change and token movement; the display client hides chrome and frames all PC tokens; report bridge status.
- **v2**: provision actors/tokens for the entities present, joined by a `flags.transversal.entityId`, with ownership derived from the user mapping.
- **v3**: status mirroring (SFX outcomes → token status icons), attention sync (GM spotlights a token → every client's camera pans to it — pure delight, tiny code), beat-end auto-exit.
- **Never**: rolls, rules, mechanics, coordinate sync, world graph.

### Hosting

The iframe question is really an **origin** question:

- Serve Foundry under the **same origin** as the app, behind the existing nginx edge, using Foundry's path-prefix support. Same origin makes iframe cookies first-party and removes the whole third-party-cookie problem (iOS Safari in particular).
- Confirm frame headers with `curl -I`; if Foundry (or the proxy) refuses framing, **fall back to a separate window/tab** — the design must not depend on the iframe.
- **One Foundry login per browser.** Each device holds its own session; the TV uses a dedicated **display user** of *player* type (a GM session on the TV would leak fog and secrets).
- Foundry is paid, self-hosted software; the module stays private for now. Version upgrades are a deliberate act (`compatibility.verified` pins the tested major).

## UX flows

- **Entering a tactical location**: move → `location_changed` → every client swaps surface (curtain animation reused) → module activates/pulls. If Foundry is unavailable, the app stays on concept art with a badge and the GM can keep playing narratively.
- **Leaving**: a Foundry region bound to a Transversal location fires a move → the destination's `render` decides what happens next. Concept → `LocationViewer`; tactical → the next scene.
- **Party split**: each player is pulled to their own scene; the shared screen shows **the GM's chosen scene** (rule to confirm).
- **GM override**: `render` is explicit, so a tactical location can be run as theatre of the mind tonight, and a scene can be previewed without committing the table.
- **Attention sync** (v3): when a roll, SFX or spotlight happens, every client's camera can pan to the focus — the feature that makes a multi-device table feel like one table.

## Staging

| Phase | Scope | Acceptance |
| --- | --- | --- |
| **M0 — No code** | Foundry v14 + a minimal system + one scene. TV as display user, one tablet as player. Test framing, touch, chrome hiding. Run the `curl -I` header check. | A verdict on the interaction premise from real hardware, and the frame-header answer. |
| **M1 — Transversal only** | `render` + `battlemap` fields; GM panel binding UI (paste/pick scene id); `App.vue` surface swap with a placeholder `FoundrySurface`; `location_changed` payload extension. No module — the GM activates scenes by hand. | Stepping into a tactical location swaps the surface on all clients; leaving returns. Model + serialization tests pass. |
| **M2 — Module v1** | SSE subscription; scene activation/pulls; camera centering; chrome hiding on the display client; bridge status. | Two devices + TV land on the right scene, with the right camera and the right chrome, driven by a single move. |
| **M3 — Regions** | Region binding UI (module); region → `move`; per-region policy (crossing token vs. whole party). | Crossing a door on the map moves the entity in Transversal and swaps surfaces to the destination. |
| **M4 — Polish** | Token provisioning; status mirroring; attention sync; beat-end exit; failure states; docs (Hub, Manual, API Contract). | A full session runs on the new surface with no manual scene handling. |

M0 and M1 are cheap and independently valuable; M2 onward is the real workstream and needs its own ticket and owner.

## Risks

- **The GM client is a hard dependency.** No headless Foundry: if no GM browser session is open, nothing authoritative can happen. Mitigate with a dedicated bridge account, a visible status, and documentation.
- **Iframe on phones.** WebGL + two gesture systems + small screens. Tablets first; phones may end up sheet-only with the map on the shared screen.
- **Two systems, two uptimes.** Transversal API + Foundry + Redis must all be up for tactical play. Degrade to concept art, always.
- **Version drift.** Foundry majors break modules; an upgrade is a migration, not a routine update.
- **Authoring duplication.** Maps are authored in Foundry and never mirrored back. Resist the temptation to generate scenes from Transversal art (that would drag grid metadata across the boundary).
- **Scope creep into mechanics.** Status icons only. The moment Foundry "knows rules", there are two rules engines.

## Open questions

1. **Battlemap granularity** — one scene per *location* (dungeon level / encounter area, recommended) or one per room?
2. **GM override** to run a tactical location in concept mode — confirm (assumed yes).
3. **Shared-screen rule** when the party is split across two tactical locations.
4. **Region default policy** — move only the crossing token, or the whole party?
5. **Phones** — mini-map enabled, or sheet-only with the map on the shared screen?

## Out of scope

Foundry as a content export target (the B89 universe zip), marketplace/sharing, writing a Foundry game system, dice in Foundry, coordinate sync, multi-GM worlds, and any map authoring inside Transversal.

## References

- [[Transversal Hub]], [[System Architecture]], [[Data Model]], [[API Contract]], [[Location Viewer]]
- [[Portal Transversal Effect]] — the travel vocabulary this plan reuses (a "portal" here means an edge + effects; the new concept is a *render binding*, deliberately not called a portal)
- [[to-do]] — "Foundry integration" `#deferred`; [[Tickets]] — "out of this release"
- Verified API sources (2026-09-13): `foundryvtt.com/api` — Scene, Canvas, TokenDocument, module development article

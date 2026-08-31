---
title: Relational Canvas
date: 2026-08-14
tags:
  - transversal
  - technical
  - design
  - frontend
  - gm-tools
aliases:
  - Canvas
  - Location Map
  - Faction Map
status: working
---

# Relational Canvas

A GM-only interactive canvas that visualizes location hierarchies, transversal travel links, faction GMC networks, and character relationships as a zoomable/pannable node graph.

> [!abstract] At a Glance
> - **Tech**: D3-hierarchy (layout) + Vue Flow (canvas UX)
> - **Entry**: GmPanel buttons (embedded sidebar or full-viewport)
> - **Modes**: Location neighborhood, faction network, GMC relational web
> - **Growth**: Lazy-load on expand — one hop per click
> - **Layout**: Full auto-layout, not persisted

## Design Goals

- Replace the indented tree list with a spatial, explorable graph
- Make location hierarchies, transversal travel, and faction networks visible at a glance
- Keep initial load small — only the focus location's neighborhood
- Grow incrementally via user-initiated expand
- Work in both a narrow GmPanel sidebar (~350px) and a full-viewport overlay

## Technology

| Layer | Library | Weight | Role |
|-------|---------|--------|------|
| Layout | `d3-hierarchy` | ~8 KB | Compute tree positions via `d3.tree()`; conspyramid rows computed manually |
| Canvas UX | `vue-flow` + `@vue-flow/core`, `@vue-flow/background`, `@vue-flow/controls`, `@vue-flow/minimap` | ~80 KB | Pan, zoom, drag, minimap, custom node components, edge handles for connect mode |
| Data | New REST endpoint | — | One call per expand, returns location + neighbors + occupants + relationships |

D3 never touches the DOM — it is a pure layout function that outputs `{x, y}` coordinates, which are fed into Vue Flow's reactive `nodes` array.

## Data Model

### REST Endpoint

```
GET /api/v1/locations/{location_id}/canvas?mode=location
GET /api/v1/locations/{location_id}/canvas?mode=expand
```

Both return the same shape:

```json
{
  "location": {
    "id": "loc-valley",
    "name": "Valley of Ascension",
    "universe": "three_realms",
    "zones": [{"name": "Verdant Dominion", "x": 30, "y": 40}],
    "background_image": "/media/loc-valley.webp"
  },
  "parent": { "id": "loc-three-realms-root", "name": "Three Realms" },
  "children": [
    {"id": "loc-verdant", "name": "Verdant Dominion", "universe": "three_realms"}
  ],
  "transversal_peers": [
    {"id": "loc-platform", "name": "The Arrival Platform", "universe": "earth"}
  ],
  "occupants": [
    {"id": "gmc-wei", "name": "Wei Zhào", "type": "gmc", "current_location": "loc-valley", "background_image": null}
  ],
  "faction_memberships": {
    "gmc-wei": [{"id": "fac-argent", "name": "Argent Meridian Sect"}]
  }
}
```

`mode=location` returns the focus location's neighborhood. `mode=expand` returns the expanded node's neighborhood — same query, different node. The frontend merges results into its local node/edge cache.

### Faction Membership Lookup

Membership is a `relationships` edge of type `membership` from the GMC (or character) to the faction:

```aql
FOR r IN relationships
  FILTER r.type == 'membership' AND r._to == @faction_ref
  RETURN PARSE_IDENTIFIER(r._from).key
```

Rank and role are **not** fields on the edge — they are `traitsettings` documents hanging off the membership relationship. Their `_from` points at `relationships/{edge_key}` (i.e. `from_type == "relationship"`), not at the GMC entity:

- **rank** — trait `trait-rel-rank` (die rating, e.g. `d4`–`d12`)
- **role** — trait `trait-role-cd1b` (die rating + `statement` carries the role description, e.g. "they are my cell leader")

Both live in the `relations` traitset (`ts-relations-b114`). The canvas resolves rank/role by joining the membership edge key against `traitsettings.entity_id`.

### Relationship Edges on the Canvas

| Edge type | Data source | Visual |
|-----------|-------------|--------|
| `super` (parent→child) | `relationships` collection, type: `super` | Solid line, downward, no arrowhead |
| `transversal` | `relationships` collection, type: `transversal` | Dashed curved bezier, bidirectional arrowheads, label "transversal" |
| `membership` (GMC→faction) | `relationships` collection, type: `membership` | Dotted line to faction badge (faction not rendered as a tree node) |
| GMC-to-GMC (e.g. `associate`) | `relationships` collection, any entity→entity edge type with a `description` set | Solid line, arrow toward target, edge label from `description` |
| Located-at (occupant→location) | Entity `current_location` field | Dotted, no arrow — implicit |

## Canvas Modes

### Location Mode (default)

Opens centered on the focus location with:
- The focus location (highlighted)
- Its parent (one hop up via `super`)
- Its children/zones (one hop down via `super`)
- Transversal peers (one hop laterally via `transversal`)
- Occupants at the focus location (characters + GMCs)

Non-focus nodes have an ⊕ expand button. Expanding a non-focus node lazy-loads *its* children, transversal peers, and occupants, merging them into the existing graph.

Switching focus re-centers the canvas and adjusts collapse behavior.

### Faction Mode

Opened from GmPanel's faction list or from an occupant's 🏴 button. Shows:
- Only locations where the faction has at least one GMC
- Ancestor locations kept as **scaffolding** (rendered smaller, semi-transparent) to preserve the structural tree
- All faction GMCs at their locations
- All GMC-to-GMC relationship edges between faction members (always visible)

Locations without faction GMCs are hidden — the tree is pruned.

### GMC Relational Web

Opened from an occupant node's 🏴 → "Show Faction X" (narrower variant of faction mode). Shows:
- The GMC's location
- Other faction GMCs that this GMC has direct `relationships` edges to
- Those GMCs' locations

This is the "pusher → dealer → apartment" view — a tight, relationship-driven subset rather than the full faction tree.

## Display Modes

### Embedded Canvas

Opens inside the GmPanel sidebar (~350px). The default entry point for all canvas views. An "Expand" button promotes to full-viewport.

Entry points:
- GmPanel "Show neighborhood" button (above the GmLocationTree)
- Faction list "Show in Canvas" button
- Occupant node 🏴 → "Show Faction X" button

### Full-Viewport Canvas

Replaces the LocationViewer area (main content). GmPanel stays on the left. Triggered by:
- "Open location in full canvas" button (GmPanel)
- "Open faction in full canvas" button (GmPanel)
- "Expand" button on the embedded canvas

The LocationViewer is hidden behind the canvas. Closing the canvas restores the LocationViewer.

## Interaction Model

### Canvas-level

| Input | Action |
|-------|--------|
| Scroll / pinch | Zoom |
| Drag background | Pan |
| Drag node | Reposition (temporary, auto-layout on next expand) |

### Location nodes

Each location node renders as a bubble-style card (matching the existing location bubble aesthetic) with the location name, universe badge, and background thumbnail if available.

| Button | Action |
|--------|--------|
| ⊕ Expand | Lazy-load children, transversal peers, and occupants (one call to `?mode=expand`) |
| ⊖ Collapse | Recursive collapse of subtree, subject to focus-pin exception |
| Click body | Set this location as the new focus — re-centers canvas, adjusts collapse anchor |
| 🔗 Connect | Enter connect mode — drag a handle to another location node to create a transversal edge (`POST /api/v1/locations/{from}/edges/{to}` with `type: transversal`) |
| 📥 Import | Select active entities (characters, GMCs) to move to this location (updates `current_location`) |

### Occupant nodes

Each occupant node renders as a portrait circle (matching the existing occupant circle aesthetic) with name, type badge, and faction badges.

| Button | Action |
|--------|--------|
| 🔗 Toggle relations | Toggle on/off — show or hide this occupant's GMC-to-GMC relationship edges (labeled) |
| 🏴 Show faction | Dropdown: "Show Faction X" / "Show Faction Y" — loads faction mode with that faction |
| 🔍 Inspect | Open GmEntityEditPanel for this entity |

### Edge creation (Connect mode)

1. Click 🔗 on a location node → enters connect mode
2. Drag from the location's edge handle (Vue Flow native)
3. Release on another location node's handle
4. Confirmation: "Create transversal link from X to Y?"
5. `POST /api/v1/locations/{from}/edges/{to}` with `{ "type": "transversal" }`
6. Edge appears immediately on the canvas

Transversal edge deletion: right-click or double-click the edge → "Remove link?" → `DELETE /api/v1/locations/{from}/edges/{to}?type=transversal`

## Focus-Aware Collapse

The **focus node** anchors the ancestor chain. Collapsing a node is always recursive, but the path from focus to root is **pinned** — it cannot be collapsed away.

### Rules

- Collapsing node `X` removes `X`'s children, transversal peers, and their subtrees
- *Except*: any node on the path from the current focus to the root is preserved
- Collapse is recursive — grandchildren fold with their parent, subject to the pin

### Examples

> `A → B → C` with focus on `C`

- Collapse `B`: removes `B`'s other children (siblings of `C`). `C` stays. `A → B → C` stays.
- Collapse `A`: `B` and `C` are on the focus path, so they stay. `A`'s other children go.

> `A → B → C` with focus on `A`

- Collapse `B`: `B`, `C`, and everything below `B` vanishes.
- Switch focus to `C` (click `B` then `C`), then collapse `B`: `C` stays, `A → B → C` stays, `B`'s siblings/peers go.

The rule: the focus node and its ancestors are always visible. Anything else under a collapsed node is hidden.

## Layout Algorithm

### Tree layout (D3)

1. Build a D3 hierarchy from the `super` edge tree
2. `d3.tree().nodeSize([dx, dy])` — fixed spacing, vertical orientation
3. On expand/collapse, rebuild the hierarchy and re-run the layout
4. Feed resulting `{x, y}` into Vue Flow node positions
5. Transversal edges: compute curved bezier paths between the two location nodes' positions

### Conspyramid rows (manual)

For faction mode, GMCs at the same conspyramid level are arranged in a row:
- Row spacing proportional to level depth
- Horizontal spread proportional to node count at that level
- Positioned relative to the faction's primary (most-GMC-dense) location

### Mode transitions

When switching modes or expanding, the layout recomputes. Vue Flow nodes jump to new positions — no animated transitions in the initial implementation. `fitView()` is called after layout settles to frame the graph.

## File Layout

```
src/frontend/src/
  components/
    canvas/
      RelationalCanvas.vue        # Vue Flow wrapper, mode bar, zoom controls
      nodes/
        LocationNode.vue          # custom node: location bubble with action buttons
        OccupantNode.vue          # custom node: portrait circle with faction badges
      edges/
        SuperEdge.vue             # solid vertical, no arrow
        TransversalEdge.vue       # dashed curved bezier, bidirectional arrows
        RelationEdge.vue          # solid arrow, labeled
      useCanvasData.js            # fetch + normalize from REST endpoint
      useCanvasLayout.js          # D3 tree → {nodes, edges} for Vue Flow
      useCanvasExpand.js          # expand/collapse logic, focus-pin enforcement
  composables/
    useCanvas.js                  # shared state: mode, focus, lazy-loaded cache
```

## New npm Dependencies

```json
{
  "@vue-flow/core": "^1.40",
  "@vue-flow/background": "^1.3",
  "@vue-flow/controls": "^1.1",
  "@vue-flow/minimap": "^1.5",
  "d3-hierarchy": "^3.1"
}
```

## New Backend Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/locations/{id}/canvas?mode=location\|expand` | Return focus/expanded location neighborhood |
| `GET` | `/api/v1/factions/{id}/canvas` | Return pruned location tree where faction has members + member relations |
| `GET` | `/api/v1/gmcs/{id}/web` | Return GMC + its location + direct faction relations + those GMCs' locations |

Implementation lives in `src/api/src/transversal/api/rest/locations.py` (or a sibling router) alongside the existing location endpoints. Query logic in `src/api/src/transversal/db/repository.py`.

## Seed Data (Actual Database State)

The seeded scripts are **not** the source of truth. Ground truth lives in ArangoDB (`transversal` database), which contains far more than the scripts suggest:

- **137 locations** in a deep, multi-level `super` hierarchy (3 roots: Earth's `Krasnoyarsk-45`, Three Realms' `River` and `Valley of Ascension`; the Valley branches several levels deep)
- **2 universes** (`earth`, `three_realms`)
- **2 GMCs** (`Su Hui`, `Gu Yuan`), both placed in Three Realms locations
- **2 factions** (`Verdant Steps Sect`, `Rogue Cultivators`) — currently life-path factions with no members
- **1 `membership` edge** (`kael-1` → `fac-verdant-steps`) — a character, not a GMC
- **No `transversal` edges** — the seed script declares one (`krasnoyarsk ↔ platform`) but it is not present in the DB
- **No GMC-to-GMC relationships** — only `associate` edges between characters
- **`rank` / `role` traits are registered but unassigned** — no traitsettings reference `trait-rel-rank` or `trait-role-cd1b` yet

Conspyramid seeding therefore must create, against the **actual** DB (not the scripts):

1. GMC entities placed at existing locations (reusing the existing `Su Hui` / `Gu Yuan` where appropriate)
2. `membership` relationship edges (GMC → faction)
3. `rank` traitsettings on each membership edge (`trait-rel-rank`, die = level)
4. `role` traitsettings on each membership edge (`trait-role-cd1b`, `statement` = role text)
5. GMC-to-GMC relationship edges with `description` (for edge labels)
6. At least one `transversal` edge so travel links are demonstrable

Seed functions must be idempotent (existence-guarded) and must reconcile against live DB keys, not the script's hardcoded `loc-*` IDs.

## Reusability

The full-viewport canvas is a **generic graph viewer**, not a location-specific tool. The core (`RelationalCanvas.vue` + `useCanvasLayout.js`) stays domain-agnostic; domain semantics live in the node components, edge components, and data-loading composables. This separation lets the same canvas shell render other graph-like content:

- **Life paths** — a life path is a linked roll-table. Render as nodes (path → terms → roll-table entries → linked tables) with the existing tree layout and labeled edges.
- **FOAF overviews** — friend-of-a-friend social graphs. Render people as nodes with relationship edges, using a force or radial layout instead of the tree layout.

To support this, `useCanvasLayout.js` should expose pluggable layout strategies (`tree`, `force`, `radial`, `pyramid`) rather than hard-coding the location tree. The node-type registry is already pluggable via Vue Flow's `:node-types` prop.

## Out of Scope (Future Phases)

- Persisted canvas positions — full auto-layout only
- Edge traits — traits attached to relationship edges
- Conspyramid visual pyramid layout — GMCs render at locations, not in a pyramid shape
- Player-facing canvas — GM-only
- Animated layout transitions — nodes jump to new positions on expand/collapse

## Related

- [[System Architecture]] — overall frontend/backend architecture
- [[API Contract]] — existing REST and GraphQL endpoints
- [[Data Model]] — entities, relationships, and conspyramid schema
- [[Inspired Mechanics]] — conspyramid and faction design
- [[Project Roadmap]] — current phase and milestones

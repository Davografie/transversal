---
title: Guided Route
date: 2026-09-23
last-updated: 2026-09-23
tags:
  - transversal
  - technical
  - navigation
  - effects
aliases:
  - Destination
  - Directions
  - Set Destination
  - Next Hop
---

# Guided Route

> [!info] Split across two roles — navigation's half is **built** (2026-09-23)
> The human's ask: *"the ability to set a target destination and have the shortest
> path become highlighted"* — evolved into something diegetic: **an SFX grants the
> directions**, so guidance is authored content rather than a UI toggle. A mayor
> asks the party to clear the goblin cave; every selected character is handed the
> objective and the map lights the next hop.
> The **plumbing and the rendering are merged** ([[navigation]], `13d57927` +
> `1668c883`); the **effect action, its revert, the arrival clearing and the
> authoring refusal are [[Effects]]'s** — see **What Effects builds**.

## Decisions (human, 2026-09-23)

| Question | Answer |
|---|---|
| Party-wide or per-character? | **Per character** — the SFX machinery fans out to every selected entity. |
| Whole route, or one hop? | **One hop** — each location highlights only its next step. |
| Hidden locations? | **Stay hidden unless there is no way around them.** |
| A destination with no route? | **Refuse, with an error message** — never a silent no-op. |

The "one hop" choice is what keeps exploration alive: the map never becomes a
read-out of the graph, and the player still has to travel, arrive and look around.
Guidance being *granted in the fiction* is what keeps it scarce — a character can
only be told the way when someone in the story tells them.

## What is built ([[navigation]])

- **`Entity.destination_location: Optional[str]`** — the objective, a location id.
  Only the id is stored: the destination's **name** and the **route** are both
  derived, so renaming a location or editing the graph cannot leave a stale label
  or a stale route behind.
- **`repo.get_route_next_hop(origin, destination)`**
  (`db/repository_mixins/canvas.py`) — the next step from `origin`, or `None` when
  the character is already there or nothing connects them. It reuses the one graph
  definition (`_location_adjacency`: `super` + `transversal`, undirected,
  `CROSS_UNIVERSE_WEIGHT` at a universe boundary) through
  `get_location_distances_from`, so "the way there" cannot come to mean something
  different from "how far".
  **Hidden-aware by two passes, not by a weight:** the search runs with `hidden`
  locations removed, and falls back to the full graph **only** when that leaves the
  origin unreachable. A penalty would instead trade a cheap hidden shortcut against
  a long open detour — a different rule. `tests/test_location_routes.py` makes the
  hidden road the **shorter** one precisely so a penalty-based rewrite fails it.
- **`GET /locations/{id}/navigate?entity_id=…`** adds `destination {location_id,
  name}` and `next_hop`. Both keys are **absent** without an `entity_id`, so
  existing callers are unchanged. The hop is measured from the **location being
  viewed**, so every location shows its own next step.
- **The viewer** ([[Location Viewer]]): `guidedDot` maps `next_hop` onto exactly one
  dot **by the stored link** (a nav dot's `target.id`, or a zone's `location_id` —
  never a name) and renders it as `.map-dot.guided`, a gold sonar ping distinct
  from the cyan travel-armed breathe.

## What [[Effects]] builds

1. **A `set_destination` action** in `services/effects_registry/actions_world.py`,
   beside `travel` and `set_location` — which already share the *Destination
   Location* field. Target: **each selected character** (the target machinery fans
   out for you). `supports_duration=True` gives the timer form for free.
2. **A handler** that writes `destination_location` on the subject(s), plus the
   `inverse` that clears it — so "the directions expire" and "the directions are
   finished" are the existing revert patterns, not new machinery.
3. **Clear it on arrival** using the **existing `on_location_change` trigger** — and
   compare against *the destination*, not just any location change, or travelling
   **through** the destination would clear it early.
4. **Refuse at authoring time, with an error message**, when the destination is
   unreachable. The read is `repo.get_location_distances_from(origin,
   {destination})`, which is empty **exactly** when there is no route.
   ⚠ **This will fire in real authoring:** 195 of 410 locations are unreachable from
   the single authored control point. A GM must not be able to author *"directions
   to the goblin cave"* that silently does nothing.

## Open questions

- **A character who joins later** has no `destination_location`, so they get no
  directions. Decide: fan out again on join, or accept it.
- **Does the marker clear when the SFX is removed**, or only on arrival/duration?
- **Visibility** — directions are per-character and private today. A *shared* party
  objective would need a home that does not exist yet.

## Related

- [[Location Viewer]] — the dot model and the guided-route rendering.
- [[B36]] — the earlier shape of the same idea: show the shortest path in the blue
  book. Worth keeping as its archival counterpart: the book can show a route the
  character has **lived**, while the map only ever lights the next hop.
- [[B137]]-era visibility (`hidden`/`known_to`) is what a "who may see this
  direction" rule would build on, if directions ever need to be shared.

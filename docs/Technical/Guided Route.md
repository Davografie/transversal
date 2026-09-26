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

> [!info] Both halves are **built** — the feature is complete (2026-09-24)
> The human's ask: *"the ability to set a target destination and have the shortest
> path become highlighted"* — evolved into something diegetic: **an SFX grants the
> directions**, so guidance is authored content rather than a UI toggle. A mayor
> asks the party to clear the goblin cave; every selected character is handed the
> objective and the map lights the next hop.
> The **plumbing and the rendering are merged** ([[navigation]], `13d57927` +
> `1668c883`). The **effect action, its restoring inverse, the arrival clearing and
> the authoring refusal landed 2026-09-24** as **[[B174]]** ([[Effects]], done) —
> see **What Effects builds** for the spec and *Landed* below for what was realised.
> The human's to-do line for this is ticketed as **[[B181]]**, which that landing
> closes. One deliberate refinement of the original ask: the map lights **one hop**,
> never the whole path (the human's decision, below), so `B181`'s "shortest path" is
> realised as "the next step of the shortest path, at every location".

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

## What [[Effects]] builds — **landed 2026-09-24 as [[B174]] (done)**

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

**As built ([[B174]], 2026-09-24) — three refinements of the sketch above:**

- The action is `set_destination/set`, with `inverse=("set_destination", "clear")`
  and **`inverse_captures_prior=True`** — so the inverse **restores** what the
  guidance replaced rather than always emptying it. That answers the
  *"does the marker clear when the SFX is removed"* question below: it reverts.
- Arrival clearing happens in `dispatch_event`'s `location_changed`, compared
  against the destination and **before** the rules run (`clear_arrived_destination`
  in `services/guided_route.py`).
- The unreachable refusal fires at the **attach**, not at the action
  (`attach_refusal`) — the point where the origin first exists — measured from the
  location that owns the rule. Verified live: an "Ask the Mayor" rule pointed at
  Antarctica is refused with *"'Ask the Mayor' belongs on a place that can reach
  Antarctica, not location"*. 18 tests in `tests/test_guided_route.py`.

## Open questions

- **A character who joins later** has no `destination_location`, so they get no
  directions. Decide: fan out again on join, or accept it.
- **Visibility** — directions are per-character and private today. A *shared* party
  objective would need a home that does not exist yet.
- *(answered by `B174`)* **Does the marker clear when the SFX is removed?** — yes:
  the inverse **restores** the prior value (`inverse_captures_prior=True`), so
  removing the SFX or letting its duration lapse reverts the directions.

## Related

- [[Location Viewer]] — the dot model and the guided-route rendering.
- [[B36]] — the earlier shape of the same idea: show the shortest path in the blue
  book. Worth keeping as its archival counterpart: the book can show a route the
  character has **lived**, while the map only ever lights the next hop.
- [[B137]]-era visibility (`hidden`/`known_to`) is what a "who may see this
  direction" rule would build on, if directions ever need to be shared.

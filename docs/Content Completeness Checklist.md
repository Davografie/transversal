---
title: Content Completeness Checklist
tags:
  - authoring
  - transversal
  - guidelines
  - mcp
aliases:
  - What makes content complete
  - Authoring checklist
status: canonical
---

# Content Completeness Checklist

What a *finished* piece of Transversal content actually needs. Use this when
authoring through the MCP tools (or the frontend), so nothing ships half-wired.
See [[MCP Tool Experience]] for the tooling gaps this checklist assumes.

> [!tip] Golden rules
> - Everything starts `unpublished=true` (staged, GM-only). Publish (`reveal`) last.
> - Keep `universe` slugs consistent across a universe and every child.
> - A sub-location is *two* things: a location entity (under a `super` edge) **and**
>   a zone hotspot on its parent's background. Don't forget the second.

## Universe

- `name` + `type="universe"`. The slug is **derived from the name** (`The Emberline` → `the_emberline`); pick the name so the slug matches the value you use for all children.

## Location

A location is complete when it has:

- [ ] `name`, `universe`, and (except the root) a parent via a `super` edge + `current_location`.
- [ ] **Zones** on its parent — every sub-location needs a matching zone (`name` = child name, `x`/`y`, `location_id` = child id) so it appears as a dot on the parent's background.
- [ ] (Its own) `zones` list for any hotspots *within* it.
- [ ] `background_image` (optional — gradient fallback otherwise).
- [ ] `map_x`/`map_y` if it is itself positioned on another location (occupant dot).

## GMC

- [ ] `name`, `universe`, `current_location`.
- [ ] **Traits** — at minimum a distinction and one or two attribute/skill
      trait settings (via `add_trait_to_entity`; universe-correct trait ids).
- [ ] If a faction member: `membership` edge + **rank/role** (`set_rank_role`),
      and a place in the `commands` chain (superior → subordinate).
- [ ] `map_x`/`map_y` on its location so the occupant dot shows.

## Faction

- [ ] `name`, `universe`.
- [ ] **Conspyramid** — member GMCs with `membership` edges + rank (L1 = d4,
      ladder d4→d6→d8→d10→d12→d12) + role, and `commands` edges (apex → … → street).
- [ ] `suitable_life_path_ids` — the life path(s) this faction offers.
- [ ] Optional: faction traits (`influence`, `secrecy`, `resources`).

## Asset

- [ ] `name`, `universe`, `current_location`, `owned_by`.
- [ ] Optional: asset traits.

## Life path

A life path is usable only when it is a *graph of linked roll tables* and is
*offered by a faction*:

- [ ] `LifePath` definition — `id`, `name`, `universe`, `description`, `entry_table_id`.
- [ ] Entry roll table + downstream tables; every non-terminal entry ends in a
      `next_step`, terminal entries use `muster` / `force_muster`.
- [ ] Trait grants in entries (`modify_trait` effects) reference trait ids that
      exist **for the path's universe**.
- [ ] A faction lists the path in `suitable_life_path_ids`.

## Cross-cutting

- [ ] Universe slug consistency (universe entity vs every child's `universe`).
- [ ] Traitsets used are universe-scoped to the new universe (the `relations`
      traitset is `earth`-only by default — add your universe before rank/role
      is mechanically valid there).

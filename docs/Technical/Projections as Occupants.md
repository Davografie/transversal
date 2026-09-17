---
title: Projections as Occupants
date: 2026-09-15
tags:
  - transversal
  - technical
  - navigation
  - open
aliases:
  - Bodies as Occupants
  - Occupant Identity
  - Occupant Projections
---

# Projections as Occupants

> [!warning] Open discussion — **not decided, not built**
> Raised by the human 2026-09-15: *"I want the occupants to show the projections,
> not the entities."* Investigated the same day; the findings below are measured
> against the live database, not inferred. Nothing has been implemented. This note
> exists so the discussion is not lost — see **Open decisions**.

## The question

The location viewer lists **occupants** at a location and draws one dot each, with
a name and a portrait. Should that dot represent the **entity** (the character)
or the **projection** (the body that is actually standing there)?

## What a projection is

A `Projection` is a **per-universe body** ([[Projections and Transversal]]). The
first body keys as `{entity_id}:{origin_universe}`; extra bodies append `:2`, `:3`.
`entity.current_projection` is the body the consciousness is **in** right now.

Crucially, a projection **already carries its own** `name` and
`background_image` — both documented in the model as falling back to the entity —
and images can be **body-scoped** (`EntityImage.projection_id`), with a documented
resolution order: the body's own image → an entity image matching the body's
current/origin universe → any entity image.

So the domain already models "this body, which may look and be named differently".
The viewer is what does not use it.

## What the data shows (2026-09-15)

| Fact | Count |
|---|---|
| Projections (bodies) | 886 |
| Bodies currently standing in a location | 152 |
| Bodies with their **own name** | 1 |
| Bodies with their **own background image** | 0 |
| Entity images that are **body-scoped** | 436 of 1089 |
| Entities with **two bodies in the same location** | **0** |
| **Left-behind bodies** (body's location ≠ entity's location) | **4** |
| …of those, not the entity's active body | 4 |
| Occupants present with **no body row** at their location | 286 |

**Two of these decide the shape of any fix.** Only one body is named and none
carry their own background, so "show the body's name/art" looks *identical to
today* for 151 of 152 occupants. And no entity has two bodies in one place, so
"one dot per body" would add **no dots at all** today.

**But body-scoped art is real and used** — 436 images — and the viewer currently
resolves an occupant's portrait through the entity's **active** body
(`e.current_projection`) rather than the body **present** at that location.

## The narrative constraint

The human's framing: *"when an entity consciousness-travels to another universe,
they leave their body behind."* The data matches exactly — the four left-behind
bodies are:

| Entity | Body left behind | Body's location | Consciousness now in |
|---|---|---|---|
| Truck-Kun | `:three_realms` | `loc-56720896` | `:earth` |
| Phaos Tyish | `:earth` | `loc-469287` | `:three_realms` |
| Arc Brave | `:earth` | `loc-6536146` | `:three_realms` |
| Dr. Strange | `:three_realms` | `loc-40649391` | `:earth` |

All four are therefore **already on the map** (the occupant query lists bodies by
`p.current_location`) — but each wears the face of the body the consciousness
went *to*. Three of the four own their own navdot art, so this is visible, not
theoretical.

That makes the defect precise: **the left-behind body renders with the wrong
body's name and portrait.** Nothing about *which* occupants are listed is wrong.

## What the change would mean

**(A) Resolution only — recommended.** The dot stays *the entity* (so travel,
drag-to-reposition, the sheet, pool dice rings, "who is driving this" and the self
dot all keep working), but its **name and art resolve from the body present at
that location** instead of the entity's active body.
- Visible effect today: the 4 left-behind bodies.
- Cost: one extra field in the navigate query; pass the present body's id into
  `get_navdot_images` instead of `current_projection`; the same in the canvas's
  `_occupants_for_locations`, or the canvas and the map will disagree.
- Risk: low.

**(B) Identity — one dot per body.** Remove the `RETURN DISTINCT p.entity_id`.
- **A body has nowhere to store its map position.** `map_x`/`map_y` live on the
  *entity*; `Projection` has no coordinates. Dragging a body's dot and dropping
  one to travel would have nothing to persist per body.
- Also keyed off the entity id today: the self dot, `controlledEntityIds` /
  `playerBodies` sizing, `remotePools`/`remoteResults` dice rings, and
  `inspectEntity` (the sheet). All would need the entity id carried alongside.
- Gain today: **zero** extra dots.

(B) also introduces a second identity for the same thing — projection for
display, entity for every action — which is the exact split that has produced the
drift bugs this role has been fixing.

## Open decisions

1. **(A) or (B)?** Recommendation: (A). (B) only becomes worth it if bodies need
   their own positions, or two bodies of one entity should stand in one place —
   neither exists in the data today.
2. **Should a vacant body look vacant?** The narrative gives the viewer a fact it
   does not show: this body has no consciousness in it. Dim it, mark it, or leave
   it looking like any other body? Undecided.
3. **Do bodies get their own map position?** Today a left-behind body and the body
   the consciousness is in **share one `map_x`/`map_y`** (entity-level). Mostly
   invisible while they are in different locations, but moving one body's dot
   moves the other's. If bodies are to stand independently this must move onto
   `Projection` — a real domain change, its own ticket, not part of (A).
4. **Names.** Only 1 of 886 bodies is named, but the field exists and a body in
   another universe could legitimately read as a different person. Confirm the
   fallback (body name → entity name) is the intent.

## Not decided here

Ownership spans two roles: the query and the resolver are
[[backend-platform]]'s surface (`canvas.py`, `images.py`), the dot is
[[navigation]]'s. Needs a ticket and the human's answer to decision 1.

## Related

- [[Location Viewer]] — the component and its dot model.
- [[Projections and Transversal]] — what a projection is.
- [[API Contract]] — the `/navigate` occupant payload.
- [[Overseer]] — please ticket this rather than leaving it in a session doc.

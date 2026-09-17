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

## Direction (human, 2026-09-15) — supersedes the (A)/(B) framing

The human rejected the "resolution-only" shape and stated the model directly:
**the map should draw the body, and the body should carry its own state.**

1. **Positions move onto the projection.** `map_x`/`map_y` currently live on the
   entity; track them per projection instead. This is the item that made the
   earlier "(A) resolution-only" proposal wrong — it left two bodies sharing one
   coordinate.
2. **Only the *active* projection grows** (the enlarged "someone is in this body"
   size) — wire it to the projection's active state rather than the entity-keyed
   `controlledEntityIds`.
3. **Only the *active* projection shows the dice ring** — same keying.
4. **The canvas changes with it** — it must agree that a location contains a
   projection, not an entity.
5. **`hidden` becomes read-time enabled.** It is currently a stored `Entity` flag
   that nothing filters on (settable through GraphQL, read nowhere); a vacant body
   needs it honoured at read time. *Needs confirming — see below.*

### Answered (human, 2026-09-15)

- **Self is body-aware. Confirmed.** "Self" is the acting **body**, so the
  occupant list stops hiding a body just because it belongs to the acting entity,
  and the self dot only draws where that body actually is. Covers dangling items
  2 and 4 — they were one root cause.
- **Visibility rule (item 6), stated:** an occupant that reads as
  **`hidden` and not `known_to`** is **invisible to players** and **transparent
  for GMs**. Which makes `known_to` a required field on projections as well.
  Note both flags are **inert today** — stored, exported, settable through
  GraphQL/MCP, and read nowhere — so this is *making them work*, not adding them.
- **An `enabled`/`disabled` flag on projections, independent of vacant/occupied**
  (for a body that must be stored but is not physically present) — raised and
  **explicitly parked** by the human as "a whole other discussion". Not part of
  this work. Precedent if it returns: `TraitSetting.enabled` ("false = disabled;
  contributes no dice until re-enabled").

- **`unpublished` and `hidden`/`known_to` are separate axes — keep both.** They
  answer different questions and are *not* to be merged:

  | flag | players | GM | means |
  |---|---|---|---|
  | `unpublished` | invisible | normal, with a **draft badge** | authoring state — "I am still building this" |
  | `hidden` and not `known_to` | invisible | **transparent** | in-fiction concealment — "they have not found this" |

  They must **compose** rather than override: an occupant that is both is
  invisible to players and, for the GM, a transparent ghost *carrying the draft
  badge*. Independent axes, independent renderings, superimposed.
- **Visibility is per-viewer, which means it belongs server-side.** `known_to` is
  a list of player ids, so `hidden && !known_to` cannot be answered without
  knowing who is looking. The viewer today only knows `gmMode` — it has no player
  identity for occupants — so either the navigate query resolves visibility for
  the requesting session, or the viewer is handed the viewer's id. Server-side is
  the better home: the client should not be the thing deciding what a player may
  see. (`unpublished` is currently filtered client-side in `occupantDots`; that
  could move with it.)

### Still unresolved, needs an answer before planning

- **Where `hidden`/`known_to` live** — on the projection (per-body, pairing with
  the position move) or on the entity, merely honoured when reading.
- **Who computes vacancy** — the reader, from
  `entity.current_projection != projection.id`.

### Superseded framing (kept for the record)

**(A) Resolution only** — the dot stays the entity; only its name and art resolve
from the body present. **Rejected**: leaves positions, control and dice
entity-keyed, so a vacant body would still be sized as "driven" and ringed with
the entity's dice.

**(B) Identity — one dot per body** — the shape now chosen, with the pieces above
spelled out.

## Open decisions

1. **~~`unpublished` vs `hidden`~~** — **decided: separate axes, keep both.**
2. **Where `hidden`/`known_to` live** — on the projection, or honoured from the
   entity (see above).
3. **~~Do bodies get their own map position?~~** — **decided: yes** (direction 1).
   Remaining question is migration: the 152 bodies standing somewhere today have
   no stored coordinate of their own, so they need a starting value.
4. **Names.** Only 1 of 886 bodies is named, but the field exists and a body in
   another universe could legitimately read as a different person. Confirm the
   fallback (body name → entity name) is the intent.
5. **Parked:** an `enabled` flag on projections, independent of vacancy.

## Plan (draft — awaiting a ticket)

Ordered so each slice is independently verifiable and nothing lands in a broken
state. Ownership spans [[backend-platform]] (query, resolver, domain) and
[[navigation]] (the dot); every slice needs both or neither, so the split is
noted per slice.

**S0 — settle the two remaining decisions.** Where `hidden`/`known_to` live
(projection vs entity) and the position-migration default (proposal: seed each
body from its entity's current `map_x`/`map_y`, so nothing moves on day one).
Blocks S2 and S5.

**S1 — the portrait follows the body present.** `get_navdot_images` resolves
through the *present* body instead of `entity.current_projection`. Independent of
everything else, small, and the only slice that is purely a fix: it corrects the
**4** left-behind bodies (3 of which own their own art). *Owner: mostly
backend-platform.* **Done when:** a body shows its own portrait, not the
portrait of the body the consciousness went to.

**S2 — bodies get their own position.** Add `map_x`/`map_y` to `Projection`,
migrate the 152 standing bodies per S0, and let the map-position write address a
*body*. Flagged decision here: does `Entity.map_x/map_y` remain (the active
body's position) or become derived? *Owner: backend-platform.* **Done when:** two
bodies of one entity can sit at different places without sharing a coordinate.

**S3 — the occupant payload describes bodies.** `navigate_from` and the canvas's
`_occupants_for_locations` return one entry per body, carrying **both** ids
(`body_id` and `entity_id`), the body's name (entity fallback) and `is_active`.
Landing this **without breaking the client** is the point of carrying both ids:
the viewer keeps using `entity_id` for now. *Owner: backend-platform.* **Done
when:** the payload names every standing body, and the client is unchanged.

**S4 — the viewer draws bodies.** Key occupant dots by `body_id`; route every
action (drag, sheet, dice, control) to `entity_id`. **Self becomes body-aware**:
the occupant list stops hiding a body because it belongs to the acting entity, and
the self dot only draws where the acting body is. Sizes and the dice ring key to
`is_active`. *Owner: navigation.* **Done when:** a vacant body renders at its own
location, normal-sized and ring-free, and no longer displaces the self dot.

**S5 — visibility.** `hidden`/`known_to` resolved **server-side** in the navigate
query, per viewer; move `unpublished`'s filtering there in the same pass so "who
may see this occupant" is decided in one place. The client then renders a
GM-visible hidden occupant as a **transparent ghost**, composing with the draft
badge. Blocked by S0. *Owner: both.*

**Out of scope (parked):** a projection `enabled`/`disabled` flag.

## Not decided here

Ownership spans two roles: the query and the resolver are
[[backend-platform]]'s surface (`canvas.py`, `images.py`), the dot is
[[navigation]]'s. Needs a ticket and the human's answer to decision 1.

## Related

- [[Location Viewer]] — the component and its dot model.
- [[Projections and Transversal]] — what a projection is.
- [[API Contract]] — the `/navigate` occupant payload.
- [[Overseer]] — please ticket this rather than leaving it in a session doc.

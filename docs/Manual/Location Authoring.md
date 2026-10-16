---
title: Location Authoring
date: 2026-10-16
tags:
  - transversal
  - authoring
  - location
  - manual
  - mcp
aliases:
  - Place Authoring
  - Making a place playable
status: draft
---

# Location Authoring

How to author a **place** in Transversal so that it is *functional* — a scene can be set there and played — and then **rich**, so it rewards being there.

Written for two readers, because both do the same work: **you, in the GM panels**, and **an agent** writing the same layers through the tools. Every layer below says where it is written.

A running example runs through the note: **Barragem Norte**, the dam above São Bento do Vale. It is deliberately plain, so each layer shows up as a gap rather than a hypothetical.

Related: [[Location Viewer]] (what the renderer reads), [[Media Pipeline]] (backgrounds), [[Appearance Authoring Guide]] (writing the image prompt), [[Content Completeness Checklist]] (the per-type checklist).

> [!info] The one rule
> **Every authored thing on a place is read by a specific surface.** Before writing a layer, know what reads it. § 7 lists the fields nothing reads yet — writing into those produces content that exists, validates, and does nothing.

## 1. What "functional" and "rich" mean

Four states, each strictly better than the last. **The state is decided by what is missing, not by how much is there** — a place with forty traits and no background is still only in the tree.

| | State | A scene here can… | What it costs |
|---|---|---|---|
| **0** | In the tree | be *reached* by travel, and shows a gradient | one create |
| **1** | Playable | *look* like a place, and a roll here has something to oppose | a background + a small stat block |
| **2** | Rich | *reward* being explored: people to meet, things to do, danger, ways out | + cast, zones, challenges, portals |
| **3** | Deep | *change over a campaign*: it has an owner, a mood that shifts, secrets, a history | + faction ties, rules, a blue book |

**State 1 is the minimum for play.** The model to copy is ***Azure Dawn*** — laws, two challenges, a background image, four zones and twelve occupants. A place built to that shape reads as a place rather than a name.

The layer most often missing is not the writing but the **image**: a place can carry a great deal of good text and still render as a colour gradient, because nothing surfaced it.

> [!danger] A place's traits can live in two places
> Its traits can be attached to the **place** or to one of its **bodies** (a projection), and both are in use. A read or a count that looks at only one of them comes back **smaller rather than wrong** — the failure is silent. § 8 has the short version of how to count and how to say which one you are editing.

## 2. Layer 0 — the place exists

**Required:** a `LOCATION` entity with a `name`, a `universe`, and a **parent**.

There is no such thing as a location without a parent. A place that is a root — the country, the region, the valley — has the **universe** as its parent. The parent link is what makes the tree, and everything about navigation is derived from it.

| | |
|---|---|
| **Panels** | The **＋** row in the tree, under the place or universe it belongs in; the create form's **Type** is `LOCATION`. |
| **Agent** | `create_location` — creates the entity, sets its location, and adds the parent link in one call. New locations start **unpublished**; pass `unpublished=false` to publish immediately. |
| **Read back** | `location_tree` (the whole hierarchy) or `location_neighborhood(id)`. |

> [!warning] The commonest authoring mistake
> Creating a location **without a parent**. The entity then exists, is reachable by direct link, and is **absent from the tree** — so it never appears on any map and no travel route reaches it.

**A child location is two things, not one.** The entity in the tree, **and** a zone on its parent's background. Creating it with a parent does half of that — it appends a default zone at the centre of the picture. Placing it properly is Layer 2.

**A place can also be held *inside* something** rather than filed under a world — an inner world that a character, a GMC, an asset or a faction carries. It is the same parent link, with an entity on the other end instead of a place, and **it does not appear in the Places tree at all**: you make it and read it from that entity's own panel, where the **Inner locations** section lists what it carries and opens any of them as a child panel. Reach for this when the place belongs to a *thing* rather than to a world — and note that the carrier's universe need not be the carried place's.

### What a developed place looks like

**Krasnoyarsk-45** is the standard to aim at. The place itself carries `climate` *"frozen from October to May"*, `function` *"a town that exists to support a thing above it"*, `population` *"a closed town the maps leave out"*, and its own doom pool; the facility above it carries `function` *"the state's anomalous-artifact programme"*, `surveillance` *"every corridor, and one agent"* and `resources` *"a budget that appears from nowhere"*.

That is what the trait statements are for. Each one is a sentence the GM can read aloud, and the set of them is the place.

## 3. Layer 1 — the place can be seen and opposed

This is the layer where a place stops being a name. Two things, and both are required.

### 3.1 The background image

**Required: one image with the `background` role.** Without it the viewer renders a gradient, the dots float on a colour, and every travel preview degrades to a plain thumbnail.

Author it from the `imagen` **appearance** trait on the location — see [[Appearance Authoring Guide]] for the wording, and remember a location is a **humanless backdrop**.

> [!tip] Two things that are easy to get wrong
> - **The picture's size matters.** The viewer's zoom is bounded by the art, and the long side wants to be **≥ 1216px** — on a phone the art's pixels are what decide how much room the dots have.
> - **Do not hand-write the stored `background_image` field.** It is a copy, and it goes stale when a file is renamed; the renderer resolves the image **by role** instead. Set the image and let the app resolve it.
>
> | | |
> |---|---|
> | **Panels** | The image section on the location — upload, or generate from the appearance. |
> | **Agent** | Generation and upload go through the media endpoints, not the authoring tools: `POST /api/v1/imagen/{entity_id}` and `POST /api/v1/media/upload`. |
> | **Read back** | The `image(role: "background")` resolver, which is what the renderer uses. |

### 3.2 The stat block — a small set of rated traits

**Required: 3–5 trait settings from the `location` set.** This is what a roll "here" is opposed by, and what the place *is*.

The set is large; the point is not to use all of it. A place wants one trait from each of four jobs:

| Job | Traits to reach for | Why |
|---|---|---|
| **What it looks like** | `atmosphere`, `architecture`, `terrain`, `appearance`, `size` | what a player sees when the scene opens |
| **What it is for** | `function`, `purpose`, `production`, `operations` | why anyone is here, and what is at stake |
| **How it feels** | `mood`, `genre`, `society`, `culture`, `law` | the register the GM plays it in |
| **What opposes you** | `surveillance`, `defenses`, `regime alert`, `resources`, `infrastructure` | the mechanical answer to "can we get in?" |

Write the trait's **`statement`**. A `location` trait with a die and no statement is a number nobody can narrate.

| | |
|---|---|
| **Panels** | The location's trait section — attach from the registry, then write the die and the statement. |
| **Agent** | `add_trait_to_entity`, then `update_trait_setting` to revise. |
| **Read back** | `GET /api/v1/locations/{id}/traits` — the location's own traits, with their scene images resolved. (`location_neighborhood` does *not* return traits; § 8 says which read to use.) |

**Also required for a place with rules of its own:** a `laws` setting — the set that tells a player what gets them in trouble *here* rather than in the abstract. It is the best-populated content set in the Three Realms for exactly that reason: it is what makes a place feel governed.

### 3.3 The scene as a *place* — worked example

This is the shape, using the running example's own corridor:

```
São Bento do Vale
  population  d8   "nine thousand, and shrinking"
  economy     d10  "one company, one dam, and what it pays"
  mood        d8   "a town that already knows how this ends"
  appearance  d4   "a company town that knows"

Barragem Norte
  function     d10 "tailings dam and beneficiation plant"
  production   d10 "iron ore, and a great deal of mud"
  surveillance d8  "company cameras on every gate"
  appearance   d4  "a wall holding mud"
```

That is a playable place: four traits a player can look at, press on, or be opposed by, each with a sentence the GM can read aloud. **State 1 is roughly four to six of these**, one from each of the four jobs above — and the pattern worth copying is that good statements are **specific and loaded**: *"one company, one dam, and what it pays"* is a scenario hook wearing a stat block's clothes.

Neither place has yet what every place should have next: a **background image** and a **`laws` setting**. When a place is in this state, those are the first two things to add.

## 4. Layer 2 — the place is rich

"State 2" is "there is something here". Five independent additions, in value order.

### 4.1 Occupants (who is here)

**Occupants are entities whose current location is this place** — a character, a GMC or an asset. They appear as dots automatically; nothing needs wiring on the location.

| | |
|---|---|
| **Panels** | The **＋** row under the place; drag a dot to move somebody. |
| **Agent** | `create_gmc` to make one, `move_entity` to move an existing one. **Never** move an entity by writing its location field directly — that skips the travel rules. |
| **Placement** | Dots sit at a percentage of the picture. Unplaced occupants are derived from the zones, or fall into a row across the lower third — which can read as deliberate placement to whoever looks next. |
| **A GMC a player may take over** | Tick **support eligible** on them, or the take-over picker will not offer them. |

**Richness rule:** a scene needs at least one **face** — somebody with a name, a want, and a reason to talk. A place whose only occupant is scenery is a corridor.

### 4.2 Zones (where the doors are)

A **zone** is a pin on this location's picture that links to a **child location**. It is what makes a background *navigable* rather than a picture.

- The position is a **percentage of the image** (0–100).
- The pin points at the **child**, and it renders **the child's name** — the label is never stored, so renaming the child cannot leave a stale pin.
- The zone is also the **arrival point**: arriving at the parent *from* that child lands you on the zone's coordinates. No zone means the arrival framing falls back to the centre.

| | |
|---|---|
| **Panels** | Drag the pins in the location editor's arrange mode; the zone section also adds and removes them. |
| **Agent** | `set_zones(location_id, zones)` — **replaces the whole list**, so read first (`location_neighborhood`), adjust, then write. |
| **Read back** | `location_neighborhood(id)` → the children and the zones. |

> [!warning] Zones are the layer people skip
> Every child needs its zone placed, or the parent's picture shows a pin at dead centre with no relationship to the room it opens. When you create a batch of children, **plan a placement pass afterwards** — nothing does it for you.

### 4.3 Ways out (portals)

Travel *out of* a universe, or *between* distant places, is a **`transversal` link** between two locations. Each becomes a **portal dot**, labelled with the destination.

| | |
|---|---|
| **Panels** | The location editor's **Transversal Links** section — the destination, and the rule that fires when someone passes through. |
| **Agent** | `create_relationship(from_id, to_id, type="transversal")`. |
| **Position** | Portal dots sit on the right edge by default and stack downward. In the panels, drag them. |
| **Read back** | `location_neighborhood` → the transversal links. |

Portals are **directional**: the link points one way, and the viewer draws a dot for each outbound link. Author both directions, or know that you did not.

### 4.4 Something to do (challenges)

A **challenge** is a trait setting whose rating type is `CHALLENGE`. In a place, it is the thing the players are up against *here* — the clock, the doom pool, the project.

- **Positive** = a progress clock: `capacity` is the target, and reaching it completes the challenge.
- **Negative** = a doom pool: dice are spent *outward* to strengthen opposition, and failures add dice. **`capacity` on a negative pool is a ceiling, not a goal** — a negative pool at capacity is "maxed out", not "finished".

The registry set is `regime alert`, `doom`, `threat`, `hazard`, `event`, `environmental hazard`, `access`, `encounter` and the like, plus `complications` for what goes wrong with a person rather than a place.

| | |
|---|---|
| **Panels** | The location's trait section, with the rating type set to Challenge; the pool's dice are the ledger. |
| **Inheritance** | Pools are **inherited by zones** — a parent's pool is readable from a child, which is how one doom pool covers a whole complex. Spending it from a child spends the parent's one pool; that is the intended model. |
| **Read back** | `GET /api/v1/locations/{id}/challenge-traits` — pools only, including what the zones inherit. |

> [!note] One die per pool, or a ledger?
> A challenge's dice **are** its ledger. Record the dice it currently holds rather than a rating, and let play spend them.

### 4.5 Something to find (trait chips)

The location set doubles as the **discoverable** layer: traits a player can reach by looking around — `rumour`, `secret`, `information`, a detail of `appearance`, a hidden asset. They render as **trait chips** on the scene.

Chip **positions** can be placed on the art, and there is no authoring tool for that yet — a chip without a position still renders, in the stack of unplaced chips alongside the labels rather than on the map. So: author the **trait**, and place it later in the panels if the art warrants it.

## 5. Layer 3 — the place is alive

"State 3" is what makes a place persist across sessions. None of it is required; all of it is what separates a set from a setting.

| Addition | What it is | Where |
|---|---|---|
| **Who controls it** | A **control** trait on the faction's tie to the place — the claim, with a die. Iron Roots holds its grounds this way (`sect seat`, d10). Not ownership; a faction does not *own* a city. | The tie's traits, in the faction or location editor |
| **What is happening** | A faction **agenda** anchored at this place, so the world changes here between sessions | see [[Faction Authoring]] |
| **A rule of its own** | A **place-lent rule** — something that fires for anyone here. Worth knowing before you author the first: **no place has ever lent a rule that is not an arrival trigger**, so this path is untested. Expect to be the one who proves it. | **Manage SFX**, attached to the location |
| **Overlay** | A persistent visual state: `mist`, `fire`, `rain`, `snow`, `fog`. Cheap atmosphere. | The location editor |
| **What happened here** | A **blue book** entry tied to the place, so its history accumulates | the blue book |
| **Starter status** | Marks a place a new character may be scattered to | the location editor |
| **A route to somewhere** | The guided route to a destination. Written by a rule rather than authored by hand. | effects |

## 6. The whole checklist

Work through it in order — each layer depends on the one above it.

```
[ ] 0  LOCATION entity — name, universe, parent
[ ] 1  imagen appearance trait on the location     (text for the prompt)
[ ] 1  background image, role=background, ≥1216px long side
[ ] 1  3–5 `location`-set settings, each WITH a statement
[ ] 1  ≥1 `laws` setting — what gets you in trouble here
[ ] 1  a challenge (positive clock OR negative doom pool)
[ ] 2  occupants: ≥1 named NPC with a want, placed on the art
[ ] 2  zones for every child, positioned (not the centre default)
[ ] 2  portals: transversal links BOTH ways, positioned
[ ] 2  discoverables: rumour/secret traits, placed if the art warrants
[ ] 3  control claim on the faction tie, if a faction holds it
[ ] 3  overlay, if the place has a persistent mood
[ ] 3  blue book entry, if anything has happened here
```

## 7. Fields nothing reads yet — do not author into these

Writing here produces content that exists, validates, and changes nothing. These are the location-relevant ones.

| Field | What it looks like it does | Why it does nothing |
|---|---|---|
| **who knows of this place** | fog of war: only some entities know it exists | no hidden locations exist, and the read is not consulted in practice |
| **hidden** | conceal a location from players | no hidden locations exist, so the rule has never run |
| **precise chip positions** | place chips exactly on the art | there is no authoring tool for it yet; the chip still renders, unplaced |
| **portal positions beyond the first** | position the second, third, fourth portal | only the first portal's position is read; the rest use the default |
| **a place-lent rule that is not an arrival trigger** | a rule that fires for anyone here | nothing in the world does this yet — see § 5 |

**Before authoring a layer, confirm what reads it.** If the answer is "nothing", that is a gap for whoever owns that surface rather than an authoring job — say so rather than working around it.

## 8. Verifying a place

The panels show what a GM sees. These three reads are the whole check for an agent, and they use the **same** wire the renderer uses:

1. **`location_neighborhood(id)`** — the app's own answer to "what is around here": the place, its parent, its children, its links, its occupants, its faction ties. It confirms the tree and the cast. (It does **not** return traits.)
2. **`GET /api/v1/locations/{id}/navigate`** — the **renderer's own payload**. This is the read that proves a background resolves and a dot has an image. If a dot has no image here, it has none in play.
3. **The `image(role:)` resolver** — `background`, `sheet`, `navdot`. The reference is the **role**, not the stored filename. (For traits, use `/traits` and `/challenge-traits` as in § 3.2 and § 4.4.)

> [!important] Do not verify from the entity document
> The stored background field is a copy and **goes stale when a file is renamed**. A read that looks correct there can serve a dead URL to the viewer. Verify through the navigate payload, which resolves by role.

**A negative check worth running every time:** does the destination image at a zone actually match the location's arrival framing? The arrival rule is single — the dot preview and the travel use the same function — but it depends on the zone existing. A missing zone is invisible until someone walks through the door.

### 8.1 Counting a place's content correctly

Because a place's traits can hang off the place **or** off one of its bodies, a count taken from one anchor comes back **smaller rather than wrong** — and a place that is well authored can read as empty.

**Use the app's own read**: `GET /api/v1/locations/{id}/traits?viewer=gm` resolves both anchors, and `/challenge-traits` gives the pools alone. When a count comes back zero, corroborate it with that read before you believe it or repeat it.

### 8.2 The two anchors, and why the difference matters when you edit

A location with a body has two places its traits can live, and the reader resolves both. This matters when you *write*:

- A trait written against the **entity** is an **ego** trait — it applies wherever the entity is.
- A trait written against a **projection** is a **morph** trait — it belongs to that body only.

For a location that exists in one universe the difference is invisible in play, which is why the current data contains both.

**Which you get depends on whether you name a body.** Trait writes are **entity-anchored by default**, which is the right default for a place. When a location *has* a body and you want the trait on the place rather than the body, leave the body unset — and say so in your notes, because the two are indistinguishable in a read.

## 9. Gotchas

- **A location without a parent is unreachable.** The tree, not the entity, is what travel reads.
- **Creating a child is half the job.** The zone placement is the other half, and it defaults to dead centre.
- **Replacing a zone list replaces all of it.** Read, adjust, write — or you silently delete the other pins.
- **The label on a pin is not stored.** It is the child's name, so renaming the child is safe and correct.
- **An unplaced occupant is placed for you**, near a zone or in a row at the bottom — which can read as deliberate placement to someone who did not author it.
- **A trait with a die and no statement is not content.** The die is the mechanic; the statement is what the table reads aloud.
- **A portal points one way.** Author both directions or accept a one-way door.
- **Zone pools are inherited, not copied.** Spending a die against a child's inherited pool spends the parent's one pool — the intended model, not a leak.
- **Never move an entity by writing its location field.** Use the travel path, which runs the travel rules and the body policy.

**Scope note:** this authoring surface covers places and the things attached to them. It does **not** cover a player character — a PC's sheet is the player's, always. When a place needs a face, the answer is a GMC.

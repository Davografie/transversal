---
title: Location Authoring
date: 2026-09-27
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

Written for both readers: a person in the GM panels, and an agent driving the same work through MCP. Every layer says which surface writes it, because **the surfaces are not uniform** — some layers are GraphQL, some are REST-only, and two are not writable through MCP at all.

A running example runs through the whole note: **Barragem Norte**, the dam above São Bento do Vale — a location that exists in the live data with **zero content on it**, so every layer below is visible as a real gap rather than a hypothetical.

Related: [[Content Completeness Checklist]] (the per-type checklist — its Location section is still accurate), [[Location Viewer]] (what the renderer reads), [[Media Pipeline]] (backgrounds), [[Appearance Authoring Guide]] (the `imagen` text), [[Factions and Organizations Design Log]] §6.6 (who controls a place), [[Content Gap Analysis]] (how empty the corpus is, measured).

> [!info] The one rule
> **Every authored thing on a place is read by exactly one surface.** Before writing a layer, know which surface reads it — the layers that nothing reads are listed in § 7, and writing into them produces content that renders as a card and does nothing.

## 1. What "fully functional" and "rich" mean

Four states, each strictly better than the last. **The tier is determined by what is missing, not by how much is present** — a place with forty traits and no background is still tier 1.

| Tier | Name | A scene here can… | Cost |
|---|---|---|---|
| **0** | In the tree | be *reached* by travel, and shows a gradient | 1 create call |
| **1** | Playable | *look* like a place, and a roll here has something to oppose | background + a small stat block |
| **2** | Rich | *reward* being explored: people to meet, things to do, danger, ways out | + cast, occupations, challenges, portals |
| **3** | Deep | *change over a campaign*: it has an owner, a mood that shifts, secrets, a history of what happened here | + faction ties, SFX, blue book |

**Tier 1 is the minimum for play, and earth is further along than it looks:** measured through the API, **46 of earth's 100 locations carry content, and 41 carry at least one `location`-set trait** (125 such traits across the universe — 25 distinct traits of the set in use). Three Realms: **204 of 258 carry content, 147 with a location-set trait.** The model to copy is ***Azure Dawn*** — 7 `laws`, two challenges (one a negative event, "Sweeping the Path of Petals"), a background image, four zones and twelve occupants — sitting among 19 locations that carry 346 traits between them.

**What is still universally missing in earth is the image layer: not one earth location has a background image.** That is the gap, not the traits.

> [!danger] Before you measure anything: locations keep traits in TWO places
> A location's traits can be **entity-anchored** (`_from → entities/{id}`) or **projection-anchored** (`_from → projections/{id}:{universe}`, the same morph model characters use). **Both are live, and which one a location uses is an accident of when it was authored.** In this corpus **5,438 of 10,732 trait settings are projection-anchored** — more than half.
>
> A count that reads only `_from == entities/{id}` is therefore **wrong by roughly half**, and silently: it returns a smaller number rather than an error. I made exactly that mistake, in AQL, and it produced the false claims this note originally carried — `Krasnoyarsk-45` "5 settings" (really **20**), `São Bento do Vale` "0 settings" (really **16**). **A place I called empty had been authored.**
>
> **Never count location traits by joining on `_from`.** Use **`GET /api/v1/locations/{id}/traits?viewer=gm`**, which resolves both anchors — or filter AQL on the setting's **`entity_id`** field, which is set for every anchor (`entity_id == "loc-…"`). Both give the same answer; only the `/traits` read also resolves inherited pools. A worked comparison is in § 8.




## 2. Layer 0 — the place exists

**Required:** a `LOCATION` entity with a `name`, a `universe`, and a **parent**.

There is no such thing as a location without a parent. A place that is a root — the country, the region, the valley — has the **universe** as its parent. What makes the tree work is the `super` edge: **child → parent**. Everything else about navigation is derived from it.

| | |
|---|---|
| **MCP** | `create_location(name, universe, parent_id)` — creates the entity, sets `current_location`, **and appends the `super` edge in one call**. New locations are `unpublished` by default; pass `unpublished=false` to publish now. |
| **Panels** | The location editor's create dialog; adding a child under a selected location. |
| **Read back** | `location_tree` (the whole hierarchy) or `location_neighborhood(id)`. |

> [!warning] The commonest authoring mistake
> Creating a location **without** `parent_id`. The entity then exists, is reachable by direct link, and is **absent from the tree** — so it never appears on any map and no travel route reaches it. In the live data this is not hypothetical: **195 of 410 locations are unreachable from the authored control point** (B174).

> [!example] What "developed" actually looks like, on live earth data
> Counted with `location_tree` for the subtree and `/locations/{id}/traits?viewer=gm` for the content — **resolving both anchors**, which is the whole point below:
>
> | Place | Locations | Traits | Of which `location`-set | Background |
> |---|---:|---:|---:|---|
> | **Krasnoyarsk-45** | 4 | **20** | **16** | none |
> | São Bento do Vale | 5 | **16** | **13** | none |
> | Турышка | 9 | 28 | **4** | none |
> | Siberia | 12 | 35 | 11 | none |
>
> **Krasnoyarsk-45 is earth's best-developed place, and it is genuinely well built.** Its whole corridor is authored: the ARD Facility reads `function` *"the state's anomalous-artifact programme"*, `surveillance` *"every corridor, and one agent"*, `operations` *"measure it, then find out what it is for"*, `resources` *"a budget that appears from nowhere"*, and a `regime alert` doom pool — and Krasnoyarsk-45 itself has `climate` *"frozen from October to May"*, `function` *"a town that exists to support a thing above it"*, `population` *"a closed town the maps leave out"*, and its own doom pool. Barragem Norte, in the Brazil corridor, is the same standard: `function` *"tailings dam and beneficiation plant"*, `production` *"iron ore, and a great deal of mud"*, `surveillance` *"company cameras on every gate"*.
>
> **Турышка, by contrast, is large but thin** — nine rooms and 28 traits, of which only **four** are `location`-set (all `appearance`); the other 24 are `imagen` prompt text (10) and a one-line `secrets` description per room (7) plus a few assets. It has the most *entities* and among the least *content*.
>
> **So the two failure modes are real and they are opposites:** Krasnoyarsk-45 is well-authored **but invisible** — every entity in its subtree is `unpublished` and it has no background, so none of that work reaches a player. Турышка is **visible but thin** — fully published, nine rooms, almost nothing to roll against.
>
> And the correction that matters: **the Brazil corridor is not empty.** São Bento do Vale carries `population` *"nine thousand, and shrinking"*, `economy` *"one company, one dam, and what it pays"* and `mood` *"a town that already knows how this ends"`. I originally reported it at zero because of the anchor mistake flagged above.
>
> On `unpublished`: it is **not** a travel gate. The backend stores and returns it; the client keeps unpublished **occupants** off a player's dot set (`LocationViewer.vue:315`) and badges drafts in the GM tree. An unpublished *location* is still reachable — a GM-only marker, not a lock. But it does mean authored content nobody sees, which is a decision worth making deliberately rather than by default.





**A child location is two things, not one.** The entity in the tree, **and** a zone on its parent's background. `create_location` with a `parent_id` does half of that — it appends a **default zone at (50, 50)**. Placing it properly is Layer 2.

## 3. Layer 1 — the place can be seen and opposed

This is the tier where a place stops being a name. Two things, and both are required.

### 3.1 The background image

**Required: one image with the `background` role.** Without it the viewer renders a gradient, dots float on a colour, and every travel preview degrades to a plain cover thumbnail.

Author it from the `imagen` **appearance** trait on the location (see [[Appearance Authoring Guide]] for the text conventions — a location is a **humanless backdrop**, and `prompt_include_ancestors` decides whether the ancestor chain joins the prompt).

> [!tip] Two constraints that are easy to violate
> - **Aspect and resolution matter.** The viewer's zoom is bounded by the background art, and the long side wants to be **≥ 1216px** — on a phone the art's pixels decide how much of the scene the dots have room to occupy.
> - **The stored `background_image` field is denormalised and goes stale.** The renderer resolves the image **by role** (`image(role: "background")`), and the navigate payload serves the same resolution. Do not hand-write the field unless there is no image record — 9 of 127 locations pointed at an `_anim_<hash>` path that no longer existed.
>
> | | |
> |---|---|
> | **Panels** | The image panel on the location: upload, or generate from the appearance. |
> | **MCP** | Generation and upload are **REST**, not MCP: `POST /api/v1/imagen/{entity_id}`, `POST /api/v1/media/upload`. |
> | **Read back** | `get_entity` → `background_image`; or the `image(role:)` resolver, which is what the renderer uses. |

### 3.2 The stat block — a small set of rated traits

**Required: at least 3–5 trait settings from the `location` set** (`ts-location-afd2`, 42 traits). This is what a roll "here" is opposed by and what the place *is*.

The set is big; the point is not to use all of it. A place needs one trait from each of four jobs:

| Job | Traits to reach for | Why |
|---|---|---|
| **What it looks like** | `atmosphere`, `architecture`, `terrain`, `appearance`, `size` | what a player sees when the scene opens |
| **What it is for** | `function`, `purpose`, `production`, `operations` | why anyone is here, and what is at stake in it |
| **How it feels** | `mood`, `genre`, `society`, `culture`, `law` | the register the GM plays it in |
| **What opposes you** | `surveillance`, `defenses`, `regime alert`, `resources`, `infrastructure` | the mechanical answer to "can we get in?" |

Write the trait's **`statement`** — that is the authored text. A `location` trait with a die and no statement is a number nobody can narrate. (Measured: on earth, **162 of 334 settings carry no statement at all**; in three_realms, 1449 of 3150.)

| | |
|---|---|
| **MCP** | `add_trait_to_entity(entity_id, trait_id, statement, die, …)`; `update_trait_setting` to revise. |
| **Panels** | The location's trait panel. |
| **Read back** | `GET /api/v1/locations/{id}/traits` — the location's own traits **with their navdot images resolved**. (`location_neighborhood` does *not* return traits; it returns the neighborhood structure — see § 8.) |

**Also required for a place with rules of its own:** a `laws` trait setting (`ts-338519695`: `rules`, `unwritten rule`, `save face`, `might makes right`). This is the set that tells a player what gets them in trouble *here* rather than in the abstract — and it is the best-populated content set in three_realms (411 settings) precisely because it is what makes a place feel governed.

### 3.3 The scene as a *place* — worked example

**This one is not invented — it is what the Brazil corridor already carries, verbatim:**

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

That is a playable place: four traits a player can look at, press on, or be opposed by, each with a sentence the GM can read aloud. **Tier 1 is roughly four to six of these**, one from each of the four jobs in § 3.2 — and the pattern to notice is that good statements are **specific and loaded**: *"one company, one dam, and what it pays"* is a scenario hook wearing a stat block's clothes.

What neither of these has yet is a **background image** and a **`laws` setting** — the two things every earth location lacks, and the first two things to add.


## 4. Layer 2 — the place is rich

Tier 2 is "there is something here". Five independent additions, in value order.

### 4.1 Occupants (who is here)

**Occupants are entities whose `current_location` is this place** — `CHARACTER`, `GMC` or `ASSET`. They appear as dots automatically; nothing needs wiring on the location.

| | |
|---|---|
| **MCP** | `create_gmc(name, universe, location=…)`; `move_entity` to place an existing one. **Never** set `current_location` through `update_entity` for a move — it is a bare field assignment that skips the travel effect and the body policy. |
| **Placement** | `map_x` / `map_y` (percentages), **REST-only**: `PATCH /api/v1/entities/{id}/map-position`. Without them the viewer **derives** a position from the zones, or falls back to a row across the lower third. |
| **Portrait** | The occupant dot renders the entity's image; the `navdot` role is the small-round variant. |
| **A GMC a player may take over** | `update_entity(support_eligible=true)` — without it the take-over picker will not offer them (B86). |

**Richness rule:** a scene needs at least one **face** — somebody with a name, a want, and a reason to talk. A place whose only occupant is scenery is a corridor.

### 4.2 Zones (where the doors are)

A **zone** is a pin on this location's background that links to a **child location**. It is what makes a background *navigable* rather than a picture.

- `x` / `y` are **percentages of the background image** (0–100).
- `location_id` points at the **child location**; the pin renders **the child's name**, so the label is never stored and a rename cannot leave a stale pin.
- The zone is also the **arrival point**: arriving at the parent *from* that child lands you on the zone's coordinates. No zone means the arrival framing falls back to centre.

| | |
|---|---|
| **MCP** | `set_zones(location_id, zones)` — **replaces the whole list**, so read first (`location_neighborhood`), adjust, then write. Returns the zones as they are after the write. |
| **Panels** | Drag the pins in the location editor's arrange mode. |
| **Read back** | `location_neighborhood(id)` → `children` + the location's `zones`. |

> [!warning] Zones are the layer people skip
> Every child needs its zone placed, or the parent's background shows a dot at the default (50, 50) — a pin floating in the middle of the art with no relationship to the room it opens. When creating a batch of children, **plan to spend a placement pass afterwards**; there is no tool that does it for you.

### 4.3 Ways out (portals)

Travel *out* of a universe or *between* distant places is a **`transversal` edge** between two locations. Each becomes a **portal dot**, labelled with the destination and its `transversal_type`.

| | |
|---|---|
| **MCP** | `create_relationship(from_id, to_id, type="transversal")`. |
| **Panels** | The location editor's portal controls. |
| **Position** | `nav_positions` — a JSON string of `{"parent": {"x":90,"y":15}, "portal": {"x":90,"y":50}, "portal:1": {…}}`. Defaults are parent (90, 15) and portals stack down the right edge at +10 y each. **MCP: `update_entity(nav_positions=…)`.** |
| **Read back** | `location_neighborhood` → `transversal`; `update_entity` echoes `nav_positions`. |

Portals are also **one-way-capable**: the edge is directional, and the viewer draws a dot for each outbound link. Author both directions (or know that you did not).

### 4.4 Something to do (challenges)

A **challenge** is a trait setting with `rating_type = CHALLENGE`. In a place, it is the thing the players are up against *here* — the clock, the doom pool, the project.

- **Positive** = a progress clock: `capacity` is the target, and reaching it fires `challenge_completed`.
- **Negative** = a doom pool: dice are spent *outward* to strengthen opposition, and failures add dice. **`capacity` on a negative pool is a ceiling, not a goal** — a negative pool at capacity is "maxed out", not "finished", and the completion event does not fire for it (see [[Challenge Rating Type]]; the semantics are deferred).

The registry set is `ts-156724245` (`regime alert`, `doom`, `threat`, `hazard`, `event`, `environmental hazard`, `access`, `encounter`, …), plus `complications` for what goes wrong with a person rather than a place.

| | |
|---|---|
| **MCP** | `add_trait_to_entity(…, trait_id="trait-regime-alert", rating_type="CHALLENGE", polarity="NEGATIVE", dice=[…])`; `update_trait_setting` for `capacity`. |
| **Inheritance** | Pools are **inherited by zones** — a parent's pool is readable from a child, which is how one doom pool covers a whole complex (B191). |
| **Read back** | `GET /api/v1/locations/{id}/challenge-traits` — pools only, including what the zones inherit. (`/traits` is the read that adds the location's non-challenge traits.) |

> [!note] One die per pool, or a ledger?
> A challenge's `dice` **is** its ledger. Record a pool as the dice it currently holds, not as a rating, and let play spend them.

### 4.5 Something to find (trait chips)

The location set doubles as the **discoverable** layer: traits a player can reach by looking around (`rumour`, `secret`, `information`, `appearance` details, hidden `assets`). They render as **trait chips** on the scene.

Chip **positions** live in `trait_positions` (a map of trait-setting id → {x, y}) — **REST-only**, `PUT /api/v1/locations/{id}/trait-positions`, and **there is no MCP tool for it**. A chip without a position still renders, in the **stack of unplaced chips** alongside the labels rather than on the map. So: author the *trait*, and place it later in the panels if the art warrants it.

## 5. Layer 3 — the place is alive

Tier 3 is what makes a place persist across sessions. None of it is required; all of it is what separates a set from a setting.

| Addition | What it is | Surface |
|---|---|---|
| **Who controls it** | `control` on the **faction ↔ location tie** — the claim, with a die. Iron Roots holds its grounds this way (`sect seat`, d10). Not `owned_by`; a faction does not *own* a city. | `add_relationship_trait` |
| **What is happening** | A faction **agenda/portent chain** anchored at this place, so the world changes here between sessions | see [[Faction Authoring]] |
| **A rule of its own** | A **place-lent SFX** — something that fires for anyone here. **Unexercised, not merely unauthored:** the only location-owned SFX in the whole graph is Azure Dawn's arrival trigger, which `placeSfxRules` filters out as an arrival trigger, so nothing in the live tree reproduces the branch (B189). Authoring the first one is genuinely unexplored — expect to be the one who tests it. | `create_sfx` + `add_owner_sfx(owner_type="location")` |
| **Overlay** | A persistent visual state: `mist`, `fire`, `rain`, `snow`, `fog` (the data also accepts `sparkles`). Cheap atmosphere. | `update_entity(overlay=…)` — MCP-covered |
| **What happened here** | A **blue book** entry tied to the place, so its history accumulates | `add_journal_entry` |
| **A route to somewhere** | The guided route: `destination_location` plus the next hop. **Effect-only** — written by an SFX, never authored directly. | effects |
| **Starter status** | `starter_location=true` marks a place a new character may scatter to | `update_entity(starter_location=…)` |

## 6. The whole checklist

Copy this into a ticket or a work note. **Order matters** — each layer depends on the one above it.

```
[ ] 0  LOCATION entity — name, universe, parent (super edge)
[ ] 1  imagen appearance trait on the location     (text for the prompt)
[ ] 1  background image, role=background, ≥1216px long side
[ ] 1  3–5 `location`-set settings, each WITH a statement
[ ] 1  ≥1 `laws` setting — what gets you in trouble here
[ ] 1  a challenge (positive clock OR negative doom pool)
[ ] 2  occupants: ≥1 named NPC with a want; map_x/map_y placed
[ ] 2  zones for every child, positioned (not the 50,50 default)
[ ] 2  portals: transversal edges BOTH ways, nav_positions placed
[ ] 2  discoverables: rumour/secret traits, positions if the art warrants
[ ] 3  control claim on the faction tie, if a faction holds it
[ ] 3  overlay, if the place has a persistent mood
[ ] 3  blue book entry, if anything has happened here
```

## 7. What nothing reads — do not author into these

Writing here produces content that exists, validates, and changes nothing. These are the location-relevant entries from [[Content Gap Analysis]] § 3.15; each is a broken or absent reader, not a missing content layer. **Two have since been fixed** — kept in the table because a guide that lists a repaired defect as broken is its own kind of drift.

| Field | Status | What it looks like it does | Why it does nothing |
|---|---|---|---|
| `known_to` | **open** | fog of war: only some entities know of this place | empty on **302 of 304** reads that consult it; there are **no hidden locations and no hidden trait owners** in live data |
| `Entity.hidden` | **open** (B137, in progress) | conceal a location from players | no hidden locations exist, so the rule is code-read only |
| `trait_positions` | **by design** | place chips precisely on the art | writable only by REST, no MCP tool — a chip with no position lands in the unplaced stack (B92) |
| `nav_positions` beyond the first portal | **by design** | position the 2nd, 3rd portal | keyed `portal:1`, `portal:2`… — a single `portal` key positions only the first |
| place-lent SFX | **open, and unexercised** | a rule that fires for anyone at this place | **no place lends a non-arrival rule** anywhere in the graph (B189, done 2026-09-25 — the card fix landed, the data gap did not) |
| `RollTableEntry.conditions` | **✅ fixed** (B179, done 2026-09-25) | conditional table entries | was stored and never read; the roll path now falls back to the nearest earlier matching entry, and a chosen menu row is refused |

**Before authoring a layer, confirm which surface reads it.** If the answer is "none", that is the reader's owner's ticket, not an authoring job.

## 8. Verifying a place

The panels show what a GM sees. For an agent, these three reads are the whole check, and they read the **same** wire the renderer uses:

1. **`location_neighborhood(id)`** — the app's own answer to "what is around here": `location`, `parent`, `children`, `transversal`, `occupants`, `faction_memberships`, `occupant_relations`. It confirms the tree and the cast. (It does **not** return traits — use `/traits` and `/challenge-traits` for those.)
2. **`GET /api/v1/locations/{id}/navigate`** — the **renderer's own payload**. This is the read that proves a background resolves (`resolved_bg`), a navdot image resolves (`navdot_image`), and the guided route lights. If a dot has no image here, it has none in play.
3. **The `image(role:)` resolver** — `background`, `sheet`, `navdot`. The reference is the **role**, not the stored filename.

> [!important] Do not verify from the entity document
> `background_image` on the entity is denormalised and **goes stale when the media pipeline renames a file**. A read that looks correct there can serve a dead URL to the viewer. Verify through the navigate payload, which resolves by role.

**A negative check worth running every time:** does the destination image at a zone actually match the location's arrival framing? The arrival-point rule is single — the dot preview and the travel use the same function — but it depends on the zone existing. A missing zone is invisible until someone walks through the door.

### 8.1 Counting content correctly — a worked comparison

Two locations, both live, both earth, counted three ways:

| Location | AQL on `_from == entities/{id}` | AQL on `entity_id == "{id}"` | `GET /locations/{id}/traits` |
|---|---:|---:|---:|
| `loc-krasnoyarsk` | 5 | **5** | **5** |
| `location-ard-facility-de4078f2` | **0** ❌ | **5** ✅ | **6** |

Two things to take from that table:

1. **The `_from` join is wrong**, and wrong *silently* — it reported 0 for a location that has five authored traits. It only finds entity-anchored settings; the ARD Facility's five hang off `projections/location-ard-facility-de4078f2:earth`.
2. **The `/traits` read returns one more than `entity_id`** (6 vs 5) — that sixth is the `regime alert` **challenge pool**, which `/traits` includes and a plain setting count does not need. Use `/challenge-traits` when you want pools alone.

`entity_id` is set correctly on **all 10 732** settings, so it is the reliable AQL join if you are not using the API. **Prefer the API read anyway** — it also resolves inherited pools, which no single-collection query will.

### 8.2 The two anchors, and why a location's identity is one of them

A location with a **projection** has two places its traits can live, and the reader resolves both. This matters when you *edit*: a trait written against the entity is an **ego** trait and applies wherever the entity is; a trait written against a projection is a **morph** trait and belongs to that body only. For a location that exists in one universe the distinction is invisible in play — which is exactly why the corpus has both without anyone noticing.

**Which you get depends on `projection_id`.** `add_trait_to_entity` omits it unless you pass it, so the setting is **entity-anchored by default** — which is the right default for a location, and it means the mixed anchoring in this corpus came from elsewhere (the migration, or the frontend editor). When a location *has* a projection and you want the trait on the place rather than the body, **leave `projection_id` unset** and say so in your notes, because the two are indistinguishable in a read.


## 9. Gotchas

- **A location without a parent is unreachable.** The tree, not the entity, is what travel reads.
- **Creating a child is half the job.** The zone placement is the other half, and it defaults to dead centre.
- **`set_zones` replaces the entire list.** Read, adjust, write — or you silently delete the other pins.
- **The label on a pin is not stored.** It is the child's name. Renaming the child is safe and correct; there is no label to keep in sync.
- **`map_x`/`map_y` are REST-only, and absent means derived.** An unplaced occupant is put near a zone or in a row at the bottom, which can read as deliberate placement to someone who did not author it.
- **A trait with a die and no statement is not content.** The die is the mechanic; the statement is what the table reads aloud.
- **`transversal` is directional.** Author both directions or accept a one-way door.
- **Zone pools are inherited, not copied.** Spending a die against a child's inherited pool spends the parent's one pool (B191) — which is the intended model, not a leak.
- **Never move an entity with `update_entity(current_location=…)`.** Use `move_entity` / the travel path, which runs the travel effect, the transversal record and the body policy.

## 10. Provenance

The surfaces and field semantics in this note were read from the code on 2026-09-27: `entity_manager`/`navigate_from` (`db/repository_mixins/canvas.py:456`), the navigate and zone REST endpoints (`api/rest/locations.py`), the viewer's dot model (`LocationViewer.vue` — `navDots`, `arrivalPoint`, `NAV_DOT_DEFAULTS`), the MCP tool schemas (`mcp/server.py` — `create_location`, `set_zones`, `update_entity`), and the domain models. **The completeness figures are from [[Content Gap Analysis]]'s live census**, not from this guide's own measurement.

**Two corrections this note carries, both mine, both from measuring with raw AQL instead of the API's own reads.** The human caught the first; the second I found while answering *"how are you checking locations?"*

1. **The hierarchy.** I walked it through the denormalised `current_location` field when **the parent link is the `super` edge** (child → parent), so descendants were invisible and a 9-location subtree read as 1. *Fix:* walk `super` inbound, or just take `location_tree`, which is the app's own nesting.
2. **The anchoring — the larger error.** I counted a location's traits with `_from == entities/{id}`, which sees only **entity-anchored** settings. **5,438 of the corpus's 10,732 settings are projection-anchored**, and this guide's original figures were wrong by roughly half as a result: `Krasnoyarsk-45` at "5" (really 20), and **`São Bento do Vale` at "0" — a place I called empty that had 16 traits authored, including `mood` *"a town that already knows how this ends"*.** *Fix:* read `GET /api/v1/locations/{id}/traits?viewer=gm`, or filter on the setting's `entity_id` field. § 8.1 shows both side by side.

**Both errors had the same root cause and the same tell:** the count came back *smaller* rather than *wrong*, and I reported the number without a second read to corroborate it. The standing rule this role already had — **API first; AQL only where no API surface exists** — would have prevented both. The corollary now written into the guide and my session doc: **when a census produces a zero, corroborate it against the API's own read before it becomes a claim.**

**Scope note:** this authoring surface covers places and the things attached to them. It does **not** cover a player character — a PC's sheet is the player's, always. When a place needs a face, the answer is a GMC.

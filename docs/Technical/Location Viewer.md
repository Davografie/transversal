---
title: Location Viewer
tags:
  - transversal
  - technical
  - frontend
  - locations
  - navigation
  - animation
aliases:
  - LocationViewer
  - Map Viewer
  - Location Navigation
status: canonical
---

# Location Viewer

How the full-screen location renderer works — the background image/video, the
draggable dots, travel between locations, and the animations that accompany
each step.

The component is `src/frontend/src/components/LocationViewer.vue`, mounted once
by `App.vue`. It is the immersive projection of the player's current location:
a background scene with interactive dots for zones, navigation destinations,
other occupants, and the player's own character.

> [!note] Rework complete (2026-09-09)
> Parallax is **2D overscan** (scene rendered ~10% larger than the viewport on
> both axes). The [[Location Parallax Rework]] is done: everything that moves is
> a GPU `transform` driven by a single `sceneCamera` object — the background and
> world dots live in one transformed scene layer, navdot "hole" previews are
> inner `<img>`s moved by an explicit (clamped) transform, and
> `background-attachment: fixed` is gone entirely. Drags measure ~144 fps with
> zero dropped frames on a hardware-accelerated display.

## Responsibilities

- Render the current location's background (static image, or animated `.webm`/`.mp4`).
- Pan the background so it follows the player character's `map_x`/`map_y` (parallax).
- Render four kinds of dots as `<MapDot>`: **zones**, **nav destinations**, **occupants**, and **self**.
- Handle three drag systems: zone placement (GM), nav-dot placement (GM), and occupant/self movement.
- Drive location travel: drag the self dot onto a zone/nav dot, or tap an expanded zone/nav dot, to travel.
- Play the travel portal, arrival, and ambient effects.
- Sync with other players via SSE (`entity_moved`) and render their dice pools as rings.

It is deliberately **state-light**: it fetches navigation state from the backend
and re-renders from that projection, rather than keeping a separate world model
locally.

## Component & dependency map

- `LocationViewer.vue` — the renderer (this document's subject).
- `MapDot.vue` — the reusable circular dot `<button>`. Collapses to 16px, expands
  to a larger image/label bubble when `expanded`, and grows again when
  `draggable`. Emits `click`, `overlay-click`, and `drag-start`.
- `PoolDiceRing.vue` — the dice ring orbiting a dot (dice pool phase + resolved total).
  Its radius is `BASE_RADIUS_PX × scale`, where `scale` is the dot's own
  `CONTROLLED_SCALE` (1.4) when a client is driving that entity and 1 otherwise —
  so the ring stays outside the rim at every dot size instead of slipping inside a
  grown portrait. Transparent portraits overflow the rim at the top, so their dice
  are **bottom-anchored**: spread over the arc that excludes the top
  `TOP_GAP_FRACTION` (0.2) of the circle, centred on 6 o'clock and fanning upward
  to both sides (verified: no die lands in the reserved slice for n = 1–6, and
  `n = 1` sits exactly at the bottom). The resolved total badge mirrors that —
  above the ring normally, below it when the portrait overflows the top.
- `composables/useTransversalLinks.js` — toggles a transversal edge's
  `transversal_type` (`consciousness` ⇄ `inapposite`).
- `composables/media.js` — shared helpers `isVideoUrl(url)` and
  `panAxis(imageAspect, viewAspect)` (returns `'x'`, `'y'`, or `null`).

## Props & emits

```js
props = {
  locationId,           // string, required — current location
  locationName, universe,
  backgroundImage,      // resolved (quality-adjusted) URL
  rawBackgroundImage,   // pre-quality URL, used as load-error fallback
  entityId,             // string, required — the player's character
  editZones,            // GM "arrange map elements" mode
  overlay,              // 'mist' | 'fire' | 'rain' | 'snow' | 'fog' | null
  gmMode,
  remotePools,          // entity_id → { dice, player_id, phase }
  remoteResults,        // entity_id → { total, effect_die, rolls, ... }
  camera,               // mobile teaser: zoom in on the self character
}

emits = ['moved', 'update:editZones', 'inspectEntity', 'dragging']
```

`moved` fires after any relocation and is handled by `App.vue` (`onMoved`) to
update `currentLocationId`/`universe` and re-fetch peers. `inspectEntity` opens
the character sheet for a tapped occupant. `dragging` (boolean) fires when an
occupant drag actually starts/ends, so `App.vue` fades the HUD out during desktop drags.

## State model

```js
currentImage        // active background URL (image or video)
imageAspect         // width/height of currentImage, or null if unknown
isVideoBg           // computed — isVideoUrl(currentImage)
nav                 // raw GET /navigate response (location, parent, children, transversal, occupants)
zones               // nav.location.zones (location_id, x, y, background_image) — the dot's
                    //   label is the *linked child's* name, never stored on the zone
occupants           // nav.occupants (name, type, id, image, map_x, map_y)
activeElement       // { type, name?, id?, key? } — which dot is currently expanded/pop-out
travelAnim          // { active, x, y, image, bgX, bgY } — portal overlay state
showElements        // toggled off during the portal so dots remount and fade back in
showSelf            // toggled off during the portal so the self dot re-runs its arrival pop
optimisticOverlay   // immediate UI overlay value, synced from props.overlay (SSE)
navDotPositions     // { parent: {x,y}, portal: {x,y}, 'portal:N': {x,y} }
destNavCache        // lazy cache: destination_id → { arriveX, arriveY, destAspect }
lerpActive          // true while non-self occupant dots ease to new SSE positions
gmDotPositions      // { [locationId]: {x, y} } — GM free-roam dot, device-local
```

Drag state is kept separately:

```js
dragging          // zone drag: { index, startX, startY, origX, origY }
occDragging       // occupant drag: { index, startX, startY, origX, origY }
dragTarget        // non-reactive — nearest travel target during self-drag
expandLevels      // reactive — 'zone-<zoneId>'/'nav-<key>' → 0..1 proximity level (multi-bubble)
armedDot          // reactive — which dot is within travelProximity (drop → travel)
guidedDot         // reactive — the single dot that is the next hop toward the character's
                  //   destination ('zone-<id>'/'nav-<key>'), from nav.next_hop; '' when none
occDragMoved      // pointer passed the 6px tap threshold
occSuppressClick  // suppress the synthesized click after a real drag
```

## Data flow

On mount (and whenever `locationId` changes while not mid-travel),
`fetchNav()` runs:

1. `GET /api/v1/locations/{locationId}/navigate` → `nav`, `zones`, `occupants`.
2. `loadNavPositions()` reads `location.nav_positions` into `navDotPositions`.
3. `preloadDestNavCache()` lazily pre-fetches each connected destination's
   `/navigate` to compute arrival positions + destination aspect ratios (see below).
4. Auto-pops the player's own character (`activeElement = { type: 'occupant', id: entityId }`).
5. `fetchPools()` pulls the location's active dice pools for the ring badges.

### navigate response shape

```json
{
  "location":   { "_key", "name", "zones", "nav_positions", "background_image", ... },
  "parent":     { "_key", "name", "navdot_image", ... } | null,
  "children":   [ { "_key", "name", "navdot_image", ... } ],
  "transversal":[ { "_key", "name", "navdot_image", "transversal_type", ... } ],
  "occupants":  [ { "name", "type", "id", "image", "map_x", "map_y" } ]
}
```

- `parent` = the single outbound `super` edge (up).
- `children` = inbound `super` edges (down).
- `transversal` = outbound `transversal` edges (lateral), each merged with its
  `transversal_type` (`consciousness` or `inapposite`).
- `occupants` = characters/GMCs/assets whose `current_location` is here, or who
  have a projection here; nav-dot images resolved from the `navdot` image role.

## Rendering model

### Background & parallax

A single `sceneCamera` computed derives everything — container dims
(`cw`/`ch` via ResizeObserver), scene size (`w`/`h` — the cover fit, overscanned
by `PAN_OVERSCAN` (1.1) on **both** axes so it pans horizontally and vertically),
and the pan (`panX`/`panY`) that anchors the self character (50/50 in the mobile
`camera`/teaser mode, otherwise its `map_x`/`map_y`, with `TEASER_ZOOM` scaling
the scene in teaser mode).

**The scene also scales to the viewer's WIDTH** (`locationScale`: `880 / viewerWidth`,
clamped 1–2.2, folded into `zoom`). Since everything in the scene layer is positioned in
`image-%`, the scene's size is what decides how far apart two chips or dots really sit:
a chip is a fixed number of pixels, so the narrower the viewer, the smaller the share of
the scene those pixels cover. The same location gave its nearest chip pair 44px apart on
a 390px phone against 86px in the docked desktop view; the compensation puts 66px between
them and leaves the wide layout at exactly 1.0, so travel dots stay reachable where there
is room. `880` is deliberately the docked view's own width: at `900` the wide layout
picked up a 2% increase, and that alone was enough to put the docked view's travel dot
out of reach — raising the scale *flat* costs map coverage everywhere.

**Scale is bounded by the background art, not by taste.** Every location background in
the database is at most 1080px wide (median 832; none reaches 1500), and the `background`
role is served as the **`_Large`** variant — 478×700 — while an 832×1216 `_Original` sits
beside it. A Pixel-class phone (412×915 CSS, DPR 2.625, ~817px viewer band) therefore
draws the background at:

| scale | scene tall (CSS) | drawn (device px) | vs `_Large` 700 | vs `_Original` 1216 |
| --- | --- | --- | --- | --- |
| 0.42 | 378 | 991 | 1.4× | 0.8× |
| 1.0 | 899 | 2360 | 3.4× | 1.9× |
| 1.845 | 1659 | 4355 | 6.2× | 3.6× |
| 2.2 (cap) | 1978 | 5193 | 7.4× | 4.3× |

So the background is upscaled in every configuration, before any compensation is applied:
1:1 would need a scale of about **0.42**. Raising the cap buys map size and spends
sharpness in proportion — the real levers are serving the `_Original` (1.74× linear) and
larger source art, both outside this role.

```
<viewer (overflow:hidden)>
  <scene-layer transform:translate3d(-panX,-panY,0)>
    <bg img/video (overscan-sized)>
    <zone/nav/occupant dots + pool rings (image-space, transform-centered)>
  </scene-layer>
  <self dot + arrival rings + HUD (screen-space)>
  <travel overlay>
</viewer>
```

The background is a plain `<img>`/`<video>` filling the scene layer. World dots
sit at **image-space** coordinates inside the layer, so panning never moves them
individually — one compositor operation moves everything. `toViewportPos()`
(image → viewport) and `toImagePos()` (viewport → image) are thin wrappers over
`sceneCamera`; they stay in lock-step so a dragged dot's `map_x`/`map_y` stays
correct as the scene pans under it. Navdot destination images pan inversely
through the "hole" (`navDotPerspective`), clamped to the image bounds (see
gotchas).

### Dot types

| Type | Variant | Default color | Meaning |
|------|---------|---------------|---------|
| `zone` | — | green | A child location hotspot on the map |
| `nav` | `parent` | gold | Travel up (to the parent location) |
| `nav` | `portal` | purple | Travel laterally (transversal destination) |
| `occupant` | `character` | blue | Another player's character here |
| `occupant` | `gmc` | amber | A GMC here |
| `occupant` | `asset` | (base) | An asset here — currently no dedicated color |
| `self` | `character` | pulsing blue | The player's own character |

A **zone** is a pin that links to a **child location** via `location_id` — and that
link supplies both its identity (`zoneId`) and its **label**: the dot renders the
child's *current* name (`zoneLabel`), so renaming a child can never leave a pin
stale. Nothing about the zone's name is stored on the zone itself. A zone is always
a link — there are no decorative pins.

### Guided route — the next hop

An SFX can hand a character **directions** in the fiction (the effects system's
"set destination" action writes `Entity.destination_location`); the map then lights
the way, one step at a time.

- `fetchNav` asks *as the acting character*
  (`/locations/{id}/navigate?entity_id=…`), so the response carries
  `destination {location_id, name}` and `next_hop` (a neighbouring location id).
  Both keys are **absent** without an `entity_id`, so other callers are unaffected;
  `next_hop` is **null** when the character is already there or nothing connects them.
- `guidedDot` maps `next_hop` onto **exactly one** dot, by the stored link: a nav dot
  whose `target.id` matches, else a zone whose `location_id` matches — never by name.
- That dot renders as `.map-dot.guided`: a **gold sonar ping** (`guided-ping`),
  deliberately unlike the cyan `armed` *breathe*, because "this is the way" is a
  different statement from "you would travel if you dropped here" — and both can be
  true at once (a guided dot arms the moment you drag onto it).
- **One hop, never the whole route.** Following the blinks still means travelling, so
  the map never becomes a read-out of the graph.
- The hop is measured from the **location being viewed**, so each location shows its
  own next step.
- **Hidden locations stay hidden unless unavoidable.** `get_route_next_hop`
  (`db/repository_mixins/canvas.py`) searches with `hidden` locations removed and
  falls back to the full graph **only** when that leaves the origin unreachable — so a
  concealed place is never given away while a way around it exists. It is a two-pass
  exclusion, not a weight penalty: a cheap hidden shortcut versus a long open detour is
  a different answer from "avoid it if you can".

**Authoring is meant to refuse a destination with no route**
(`get_location_distances_from(origin, {destination})` empty ⇒ refuse, with an error),
so an unusable directions SFX should never reach a player; `destination` present with
`next_hop: null` is the belt-and-braces case for a graph that changed afterwards.

### Trait chips

The location's own traits (plus the challenge pools it inherits) render as **chips** —
see [[Location Trait Chips]] for the spec, the placement (`trait_positions`, dragged in
arrange mode through `usePercentDrag`) and the traits-tab filter. Two things belong
here because they are the viewer's:

- **Clicking a chip plays its trait**, through `composables/useTraitPlay.js` — the same
  act, and the same code, as clicking a trait's *rating* in a sheet. The map supplies
  no-ops for what it does not have (no pool tree, no armed-SFX view) and emits
  `addToPool`, which `App.vue` routes to the same `diceRef.addFromSheet` the sheet
  uses. A click in arrange mode is a drag, not a play.
- **The wire shape is normalised** on the way in (`utils/locationTrait.js`): the REST
  read is snake_case with lowercase enums, and the shared play compares the sheet's
  camelCase uppercase. Skipping it makes a CHALLENGE trait behave like a static one —
  it pushes its raw dice instead of spending a die.
- **A chip wears its trait's picture** when it has one (`B200`): the trait's `navdot`
  image leads the chip, and a transparent cutout is sized past the chip's own height so
  it breaks the chip's outline instead of being contained by it. The payload carries
  `navdot_image` / `navdot_transparent`, batch-resolved per page; the geometry is pinned
  in `e2e/tests/trait-chip-marker.spec.js`. See [[Location Trait Chips]] §marker.
- **A placed chip rests as its marker and opens near the character.** Proximity here is
  a `computed` over `selfPos`, not the drag-time `expandLevels` the bubbles use, because
  a chip has to *stay* open at rest; the pointer and a tap open it too, a tap on a
  closed chip opens it rather than playing it, and **arrange mode opens them all**. The
  auto-stack never collapses. See [[Location Trait Chips]] §resting and open.

Zones and nav dots show the destination's background as their expanded image
(the `navdot_image` role) — the "hole": an inner `<img>` sized as the
**destination's own scene layer** (cover + `PAN_OVERSCAN` + the teaser zoom) and
moved by an explicit px transform that cancels the scene layer's pan
(screen-fixed content), aligns the destination's arrival point, and adds the
inverse-parallax shift. The dot's own `border-radius` + `overflow: hidden` clips
it; the img must not clip itself (`border-radius: 0`). `destNavCache` supplies
`arrivalX`/`arrivalY`/`destAspect` so that preview shows the exact arrival point
**and scale** — see the destination-preview gotcha below.

`self` is the camera anchor: the scene pans so this dot keeps its image position,
and it is always draggable. With no perspective entity (`entityId == null` — the
GM free-roam view) it becomes a **GM free-roam dot**: draggable, labelled with the
role glyph (🏛 Architect / 🎭 Player — the same icons as the player settings
overlay). Its position is **not stored** (B96): taking over free-roam parks the
dot on whatever sits under the centre of the view at that moment, so the camera
does not jump to a remembered spot, and opening straight into free-roam falls back
to the location centre. It is held per location for the session only
(`gmDotPositions`, in memory). Dropping it on a
zone/navdot travels the **view only** — no entity is moved: `relocate` emits a
view-only `moved` (name/id + universe) and the dot lands at the destination's
arrival point.

Transparent **occupant/self portraits** (media pipeline's
`EntityImage.transparent`, exposed as `image_transparent` on occupants) render
as **floating cutouts emerging from a portal ring**: the dot becomes a
see-through circle outline (no fill, no vignette), the bottom-anchored cutout
is cropped to the ring's bottom radius (`--dot-r`) with a matching bottom
border, and the head sticks out above the rim — `object-fit: contain`, no
circular crop, the image's own alpha is the shape. The video branch (transparent
WEBM) uses the same path. Occupants share one size (60–88px). Location images
are assumed never transparent, so the hole path is unaffected.

**Viewed occupant** (`viewed`, from `viewingEntityId`) mirrors the rail's
`.peer-chip.viewing` state on the map: a highlight ring (2px `--accent`) with no
fill change — "you are peeking at this one". It is drawn as a `box-shadow`
spread rather than a border so the dot's box never changes size and the
expanded ring/portrait geometry stays exact; the expanded variant re-states the
inset vignette. Assumed = the `self` dot (pulsing blue), so the two states stay
visually distinct.

**Actively controlled** occupants (`.controlled`) are scaled up by
`--controlled-scale` (currently 1.4, tunable in `MapDot`). "Controlled" is a
table-wide fact, not a local one: `App.vue` unions the server's `playerBodies`
(the entity each player is currently driving — refreshed on the `main_active`
SSE event) with the local `entityId`, and passes `controlledEntityIds` down. The
`self` dot carries it whenever a perspective entity is set; the GM free-roam dot
does **not** — that is a view marker, not a driven entity. The GM's own
assumptions feed the same set: `switchPerspective` reports the taken body with
`POST /players/{id}/control/{entity}?stamp=false`, which records presence without
touching spotlight recency (see [[Troupe Play]]), and `returnToSelf` clears it
when the GM goes to free-roam. Both arrive over SSE as `body_changed`, which
refreshes `playerBodies`.

**How the size is applied — and why it must differ.** Occupant dots rest at
`transform: scale(var(--controlled-scale))`. The `self` dot cannot use that — it
runs `arrivePop`, which fills `transform` forwards and outranks any normal
`transform` declaration — so its resting size comes from the *individual* `scale`
property, which composes with `transform` instead of competing with it. That costs
nothing there, because a take remounts the self dot (it is keyed by the perspective
entity).

**The animation is a keyframe, not a transition.** A transition only runs if the
element *persists* and the property *interpolates*; neither held for dots
re-rendered by an SSE update, so the size snapped on Chrome and Firefox alike.
Instead `LocationViewer` diffs `controlledEntityIds` on every change
(`animateSizeChanges`) and marks the ids that entered or left for one 300ms cycle:
`.growing` runs `controlledGrow` (1 → `--controlled-scale`), `.settling` runs
`controlledSettle` (`--controlled-scale` → 1). A keyframe fires whenever the class
appears — **including on a freshly mounted element** — so the growth cannot be
skipped. Both use `both` fill, so their end state equals the resting rule and
removing the class afterwards cannot jump.

**Why a dot could stick large.** `controlledEntityIds` used to union *every*
`playerBodies` entry, our own included — and our own is a server echo: it arrives
late over SSE and, when no session is streaming, may never arrive at all. After a
switch the stale entry kept the body just left in the sized-up state,
inconsistently (only when the refresh was missed). Our own body is now read from
the local `entityId` alone — `playerBodies` entries for our own `playerId` are
skipped — while the server list still drives *other* clients' dots. The 60s
presence poll also re-fetches `playerBodies`, so a missed `body_changed` cannot
leave a dot sized up for long.

  `poolDiceFor` returns the pool's dice in every phase, and prefers `results.rolls`
  once the phase is past `adding` (never in `adding`, where the pool itself is the
  truth).
- **The roll animation is mirrored from the panel**: while a roll is live the ring
  tumbles each die's face every `TUMBLE_MS` (70ms, the roller's interval) and locks
  them **one at a time** left-to-right — `FIRST_LOCK_MS` (900) before the first,
  `LOCK_STAGGER_MS` (1000) between each — playing `roll-pop` on entry and
  `die-lock` as each face settles, the same shapes as `DiceRoller`. Animations use
  the **`scale` property, never `transform`**: each item's inline `transform` is
  what places it on the ring, so a `transform` animation would override it and
  stack every die at the centre.
- **Results are shown only while the roll is live.** `poolDiceFor` prefers
  `results.rolls` only when the phase is *past* `adding` — so clearing the pool
  (which returns the phase to `adding`) hides the ring immediately instead of
  holding the last roll's dice until the end of the beat.
- **The ring's dice come from the pool in *every* phase.** There are two phase
  vocabularies: the roller publishes `rolling`/`picking`, while the server's roll
  endpoints (`api/rest/roll.py`) broadcast `rolled`/`selected`/`resolved` with the
  dice already carrying their results. Gating on a phase list (`adding`/`rolling`)
  meant that mid-roll — when the server's `rolled` arrives before `roll_result` sets
  `results.rolls` — the ring had dice and a phase it didn't recognise, so it
  **vanished until the results landed**. It now returns the pool's dice in every
  phase; a cleared pool still empties it, because the server sends that as
  `dice: []` with phase `adding`.
- **The ring's reveal runs *with* the panel, not after it.** The roller's own
  sequence is: tumble → (server call) → first lock at `FIRST_LOCK_MS` (900) → one
  die per `LOCK_STAGGER_MS` (1000) → `emit('rolled')` *at the end*. Anything keyed
  off `roll_result` therefore started a full settle-cycle late (the reported
  "the diceroll already settled before the rings start"). The ring instead derives
  its results from **the server's enriched dice**: `api/rest/roll.py` broadcasts
  `pool_updated` with dice already carrying `result` the moment the roll resolves,
  and `PoolDiceRing.rolledDice` treats a fully-resulted pool as the result set. On
  our own device that broadcast used to be dropped entirely (the handler's
  own-entity branches both declined it), so `App.vue` now records it into
  `remotePools` as well — same data the other devices already had.
- **The reveal reads left-to-right, like the panel's row.** Dice are placed from
  9 o'clock sweeping up and over (`distribute(..., Math.PI)`), and the
  bottom-anchored transparent spread starts at the arc's *left* end — previously
  the transparent case began on the right, so its settle order mirrored the panel.
  (Verified numerically for n = 1–5: x ascends with the index, and no die enters
  the reserved top slice.)
- **Your own ring is fed locally.** `sharePhase`/`onDiceRolled`/`@picked` write the
  acting entity's phase and results into `remotePools`/`remoteResults` too (via
  `mirrorOwnResult`). Solo play has no SSE at all, and in a session the `pool_updated`
  echo deliberately skips the acting entity — so without this the dot you are
  rolling from would never animate.

## Interactions

### Click / pop-out

- **Occupant** → always `emit('inspectEntity', id)` (opens the sheet).
- **Self dot** → `emit('inspectEntity', entityId)`; the GM free-roam dot emits
  nothing (there is no entity to inspect).
- **Zone / nav dot** → toggle the expanded bubble via `activeElement`.
- **Expanded zone / nav dot overlay** → `onExpandedClick` triggers travel.
- **Background click** → dismisses the pop-out, re-popping self.
- **Edit mode** → clicking a portal nav dot toggles its `transversal_type`.
- In GM mode `inspectEntity` lands in `App.vue`'s peer-click semantics: clicking
  the character you already act as while inspecting another resets the view back
  to it (the sheet swaps on the `overrideEntityId` watch); with nothing being
  inspected, the same click exits to free-roam.

### Three drag systems

**1. Zone drag (GM edit mode)** — `onZoneDragStart` records the origin, `onDragMove`
mutates `zones[i].x/y` live (clamped to 2–98), `onDragEnd` persists via
`PUT /api/v1/locations/{id}/zones`.

**2. Nav dot drag (GM edit mode)** — `onNavDragStart` moves `navDotPositions[key]`
live and persists the whole `nav_positions` object on end via the
`updateEntity` GraphQL mutation.

**3. Occupant / self drag** — the core interaction:

- `canDragOccupant`: GM (arrange mode) can drag anyone; the player can drag
  self; the GM (outside arrange mode) can drag GMCs/assets directly.
- A 6px threshold separates a tap (inspect) from a real drag (`occDragMoved`).
- Pointer moves are **coalesced to one update per animation frame**:
  `onOccDragMove` buffers the latest pointer position and schedules a single
  `requestAnimationFrame` (`applyOccDragFrame`), so a high-polling mouse can't
  starve rAF with per-event re-renders.
- While dragging self, **or a GMC/asset the GM is carrying (B170)**, the drag frame
  computes two proximity sets:
  - **`expandLevels`** — every zone/nav bubble within `EXPAND_PROXIMITY` (24 image-%)
    opens, sized continuously by distance (`1 - (d/EXPAND_PROXIMITY)²`, quick ramp).
  - **`armedDot`** — the single nearest bubble within `travelProximity()` (the
    expanded bubble's rendered radius) arms travel; it breathes so a drop there
    reads as "will travel".
  - `dragTarget` (non-reactive) holds the armed target for the drop handler.

On drop:

- **Self + near a zone** → find the matching child and `travelWithAnimation`.
- **Self + near a nav dot** → `travelWithAnimation` to the parent/portal target.
- **GM + a GMC/asset dropped on a zone or nav dot (B170)** → **send that occupant
  travelling** via `sendOccupant`, and persist *nothing* here: it no longer stands
  on this location. The GM's own view does not move and no portal animation plays —
  the viewer is not travelling, only the occupant is. `canTravelOccupant` gates it
  (never self; never arrange mode, which is for positioning), and
  `travelDescriptor` resolves the destination so the world lands in the same state
  the occupant's own drop would have produced: a plain `POST /entities/{id}/move`
  for a zone/parent, `POST /entities/{id}/consciousness-travel` for a consciousness
  portal, or `POST /locations/{from}/portal/{to}/fire` when the portal has effects.
  The dot then disappears on the `fetchNav()` refresh.
- **Otherwise** → persist the new `map_x`/`map_y` via
  `PATCH /api/v1/entities/{id}/map-position` (which broadcasts `entity_moved` over SSE).

## Travel pipeline

`travelWithAnimation(zone, child, imageUrl?)` is the single entry point for all
location switches (zone click, nav-dot click, and drop-on-target):

1. Resolve the destination image (`imageUrl` or `childImage(zone)`), using the
   `navdot_image` role.
2. Preload the destination image (await `onload`/`onerror`).
3. Hide dots (`showElements = false`, `showSelf = false`).
4. Fetch the destination's `/navigate` and compute the **arrival position**:
   - the destination's zone whose child points back to `sourceId`, else
   - the destination's parent dot, else
   - the destination's matching portal dot, else
   - fall back to the source zone's own position.
5. Set `travelAnim = { active: true, x, y, image, bgX, bgY }` — origin is the
   source dot's viewport position; `bgX`/`bgY` seed the overlay's background pan.
6. `relocate(child._key, child.current_universe, child.transversal_type === 'consciousness')`.
7. After a 1300ms timeout (the portal expansion): `fetchNav()`, lock the
   character at the arrival position, swap `currentImage`, clear the portal, and
   re-show elements + self.

> [!warning] The wipe's box is the **map's**, so `TravelOverlay` must stay `absolute`
> `TravelOverlay` is a direct child of `.location-viewer` and must be
> `position: absolute; inset: 0` — **never `fixed`**. Every percentage it receives
> (`--travel-x`/`--travel-y` from `toViewportPos`, and the destination scene box
> sized from `cw`/`ch`) is measured against the **viewer's** box, so the wipe has to
> be that same box. `fixed` resolves against the viewport, and the docked layout
> makes those two differ: `.stage.dock-sheet .location-viewer { left: var(--dock-w) }`
> offsets the map by 400px, which opened the portal one dock width away from the dot
> that was clicked and parked the destination scene at the viewport's left edge. The
> mobile stack breaks the same thing on the vertical axis, where the viewer is a
> band rather than the whole screen. Pinned by a browser test —
> `e2e/tests/travel-overlay.spec.js` asserts `offsetParent` is the map and that the
> overlay matches the map's client box **at the same moment** (comparing bounding
> rects across two round-trips reports a phantom offset, because the map is a moving
> frame while the wipe opens).

`relocate` routes the move:

- **Consciousness travel** (`transversal_type === 'consciousness'`) →
  `POST /api/v1/entities/{id}/consciousness-travel` (project into a body at the
  destination; see [[Projections and Transversal]]).
- **Otherwise** → `POST /api/v1/entities/{id}/move` (full physical transport).

## Animation timeline

The travel effect is a choreographed sequence:

1. **Portal expand** (`.travel-overlay`, `portal-expand`) — a `clip-path: circle()`
   expands from dot-size at the departure point to full-screen over 1.2s,
   revealing the destination background. The overlay renders the destination as
   the scene layer it is about to become (`travelScene` → `destSceneLayer`), not
   as a CSS `cover`: a plain `cover` is a `PAN_OVERSCAN` short, so the background
   visibly grows the moment the wipe swaps out.
2. **Background swap** — at ~1.3s the real background is patched in *under* the
   portal, then the portal is lifted only once that media has actually painted
   (`waitForBackgroundPaint`: image `decode()`, or video `loadeddata` + a paint
   cycle). Transitions are force-disabled for one frame to avoid cross-frame
   flicker, then re-enabled. The portal is **not** removed on the timer — see the
   arrival-paint gotcha.
3. **Arrival rings** — around the landing spot: two implode rings (energy drawn
   inward), a portal flash, then three outward bursts.
4. **Self pop-in** (`arrivePop`) — the character scales in with a brightness
   flash, then settles into the idle `selfPulse` glow.

Ambient effects — `selfPulse` (idle player glow), `dot-pulse` (draggable dashed
border), and the overlay/particle system below — run continuously.

## Effects

- **CSS overlay layer** — `mist`, `fire`, `rain`, `snow`, `fog`, each with a
  backdrop-filter and keyframe animation (`mistDrift`, `fireFlicker`, `rainFall`,
  `snowFall`, `fogRoll`).
- **Canvas particle system** — a `<canvas>` layer driven by `requestAnimationFrame`;
  `fire` (embers), `snow` (flakes), and `rain` (streaks) emit particles per a
  per-overlay config (`PARTICLE_CONFIGS`).
- **GM overlay switcher** sets `overlay` on the location (optimistic, with
  rollback on error); **player effects toggle** disables the visual/particle
  layer per device, persisted in `localStorage`.

## SSE & multiplayer

- `location_changed` drives the GM's move toast, so its payload carries **names
  as well as ids**: `name` (the entity) and — on a plain move — `to_name` (the
  destination). `move_to` already loads the destination to read its universe, so
  that one is free; `name` is free everywhere. Without them the toast can only
  print ids, because the entity has just left the location whose peers would name
  it and the destination may be somewhere the client has never been. `App.vue`
  prefers the payload, falls back to `entName`/`placeNames`, and looks an unknown
  place up once. (It used to read a `to_name` the payload did not have and cache
  it under the *entity's* key, which is why the toast turned into ids from the
  second move on.)
- `entity_moved` events (broadcast by the map-position endpoint) arrive through
  `App.vue`'s SSE composable; `fetchNavWithLerp()` is exposed and re-fetches nav
  with `lerpActive = true`, so non-self occupant dots ease to their new positions
  over 1.5s instead of teleporting.
- **The lerp is for *foreign* moves only — direct input must land instantly.**
  The map-position endpoint broadcasts to *every* subscriber, including the one
  that sent it, so the mover's own echo used to arm the 1.5s ease and the next
  drag of a dot would slide out from under the pointer still holding it (most
  visible for a GM repositioning several occupants in a row). Two guards, both
  needed:
  - `App.vue` passes the moved entity and position to `fetchNavWithLerp`, which
    checks them against `ownMoves` — the writes this viewer sent, keyed by entity
    and the exact position, trusted for 2s — and does a plain `fetchNav()` when
    they match. (If the position matches what we wrote, our local state already
    has it, so nothing would animate anyway; the point is not to *arm* the ease
    for what comes next.)
  - `:lerping` is `lerpActive && dragDotKey !== o.id`, so the dot under the
    pointer never has the `left`/`top` transition regardless of what armed
    `lerpActive`. Note `entity_updated` also calls `fetchNavWithLerp()` with no
    origin, which is correct: only `entity_moved` carries a position to match on.
- `remotePools` / `remoteResults` props drive `PoolDiceRing` around occupant and
  self dots; the ring takes the dot's `scale` and `transparent` so it tracks both
  the controlled-dot size and the portrait's top overflow (see the component entry
  above).

## Key design decisions & gotchas

- **One `sceneCamera` source.** All pan/size math (`sceneLayerStyle`,
  `toViewportPos`/`toImagePos`, `navDotPerspective`, `holeStyleFor`,
  `travelProximity`, the drag frame) reads from the single `sceneCamera`
  computed — never re-derive the pan independently or the math will drift.
- **The pan is clamped to the image bounds.** `sceneCamera` clamps `panX`/`panY`
  to `[0, w - cw]` / `[0, h - ch]` so the scene always covers the viewport. The
  teaser pulls the character to the *viewport centre*, and near the edge of a map
  that asks for more pan than the image has to give: on mobile the image slid
  off-screen and left a black band beside the character (measured: 99px of a
  390px viewport with the character at 90%, up to 195px at the edge; 0 before the
  fix when expanded, because at `p = 0` the pan is proportional and already in
  range — so this only ever bit as the teaser zoomed). Clamping loses the
  character's exact anchoring at the extremes; that beats showing the void behind
  it. Verified across band heights, aspect ratios and positions: worst band is
  0px, and the character never ends up off-screen.
  Note the camera zoom is necessarily **uniform**: `.scene-media` is a
  `cover`-fit, so the visible image always has the scene layer's aspect (which is
  the image's own). "Zoom in vertically but not horizontally" would change that
  aspect — it needs either a stretched image or a re-crop, both worse than the
  current behaviour. If the *horizontal framing* should hold steady instead, the
  lever is the anchor, not the zoom: keeping `anchor.x = mx` pulls the character
  to the centre vertically only.
- **One arrival-point rule.** `arrivalPoint(destNav, fromId)` is the only place
  that answers "where does an entity land when it arrives at a location from
  another one", and both the dot preview (`preloadDestNavCache`) and the travel
  (`travelWithAnimation`) call it. There used to be two implementations, with
  *different fallbacks* when nothing was stored — the preview guessed the map
  centre, the travel guessed the parent dot — so for the 351 of 410 locations
  with empty `nav_positions` the hole framed the destination at one spot and the
  arrival anchored it at another. That is the "the image drifts on arrival" bug:
  the preview and the landing were answering the same question differently.
  The same rule covers which dot each relation lands on: a zone on the
  destination whose `location_id` is the source, else the destination's parent
  dot, else its matching portal dot (by index). The defaults it falls back to are
  `NAV_DOT_DEFAULTS`, the same object `navDots` draws the dots from, so a missing
  value cannot make the drawing and the landing disagree.
- **The backend materialises those defaults when a link is created.**
  `ensure_location_link_defaults` (repository) writes the child's `parent` dot on
  a `super` edge and both ends' `portal` dot on a `transversal`, matching
  `NAV_DOT_DEFAULTS` in the viewer — keep the two in step. It is called from
  *both* edge-creation paths, because the REST edge endpoint inserts the edge
  document directly and never goes through `create_relationship`; the UI uses the
  REST path. Seeding is idempotent and never overwrites an authored position.
  Locations that predate it are simply unseeded, which the shared rule handles.
- **Destination previews are sized as the destination's scene layer.** The hole
  preview and the travel wipe must both go through `destSceneSize` /
  `destSceneLayer`, which apply the same cover + `PAN_OVERSCAN` + teaser zoom as
  `sceneCamera` but for the destination's aspect and arrival point. A CSS
  `background-size: cover` looks equivalent and is not: it comes out exactly
  `1 / PAN_OVERSCAN` (≈90.9%) short, so the destination jumps ~10% larger the
  instant the preview hands over to the real scene layer (and much more in the
  teaser band, where the zoom is unaccounted for). `destSceneLayer` is
  algebraically identical to `sceneCamera` at the arrival point, so the wipe and
  the background it exposes are the same box.
- **The handover waits for a painted frame, never for the clock.** The portal is
  lifted only after the scene layer's *own* element has a frame to paint
  (`waitForBackgroundPaint`), because the scene layer's media is a separate
  element from anything preloaded: it needs its own `decode()` (stills) or
  `loadeddata` (video), and a video needs to have started at all. Removing the
  overlay on the 1.3s timer instead — which is what it used to do — flashes the
  dark viewer background for the frames between "new `src`" and "decoded frame".
  `preloadMedia` (in `composables/media.js`) warms the URL video-aware and is
  deliberately *bounded*, so a slow asset costs at most a short delay before the
  portal opens and never strands the overlay; the gate itself is capped too.
  Note an `<img>`/`background-image` cannot decode a `.webm` — the wipe needs a
  real `<video>` branch (`TravelOverlay`), exactly like the hole preview in
  `MapDot`. `requestVideoFrameCallback` may only *confirm* the paint: a
  fully-occluded video can be throttled into never presenting a frame, so it is
  raced against a plain paint cycle rather than awaited outright.
- **The scene layer is `pointer-events: none`.** Background taps must fall
  through to the viewer (`onBgClick`); dots opt back in with
  `pointer-events: auto`.
- **Crowded travel dots: the armed one rises, the rest step back, the dragged dot
  is a ghost.** `updateTravelTargets` already picks exactly one nearest target and
  marks it `armed`, so "where will I travel" is never ambiguous in the *logic* —
  it was a *visibility* problem. Every expanded bubble shares one stacking level
  (`z-index: 10`), so ties broke by DOM order and the armed bubble could sit
  underneath a neighbour. Now `.armed` is `z-index: 15`, the non-armed zone/nav
  bubbles get `.dimmed` (opacity 0.35) while a target is armed, and the dot under
  the pointer is `.dragging` — faded to 0.45 and raised to `z-index: 30`. The
  last one matters because occupants and nav dots are *both* `expanded` and nav
  dots come later in the DOM, so a dragged occupant otherwise paints under the
  bubbles. `.dragging` fades with `!important` on purpose: the self dot runs
  `arrivePop`, which animates `opacity` with a `both` fill, and an animation
  outranks a normal declaration — the same trap as `.controlled` (see above).
  `dragDotKey` ('self', an occupant id, or '') is set in the drag-move handlers
  once the 6px tap threshold is crossed, so a tap never flickers the ghost.
- **Dot styling lives in `MapDot.vue` and nowhere else.** `LocationViewer.vue` used
  to carry a *scoped* copy of the whole dot stylesheet, left behind when the dots
  were extracted into their own component. Because it was scoped it compiled to
  `.map-dot[data-v-…]` — specificity **0,3,0 against the component's own 0,2,0** —
  so it silently outranked `MapDot`'s real rules and the two copies drifted:
  - its `transition` had no `opacity`, so the drag ghost and the neighbour dim
    snapped instead of fading (`transition` is a shorthand list — a second
    declaration replaces it whole, it does not merge);
  - its `.expanded` carried `width/height: … !important`, which beat the *inline*
    size `dotStyle` computes, so zone/nav bubbles jumped to full size the moment
    `expanded` appeared instead of growing through `expandLevel`;
  - it re-declared `.expanded { z-index: 10 }` at 0,3,0, which beat the global
    `.armed`/`.dragging` z-index lifts at 0,2,0 — so those did nothing at all.
  Any scoped rule on a child component's root beats that component's own global
  rules; if a component's styles "don't take effect", check for a scoped copy
  first. One stylesheet per component.
- **Hole alignment is clamped to [0, 100].** The destination image is aligned
  at `arriveX/Y` + the inverse-pan shift; clamping keeps the shift proportional
  to the remaining image space, so the image never runs out and shows an edge.
- **Tunable constants live together** at the top of `LocationViewer.vue`'s
  `<script>`: `INVERSE_PAN_STRENGTH`, `TEASER_ZOOM`, `EXPAND_PROXIMITY`,
  `TRAVEL_PROXIMITY_FACTOR` (`PAN_OVERSCAN` is in `composables/media.js`).
- **One source of truth.** The viewer re-renders from `navigate_from` state; it
  does not keep a local world graph. `moveTo`/`relocate` update the entity and
  the UI re-fetches.
- **Tap vs drag.** A 6px `occDragMoved` threshold and `occSuppressClick` separate
  a tap (inspect) from a drag (move/travel), so a drag never fires the click handler.
- **Coordinate conversion is symmetric.** `toViewportPos` (image → viewport) and
  `toImagePos` (viewport → image) must stay in lock-step, or dots drift when the
  background pans under a drag.
- **Portal timing is hard-coded.** The 1300ms swap timeout matches the 1.2s
  `portal-expand` keyframe; changing one without the other desyncs the transition.
- **`destNavCache` avoids blocking renders.** Destination nav data is pre-fetched
  in the background so the dot previews (arrival point + aspect) are ready before
  a travel, not fetched on click. Its `destAspect` must be probed from the image
  the destination **actually shows**: `background_image` when it has one, else the
  **navdot image** (`dest.image`, taken from the source's own nav payload — the
  destination's `/navigate` does not carry its own navdot role). Most locations
  carry a navdot image and no background at all (283 of 410 at time of writing),
  and the arrival falls back to the navdot image for those, so probing
  `background_image` alone left every one of them with a null aspect — and a null
  aspect silently drops the hole preview back to a dot-sized thumbnail
  (`holeStyleFor` returns null). The cache also counts only a *non-null* aspect as
  cached, so a destination that gains an image can pick it up without a reload.
- **The cache is invalidated when this location's dots move.** An entry describes
  how to arrive *here*, so it is derived from this location's own `nav_positions`
  and zones; editing either (dragging a nav dot, dragging a zone — `onEnd` and the
  zone `PUT`) drops `destNavCache[thisLocation]`. Without that the staleness is
  invisible and sticky: the hole keeps framing a destination at the old spot, and
  because the travel now reads the same rule both would agree on the *wrong*
  number until the page was reloaded.
- **GM free-roam is device-local and unpersisted** (B96, 2026-09-15). The GM dot
  is held in memory per location for the session; nothing is written to
  `localStorage`, and dropping it on a target travels the **view** only — no
  server state, no cross-device sync, no restore after a refresh. Sample the view
  centre **while an entity is held**: the camera re-anchors the instant
  `entityId` clears, so reading it inside the transition watcher returns the
  post-jump framing. The spawn still shifts the view a little — the camera
  anchors a dot at *its own image fraction*, not at the screen centre, so
  "spawn at the view centre" is not the same as "no movement" (measured 9% of the
  width to the location centre vs 7% to the view centre; the character's own
  position is the only zero).
- **Constants are author-tuned, not derived.** `EXPAND_PROXIMITY` /
  `TRAVEL_PROXIMITY_FACTOR` decouple bubble expansion from drop-to-travel, and
  `INVERSE_PAN_STRENGTH` sets the hole illusion's strength; they are hand-tuned
  values at the top of the file, kept there so they can be adjusted in one place.

## Related

- [[System Architecture]] — where the viewer sits in the stack.
- [[API Contract]] — the REST endpoints and GraphQL mutations it calls.
- [[Projections and Transversal]] — the consciousness/inapposite travel model.
- [[Projections as Occupants]] — **open discussion**: should an occupant dot show
  the entity or the body standing there? The viewer resolves an occupant's name
  and portrait through the entity's *active* body, so a body left behind by
  consciousness travel currently wears the face of the body the character went to.
- [[UI-UX Design]] — interaction conventions and feel constants.
- [[Relational Canvas]] — the GM node graph built from the same nav data.

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
zones               // nav.location.zones (name, x, y, location_id, background_image)
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
expandLevels      // reactive — 'zone-<name>'/'nav-<key>' → 0..1 proximity level (multi-bubble)
armedDot          // reactive — which dot is within travelProximity (drop → travel)
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

Zones and nav dots show the destination's background as their expanded image
(the `navdot_image` role) — the "hole": an overscan-sized inner `<img>` moved by
an explicit px transform that cancels the scene layer's pan (screen-fixed
content), aligns the destination's arrival point, and adds the inverse-parallax
shift. The dot's own `border-radius` + `overflow: hidden` clips it; the img must
not clip itself (`border-radius: 0`). `destNavCache` supplies
`arrivalX`/`arrivalY`/`destAspect` so that preview shows the exact arrival point.

`self` is the camera anchor: the scene pans so this dot keeps its image position,
and it is always draggable. With no perspective entity (`entityId == null` — the
GM free-roam view) it becomes a **GM free-roam dot**: draggable, labelled with the
role glyph (🏛 Architect / 🎭 Player — the same icons as the player settings
overlay), with its position per location persisted on the device
(`gmDotPositions` in localStorage) so a refresh restores it. Dropping it on a
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
`--controlled-scale` (currently 1.2, tunable in `MapDot`). "Controlled" is a
table-wide fact, not a local one: `App.vue` unions the server's `playerBodies`
(the entity each player is currently driving — refreshed on the `main_active`
SSE event) with the local `entityId`, and passes `controlledEntityIds` down. The
`self` dot carries it whenever a perspective entity is set; the GM free-roam dot
does **not** — that is a view marker, not a driven entity. The GM's own
assumptions feed the same set: `switchPerspective` reports the taken body with
`POST /players/{id}/control/{entity}?stamp=false`, which records presence without
touching spotlight recency (see [[Troupe Play]]), and `returnToSelf` clears it
when the GM goes to free-roam. Both arrive over SSE as `body_changed`, which
refreshes `playerBodies`. The size change uses
the **individual `scale` property**, not `transform: scale()`: the `self` dot runs
the `arrivePop` animation, which fills `transform` forwards and therefore wins
the cascade over any normal `transform` declaration (this silently disabled the
first attempt). `scale` composes with `transform` instead of competing with it,
so the dot grows on take and shrinks on hand-off while `--dot-r` geometry scales
uniformly with the ring. Note that a switch *swaps elements* — the entity you
take becomes the `self` dot, the one you leave returns as an occupant dot — so
the size change reads as the abandoned dot shrinking and the new one being
larger, not as one dot animating between the two.

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
- While dragging self, the drag frame computes two proximity sets:
  - **`expandLevels`** — every zone/nav bubble within `EXPAND_PROXIMITY` (24 image-%)
    opens, sized continuously by distance (`1 - (d/EXPAND_PROXIMITY)²`, quick ramp).
  - **`armedDot`** — the single nearest bubble within `travelProximity()` (the
    expanded bubble's rendered radius) arms travel; it breathes so a drop there
    reads as "will travel".
  - `dragTarget` (non-reactive) holds the armed target for the drop handler.

On drop:

- **Self + near a zone** → find the matching child and `travelWithAnimation`.
- **Self + near a nav dot** → `travelWithAnimation` to the parent/portal target.
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

`relocate` routes the move:

- **Consciousness travel** (`transversal_type === 'consciousness'`) →
  `POST /api/v1/entities/{id}/consciousness-travel` (project into a body at the
  destination; see [[Projections and Transversal]]).
- **Otherwise** → `POST /api/v1/entities/{id}/move` (full physical transport).

## Animation timeline

The travel effect is a choreographed sequence:

1. **Portal expand** (`.travel-overlay`, `portal-expand`) — a `clip-path: circle()`
   expands from dot-size at the departure point to full-screen over 1.2s,
   revealing the destination background.
2. **Background swap** — at ~1.3s the real background is switched in with the
   portal removed, transitions force-disabled for one frame to avoid cross-frame
   flicker, then re-enabled.
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

- `entity_moved` events (broadcast by the map-position endpoint) arrive through
  `App.vue`'s SSE composable; `fetchNavWithLerp()` is exposed and re-fetches nav
  with `lerpActive = true`, so non-self occupant dots ease to their new positions
  over 1.5s instead of teleporting.
- `remotePools` / `remoteResults` props drive `PoolDiceRing` around occupant and
  self dots.

## Key design decisions & gotchas

- **One `sceneCamera` source.** All pan/size math (`sceneLayerStyle`,
  `toViewportPos`/`toImagePos`, `navDotPerspective`, `holeStyleFor`,
  `travelProximity`, the drag frame) reads from the single `sceneCamera`
  computed — never re-derive the pan independently or the math will drift.
- **The scene layer is `pointer-events: none`.** Background taps must fall
  through to the viewer (`onBgClick`); dots opt back in with
  `pointer-events: auto`.
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
  a travel, not fetched on click.
- **GM free-roam is device-local by design** (decided 2026-09-11). The GM dot's
  position per location lives in `localStorage` only, and dropping it on a target
  travels the **view** only — no server state, no cross-device sync.
- **Constants are author-tuned, not derived.** `EXPAND_PROXIMITY` /
  `TRAVEL_PROXIMITY_FACTOR` decouple bubble expansion from drop-to-travel, and
  `INVERSE_PAN_STRENGTH` sets the hole illusion's strength; they are hand-tuned
  values at the top of the file, kept there so they can be adjusted in one place.

## Related

- [[System Architecture]] — where the viewer sits in the stack.
- [[API Contract]] — the REST endpoints and GraphQL mutations it calls.
- [[Projections and Transversal]] — the consciousness/inapposite travel model.
- [[UI-UX Design]] — interaction conventions and feel constants.
- [[Relational Canvas]] — the GM node graph built from the same nav data.

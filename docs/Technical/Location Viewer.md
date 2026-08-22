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
}

emits = ['moved', 'update:editZones', 'inspectEntity']
```

`moved` fires after any relocation and is handled by `App.vue` (`onMoved`) to
update `currentLocationId`/`universe` and re-fetch peers. `inspectEntity` opens
the character sheet for a tapped occupant.

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
```

Drag state is kept separately:

```js
dragging          // zone drag: { index, startX, startY, origX, origY }
occDragging       // occupant drag: { index, startX, startY, origX, origY }
dragTarget        // non-reactive — nearest zone/nav/occupant during self-drag
hoveredDot        // reactive — CSS class for the proximity highlight
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

The background is a `position: fixed` div whose `backgroundSize`/`backgroundPosition`
are computed from the player's position (`self.map_x`, `self.map_y`) and the
image's aspect ratio (`panAxis`):

- Image **wider** than viewport → `backgroundSize: auto 100%`, pan horizontally on `map_x`.
- Image **taller** than viewport → `backgroundSize: 100% auto`, pan vertically on `map_y`.
- Aspect unknown → fallback `backgroundSize: 180%`, pan both axes.

Animated backgrounds render as a `<video>` (`object-fit: cover`, `objectPosition`
driven the same way) instead of a CSS background.

Dots are positioned in **image-space** (0–100) and converted to viewport
percentages with `toViewportPos()`; the inverse `toImagePos()` is used during
drags so a dot's stored `map_x`/`map_y` stays correct even as the background
pans under it.

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
(the `navdot_image` role), with `background-attachment: fixed` so the image stays
glued to the viewport while the dot itself moves — a preview of where you'd land.
`destNavCache` supplies `arrivalX`/`arrivalY`/`destAspect` so that preview pans to
show the exact arrival point.

## Interactions

### Click / pop-out

- **Occupant** → always `emit('inspectEntity', id)` (opens the sheet).
- **Zone / nav dot** → toggle the expanded bubble via `activeElement`.
- **Expanded zone / nav dot overlay** → `onExpandedClick` triggers travel.
- **Background click** → dismisses the pop-out, re-popping self.
- **Edit mode** → clicking a portal nav dot toggles its `transversal_type`.

### Three drag systems

**1. Zone drag (GM edit mode)** — `onZoneDragStart` records the origin, `onDragMove`
mutates `zones[i].x/y` live (clamped to 2–98), `onDragEnd` persists via
`PUT /api/v1/locations/{id}/zones`.

**2. Nav dot drag (GM edit mode)** — `onNavDragStart` moves `navDotPositions[key]`
live and persists the whole `nav_positions` object on end via the
`updateEntity` GraphQL mutation.

**3. Occupant / self drag** — the core interaction:

- `canDragOccupant`: GM can drag anyone; the player can drag self and any GMC/asset.
- A 6px threshold separates a tap (inspect) from a real drag (`occDragMoved`).
- While dragging self, `onOccDragMove` tracks the nearest target within 12%
  distance, in priority order: zones → other occupants → nav dots. The winner is
  stored in `dragTarget` (non-reactive) and reflected in `hoveredDot` for the
  snap highlight.

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

- **Negative margins, not `transform`.** Dots center themselves with negative
  `margin` rather than `translate(-50%, -50%)` to preserve
  `background-attachment: fixed` on the zone/nav image previews.
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

## Related

- [[System Architecture]] — where the viewer sits in the stack.
- [[API Contract]] — the REST endpoints and GraphQL mutations it calls.
- [[Projections and Transversal]] — the consciousness/inapposite travel model.
- [[UI-UX Design]] — interaction conventions and feel constants.
- [[Relational Canvas]] — the GM node graph built from the same nav data.

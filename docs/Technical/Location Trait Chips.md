---
title: Location Trait Chips
date: 2026-09-25
last-updated: 2026-09-25
tags:
  - transversal
  - technical
  - navigation
  - planned
aliases:
  - Trait Chips
  - Location Traits on the Map
---

# Location Trait Chips

> [!info] Built 2026-09-25 — **verified end to end, drag included**
> How a location's traits render on the map ([[B92]]'s rendering half). The chip, the
> traits-tab filter, **placement** (`trait_positions`, the arrange-mode drag and the
> `PUT /locations/{id}/trait-positions` endpoint) and the **resting/open** form all
> landed, and the drag gesture is no longer a hand-check. See *Built* below.

## The chip (human's spec, 2026-09-25)

A **chip**, in the same visual language as a trait row on the character sheet
([[TraitRow]]), so traits read consistently wherever they appear:

```
╭───────────────────────────────╮
│  Regime Alert              d6 d8 d6 │
│  the city watches its own   │
╰───────────────────────────────╯
```

- **Left edge: an ordinary rounded chip border.** No die glyph hangs off it any
  more — that earlier idea (a `<d8>` overhanging and obscuring the left edge) was
  dropped in favour of consistency with the sheet.
- **Text, at most two rows:**
  - row 1 = the trait's **name**
  - row 2 = the trait's **statement** (omitted when there is none, so a
    single-row-chip is the common case)
- **Right side: the trait's full rating**, rendered the way the sheet renders one —
  not the chip's own edge. A trait with several dice shows them all
  (`d6 d8 d6`), because live traits really do carry more than one.
  The dice hang off the chip's right edge and grow **leftwards**, so the chip reserves a
  lane equal to the rating's **own computed width** (`--rating-w`, from the dice groups)
  plus 2px — 8px of clearance from the text, with the last die still straddling and
  hiding the border. A fixed lane cannot work: one die is 24px but `d4 d6 d8 d10` is
  120px, and with the old 22px lane that rating printed **92px inside its own name**.
  `e2e/tests/trait-chip-rating-lane.spec.js` pins the clearance for one die, a deep fan of
  one type, and several types at once.

## Resting and open (human's spec, 2026-09-25)

The chip above is the **open** form. At rest a placed chip is **only its marker** —
its picture if it has one, else its rating — because a room with thirty traits in it
must not be thirty labels. The words arrive when it opens.

| | resting | open |
| --- | --- | --- |
| has a `navdot` picture | the picture alone | picture + name + statement + rating |
| no picture | the rating alone | name + statement + rating |

> [!warning] A pool with an empty ledger has no resting marker (found 2026-09-26)
> The table has no row for **neither a picture nor dice**, and that is a real state, not
> a corner: a **challenge pool with nothing banked yet is a pool's normal resting
> state** (Palace's inherited `doom` pool reads `dice: []`). A **placed** chip at rest
> renders only its marker, so such a chip draws as an **invisible, near-zero-size
> marker** on the map — a GM who drags a doom pool into the scene gets a chip they
> cannot see or find. It is unplaced today (the stack is arrange-mode only, and stack
> chips are always open), so nothing is visibly broken yet. **Left as a design call,
> not patched:** an empty pool's resting form could be a die outline, the capacity, a
> neutral glyph, or simply the trait's initials. Recorded in [[B191]]'s reconciliation.

- **What opens it:** the **character's proximity** (the same radius and quadratic
  curve the nav bubbles use — `EXPAND_PROXIMITY`, 24 image-%), the **pointer**, or a
  **tap**.
- **Proximity HOLDS.** The bubbles only expand *while a drag is running*: they are
  driven from the drag frames and wiped on release. A chip is driven from a
  `computed` over the character's position instead, so it stays open at rest and
  after a drag — the human's stated difference. It measures from the character's own
  body when that body is on this map, else the GM's free-roam dot, else nowhere:
  `selfPos` falls back to the room's centre for the camera's sake, and opening chips
  around a viewer who is standing nowhere would be a lie.
- **A tap on a closed chip opens it; the tap after that plays it.** Resting there are
  no words to read, so one tap must not spend a die. The stack's chips are always
  open, so they still play on the first click.
- **The stack is arrange-mode only** (the human, 2026-09-25). Unplaced traits are **not on
  the map by default**; the stack appears while the GM is arranging, which is the only
  time it is needed. It was crowding the map badly — on a phone Everbloom's twelve
  unplaced chips ran **526px down an 844px screen**, which is what made the room feel
  overwhelming, and no scene scale can help, because the stack is fixed UI rather than
  part of the scene. A chip dragged out of it becomes a scene element and never returns,
  so "hidden by default" costs nothing once a location has been arranged; placed chips are
  still always on the map, resting as their markers. The stack's own chips are open and
  cannot be approached, so they do not collapse.
- **Arrange mode opens every chip.** The GM is placing these, and you cannot place what
  you cannot read — otherwise dragging means chasing an unlabelled marker around the
  map. The zone and nav dots already follow this rule (`:expanded="editZones || …"`).
- **The resting marker is given its own box** rather than deriving its width from the
  picture: a cutout's `width: auto` is its intrinsic ratio, which is 0 until the file
  decodes — a sliver on first paint, and permanent if the file ever 404s. A collapsed
  chip also drops its padding and border, so its box — and therefore its click target
  — is the marker, not an invisible pill.
- **A resting cutout is a map figure, not a thumbnail** (the human, 2026-09-26: *"much
  bigger than it is now. Maybe 5x or so"*). The collapsed cutout box went **23×34 →
  115×170**, five times the linear size, keeping the 512×758 aspect the cutouts are
  stored at exactly. An opaque resting thumbnail is unchanged at 26×26 — the call was
  about cutouts, which read as specks against the background art. Two consequences
  worth knowing: the **click target** grows with it (the resting chip's box *is* the
  marker), and a room of many placed cutouts is busier than it was, since the resting
  marker is what a map mostly shows.
- **The spec asserts the relation, not the size.** `chip-proximity.spec.js` used to pin
  the resting chip to `width < 60`; that was really testing "no pill around it", so it
  now asserts the chip **hugs** its marker (`chipBox − img < 4px`) — a 5× marker had to
  be a deliberate change, not a test edit that silently moved the goalposts.

`e2e/tests/chip-proximity.spec.js` pins all of it on both engines, with both reads
mocked so the geometry is exact.

## Only the trait tab's traits

The human's rule: **do not render profile traits — only the trait tab's traits.**
The sheet splits these by `traitsetTab === 'PROFILE'` vs the rest
(`CharacterSheet.vue:723`), and the field behind it is a **derived resolver**:
`traitset_tab` on the GraphQL trait-setting type
(`api/graphql/type_defs/traits.py:247`, returning `SheetTab`).

## Placement — x/y in the scene

Chips are **placed anywhere in the scene**, exactly like nav dots: image-space
coordinates inside the scene layer, so they pan and zoom with the map.

- **Storage (human's decision):** a **positions map on the location entity**
  (mirroring the existing `nav_positions`), keyed by trait-setting id. No
  domain-model change beyond the new map field, and an *inherited* trait's chip is
  positioned **per location** — the same doom pool can sit differently in the hall
  and in the cellar, because nothing is copied onto the owner.
- **Who may move them:** **GM only, in arrange mode** (`editZones`) — the same gate
  as zone and nav dots, so placement behaves like everything else on the map.
- **Before placement:** an **auto-stack** (roughly today's block), shown **only in arrange
  mode**. A chip that has never been dragged stays in the stack; once placed it locks to
  its scene position and leaves the stack. Nothing has to be hand-placed to be readable —
  but nothing unplaced is on the map either, which is the point (see *Resting and open*).
- **A stacked chip is as wide as its own content** — the width it has when placed. The
  stack is a column flex container, and a column flex container stretches its items
  across the cross axis by default, so every chip used to take the width of the
  **widest** one in the stack; on a phone the container's `max-width: 40vw` then
  capped that, drawing a two-word trait as wide as the longest sentence in the room.
  `align-items: flex-start` on `.loc-traits` is the whole fix, and
  `e2e/tests/trait-chip-width.spec.js` asserts it by giving a placed and a stacked chip
  identical text and comparing their measured widths.

## Built (2026-09-25)

- **`TraitChip.vue`** — the chip as one component, because it renders in two places:
  the auto-stack beside the labels, and a scene element once placed. It takes
  optional `x`/`y`; given them it is absolutely placed at that image-space point and
  centred, so it pans and zooms with the map.
- **`traitPositions`** — a ref with a loader, mirroring `navDotPositions`;
  `placedTraits`/`unplacedTraits` split the list, and placed chips render inside the
  scene layer.
- **The drag** reuses **`usePercentDrag`**, the same composable the nav dots use —
  a chip and a dot are both one `{x, y}` entry in a position map on the location. A
  chip promoted out of the stack lands under the pointer rather than jumping to a
  default spot. `pointer-events: auto` only when `draggable`, so a chip is grabbable
  exactly when arrange mode is on and never eats a map click otherwise.
- **`PUT /locations/{id}/trait-positions`** replaces the whole map, mirroring `PUT
  /zones`. An absent id keeps meaning "not placed yet", which leaves that chip in
  the stack.
- **The tab filter is real, and the earlier worry was wrong.** `_trait_entry` now
  reports `sheet_tab` — the read-through of `TraitSet.sheet_tab` that the GraphQL
  `traitsetTab` field already did — and the viewer keeps only the traits tab. Live
  proof at Krasnoyarsk-45: **5 traits, 4 kept, 1 profile dropped.** (The old note
  here guessed the filter might be a no-op because the location trait *set* carries
  no tab of its own; the per-trait answer comes from each trait's set, and plenty of
  those are profile — the imagen/appearance config, `LoRA 1`, `positive imagen`,
  `negative imagen`.)

## Playing a chip (2026-09-25)

**Clicking a chip does what clicking a trait's *rating* does in a sheet** — not what
clicking its *name* does (that opens the read-only detail panel). The dice go into the
roller, or a pool gives one up. The human's steer was to **share** those rules rather
than copy them, and to leave the sheet where it is, so they live in
`composables/useTraitPlay.js` and the sheet was rewired onto them too.

What a click means, and what it deliberately does not:

- **Gates:** only while the roller is `adding` (never mid-roll) and never for a
  disabled trait.
- **Static** → the trait's dice join the pool. A multi-die rating contributes one pool
  die per entry; negativity rides the payload so the dice layer routes it.
- **RESOURCE / CHALLENGE** → **spends one die** (doom to the opposition, progress into
  its own pool, per polarity), and the trait's own dice follow what the server returns.
- **A mixed-die pool's chip click does nothing, on purpose.** Those pools are spent
  per die group from their own buttons in the sheet, and guessing which group was meant
  is what the split exists to avoid. Verified live: clicking the mixed `regime alert`
  chip leaves the pool untouched.
- **The map has no pool tree**, so the sheet's group `cascade` (descendants, carried
  negatives, completing ancestors) is a no-op here. **Armed SFX are the roller's
  state**, so `armedSfxIdsFor` is empty — and no location trait carries SFX anyway.
  **Refund tracking is the sheet's**, so a die spent from the map is not refundable
  from the sheet's UI.

**The wire shape nearly broke this twice.** The REST read is snake_case
(`rating_type`) with **lowercase** enums (`challenge`, `negative`), while the play
compares the sheet's camelCase **uppercase** (`ratingType === 'CHALLENGE'`). Either
mistake made a CHALLENGE trait look static: its chip pushed the pool's raw dice at the
roller instead of spending a die — and a negative trait read as positive. Neither
showed up in a build or in a logic test made of hand-shaped fixtures; the browser check
caught both. `utils/locationTrait.js` now normalises at the boundary, and
`scripts/check-trait-play.mjs` feeds literal wire entries through it, with both bugs
kept as failing-if-regressed cases.

## The marker picture (2026-09-25, [[B200]])

A trait can own images, and the role that means *this surface* is **`navdot`** — the
same role the map's dots use ([[Media Pipeline]] §Traits as image owners). When a
location's trait has one, the chip leads with it, so the chip scans picture → name →
rating, the order the sheet's trait rows use.

- **The read is a read-through, not a field.** The registry **trait** owns the image
  and the **trait setting** is the variant, exactly as the sheet's
  `TraitSetting.image(role)` resolves, so slice 2's per-instance override will reach
  the map with no change to the viewer. The ladder is the shared `pick_role_image`, so
  the chip and the sheet cannot disagree about which file a role means.
- **The payload carries the URL and the flag** — `navdot_image` +
  `navdot_transparent` on both `/locations/{id}/traits` and `/challenge-traits`,
  resolved **in one batch per page**, because a location holds dozens of traits and the
  per-owner read measured ~2.7ms. An entry with no such image simply lacks the keys.
- **A cutout stands OUT of the chip — no ring.** The picture is absolutely placed (so
  the chip's height stays its text's, as the dice already are) and sized off the text
  height plus a fixed overhang, so it breaks the chip's outline above and below whether
  the chip is one line or two. That was the human's correction to the first pass, which
  contained the art in a thumbnail: on this map a cutout is never confined to the
  widget it marks. A plain opaque picture keeps a contained round thumbnail.
  `e2e/tests/trait-chip-marker.spec.js` pins both branches by geometry.

## What is still needed

**Nothing on the chip is hand-checked any more.** The last gap — the drag *gesture* —
closed on 2026-09-25: arrange mode is architect-only and the role comes from the
player read, so `e2e/tests/chip-proximity.spec.js` mocks that read to `architect`
instead of needing one of the human's own devices, drags a real chip, and asserts both
that it moved and that the positions write fired. The gesture is the same composable
the nav dots use, gated on the same `editZones`.

Things worth knowing:

- **A chip's first drag lands it under the pointer**, wherever the pointer was in
  the stack — not at the scene centre. If that feels wrong, the fallback is the one
  line in `onTraitChipDragStart`.
- **`traitDiceGroups` is still mirrored** from `CharacterSheet.vue`'s
  `groupByDieType` (now in two places: that sheet and `TraitChip`). Two copies is
  the threshold at which this should move to a shared util.
- **How far a cutout stands proud is one number** — the `calc(100% + 20px)` on
  `.trait-chip-marker.transparent .trait-chip-marker-img`, currently 6px clear of the
  chip above and below (measured on Everbloom Sanctuary's `spirit herb` chips, whose
  `navdot` art is a 512×758 portrait). It is a taste knob, not a rule.

## Related

- [[B92]] — the ticket: the server half (inheritance, per-viewer visibility), the
  chip, and placement all landed.
- [[Location Viewer]] — the dot model these chips sit alongside, and the arrange
  mode that drags them.
- [[TraitRow]] — the sheet's trait rendering this chip matches.
- [[Media Pipeline]] §Traits as image owners — the `navdot` role this chip renders.

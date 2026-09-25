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

> [!info] Built 2026-09-25 — **the drag gesture is the one piece not yet verified**
> How a location's traits render on the map ([[B92]]'s rendering half). The chip,
> the traits-tab filter and **placement** (`trait_positions`, the arrange-mode drag
> and the `PUT /locations/{id}/trait-positions` endpoint) all landed; see *Built*
> below and *What is still needed* for the single gap.

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
- **Before placement:** an **auto-stack** (roughly today's block). A chip that has
  never been dragged stays in the stack; once placed it locks to its scene
  position and leaves the stack. Nothing has to be hand-placed to be readable.

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

## What is still needed

**Only the drag gesture itself is unverified.** Everything it drives is proven:
the endpoint round-trips, a stored position renders as a scene chip (out of the
stack, with its fanned dice), and it survives a reload. But the *gesture* needs GM
arrange mode, and the testing character's player is **not an architect**, so the
e2e harness cannot enter it — it stays a hand-check. The gesture is the same
composable the nav dots already use, gated on the same `editZones`.

Two things worth knowing for whoever tests it:

- **A chip's first drag lands it under the pointer**, wherever the pointer was in
  the stack — not at the scene centre. If that feels wrong, the fallback is the one
  line in `onTraitChipDragStart`.
- **`traitDiceGroups` is still mirrored** from `CharacterSheet.vue`'s
  `groupByDieType` (now in two places: that sheet and `TraitChip`). Two copies is
  the threshold at which this should move to a shared util.

## Related

- [[B92]] — the ticket: the server half (inheritance, per-viewer visibility), the
  chip, and placement all landed.
- [[Location Viewer]] — the dot model these chips sit alongside, and the arrange
  mode that drags them.
- [[TraitRow]] — the sheet's trait rendering this chip matches.

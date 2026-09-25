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

> [!info] Spec'd 2026-09-25 — **not built yet**
> How a location's traits should render on the map ([[B92]]'s rendering half). The
> current build is a placeholder: a stacked text block under the location and
> universe labels showing each trait's name and dice. This note is the agreed
> target. **One blocker** — see *What is still needed*.

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

## What is still needed

**The payload has no tab.** `GET /locations/{id}/traits?viewer=…` (the endpoint
[[B92]]'s viewer uses) returns
`{id, trait_id, name, traitset_id, rating_type, polarity, dice[], capacity[],
statement, owner_location_id, owner_name, inherited, hidden, known_to[]}` —
**no `traitset_tab`**. The field exists only on the GraphQL type, derived.

So "only the trait tab's traits" cannot be honoured from the payload as it stands.
Two ways, and the first is much cheaper:

1. **[[applied-mechanics]] adds the derived tab to the trait entry** (it is already
   computed server-side for GraphQL, so this is one field on `_trait_entry`) — and
   the caller can then either filter for the trait tab or ask for it.
2. The viewer re-derives the tab from the trait set itself — duplicating a rule that
   already lives server-side, and the kind of drift this project keeps paying for.

**Also worth noting:** the location trait set (`ts-location-afd2`, name `location`)
carries **no tab of its own** (`tab: None`), so for locations every trait may
already resolve to the trait tab — making the filter a no-op until locations
actually have profile-tab sets. Worth confirming with the human before building the
filter, since "no profile traits exist yet" would make it untestable in live data
(the same situation as the hidden-location route rule).

## Related

- [[B92]] — the ticket; the server half (inheritance + per-viewer visibility) and
  the placeholder rendering already landed.
- [[Location Viewer]] — the dot model these chips sit alongside, and the arrange
  mode that will drag them.
- [[TraitRow]] — the sheet's trait rendering this chip should match.

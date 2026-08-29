---
title: Effect Holders and Owners
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
aliases:
  - Effect Holders
  - Owners and Sources
  - Carriers
status: proposed
---

# Effect Holders and Owners

A reconciliation of the three overlapping vocabularies the effect layer uses
today, plus a proposed way to frame them so the overlap stops causing drift.
Proposal only — no behavior change.

## The core idea

"Owner", "stamp", and "source" are all the **same shape**: a thing carrying one
or more SFX references. The difference is **lifetime** (persistent vs transient)
and **purpose** (availability vs selection), not the shape.

- **Owner** (persistent) — *"this SFX is attached to this thing."* Drives
  availability/authoring.
- **Stamp** (transient) — *"this SFX fired on this thing."* Drives which dice a
  roll-deferred effect selects (`die.armed_sfx_ids`).

A "holder" is the umbrella: anything that can carry SFX references.

## Table 1 — the three lists, per conceptual thing

| Conceptual thing | Element type | Owner surface | Source kind | `{variable}` |
|---|---|---|---|---|
| Trait instance (a trait on an entity) | `traitsetting` | `trait_instance` | `trait_setting` | `{trait_setting}` |
| Trait-set instance | `traitsetsetting` | `trait_set` | `traitset_setting` | `{traitset_setting}` |
| Entity | `entity` | `entity` | `entity` | `{entity}` |
| Projection | `projection` | `projection` | `projection` | `{projection}` |
| Trait (registry definition) | `trait` | `trait` | — | — |
| Location | `location` | — | — | — |
| Universe | `universe` | — | — | — |
| Pool | `pool` | — | — | (addressable via binding) |
| Die | `die` | — | — | (stamped per roll) |
| Table bucket | — | `table` | — | — |
| GM bucket | — | `gm` | — | — |

> The three-way overlap is the drift: `traitsetting` / `trait_instance` /
> `trait_setting` are the *same thing* with three names; same for
> `traitset` / `trait_set` / `traitset_setting`.

## Table 2 — holders by lifetime and shape

| Holder | Holds | Lifetime | Purpose |
|---|---|---|---|
| Entity / projection | SFX ids | persistent | availability |
| Trait instance / trait-set instance | SFX ids | persistent | availability |
| Trait (registry) | SFX ids (template) | persistent | provisioning |
| Table / GM bucket | SFX ids | persistent | availability (origin-less) |
| Die | SFX ids (`armed_sfx_ids`) | transient | die selection |
| Pool | — | transient | target/binding (not a holder today) |
| Roll-table entry | inline effects | persistent | consequence |
| Consequence option | inline effects + `source` | runtime | consequence menu |
| Portal config | inline effects | persistent | consequence |

## What this suggests

1. **Don't merge the three lists.** Element type (resolvable value), owner
   surface (carrier), and source kind (activator) are distinct roles. `die` and
   `pool` belong in *element types*, not *owners*.
2. **Do fix the naming drift.** Derive the triple list from one canonical
   "thing" record: `{ element, owner_surface, source_kind, variable }`, instead
   of three hand-maintained tuples.
3. **Frame owners and stamps as one "holder" concept** with a `lifetime`
   (`persistent` | `transient`) field, rather than two unrelated concepts.
4. **Leave inline-effect holders as-is** (roll-table entry, consequence option,
   portal config) until a concrete reuse need appears; converting them to SFX-id
   holders is possible but adds indirection for marginal gain today.

## Related

- [[Effect Output Variables]] — the typed-variable work this feeds.
- [[Targeting Model]] — element types / edges the catalog owns.
- [[SFX Source Model]] — the `source_kind` half of the triple list.

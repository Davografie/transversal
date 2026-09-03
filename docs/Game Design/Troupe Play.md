---
title: Troupe Play
date: 2026-09-03
tags:
  - transversal
  - game-design
  - troupe-play
  - support-cast
  - spotlight
aliases:
  - Support Cast
  - Spotlight
  - Troupe Rotation
  - Support Character
status: draft
---

# Troupe Play

> [!note] Status
> Design settled (model + decisions captured; one build item remains in [[#Open questions]]). The overseer keeps this doc updated as the design evolves. RAW framing lives in [[Inspired Mechanics#Troupe Play]].

## Mental model

Troupe play (Ars Magica-inspired) is a session structure where players rotate the spotlight between their **main characters**, and play **support characters** in each other's scenes. The persistent home is Earth; rotation is **soft** — the system aids the GM ("who's been quiet?") but never forces rotation.

## Two recency concepts (do not conflate)

| Concept | Where | Purpose |
|---------|-------|---------|
| **Projection recency** | `Projection.last_used_at` | *Mechanical* — which body a consciousness last inhabited, so transversal can target it. |
| **Spotlight recency** | `Player.last_spotlight_at` (new) | *Narrative* — which player's main has been out of the spotlight longest. |

They are different signals and must not share a field.

## Spotlight model

- **Main character is explicit** — a player designates 1+ mains; it is *not* "any owned entity" (a player may own non-main entities like retainers).
- **Auto-spotlight** — the spotlight signal is *taking control of a main character*. No manual GM stamp: when a player's active body becomes a main, the stamp fires.
- **Recency list** — character-fronted, player-sorted: one row per player, showing that player's most-recent main, ordered by `last_spotlight_at` ascending (oldest = most due for spotlight).

## Data model

On `Player`:

- **`agency` edge** (`player → entity`) carries a **`main` flag** — the player's mains are the owned entities whose `agency` edge is flagged `main` (1+).
- **`support` edge** (`entity → entity`, directional SC → main) — marks a support character and who it supports.
- `last_spotlight_at: str | None` — recency timestamp (the sort key).
- `last_main_entity_id: str | None` — the main last taken control of (the row's face).

All three stamp together on the single "took control of a main" event. `last_main_entity_id` is *stored*, not derived (reconstructing it from projection history is more fragile).

**Guard:** the stamp keys on the *actor* (the human player), not "a body became active" — so the GM testing/possessing a player's main does not falsely stamp spotlight.

## Support character model

An **SC is a relationship, not just a character** — an entity owned by its controlling player via `agency` (with `main: false`), joined to the main it supports via a **`support` edge** (directional: SC → main). The character (traits/name) hangs off the SC entity; the `support` edge is the *only* SC-specific data. Ownership is many-to-many: a main has a **cast** (1→many SCs); a player owns many SCs across mains.

- **Location is generic** — every projection already has one; an SC needs nothing special there.
- **Mobility = the generic `follow` mechanic** (any projection can follow). No anchor tag: a companion is an SC with a *follow* link to the main; a location-anchored SC has none. See the `#following` item in [[to-do]].
- **`teleport to main`** — an authored **SFX** (no new plumbing): a default SFX on support characters that sets their location to their main's (the `support` edge target). Same-universe only; cross-universe rejoining goes through transversal.
- **Lifecycle = dormant.** Location-anchored SCs persist when the main leaves and reactivate on return — a main accumulates a dormant cast at every place it's been.
- **Generation = roll tables (self-serve).** The support player rolls their own SC; no GM handout.

## Availability

An SC is **available to play exactly when its main is active** — "active" = the main's player is actively controlling it. That's the same event as the spotlight stamp: *take control of a main* → stamp `last_spotlight_at`, mark the main active, and light up its cast. The switcher **greys out** (does not hide) SCs whose main is inactive. Character switching (including assume-support) lives in the existing **player settings overlay**.

**Two ways to assume a support character:**
- **Take over a peer GMC** — pick an existing authored SC (the available-SC picker).
- **Create from scratch** — roll a new one (the roll-table entry point).

## Sheet & base difficulty

There is **no structural GMC/PC split** — an entity is an entity, and "GMC" is just *fewer traits* (and, practically, GM-controlled). A faction or baddie that has figured out Transversal simply has projections and razmerit like anything else. The sheet **adapts on effective trait count**: a flat trait list (one look) when traits are few, and the trait-set split only when `entity + projection` effective traits exceed a threshold. So a low-trait PC and a low-trait GMC render identically, and a big baddie with many traits automatically gets the split view.

**Base difficulty** is a **trait in a GMC-only trait set** (not a separate entity field) — a GMC's baseline opposition die (the Cortex "minor GMC = a die" case), shown prominently, so even a GMC with zero authored traits can still oppose a roll. "GMC-only" is just a trait set with **entity-type filtering** (already supported) — no new set or flag.

**Resolved:** the flat→split threshold is **12** effective traits; "effective" = entity + projection, already exposed as `effective_trait_settings` (`get_effective_traitsettings`).

## Support cast tiers

- **Companion** (spirit / spirit beast / artifact spirit / the follower) — *main-anchored*, recurring, defined by a **bond** + a **mystery/origin**. The rewarding tier; played by other players.
- **Peer** (same-faction fellow disciple) — *location-anchored*, recurring, lighter.
- **One-off** (adventuring party) — disposable; de-emphasized.
- **GM-character** (teacher, elder, captain, wanderer) — GM-played.

**Split rule:** a support character is someone the main can plausibly drag along as an *equal*; a GM-character is someone with authority, secrets, or plot-knowledge. "Really knowledgeable players" is the only escape hatch (an exception, not a feature).

## SC generation via roll tables

The generation flow is **SFX-driven**: an SFX opens a roll table as a **menu**, and the player picks an entry, pays its razmerit cost, and gains the entry's effect (traits / SFX / a life-path step). So a support character is created (and upgraded) by *click an SFX → open roll table → pick entry → pay → gain*.

- Granularity is **authorable** — a universe archetype table down to location / faction tables, driven by whatever SFX opens the table; no fixed structure to decide.
- Roll output is **authorable** — an entry can grant a full archetype or just a hook the player names; not a fixed contract.

**Gap:** the existing `discover` effect only *unlocks* a life path (marks it available); it does **not** open a roll table as an interactive menu. The "SFX → open table → pick → pay → gain" mechanism is therefore **new work** (a "roll table as menu" action), built on the effect system + roll tables.

## Razmerit / roll-table access

Razmerit stays **entity-scoped**. A support character **earns its own razmerit** through the same paths as any character — hitch buying, d4 rolling, SFX triggering — with no new earn mechanism. It spends razmerit via the **roll-table-as-menu** flow (see [[#SC generation via roll tables]]): the SFX opens the table, and each entry carries a razmerit cost paid on pick.

*To build:* the **roll-table-as-menu** effect action — open a roll table interactively, pick an entry, pay its cost, apply its output. The existing `discover` effect only unlocks; this open-and-pick mechanism is new.

## UX

- **GM** — a troupe overview: the recency list, the current scene (location + spotlight player), who's in-scene vs. scattered.
- **Player** — three states:
  1. **Spotlight** (on my main).
  2. **Support** (controlling a companion, with a "you're playing X — return to main" banner).
  3. **Out-of-scene** (my main is elsewhere) — surfaces a "join scene as support?" prompt with a support picker.
- **Support ends** when the player changes characters — manual switch, no auto-return.
- The **scatter** (cheap transversal) produces the out-of-scene state en masse — each non-spotlight player sees the "join as support" prompt for the first scene's location.
- "Assume support" = player-side access to the GM's existing "roam as entity" capability, plus a picker and a return affordance.

## Open questions

*(All design questions resolved — see the sections above.)*

Remaining **build** item (not a design question): the **roll-table-as-menu** effect action — `discover` only unlocks, so the "SFX → open table → pick → pay → gain" mechanism is new work for [[Effects]] + [[life-path]].

## Deferred

- The **fully-fledged GMC "brief"** + authoring **checklist** (how to make a GMC's personality/history/relations quickly reviewable with fresh eyes). Separately scoped; see the `#checklists` item in [[to-do]].
- **Multi-level razmerit** (projection / entity / player with conversion rates) — cool but complex to understand and not needed now.

## Related

- [[Inspired Mechanics#Troupe Play]] — RAW framing, scattering, session structure, GMC template.
- [[Data Model]] — `Player`, `Projection.last_used_at`.
- [[Tickets]] — B50 (recency), B51 (spotlight list), B52 (grog tables), B53 (companion authoring).
- [[Division of Labor]] — `troupe play` multi-role block.

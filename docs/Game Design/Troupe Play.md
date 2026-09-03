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
> Design in progress. Captures the decisions from the 2026-09-03 design session; the overseer keeps this doc updated as the design evolves. Open items live in [[#Open questions]]; the RAW framing lives in [[Inspired Mechanics#Troupe Play]].

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

- `main_entity_ids: list[str]` — the explicit mains (1+).
- `last_spotlight_at: str | None` — recency timestamp (the sort key).
- `last_main_entity_id: str | None` — the main last taken control of (the row's face).

All three stamp together on the single "took control of a main" event. `last_main_entity_id` is *stored*, not derived (reconstructing it from projection history is more fragile).

**Guard:** the stamp keys on the *actor* (the human player), not "a body became active" — so the GM testing/possessing a player's main does not falsely stamp spotlight.

## Support character model

An **SC is a relationship, not just a character** — a `(controlling player × main)` pair joined by a **`supports` edge** (directional: SC → main). The character (traits/name) hangs off the SC entity; `supports` is the *only* SC-specific data. Ownership is many-to-many: a main has a **cast** (1→many SCs); a player owns many SCs across mains.

- **Location is generic** — every projection already has one; an SC needs nothing special there.
- **Mobility = the generic `follow` mechanic** (any projection can follow). No anchor tag: a companion is an SC with a *follow* link to the main; a location-anchored SC has none. See the `#following` item in [[to-do]].
- **`teleport to main`** — a one-shot "join the main's current location" button, powered by `supports` (the SC already knows who its main is). Same-universe only; cross-universe rejoining goes through transversal.
- **Lifecycle = dormant.** Location-anchored SCs persist when the main leaves and reactivate on return — a main accumulates a dormant cast at every place it's been.
- **Generation = roll tables (self-serve).** The support player rolls their own SC; no GM handout.

## Availability

An SC is **available to play exactly when its main is active** — "active" = the main's player is actively controlling it. That's the same event as the spotlight stamp: *take control of a main* → stamp `last_spotlight_at`, mark the main active, and light up its cast. The switcher **greys out** (does not hide) SCs whose main is inactive.

**Two ways to assume a support character:**
- **Take over a peer GMC** — pick an existing authored SC (the available-SC picker).
- **Create from scratch** — roll a new one (the roll-table entry point).

## Support cast tiers

- **Companion** (spirit / spirit beast / artifact spirit / the follower) — *main-anchored*, recurring, defined by a **bond** + a **mystery/origin**. The rewarding tier; played by other players.
- **Peer** (same-faction fellow disciple) — *location-anchored*, recurring, lighter.
- **One-off** (adventuring party) — disposable; de-emphasized.
- **GM-character** (teacher, elder, captain, wanderer) — GM-played.

**Split rule:** a support character is someone the main can plausibly drag along as an *equal*; a GM-character is someone with authority, secrets, or plot-knowledge. "Really knowledgeable players" is the only escape hatch (an exception, not a feature).

## SC generation via roll tables

- **Universe archetype table** → one roll forks into the archetypes (e.g. spirit beast / cultivator / martial artist).
- Each archetype entry carries a **`discover` effect** that routes the character into the matching **life-path sub-graph** (a separate life path per archetype — not one graph with conditionals inside).
- **Location / faction tables** then further specify the life-path step, or the character continues along the universe path.
- The fork happens **at the roll** (entry → discover), not inside the path. No condition engine is added to life paths now; trait-dependent forks are a later nicety that can layer the effect system's conditions onto a discover effect.

**Open:** confirm `discover` **instantiates-and-executes** the path for the current character (vs. only unlocking it for the catalog) — see [[#Open questions]].

## Razmerit / roll-table access

Razmerit stays **entity-scoped**. A support character **earns its own razmerit** while played, and spends it to **buy roll-table access** — unlocking rarer or deeper life-path tables, i.e. the SC advances by buying its way further along its path.

## UX

- **GM** — a troupe overview: the recency list, the current scene (location + spotlight player), who's in-scene vs. scattered.
- **Player** — three states:
  1. **Spotlight** (on my main).
  2. **Support** (controlling a companion, with a "you're playing X — return to main" banner).
  3. **Out-of-scene** (my main is elsewhere) — surfaces a "join scene as support?" prompt with a support picker.
- The **scatter** (cheap transversal) produces the out-of-scene state en masse — each non-spotlight player sees the "join as support" prompt for the first scene's location.
- "Assume support" = player-side access to the GM's existing "roam as entity" capability, plus a picker and a return affordance.

## Open questions

- [ ] **Razmerit earn trigger** — per scene / per session / per "your SC did something that mattered" (a hitch, a successful aid)? Lean: on *accomplishment*, not time.
- [ ] **"Buy roll-table access"** — what exactly does razmerit unlock: rarer archetype tables, deeper life-path steps, location-specific casts? Define the buyable catalog.
- [ ] **Roll-table granularity** — universe archetype table, then per location-type / faction; how fine-grained do the tables get? Lean: universe → location-type first.
- [ ] **Roll output** — full SC (instantly playable) vs. archetype + player fills in the name/one trait? Lean: partial (roll the shape, let the player own the face).
- [ ] **`discover` semantics** — does the existing `lifepath_discovery` / `lifepath_executor` support "discover → immediately execute," or is that a gap to file?
- [ ] **When does support end** — manual "return to main" only, or auto-return on spotlight? Lean: auto-return when my main's scene starts.

## Deferred

- The **fully-fledged GMC "brief"** + authoring **checklist** (how to make a GMC's personality/history/relations quickly reviewable with fresh eyes). Separately scoped; see the `#checklists` item in [[to-do]].
- **Multi-level razmerit** (projection / entity / player with conversion rates) — cool but complex to understand and not needed now.

## Related

- [[Inspired Mechanics#Troupe Play]] — RAW framing, scattering, session structure, GMC template.
- [[Data Model]] — `Player`, `Projection.last_used_at`.
- [[Tickets]] — B50 (recency), B51 (spotlight list), B52 (grog tables), B53 (companion authoring).
- [[Division of Labor]] — `troupe play` multi-role block.

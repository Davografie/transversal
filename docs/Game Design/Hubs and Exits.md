---
title: Hubs and Exits
date: 2026-09-28
tags:
  - transversal
  - game-design
  - portal
  - travel
  - vagabond
  - airports
aliases:
  - Portal Model
  - Hubs
  - The Floating Vagabond
  - Portal Exits
status: draft
---

# Hubs and Exits

How a **place you can leave by more than one route** works: the multiverse's one bar, the doors in it, and the airport menu that is the first implementation.

> [!note] Where this came from
> Written 2026-09-28 after the human's account of the Floating Vagabond and the Eindhoven Airport portal. It records a **product design**; the effect machinery it rests on is [[Effects]]', the graph and the fire path are [[navigation]]'s, and the layer that authors any of it is [[mcp-architect]]'s.

## The bar, as the human describes it

The Floating Vagabond is a bar from the tabletop game of the same name. In Transversal it sits **outside and in all other universes** and works like an elevator.

- **One bar per universe.** Each universe has its own bar.
- **The stairs connect bar to bar** — and only bar to bar. Take the stairs up or down and you arrive in another universe's bar.
- **The door at the bottom of each bar opens into that bar's own universe.** Walking out the door is how you enter the world the bar is in.

The two layers are what make the model work, and they gate differently:

| Layer | Edge | Gated? |
|---|---|---|
| The stairwell | `transversal` between two bars | **No** — the stairwell is nobody's universe, so anyone can climb and look at every landing |
| The door | `transversal` from a bar to a location in that bar's universe | **Yes** — you may only walk out into a universe where you have a projection |

The gate is the human's: *"perhaps we can gate this on where a character has projections present so they have a hub to universes they've been to."* That is expressible with data that already exists — a projection **is** the record of a universe visited, one per `(entity, origin-universe)`, and 153 entities already carry more than one.

**In the graph this needs nothing new.** `transversal` edges already run between bars: `Top Floor → The Floating Vagabond`, `The Floating Vagabond → Desert`, `The Floating Vagabond → Fractured Moon`. A stair is a `transversal` edge; `arrival_kind: transversal` already marks the crossing.

**What is missing is the destination label.** Every landing is called "The Floating Vagabond" on purpose — there are four such locations in the bar's own universe and a fifth in `three_realms` — so the landing name cannot say which stair reaches where. A stair must be identified by its **destination universe**, and today nothing on the edge carries it.

## A portal has an endpoint and an exit, and they need not agree

An authored portal effect can name a destination that has nothing to do with the edge it sits on. This is not hypothetical — it is the only portal with effects in the corpus:

**`Eindhoven Airport → Турышка аэропорт`** (edge target `loc-123442274`), authored 2026-09-28:

```
travel, IMMEDIATE, context {transversal_type: inapposite, projection: active}
  target: ""                     ← the legacy field is empty
  targetSpec.steps:
    1  select   collection: locations
    2  filter   field: id, operator: in, value: [loc-155715170, loc-155545539]
    3  choose   count: 1
```

`loc-155715170` is **Cape Town International**; `loc-155545539` is **Zurich**. The edge points at **Турышка аэропорт**. So the door is labelled Turyshka and the menu offers Cape Town and Zurich, and **the endpoint is ignored entirely**.

That is the state to design against, not a bug to patch around. Two readings, and the human's call:

1. **The endpoint is an anchor, not a destination** — a portal is "a place that has exits", and the door you see on the map is where it is, not where it goes. Then the endpoint is metadata and the effect is the truth.
2. **The endpoint is the default** — an effect may override it, but an unauthored portal goes where its edge points (`fire_portal`'s existing fallback, `transversal_type or "inapposite"`), and a divergence is something the author opted into.

Reading 2 is what the machinery does today. Reading 1 is what a menu of exits really means. **They differ on whether an authored effect may silently contradict its own edge**, and nothing currently warns either way.

## The airport menu — the first implementation

Airports are the chosen first case: a single portal at each airport that, on activation, offers a destination to choose from. Earth already has **five** airport locations, each with a real parent city:

| Airport | id |
|---|---|
| Cape Town International | `loc-155715170` |
| Zurich Airport | `loc-155545539` |
| Sheremetyevo International | `loc-155555772` |
| JFK Airport | `loc-155571988` |
| Eindhoven Airport | `loc-125886561` |

The exit is **a `choose` step at the end of the effect's target path** — the human's *"a `travel` effect with target path `entities([airport 1, airport 2, …]) -> choose`"*, with two corrections found by tracing the spec language:

- **Seed from `locations`, not `entities`.** A `filter` can prove an entity *is* a location, but it does not narrow an `entity` element to a `location` one. `select entities → filter(id in […]) → choose` ends at `entity/one`, which **fails a location destination**; `select locations → filter(id in […]) → choose` ends at `location/one` and is valid. Measured both ways through `trace_target_spec`.
- **The id list goes in the filter's value**, because no seed means *these particular ones*. All fifteen `COLLECTIONS` are *all of a kind*; the single `literal` step carries one value. This is [[B242]], which also records what it costs: **the id-validity check moves to run time**, so a stale or mistyped id silently drops a destination from the menu instead of failing where it was written.

Alternatives to a literal list, both cheaper to maintain:

- `select locations → filter(name contains "airport") → choose` — also valid; an airport added later joins the menu without re-authoring. Blunt, since a name match is a search, not an identity.
- The same path with `aggregate(fn: "random", count: 1)` instead of `choose` — **the non-interactive counterpart**, and exactly the Vagabond stairs' behaviour with no new vocabulary. `choose` and `random` are one step in two modes ([[Choose and Random Resolution]]).

## The Vagabond stairs, machinery

A stair should present a **random exit within the set of bars where the character has a projection**, firing on arrival and re-rolling on leaving proximity — so a player walks closer to read the exit, then away to reshuffle.

Three things that shape it, and the third is the blocker:

- **The candidate set is computed, not authored** — "bars in universes where I have a projection" — so an authored branch list cannot express it. This is the case a `choose`/`random` step over a computed scope exists for.
- **The rungs and the exit are one path.** Walk closer to read it, walk away to re-roll: the reroll is a re-resolution, not new state.
- **Leaving is an open question, already written down.** [[Place-Owned Rules]] § 5 asks it in the human's own words: *"does a standing rule need an explicit exit moment (the author's 'walk away and the portal re-rolls')? If yes, departure is the mirror of arrival and needs the same audience resolution at the previous location."* It also sequences it: *"**4. Relations/portals**, reusing the same seam for the portal brief (**randomised destination + approach/departure**)… Steps 1 and 4 are the two the author is blocked on."* And it gives the portal's ownership row — the rule lives on the relation and reaches *whoever crosses*.

## What exists, what does not

Measured 2026-09-28. The distinction matters because the design reads as nearly finished and the data says otherwise.

| Piece | State |
|---|---|
| Effect-driven portals (`POST /locations/{from}/portal/{to}/fire`) | **Live**, with a `transversal_type` fallback when the edge carries no effects |
| `Effect.targetSpec`, and a `choose` step with real semantics | **Live** |
| A portal whose exit is chosen | **Only one exists** — Eindhoven → Turyshka — and it does not yet move anyone |
| **Portal effects anywhere else** | **None. 343 `transversal` edges, 0 carrying effects** |
| Per-edge effects authorable through MCP | **No** — `create_relationship` takes no `effects` |
| A live `choose` resolving to a destination | **No.** The fire returns `status: pending` with a pending choice of kind `location` **and no candidates**: the low-level applier entry point cannot carry the pool, so nothing can be answered and the traveller does not move ([[navigation]], 2026-09-28) |
| A chooser surface | **No** — the viewer ignores `pendingChoices` entirely; that half is [[navigation]]'s |
| `context.preview` (blind vs previewed) | **Never built** — zero hits for `preview` in the effects layer |
| A destination label on a stair | **No** — the edge carries only the relation type |
| Proximity triggers | **None, and never built.** Every "proximity" in the code is presentational (`expandLevel`, the chip that opens near the character). Effects fire on **interaction** — a drag or tap onto the portal dot — not on approach |

## Open questions, for the human

1. **Does an authored effect override its edge endpoint, or must they agree?** (See *A portal has an endpoint and an exit* above.) This decides whether the Eindhoven effect is correct or mis-authored.
2. **Does a stair flight exist between two bars no character can use?** If the stairwell is ungated, a player sees destinations they cannot reach — a place rather than a menu. That is a fiction call, not a technical one.
3. **Does a portal destination need to be a `choose` at all** — or should the fire response carry the candidate pool to a surface that presents it? [[navigation]] asks this and it is a design decision before it is an implementation one.
4. **Is leaving proximity a departure trigger** (a new event), or is the reroll simply *not persisting* the resolved destination between approach and crossing?

## See also

- [[Portal Transversal Effect]] — the effect-level five axes; **partly superseded**, see its own note
- [[Place-Owned Rules]] — the portal's ownership seam, and the departure question § 5
- [[Choose and Random Resolution]] — the `choose` / `random` step semantics
- [[Projections and Transversal]] — what a projection is, and the three ways to move
- [[B242]] — the targeting vocabulary gap the exit list runs into
- [[Setting and Narrative]] — the universes and the jian

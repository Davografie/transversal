---
title: Faction Authoring
date: 2026-10-16
tags:
  - transversal
  - authoring
  - factions
  - manual
  - mcp
aliases:
  - How to author a faction
  - Faction recipe
  - Faction authoring guide
  - Designing factions
status: canonical
---

# Faction Authoring

How to build a faction in Transversal — what to create, in what order, and where each piece is written. Written for two readers at once: **you, in the GM panels**, and **an agent** writing the same layers through the tools.

The *model*, and the reasoning behind it, is in [[Factions and Organizations Design Log]]. This page is the recipe.

## The model in one screen

| Piece | Where it lives | Notes |
|---|---|---|
| The organisation | an entity of type **FACTION** | no separate kind of thing to learn |
| The roster | a **membership** tie, member → faction | the tie carries the member's traits |
| Someone's place | traits on that tie: `role` (**the statement is the position** — "sect head"), optional `rank` (a die), `tenure`, `loyalty`, `status`, `allegiance`, `grudge` | `role` is the marker: a tie with one is a roster entry |
| The want | one **static** trait on the faction, whose statement is the aim | *what does it want?* |
| The agenda | one **container** trait whose children are the portents | a container is an ordinary trait carrying the `container` tag |
| A portent | a trait setting: `statement` (the event), `order`, `enabled` (pending or landed), `known_to` (who has discovered it), `sfx_ids` (what landing does), optional die, negative polarity | **the list is the clock** — "how close" is landed ÷ total, derived; do not add a second pool |
| The weak link | a `challenge` or `resource` trait the players can attack | *"its funding source is its weakest link"* — this is what makes a faction playable |
| Ties to anything else | a **relation** tie + its traits | org ↔ org, org ↔ place, org ↔ asset are all the same tie |
| Paths it offers | its suitable life paths | the joining-and-advancement spine |

**Two things not to author**, both retired by the design log: the `commands` tie type (nothing uses it — the seeded content wrote an ordinary relation instead), and the rank ladder *as structure* (level ⇒ die). Rank belongs in the `role` statement, and the die is intensity. If you want the ladder, make it a guideline instead: a level-5 figure should be meaningfully harder to oppose than a level-1 one.

## The recipe

| # | Step | Where |
|---|---|---|
| 1 | **Create the org** — name + universe | A **＋** row in the tree, Type **FACTION** (or `create_faction`) |
| 2 | **Say what it is** — a tag or a trait naming it ("a sect modelled on the black tortoise") | The faction's trait section |
| 3 | **Give it a body** — a few rated traits from the `faction` set: `longevity`, `isolationist`, `secret`, `organisation`, `size`, `members`, `recruitment` | The faction's trait section |
| 4 | **Build the roster** — a membership tie per member, then a `role` (the statement) and optional `rank` (a die) on the tie | The faction's **Members** section; the member's **Factions** section |
| 5 | **Name a face** — make "who speaks for this org" findable in the role statement ("sect head") | On the tie |
| 6 | **Write the want** — a static trait whose statement is the aim | The faction's trait section |
| 7 | **Write the agenda** — a container trait whose children are the ordered portents | **No panel surface yet — see the next section** |
| 8 | **Give it a weak link** — the dependency the players can attack, and what degrades when they do | The faction's trait section, as a challenge or resource |
| 9 | **Wire the life path it offers** | The faction's life-path section |
| 10 | **Give it a move or two** — a rule the org owns | **Manage SFX**, attached to the faction |

## Step 7 — the agenda, and the one step with no button

A faction's agenda is a **container trait** (a trait carrying the `container` tag) whose children are its **portents** — one step each, in order. The last one is the terminus. Together they are the clock: "how close is it" is just how many have landed.

Setting the agenda up means nesting a step **under** the container and giving it:

- a **statement** — the event, in the fiction ("the Root-Weave Repository closes its doors");
- an **order** — its place in the sequence;
- whether it has **landed** — the flag that marks a step as done;
- optionally, the **rules that fire when it lands**.

**This is the one step in the recipe with no panel surface yet.** The panels edit a faction's traits, but nesting a setting under a container, and setting its order or whether it has landed, is done by an agent today. Everything else in the recipe is clickable.

> [!caution] Give every portent a distinct statement
> Two steps of one container with the same text *are the same step* — the identity of a nested setting is derived from its parent, its trait and its text. Distinct text is also what makes the agenda readable, so this costs nothing.

## One registry trait, many settings

**Do not create a registry trait per portent.** The registry is a shared vocabulary; instances differ by their `statement`, exactly as challenges on locations work — a handful of generic traits, many settings, the specific name in the statement.

The registry already carries what a faction agenda needs — a container trait for the portents, a portent trait, and an agenda trait — so authoring an agenda requires **no new registry entries**. Reach for a new registry trait only when the vocabulary itself is genuinely missing.

## When a faction is finished

- [ ] `name`, `universe`, a home place, and a symbol or role tag.
- [ ] A **stat block**: rated traits saying what it *can do*.
- [ ] A **roster** where every member has a `role`, and exactly one **face** is findable.
- [ ] A **want** — one line.
- [ ] An **agenda**: a container whose ordered children are the portents, each with a statement and what landing does. The last one is the terminus.
- [ ] A **dependency** the players can find and attack, and a note of what degrades when they do.
- [ ] A **life path it offers**, and the path's roll tables actually exist.
- [ ] At least one **rule it owns**, so the org can act.

## A built example — Iron Roots

**Iron Roots** in the Three Realms is a faction built to this recipe, and worth opening in the panels to see the shape:

- **A stat block**: `longevity` d10 *"older than the Verdant Dominion"*, `isolationist` d8 *"sealed behind the Valley of Ascension"*, `secret` d10, `organisation` d8 *"one head, an elder bench, and the disciple ranks"*, `size` d6, `members` d8, `recruitment` d6.
- **A want**: an `agenda` trait — *"reforge the Still Water Immortal's blade and hold the Valley of Ascension"*.
- **An agenda**: a `portents` container, whose children are the ordered steps.
- **A dependency**: `fire qi` d8, *"the fire qi that feeds the Bulwark's forge-fires"*.
- **A roster**: a membership tie per member, each carrying a `role` ("head", "elder", "disciple").
- **Ties to ground**: `control` traits on the faction's ties to its places — *"sect seat"* d10, *"residual claim"* d6.

## Cautions

- **The list is the clock.** Do not add a challenge pool *and* a portent list for the same thing; "how close is it" is derived from the steps.
- **A landed step stops offering its rules**, so it cannot fire twice — which is what makes a container-level sequencer possible: a rule can tell which step changed.
- **Don't author the `commands` tie type** or a stored rank ladder. Both are retired.
- **A faction does not own a place.** The claim is a `control` trait on the tie, with a die — not ownership.
- **Never author a player's character into a roster.** A faction's members are GMCs and assets unless a player has chosen to join.

## References

- [[Factions and Organizations Design Log]] — the model, the evidence, and the open decisions
- [[Location Authoring]] — the places a faction holds or wants
- [[SFX Authoring]] — the rules a faction owns
- [[Content Completeness Checklist]] — the wider authoring checklist
- [[Relationship Types Design Log]] — why tie types are structural and posture is a trait
- [[Container Traits Design Log]] — the container machinery portents use

---
title: Faction Authoring
date: 2026-09-15
tags:
  - transversal
  - authoring
  - factions
  - mcp
  - guidelines
aliases:
  - How to author a faction
  - Faction recipe
  - Faction authoring guide
  - Designing factions
status: canonical
---

# Faction Authoring

How to build a faction in Transversal — what to create, in what order, with which
tool. Written for two readers at once: **[[mcp-architect]]**, who needs to know
which tool carries which act (and where the tool set cannot express the model
yet), and the **GM**, who is doing the authoring.

The *model* and the reasoning behind it are in [[Factions and Organizations Design Log]];
this is the recipe. Everything marked ✅ below is verified against the live DB.

## The model in one screen

| Piece | Where it lives | Notes |
|---|---|---|
| The org | an `Entity` of type `faction` | no new entity type, no separate collection |
| The roster | a **`membership`** edge, member → faction | carries the tie's traits |
| Someone's place | relation traits on that edge: `role` (**the statement is the position** — "sect head"), optional `rank` (a die), `tenure`, `loyalty`, `status`, `allegiance`, `grudge` | `role` is the marker: a tie with one is a roster entry |
| The want | one `static` trait on the faction, `statement` = the aim | AW's *impulse* |
| The agenda | one **container**-tagged trait whose children are the portents | a container is an ordinary trait carrying the `container` tag |
| A portent | a `TraitSetting`: `statement` (the event), `order`, `enabled` (pending/landed), `known_to` (who has discovered it), `sfx_ids` (what landing does), optional die, `polarity: NEGATIVE` | **the list is the clock** — "how close" is landed ÷ total, derived; do not add a second pool |
| The weak link | a `challenge`/`resource` trait the players can attack | NBA: *"its funding source is its weakest link"* — this is what makes a faction playable |
| Ties to anything else | a **`relation`** edge + relation traits | org↔org, org↔location, org↔asset are all the same edge |
| Paths it offers | `suitable_life_path_ids` | the joining/advancement spine |

**Two things not to author**, both retired by the design log: the `commands` edge
type (0 rows live; the conspyramid seed never wrote one — it wrote a `relation`
with `description="commands"`), and the rank ladder *as structure* (level ⇒ die).
Rank belongs in the `role` statement; the die is intensity — and if you want the
ladder, apply it as a guideline: a level-5 node should be meaningfully harder to
oppose than a level-1 one (NBA: Difficulty = level + 3).

## The recipe

| # | Step | Tool today |
|---|---|---|
| 1 | **Create the org** — name + universe | ✅ `create_faction` |
| 2 | **Give it a symbol/role** — a tag or a trait naming what it *is* ("a sect modelled on the black tortoise") | ✅ `add_trait_to_entity` (tags) |
| 3 | **Give it a body** — a few rated traits from the `faction` set (`longevity`, `isolationist`, `secret`, `organisation`, `size`, `members`, `recruitment`, …) | ✅ `add_trait_to_entity` |
| 4 | **Build the roster** — `membership` per member, then `role` (statement) and optional `rank` (die) on the tie | ✅ `create_relationship` + `set_rank_role` |
| 5 | **Name a face** — tag the tie (or the role) so "who speaks for this org" is findable | ⚠️ works, but nothing surfaces it |
| 6 | **Write the want** — a `static` trait whose statement is the aim | ✅ |
| 7 | **Write the agenda** — a container trait, its children the ordered portents | ❌ **not over MCP today** — see below |
| 8 | **Give it a weak link** — the dependency the players can attack | ✅ `add_trait_to_entity` (challenge/resource) |
| 9 | **Wire the life path it offers** | ✅ `set_faction_life_paths` |
| 10 | **Give it a move or two** — an SFX it owns (`entity` is an owner surface) | ✅ `create_sfx` |

Steps 1–6 and 8–10 are authorable now. Step 7 is the gap, and it is a *tooling*
gap, not a model gap: `order` and `enabled` landed on the backend on 2026-09-15.

## What the MCP tool set needs (the ask for [[mcp-architect]])

The whole portent path is currently **unexpressible over MCP**. Verified against
the tool schemas:

| Need | `add_trait_to_entity` | `update_trait_setting` |
|---|---|---|
| nest a setting under a container (`fromType: "traitsetting"` + `parentTraitsettingId`) | ❌ `from_type` allows only `entity\|projection\|relationship` | ❌ not exposed at all |
| `order` (sequence the portents) | ❌ | ❌ |
| `enabled` (mark a portent landed) | ❌ | ❌ |
| `known_to` (per-step discovery) | ❌ | ❌ |
| `sfx_ids` (the step's consequences) | ❌ | ❌ |
| `capacity` (a clock) | ❌ | ❌ |
| `notes` (the GM-only layer) | ❌ | ✅ |

So: **a faction's roster can be authored over MCP, and its agenda cannot.** The
minimum to close it:

1. `add_trait_to_entity` — accept `from_type: "traitsetting"` + `parent_traitsetting_id`, and `order`, `enabled`, `known_to`, `sfx_ids`, `capacity`, `notes`.
2. `update_trait_setting` — accept `order`, `enabled`, `known_to`, `sfx_ids`, `capacity`, and the re-anchoring pair (`from_type` / `parent_traitsetting_id`) so a portent can be moved between containers.
3. A **roster read** — `faction_canvas` returns members with rank/role, but a light `faction_members(faction_id)` (`{id name type role rank}`) avoids pulling the whole canvas for a list. The GraphQL field now exists (`factionMembers`), so it is a thin passthrough.
4. *(Optional)* a `set_portent_landed(setting_id, landed)` convenience over `update_trait_setting`, since that is the one write a GM makes repeatedly mid-scene.

Two things that are **not** needed, and would be wasted work: a `create_portent`
tool (a portent is just a trait setting — see below), and any notion of a
per-portent registry trait.

## One registry trait, many settings

**Do not create a registry trait per portent.** The registry is a shared
vocabulary; instances differ by `statement`, exactly as TV2 already models
challenges on locations — a handful of generic traits, many settings, the specific
name in the statement (`"Navigate the Forest" 9d6`).

So a faction needs at most **two** new registry entries:

- a **container** trait carrying the `container` tag (one exists today —
  `trait-3160510`, held by 90 characters — so the mechanism is proven), and
- a generic **portent** trait, in a trait set that factions can hold.

Watch the typing: the existing `sub-goal` (static *and* challenge) lives in
`subtraits`, which is typed `['subtrait']` only, so reusing it means widening that
typing. A fresh `portent` trait in a faction-typed set is cleaner.

## Completeness checklist

A faction is finished when:

- [ ] `name`, `universe`, home location, and a symbol/role tag.
- [ ] A **stat block**: rated traits saying what it *can do*.
- [ ] A **roster** where every member has a `role`, and exactly one **face** is findable.
- [ ] A **want** (static trait) — one line.
- [ ] An **agenda**: a container whose ordered children are the portents, each with a `statement`, an `order`, and `sfx_ids` for what landing does. The last one is the terminus.
- [ ] A **dependency** the players can find and attack, and a note of what degrades when they do.
- [ ] A **life path it offers** — and the path's roll tables actually exist (see below).
- [ ] At least one **SFX it owns**, so the org can act.

## Worked example: Iron Roots (live, 2026-09-15)

The real content, as the model reads it:

| Piece | Live state |
|---|---|
| The org | `faction-41014575` "the Iron Root sect", `three_realms` |
| Roster | **7 members** — `Yan Fei` = "sect head" (d12), `Jian Wei` = "honorary sect elder", `Luo Ting` / `Wang Lian` = "sect disciple", `Jianxin Fireheart` = "disciple", `Elder Zhu` = "former disciple", `Head Chef Bao` = "Sect" |
| Stat block | **none** — the sect holds zero trait settings |
| Want / agenda / dependency | **none** |
| Paths offered | **none**, and `lp-359696be` (named "Iron Roots") is an **empty stub** — no entry table, 0 roll tables |
| Ties | 34, of which the 7 above carry a role; the rest are postures |

Data smells worth fixing while authoring: `Elder Zhu` is a **"former disciple"** still
on the roster (either drop the tie or record it as tenure), `Head Chef Bao`'s role
is literally `"Sect"`, and `Tianmen`/similar unranked ties may be members whose
role was never written.

And a live wiring bug in the same family: `lp-verdant-disciple` is a **complete**
7-table path named "Azure Dawn", but it is offered by `fac-verdant-steps` — a
seeded faction with **one** tie — while the real Azure Dawn Sect (`faction-40725783`,
30 ties, 19 ranked roles) offers nothing. Someone should decide which of the two is
canonical before wiring it.

## Cautions

- **The list is the clock.** Do not add a challenge pool *and* a portent list for the
  same thing; "how close is it" is derived from the ticks.
- **Arming the next portent is authorable today** — a landing SFX's effect list can
  disable itself, apply its consequences, and `add_rating_die` on the next portent
  (the action explicitly covers "any rating type: static, resource, or challenge").
  What is *not* yet possible is the container-level version, where one SFX sequences
  the whole list; that needs the changed setting's id in the `trait_updated` event
  ([[Effects]]' file — see the ask in [[backend-platform]]'s Blockers).
- **A disabled portent still offers its SFX.** Suppression is not implemented yet
  ([[Effects]] owns it), so a landed portent can currently be re-activated. Until
  that lands, prefer effect lists that are idempotent.
- **Don't author `commands`** or a stored rank ladder — both are retired.

## References

- [[Factions and Organizations Design Log]] — the model, the evidence, and the open decisions
- [[Content Completeness Checklist]] — the wider authoring checklist (its Faction section is superseded by this document)
- [[Relationship Types Design Log]] — why edge types are structural and posture is a trait
- [[Container Traits Design Log]] — the container machinery portents use
- [[MCP Tool Experience]] — the tool set as it stands

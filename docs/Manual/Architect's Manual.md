---
title: Architect's Manual
date: 2026-10-16
tags:
  - transversal
  - manual
  - architect
  - authoring
  - gm
aliases:
  - Architect Manual
  - Authoring Manual
  - GM Authoring
  - How to contribute
status: draft
---

# Architect's Manual

An **Architect** is the role that builds the world. Players play in it; architects add to it — places, people, factions, rules and tables. If you can open the **🛠** panel, you are one. (If you cannot, see [[Getting Started]] § *Roles*.)

Everything you write goes into **one shared world**: one database, one map, one trait vocabulary, used by every table. There is no private copy and no undo. Two habits follow, and they are most of the advice on this page: **look before you write**, and **write for the person who finds it next**.

This is the front door to authoring. It gives you the words, the tools and the order to work in, then hands you to the manual for the thing you actually want to make. It is written for two readers at once, because both do the same work: **you, in the GM panel**, and **an agent driving the same writes over MCP**. Each authoring manual says, layer by layer, which surface writes it — because the surfaces are not uniform.

## The words you need

| Word | What it means |
|---|---|
| **Universe** | A world — Earth, the Three Realms. Everything else belongs to one. |
| **Entity** | One thing: a place, a character, a GMC, a faction, an asset, a universe. |
| **Location** | An entity that is a place. Places nest — every one has a parent — and that nesting is the tree. |
| **Trait** | One quality of a thing, e.g. `surveillance d8`. The **registry** holds the definition; a **setting** is that definition attached to one thing, with its own die and its own text. Reuse the registry and add a setting. |
| **Statement** | The authored sentence on a trait setting. The die is the mechanic; the statement is what the table reads aloud. |
| **Projection** | One body of an entity in one universe. Characters have one per world they can reach; a place usually does not need one. |
| **SFX** | A rule that bends the normal rules for one character, place or thing. |
| **Roll table** | A named list of outcomes. A **life path** is a chain of them that a character walks for growth. |

[[Entities and Traits]] is the full model when a word here is not enough.

## The toolbox

**The GM panel (🛠)** has two modes. **Play** runs the game — beats, scenes, who is where. **Prep** is the authoring half: **Manage Traits**, **Manage SFX**, a browser with three tabs (**Places** — the location tree — **Factions** and **Players**), a filter over the tree and the faction list, and **🗺 Canvas** for the graph view.

**The tree is the spine.** Every place, person and asset is a row in it, under its universe. Filter to find a thing, then click it to open its editor. **The ＋ rows in the tree are the only create button**: a ＋ under a place adds an occupant, under a universe adds a place, and the create form's **Type** dropdown offers all six kinds — so a faction is created by asking for one there, not from the Factions tab.

**Each editor is the editor for that kind of thing.** A place's carries its traits and images, its portals and their effects, its zones, and the rule that fires when someone walks in. A universe's adds **🎲 Roll Tables**. A trait opens the trait editor, which can also show every instance of that definition.

**Panels behave like windows.** A panel can open a child panel, and any child can be detached (⤢) into a floating window, docked back (⤓), collapsed (▾) or closed (×). Floating windows and their order are remembered **on this device**.

**MCP**, for agents: the same writes, as tools. Every mutating tool **plans by default** (`dry_run: true`) — read the plan, then pass `dry_run: false` to commit.

## Find your job

| I want to… | Read | Where |
|---|---|---|
| Make a place playable, then rich | [[Location Authoring]] | Tree → ＋ (or `create_location`) |
| Put a person in a place | [[Content Completeness Checklist]] § *GMC* | Tree → ＋ under the place |
| Build an organisation and its agenda | [[Faction Authoring]] | Create form → FACTION (or `create_faction`) |
| Write a rule, technique or curse | [[SFX Authoring]], and [[SFX Reference]] as the lookup | **Manage SFX** |
| Write a list of outcomes, or a growth path | [[Roll Table and Life Path Authoring]] | Universe editor → **🎲 Roll Tables** |
| Add a trait to the shared vocabulary | [[Entities and Traits]] § *Trait Registry vs. Trait Settings* | **Manage Traits** |
| See the shape of a whole world | [[Relational Canvas]] | **🗺 Canvas** |
| Not authoring — playing or running the game | [[User Manual]] | GM panel **Play** mode |

The four manuals to know are [[Location Authoring]], [[Faction Authoring]], [[SFX Authoring]] and [[Roll Table and Life Path Authoring]]. Each is a recipe with a checklist at the end, and each says which surface writes each layer — some layers are GraphQL, some are REST-only, and two cannot be written through MCP at all.

## The order that works

Build outward from the tree, because each layer is read against the one above it:

1. **The place**, with a parent. Nothing is reachable without one — the tree, not the entity, is what travel reads.
2. **The people and things in it** — a GMC, an asset, a zone for every child place.
3. **The organisations** that hold or want those places.
4. **The rules** that live on any of them.
5. **The tables and paths**, alongside whatever they serve.

A place is not finished when the entity exists. [[Location Authoring]] § 1 names the four states — *in the tree*, *playable*, *rich*, *deep* — and **the tier is decided by what is missing, not by how much is there**: forty traits and no background image is still a place nobody can look at.

## Before you write, ask what reads it

Every authored thing is read by exactly **one** surface, and a few fields are read by nothing at all — writing into those produces content that exists, validates, and changes nothing. [[Location Authoring]] § 7 keeps the live list. When the answer is "nothing reads it", that is a bug for the surface's owner rather than an authoring job.

## Rules of the road

- **A player's character belongs to the player.** Never author, rename, tidy or "fix" one. When a scene needs a face, make a **GMC**. (Kael Drift is the project's own test character — also not yours to fill in.)
- **Specific beats complete.** `mood d8 "a town that already knows how this ends"` is content; a die with no statement is a number nobody can narrate.
- **Publish deliberately.** New content starts **unpublished**: the tree badges it *draft*, and players do not see unpublished occupants. It is a GM-only marker rather than a travel lock — but it does mean authored work nobody sees.
- **Names, not ids.** You name things by name everywhere; an id on a card is a sign the thing points at something that no longer exists.
- **Check it the way the app reads it.** [[Location Authoring]] § 8 gives the three reads that prove a place is wired.
- **Bulk writes deserve a second look.** There is no undo, and some writes replace a whole list.

## Where to go next

- [[Location Authoring]] · [[Faction Authoring]] · [[SFX Authoring]] (with [[SFX Reference]]) · [[Roll Table and Life Path Authoring]]
- [[Content Completeness Checklist]] — the per-type "is it finished?" list
- [[MCP Tool Experience]] — the tool set, for agents
- [[GM Panel Development]] — how the panel is built, and its conventions
- [[User Manual]] — the player's half · [[Transversal Hub]] — everything

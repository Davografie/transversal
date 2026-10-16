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

This is the front door to authoring. It gives you the words, the tools and the order to work in, then hands you to the manual for the thing you actually want to make. It is written for two readers at once, because both do the same work: **you, in the GM panel**, and **an agent** writing the same layers through the tools. Each authoring manual says, layer by layer, which surface writes it.

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

**Each editor is the editor for that kind of thing.** A place's editor carries its traits and images, its portals and their effects, its zones, and the rule that fires when someone walks in. A universe's editor adds **🎲 Roll Tables**. A trait opens the trait editor, which can also show every instance of that definition.

**Panels behave like windows.** A panel can open a child panel, and any child can be detached (⤢) into a floating window, docked back (⤓), collapsed (▾) or closed (×). Floating windows and their order are remembered **on this device**.

**Agents** write the same layers through the tools. Every mutating tool **plans by default** — read the plan, then confirm it to commit.

## Making and editing a thing

Everything in the world is made the same way.

1. **Create it from the tree.** Open **Prep → Places**, find the level it belongs under, and press that level's **＋** row.
2. **Fill in the create form.** **Name** (the 🎲 generates one for the universe), **Type** — CHARACTER, GMC, ASSET, FACTION, UNIVERSE or LOCATION — **Location** (the place it stands in; a universe has none), and **Razmerit** if the type carries a rating. Press **Create**.
3. **It opens in its own editor, and from then on every change saves itself.** Close the panel whenever you like; the thing is already saved.

The editor's sections are a small common set, and a section only appears when it applies to that kind of thing:

| Section | What it is for |
|---|---|
| **Name and type** | Rename it, move it to another place, set its razmerit. |
| **Traits** | Attach qualities from the registry — see the next section. |
| **Images** | Upload or generate a picture, and say where it shows: **Sheet**, **BG** (a detail backdrop) or **Nav** (the dot on a scene). |
| **Projections** | A character's or GMC's bodies, one per universe. Also where a body's own pictures live. |
| **Transversal Links** | The portals out of a place, and what passing through one does. |
| **Zones** | The doors on a place's picture — each one links to a child place. |
| **Fires on arrival** | The rule that runs when someone walks in. |
| **Members / Factions** | Who belongs to a faction, in what role. |
| **Inner locations** | The places this thing carries inside it — an inner world. They stay out of the Places tree, and a row opens one as a child panel. |
| **Danger Zone** | **Publish** or **Unpublish** — unpublished is GM-only and badged *draft* in the tree — and **Delete**, which is a two-click confirm and cannot be undone. |

Two buttons in the header are for running the game rather than authoring: **🎭 Assume** (act as this character) and **📥 Import to Location** (bring them to where you are).

**To fix something, find it first.** The filter above the tree searches names and ids, and the tree's **⊙** jumps to your current location — so nothing has to be hunted for by scrolling.

## The trait registry

Most things in the world are described by **traits**, and a trait has two halves:

- The **registry** — the shared vocabulary, edited under **Manage Traits**. A registry trait is a definition: its name, the universes it belongs to, a default die and rating type (static, resource or challenge), whether it is **ego** (travels with the character) or **morph** (belongs to a body), a polarity, tags, and an **Explanation** — the sentence that tells the next person what it means in play. **Sets** group traits — a location set, a faction set, a character set.
- The **setting** — that definition attached to one thing, with its own die and its own **statement**. This is what you write day to day.

**Reach for a setting first.** A new registry trait is right only when what you are describing is genuinely new vocabulary that other content should share; most authoring is a new setting on an existing trait.

Two tools in the trait editor matter when the job is *fixing* existing content:

- **Instances** — every place one definition is used, each row naming what it hangs off. Open it before you change a trait, so you can see everything you are about to affect.
- **Batch Edit** — change many traits at once, from the trait-set panel.

## Universes

A universe is created like anything else — a **＋** row at the top level, Type **UNIVERSE**. Its **name becomes its id**, so settle the name early. Its editor adds three things no other kind of thing has: **LoRA Configuration** and **Universe Style** (the palette), and **🎲 Roll Tables**, because tables belong to a universe.

## Find your job

| I want to… | Read | Where |
|---|---|---|
| Make a place playable, then rich | [[Location Authoring]] | Tree → ＋ (or `create_location`) |
| Put a person in a place | [[Content Completeness Checklist]] § *GMC* | Tree → ＋ under the place |
| Build an organisation and its agenda | [[Faction Authoring]] | Create form → FACTION (or `create_faction`) |
| Write a rule, technique or curse | [[SFX Authoring]], and [[SFX Reference]] as the lookup | **Manage SFX** |
| Write a list of outcomes, or a growth path | [[Roll Table and Life Path Authoring]] | Universe editor → **🎲 Roll Tables** |
| Add a trait to the shared vocabulary | *The trait registry*, above; [[Entities and Traits]] for the model | **Manage Traits** |
| See the shape of a whole world | [[Relational Canvas]] | **🗺 Canvas** |
| Not authoring — playing or running the game | [[User Manual]] | GM panel **Play** mode |

The four manuals to know are [[Location Authoring]], [[Faction Authoring]], [[SFX Authoring]] and [[Roll Table and Life Path Authoring]]. Each is a recipe with a checklist at the end, and each says which surface writes each layer — because not everything has a button yet, and a few things need an agent.

## The order that works

Build outward from the tree, because each layer is read against the one above it:

1. **The place**, with a parent. Nothing is reachable without one — the tree, not the entity, is what travel reads.
2. **The people and things in it** — a GMC, an asset, a zone for every child place.
3. **The organisations** that hold or want those places.
4. **The rules** that live on any of them.
5. **The tables and paths**, alongside whatever they serve.

A place is not finished when the entity exists. [[Location Authoring]] § 1 names the four states — *in the tree*, *playable*, *rich*, *deep* — and **the tier is decided by what is missing, not by how much is there**: forty traits and no background image is still a place nobody can look at.

## Before you write, ask what reads it

Every authored thing is read by exactly **one** surface, and a few fields are read by nothing at all — writing into those produces content that exists, validates, and changes nothing. [[Location Authoring]] § 7 lists them. When the answer is "nothing reads it", that is a gap for whoever owns that surface rather than an authoring job.

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

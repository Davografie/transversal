---
title: Core Mechanics
tags:
  - transversal
  - game-design
  - rules
  - cortex-prime
aliases:
  - Rules
  - Game Mechanics
status: canonical
---

# Core Mechanics

Transversal is built on the **Cortex Prime** engine, a flexible narrative-focused RPG system. This document covers the foundational mechanics; for the rolling procedure specifically, see [[Dice Mechanics]].

## Cortex Prime Foundation

Cortex Prime is a toolkit system — it doesn't prescribe a single set of rules. Instead, it provides modular components that the GM (or game designer) assembles into a specific implementation. Transversal selects from these modules to create a streamlined multiverse-traversal experience.

Key modules selected:

| Module | Usage |
|--------|-------|
| **Trait Sets** | Characters and entities are defined by groups of traits with dice ratings |
| **Dice Pools** | Actions are resolved by assembling a pool of dice from relevant traits |
| **Tests & Contests** | Two resolution frameworks for different conflict types |
| **Effect Dice** | The size of the effect die determines the outcome's magnitude |
| **Razmerit** | Hyper-dimensional material that fuels SFX and dice manipulation |

## Trait Rating Types

Every trait in Transversal has both a die rating and a **rating type** that determines how its dice behave. See [[Inspired Mechanics#Trait Rating Types]] for full rules.

| Type | Behavior | Example |
|------|----------|---------|
| **Static** | Die adds to pool, remains unchanged after resolution | `strength: d8` |
| **Resource** | Pool of individual dice; player spends from pool, depletes until replenished | `qi: 4d4 + 7d6` |
| **Challenge** | Dice represent danger (doom) or progress (clock); rolled against to reduce | `gate_project: 2d8 + 1d6` |
| **Empty** | No mechanical weight; narrative/administrative only | `pronouns: "they/them"` |

## Dice Ratings

Every trait in Transversal is rated with a die type, representing its capability level:

| Die | Rating | Description |
|-----|--------|-------------|
| d4  | Poor   | Below average, a liability |
| d6  | Average | Competent, baseline professional |
| d8  | Good    | Skilled, notably capable |
| d10 | Great   | Expert, among the best |
| d12 | Amazing | Peak human or superhuman ability |

Traits can also be unrated (no die) — meaning the character simply doesn't have that trait in a meaningful way.

> [!note] The Cortex Prime Scale
> Cortex Prime canonically supports d4–d12. Higher dice (d12+) are reserved for truly superhuman scale and would require the Scale Mod, which Transversal does not currently use.

## Trait Sets

A **trait set** is a category of traits that together describe an aspect of an entity. Each entity can have multiple trait sets. Trait sets are **universe-specific** — the sets available on Earth (Attributes, Skills, Distinctions) differ from those in the Three Realms (Cultivation, Combat Arts, Distinctions). An entity's active trait sets depend on their `effective_universes` — the active projection's universe plus any unexpired attunements.

For example, a character on Earth might have:

- **Attributes** — Strength, Agility, Intelligence, Willpower
- **Skills** — Shooting, Persuasion, Investigation, Stealth
- **Distinctions** — "Veteran of Shadow Operations", "Answered Antonov's Call"

That same character in the Three Realms has a separate projection with cultivation traits. If they hold a Three Realms attunement on Earth (e.g., the jian), those cultivation traits become available alongside their Earth traits.

Each trait within a set receives its own die rating. When building a dice pool for an action, the player (or system) picks one trait from each relevant trait set available in the current universe.

See [[Entities and Traits]] for the trait registry and entity types, [[Projections and Transversal]] for projections and attunement, and [[Inspired Mechanics#Sub-Traits]] for sub-traits.

### Sub-Traits

A **sub-trait** is a trait nested within another for organizational clarity. Sub-traits may carry conditional mechanical triggers: for example, a character's spirit root elements (fire, water, etc.) are sub-traits of spiritual power. When using a technique whose element matches a spirit root element, the matching sub-trait die can be added to the pool. See [[Inspired Mechanics#Sub-Traits]].

## Dice Pools

A **dice pool** is the collection of dice a player rolls to resolve an action. The pool is assembled by selecting:

1. One trait from each applicable trait set (rated d4–d12), drawn from traits available in the **current universe** (or through razmerit attunement)
2. Any bonus dice from assets, circumstances, or razmerit spends
3. Any complication dice assigned by the GM (opposition, environmental hazards)

The number of dice in the final pool determines which resolution pipeline fires: 1–2 dice use the Simplified pipeline, 3+ dice use the Cortex Prime Dice Pool pipeline. See [[Dice Mechanics]] for both procedures.

### Building a Pool — Example

A character attempts to hack a dimensional gateway console:

| Source | Trait | Die |
|--------|-------|-----|
| Attribute | Intelligence | d8 |
| Skill | Hacking | d10 |
| Distinction | "Ghost in the Machine" | d8 |
| Asset | Custom Decryption Rig | d6 |

Pool: d10 + d8 + d8 + d6

## Tests vs. Contests

### Test
A **test** is a roll against a fixed difficulty set by the GM. The GM establishes a target number and the player rolls to meet or beat it. Tests are used for:

- Overcoming environmental obstacles
- Using skills against static opposition
- Simple pass/fail situations

### Contest
A **contest** is a roll where two parties are actively opposed. Both sides assemble dice pools and roll against each other. Contests are used for:

- Combat
- Social confrontations
- Any situation where an NPC actively resists

The winner is determined by the rolling procedure — see [[Dice Mechanics]].

## Effect Dice

The **effect die** determines the magnitude of a successful outcome — how much impact the action has beyond simple pass/fail.

| Effect Die | Outcome Magnitude |
|------------|-------------------|
| d4         | Minimal |
| d6         | Standard |
| d8         | Significant |
| d10        | Major |
| d12        | Extraordinary |

**In the Simplified pipeline**, the effect die is derived from the outcome tier: Marginal = d4, Success = d6, Exceptional = d8, Perfect = d10. No separate die selection is needed. See [[Dice Mechanics#Effect Die in Simplified]].

**In the Dice Pool pipeline**, after determining the total, the player chooses one unused die from their pool as the effect die. Its type (not its rolled value) sets the magnitude. The effect die is also used for comparisons against challenge pool dice. See [[Dice Mechanics#Effect Die in Dice Pool]].

> [!example] Effect Die in Practice
> Rolling to convince a guard: a d8 effect means the guard is thoroughly convinced and may offer additional information. A d4 effect means the guard barely buys it and remains suspicious.

## Complications

### Hitches

When a player rolls a **1** on any die in their pool, the GM may activate a **hitch** — a complication. Hitches are narrative twists, not failures — they add tension alongside the result:

- The guard lets you through, but a supervisor arrives moments later
- The hack succeeds, but sets off a silent alarm
- The jump clears the gap, but your pack snags and tears open

Complications can also add a complication die (starting at d6, escalating on repeated hitches) to future rolls related to the situation. A complication die counts toward pool size, which can push a roll from the Simplified pipeline into the Dice Pool pipeline.

### Botches

If **all** dice in the pool show a 1, the roll is a **botch** — a catastrophic failure. The action fails completely and the situation worsens dramatically. Unlike a hitch, which adds cost to a potentially successful roll, a botch means everything goes wrong at once.

- In the Simplified pipeline: a single-die roll of 1 is both a hitch and a botch (Fail tier). A two-dice roll requires both to show 1.
- In the Dice Pool pipeline: all dice must show 1 — rare but devastating when it happens.

Botches do not grant additional razmerit beyond the standard hitch earn. The catastrophic outcome is its own penalty.

See [[Dice Mechanics]] for botch rules in each pipeline.

## Razmerit

Razmerit is the hyper-dimensional material that fuels SFX and powers dice manipulation in Transversal. Players earn razmerit primarily through complications, and spend it to activate SFX and influence rolls. Common spends include:

- Add an extra trait die to a pool (either pipeline)
- Keep a third die in the total (Dice Pool pipeline only — see [[Dice Mechanics#Dice Pool Pipeline (3+ Dice) — Cortex Prime]])
- Reroll a die (Simplified pipeline)
- Step up a die before rolling (either pipeline)
- Activate an SFX (see [[SFX and Effects]])
- Declare a story detail

See [[Entities and Traits#Razmerit]] for the full razmerit economy, earning rules, and in-fiction description.

## Beats, Scenes, and Sessions

Transversal organizes time into three nested units.

| Unit | Duration | What Happens |
|------|----------|-------------|
| **Beat** | A single action or exchange | Dice pools are built, rolled, and resolved. At the end of a beat, all dice pools clear. |
| **Scene** | A narrative unit, typically one location | Begins when the location changes (outside of conflict). Contains multiple beats. |
| **Session** | From play start to play end | Prepared by the GM beforehand. Contains multiple scenes. |

**Beat boundaries** are the game's primary state-reset point. When a beat ends, any dice still in play (unresolved pools, temporary modifiers) are discarded. The next beat starts fresh. This prevents modifier accumulation across actions without requiring constant cleanup.

**Scene boundaries** trigger when the party changes location outside of conflict. A new scene means a new location background image, new zone traits, and potentially new available actions. SFX can be scheduled to fire at scene boundaries.

**Session boundaries** mark the beginning and end of playtime. The GM prepares the session beforehand — creating locations, NPCs, and challenges. At session end, persistent state (traits, razmerit, relationships) carries forward; temporary state (active dice pools, scene-specific modifiers) does not.

## Advancement

Characters grow through **life paths** — sect, guild, career, or way-of-life terms — plus **trait transfer** (teach / gift / take) and **rated relationships**. See [[Character Growth]] for the full system.

> [!note] Superseded
> The older "advancement challenge pools" model is retired. Life paths are now the single training mechanic — there is no separate per-trait advancement challenge.

## Negative Traits

Not all traits are assets. **Negative traits** represent harm, stress, trauma, curses, and other conditions that work against the character.

A negative trait's die is added to the **opponent's** pool (or the GM's pool) when narratively relevant. If Kael has *Physical Stress d6*, an opponent attacking him adds that d6 to their attack pool.

| Severity | Die | Example | Recovery |
|----------|-----|---------|----------|
| Minor | d6 | Bruised, winded, rattled | Resolves easily — rest, first aid, a scene of downtime |
| Significant | d8 | Bleeding, concussed, shaken | Requires active effort — medical attention, cultivation cycling |
| Major | d10 | Broken bone, qi deviation, traumatic shock | Requires significant narrative effort — surgery, tribulation recovery, rare medicine |
| Critical | d12 | Dying, shattered cultivation, soul-wound | Requires extraordinary intervention — legendary healing, immortal's aid |

Negative traits do not kill a character outright. A character with multiple high-rating negative traits becomes unable to act effectively — their dice keep feeding the opposition. "Death" is the point where accumulated negative traits make survival narratively impossible, not a binary hit-point threshold.

### Earning Razmerit from Negative Traits

When the GM activates a hitch and the complication manifests as a negative trait, the affected character earns 1 razmerit — same as any complication. The negative trait is the complication.

## Narrative Actions

Some actions have no trait analog. A character wants to remember a piece of lore, recognize a face, or notice the weather changing. If no trait applies and the outcome isn't contested, the action resolves **narratively** — the players and GM decide what happens without rolling.

The dice engine only engages when:
- An action is contested (opposition exists)
- An action has meaningful stakes (failure matters)
- A player spends razmerit or activates an SFX

Everything else is conversation.

## Next

- [[Dice Mechanics]] — The full rolling procedure, conflict structure, and negative trait mechanics
- [[Character Growth]] — Life paths, trait transfer, and relationship ratings
- [[Entities and Traits]] — The entity system and trait registry
- [[SFX and Effects]] — How exceptions and automation work
- [[Inspired Mechanics]] — Conspyramid, zones, sub-traits, challenge pools

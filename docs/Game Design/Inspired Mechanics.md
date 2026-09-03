---
title: Inspired Mechanics
tags:
  - transversal
  - game-design
  - mechanics
  - advanced
aliases:
  - Advanced Mechanics
  - Subsystems
status: canonical
---

# Inspired Mechanics

Transversal draws mechanical inspiration from several tabletop RPGs. Each subsystem is adapted to Cortex Prime primitives — distinctions, trait sets, die ratings, and SFX — so they compose cleanly with the core resolution engine.

## Trait Rating Types

Every trait in Transversal has a **rating type** that determines how its dice behave beyond simple pool contribution.

### Static

The default. The trait's die is added to dice pools when relevant and remains unchanged after resolution.

```yaml
strength: d8    # static — always adds d8, never depletes
```

### Resource

The trait holds a pool of individual dice. The player chooses which dice to spend from the pool before rolling. Spent dice are removed from the pool until replenished.

**Temporary resources** have a defined capacity and regenerate over time or through specific actions (rest, cultivation, time skips). **Permanent resources** have no cap and do not regenerate — once spent, they're gone.

```yaml
# Temporary: qi pool for a Foundation Establishment 7th-level cultivator
qi:
  type: resource
  rating: 4d4 + 7d6    # 11 dice total; 4 are still d4, 7 stepped to d6
  capacity: 13d4        # original capacity (pre-step-up)
  regeneration: "full on long rest; partial on cultivation cycle"

# Permanent: beast cores collected from slain spirit beasts
beast_cores:
  type: resource
  rating: 3d6           # three beast cores of d6 quality
  regeneration: none     # must be earned through play
```

> [!note] Resource Spending
> The player announces which dice they're spending from the resource, removes those dice from the pool, and adds them to the current dice pool. The remaining dice stay in the resource for future use. For temporary resources, spent dice return to capacity after the appropriate recovery condition.

### Challenge

The trait holds dice that represent either accumulating danger (negative / doom pool) or work-in-progress (positive / progress clock).

**Negative challenges** (doom pools): the GM spends dice from the pool to strengthen opposition. Player failures, hitches, and narrative events add dice to the pool or step existing dice up.

**Positive challenges** (progress clocks): the players roll against the pool to reduce it. Each success removes or steps down dice. When the pool reaches zero, the project completes.

```yaml
# Negative: ambient danger under a fascist regime
regime_alert_level:
  type: challenge
  polarity: negative
  rating: 2d6 + 1d8

# Positive: developing an inapposite gate
inapposite_gate_project:
  type: challenge
  polarity: positive
  rating: 1d8 (razmerit) + 1d8 (technical) + 1d8 (political)
  description: "Build a portal capable of full physical transversal"
```

> [!note] Challenge Resolution
> The player selects one die from the challenge pool to target. The GM rolls that die as opposition. The player rolls their pool. The result determines what happens to the targeted die. See [[#Rolling Against Challenge Pools]].

### Empty

No mechanical weight. Used for narrative or administrative data — notes, pronouns, nicknames, appearance descriptions. Empty traits never enter dice pools and are ignored by the effects system.

```yaml
pronouns: "they/them"     # empty — informational only
appearance: "Tall, silver hair, jade-green eyes"
```

## Rolling Against Challenge Pools

> [!warning] Superseded
> The progress-clock resolution described below has changed: positive challenge
> pools are now **count-up-to-a-target** (a spend-from pool), not
> roll-against-to-shrink. See [[Challenge Rating Type]] for the current design.
> The negative (doom pool) behavior is unchanged.

### Simplified Pipeline (1–2 Dice)

1. Player selects one die from the challenge pool to target (e.g., a d8)
2. GM rolls that die
3. Player rolls their 1–2 dice
4. Compare the player's highest result to the GM's result

| Player beats GM by | Outcome | Effect Die |
|--------------------|---------|------------|
| 0 or less | **Fail** | Challenge die steps up (negative) or no progress (positive) |
| 1–2 | **Marginal Success** | d4 |
| 3–5 | **Success** | d6 |
| 6–8 | **Exceptional Success** | d8 |
| 9+ | **Perfect Success** | d10 |

**Effect application:**
- Effect die > challenge die: challenge die is **removed** from the pool
- Effect die ≤ challenge die: challenge die **steps down** one size (d8→d6)
- On failure (negative challenge): GM may step up the targeted die or add a new die based on their roll's effect (GM rolls a separate effect die from the opposition pool)
- On failure (positive challenge): no change, but the situation may worsen narratively

> [!example] Simplified Challenge Roll
> The inapposite gate project has a d8 (political) remaining. Kael targets it.
>
> GM rolls d8 → **4**. Kael rolls d10 (Persuasion) + d6 (Distinction) → 9, 3.
>
> Highest is 9. Beat the GM by 5 → **Success (d6 effect)**.
>
> Effect d6 ≤ Challenge d8 → the political d8 steps down to **d6**.
>
> New project rating: 1d8 (razmerit) + 1d8 (technical) + **1d6** (political).

### Dice Pool Pipeline (3+ Dice)

1. Player selects one die from the challenge pool to target
2. The targeted die becomes part of the opposition — GM rolls it alongside the challenge's remaining dice (if any are designated as active opposition)
3. Player rolls their pool, keeps two highest, adds for total
4. GM keeps the targeted die plus one other high die from the challenge as opposition total
5. Compare totals

| Result | Effect |
|--------|--------|
| Player total > GM total | Player's effect die applied to challenge die (same remove/step-down rules as simplified) |
| Player total ≤ GM total | Failure — challenge die steps up (negative) or no progress (positive) |

The effect die is chosen from the player's unused dice, per standard Dice Pool rules.

> [!example] Dice Pool Challenge Roll
> Same project, Kael goes all-in with a full pool.
>
> Kael's pool: d10 (Intelligence) + d8 (Engineering) + d8 (Distinction) + d6 (Asset)
> Roll: 9, 6, 5, 4 → keep 9+6 = **15**. Effect die: d8.
>
> Challenge: GM rolls targeted d8 (political) → 5. No other active opposition.
> GM total: **5**.
>
> Player wins (15 > 5). Effect d8 ≤ Challenge d8 → steps down to **d6**.

## Simplified Outcome Tiers and Effect Dice

The simplified pipeline's outcome tiers determine a **virtual effect die** used for comparisons (challenge pools, SFX resolution, narrative magnitude).

| Highest Die Roll | Outcome | Effect Die |
|------------------|---------|------------|
| 1–2 | Fail | None |
| 3–5 | Marginal Success | d4 |
| 6–8 | Success | d6 |
| 9–11 | Exceptional Success | d8 |
| 12 | Perfect Success | d10 |

The Dice Pool pipeline continues to use standard Cortex effect dice — chosen from unused dice in the pool after the two-dice total is selected.

> [!note] Simplified vs. Pool Effect Caps
> The simplified pipeline's effect die caps at d10. A d12 effect is only achievable in the Dice Pool pipeline (by reserving a d12 from your pool). This is intentional — simplified is faster but has a lower ceiling.

## Sub-Traits

A **sub-trait** is a trait nested within another trait for organizational clarity and conditional mechanical benefit. Sub-traits inherit their parent's trait set and rating type, but may carry additional rules.

### Structure

```yaml
attributes:
  spiritual_power: d8    # parent trait
  elements:              # sub-trait set, nested under spiritual_power conceptually
    fire: d6
    water: d4
    wood: d8
    metal: d4
    earth: d6
```

### Mechanical Rule

When a character uses a trait in a dice pool, they may also add a **matching sub-trait** if the action's context aligns:

- **Elemental matching**: If the character executes a cultivation technique whose element (e.g., fire) matches one of their spirit root elements, they add that element die to the pool. The spirit root element is a sub-trait of spiritual power, so it enters the pool alongside the parent trait.

> [!example] Sub-Trait Activation
> Kael uses a fire-aspected sword technique. His spirit root includes fire at d6.
>
> Pool: d8 (Spiritual Power attribute) + d8 (Sword Intent combat art) + fire d6 (sub-trait match)
>
> The fire d6 enters because the technique's element matches the sub-trait.

Sub-traits can also be used for organizational purposes only — grouping related traits without mechanical triggers. The `elements` sub-trait set is both: it organizes five element dice under spiritual power, and provides the matching rule for techniques.

## Attunement

Attunement is a **temporary SFX-triggered effect** that adds a universe to a character's `effective_universes` — morph traits from that universe become available without moving the body. It is never a passive state; it always has a cost and duration. See [[Projections and Transversal#Attunement]] for the canonical model.

## The Conspyramid

A **conspyramid** models faction structure as a hierarchy of sub-entities — nodes at different levels, each with traits and visibility rules. Inspired by Night's Black Agents.

### Structure

| Level | Description | Typical Traits | Visibility |
|-------|-------------|---------------|------------|
| 1 | Street / surface | d6 | Visible to anyone who looks |
| 2 | Operations / cells | d8 | Hidden — must be discovered |
| 3 | Mid-level command | d10 | Hidden — unlocked by dismantling level 2 |
| 4 | Regional leadership | d10 | Hidden — unlocked by dismantling level 3 |
| 5 | Inner circle | d12 | Hidden — unlocked by dismantling level 4 |
| 6 | Apex / single leader | d12 | Hidden — requires special conditions |

Each level contains one or more **nodes** — sub-entities belonging to the faction. A node is a simplified entity (character, location, or asset) with a trait set appropriate to its level.

### Visibility

Nodes have a `hidden` flag and a `known_to` list — a set of entity IDs that have discovered this node. The standard rule: a node at level N becomes visible to players only when at least one node at level N−1 has been defeated.

```yaml
type: faction
name: "Argent Meridian Sect — Outer Operations"
traits:
  influence: d10
  resources: d8
  secrecy: d12
nodes:
  - name: "Supply Runner — Three Rivers City"
    level: 1
    hidden: false
    known_to: []   # visible to all
    traits:
      smuggling: d6
      loyalty: d6

  - name: "Cell Leader — Wei Zhào"
    level: 2
    hidden: true
    known_to: []   # becomes visible when level 1 node is defeated
    traits:
      command: d8
      qi_cultivation: d6
      paranoia: d8
```

### Defeating a Node

Defeating a node is a contest. When the node is defeated:

1. The node's entity is tagged `defeated`
2. An SFX fires: `on_node_defeated` → adds connected level N+1 nodes to the players' `known_to` lists
3. The faction's overall traits may step down (losing a level 2 cell reduces `resources`)

The conspyramid is not strictly gated — players can discover nodes through investigation rather than combat. But the SFX ensures that dismantling the pyramid from below always reveals what's above.

## Entanglements and Career Paths

**Entanglements** are a separate trait set that represents a character's connections, history, and baggage in their current universe. They bridge two mechanics: Traveller-style career paths (how you got here) and Legends of the Wulin-style lore sheets (what ties you to this world).

### Acquisition

Entanglements are primarily acquired during **transversal** — when a character's consciousness arrives in a new universe, the morph's prior life generates one or more Entanglements. Additional Entanglements can be purchased with advancement or gained through major narrative events.

### Generation Procedure

On transversal to a universe where the character has no existing projection, roll or choose from the universe's Entanglement table:

| d8 | Three Realms Entanglement | Starting Die | Effect |
|----|--------------------------|-------------|--------|
| 1 | "Owes a Life Debt" | d4 | A powerful cultivator saved you. They may call it in. |
| 2 | "Survived a Spirit Beast Attack" | d6 | You know the beast's lair. It remembers you. |
| 3 | "Former Outer Disciple of [Sect]" | d6 | You have basic training and a contact inside. |
| 4 | "Found a Fragment of the Still Water Immortal's Legacy" | d8 | You possess a cultivation insight others would kill for. |
| 5 | "Betrayed by a Senior" | d4 | A former mentor wants you dead. You know their methods. |
| 6 | "Merchant's Child — Debts Unpaid" | d4 | Your family owes razmerit to a trade guild. |
| 7 | "Recognized a Transversal Artifact" | d8 | You've seen something like the jian before. You know where another might be. |
| 8 | "Beloved by the Valley Spirits" | d6 | The spirits of the land favor you. Nature bends slightly. |

The table is universe-specific. Earth Entanglements would draw from espionage, academic, or military backgrounds. A cyberpunk universe would draw from corporate, street, or hacktivist backgrounds.

### Mechanical Role

Entanglements are traits with rating types — they can be static, resource, or even challenge:

```yaml
entanglements:
  owes_life_debt:
    type: static
    rating: d4
    description: "Elder Yun saved your life at the Arrival Platform"
  debts_unpaid:
    type: resource
    rating: 4d6
    description: "Your family owes the Three Rivers Trade Guild — pay it down to resolve"
```

- **Static Entanglements** function like lightweight Distinctions — add their die when narratively relevant, step up through play
- **Resource Entanglements** represent obligations that deplete as you address them (pay off a debt, fulfill a vow)
- **Challenge Entanglements** represent ongoing threats or quests ("The Argent Meridian Wants You Dead" — a negative challenge)

### Lifepath Cascades

Entanglements function as a **lifepath system** for character creation and time skips. Each Entanglement carries an SFX that fires when the Entanglement is acquired, and again when it levels up. These SFX create or step up traits in other trait sets — building the character's full profile from their history.

```yaml
entanglements:
  pilot_career:
    type: static
    rating: d6
    sfx:
      - name: "Flight School"
        trigger: "on_acquire"
        effect:
          type: "create_trait"
          target: "skills"
          trait: "piloting"
          rating: d6
      - name: "Wing Commander"
        trigger: "on_step_up"  # fires when pilot_career reaches d8
        effect:
          type: "step_up_trait"
          target: "skills.piloting"
        effect:
          type: "create_trait"
          target: "entanglements"
          trait: "airforce_contact"
          rating: d4
```

> [!note] Lifepath Chain
> Picking the Pilot career Entanglement at d6 creates the Piloting skill at d6. Leveling Pilot to d8 steps up Piloting to d8 and creates a new Entanglement: "Air Force Contact d4." That contact can then be leveled, creating further connections. The Entanglement trait set becomes a web of history that populates the rest of the character sheet.

### Standard Advancement

Entanglements can be stepped up through play (d4→d6→d8→d10) using the standard advancement procedure (see [[Core Mechanics#Advancement]]). At d8, an Entanglement may unlock an additional SFX — the narrative weight has become mechanical power. At d10, the Entanglement can be "resolved" — converted into a permanent Distinction (with its SFX retained) or retired for a significant narrative reward.

> [!example] Entanglement to Distinction
> Kael's "Found a Fragment of the Still Water Immortal's Legacy" starts at d8. Through play, he uncovers more of the legacy, stepping it to d10. The GM rules it's now central to his identity — it becomes a Distinction: "Heir to the Still Water Legacy d10" with an SFX: "When you cultivate using the Still Water method, step up your qi_reserves for the scene."

## Zones

**Zones** are sub-locations within a parent location, each with their own trait set. Inspired by Fate.

A location's zones represent distinct spatial regions — rooms in a building, areas in a valley, districts in a city. Zones inherit their parent location's traits and add zone-specific traits.

```yaml
type: location
name: "Valley of Ascension"
universe: three_realms
traits:
  qi_density: d12
  isolation: d12
zones:
  - name: "The Arrival Platform"
    traits:
      formation_stability: d10
      exposure: d8     # open to the sky, visible from afar

  - name: "Verdant Steps Sect Grounds"
    traits:
      defensive_formations: d8
      hospitality: d10  # the sect welcomes outsiders

  - name: "The Mistwood"
    traits:
      visibility: d4    # thick mist, hard to navigate
      spirit_activity: d10
```

### Zone Mechanics

- **Movement**: Moving between adjacent zones is a simplified test (Agility or relevant trait vs. zone traits like *visibility* or *obstacles*)
- **Zone traits as modifiers**: Zone traits add complication dice or bonus dice depending on the action. Firing a bow in the Mistwood (*visibility d4*) adds a d4 complication to the pool
- **Zone transitions**: Changing zones updates the background image with a transition effect (fade through mist, walk through a gate, etc.)
- **Parent inheritance**: A zone always inherits the parent location's traits. The Arrival Platform has *qi_density d12* automatically

## Troupe Play

> [!note] Detailed design
> The living design (spotlight model, support-cast ownership, roll-table generation,
> razmerit economy) lives in [[Troupe Play]]. This section is the RAW framing.

**Troupe play** is a session structure where players rotate between their main character and companion GMCs. Inspired by Ars Magica.

The persistent home is **Earth** — every main character originates there and carries a stake in it (see [[Projections and Transversal#The Earth-Bond]]). Rotation is **soft**: the GM gauges who hasn't been in the spotlight, and players can ask. A last-played **recency list** (ordered "who last played their main") surfaces who has been quiet, but it never forces rotation.

### The Scattering Effect

When a group consciousness-transverses to a new universe without razmerit stabilization, their arrival points **scatter**. Each player's main character materializes in a different zone or location within the target universe. They cannot immediately reunite — the scattering is a property of cheap transversal.

### Session Structure

Rather than running separate solo scenes, the group rotates spotlight:

1. **Scene 1**: Player A's cultivator wakes on the Arrival Platform. Players B and C play Elder Yun (a GMC) and a junior disciple (a GMC) who find them.
2. **Scene 2**: Player B's cultivator wakes in the Mistwood. Players A and C play a trapped hunter and a spirit beast.
3. **Scene 3**: Player C's cultivator wakes in the Verdant Steps Sect library. Players A and B play the librarian and a suspicious senior disciple.

Each scene advances that player's story using the other players as companions. The GM provides the situation; the players embody the world.

### GMC Templates

Companion GMCs are simplified entities — one Distinction, one trait set, maybe one SFX. They are not full characters. A GMC template:

```yaml
type: gmc
name: "Elder Yun"
distinction: "Kindly Guardian of the Arrival Platform d8"
traits:
  cultivation: d10
  perception: d8
sfx: "Offer Tea — when Elder Yun serves tea to a guest, both step up their next social roll"
```

GMCs do not have projections, razmerit balances, or complex trait sets. They exist for the scene and are controlled by whichever player is not in the spotlight.

Support cast comes in two tiers:

- **Companions** — authored, named, recurring GMCs (Elder Yun, a librarian, a hunter). They carry relationships and history.
- **Grogs** — disposable scene-filler, instantiated on demand from **archetype roll tables**: a roll-table entry is a batch of `gain` traits, so "instantiate" applies an entry's effects to a fresh GMC placed at the current location. A grog who recurs can be promoted to a companion by running it through a life path (see [[Character Growth]]).

### Reunification

As characters develop — finding transversal artifacts, building razmerit technology, or advancing cultivation to Core Formation — they can control their arrival points. At sufficient attunement strength or technology level, scattering stops and the party arrives together. Reunification is a mid-game milestone.

## Random Generation

When multiple options exist (techniques in a library, artifacts in a ruin, paths in a forest), the system supports both **player choice** and **weighted random generation**. The choice is always present; the randomizer is always available.

### Weighted Tables

Each generation table is a list of options with `random_weight`. Higher weight = more common. Weights are hardcoded per table.

```yaml
# Cultivation technique library — element weights
spirit_root_elements:
  - name: fire
    random_weight: 20
  - name: water
    random_weight: 20
  - name: wood
    random_weight: 20
  - name: metal
    random_weight: 20
  - name: earth
    random_weight: 20
  - name: lightning
    random_weight: 8
  - name: shadow
    random_weight: 5
  - name: void
    random_weight: 2
  - name: time
    random_weight: 1
```

The five basic elements (fire, water, wood, metal, earth) are equally common at weight 20 each. Exotic elements taper down. Void and time are vanishingly rare.

### Frontend Integration

When the player faces a choice (e.g., "which technique do you study from the library shelf?"), the UI presents:

1. The list of available options
2. A "Randomize" button that highlights one option based on weighted selection
3. The player can accept the random pick or choose manually

The randomization respects the `random_weight` field but never forces a choice — it's a suggestion, not a mandate.

### Backend Endpoints

A `/generate` endpoint accepts a table ID and returns a random result. The engine rolls internally and returns the selected option with its full data. The frontend can call this directly or implement its own randomization from pre-fetched table data.

---

## Next

- [[Core Mechanics]] — How rating types, sub-traits, and effect dice integrate with the core engine
- [[Dice Mechanics]] — Challenge pool rolling in both pipelines
- [[Entities and Traits]] — Conspyramid nodes, Entanglements, and GMC templates
- [[Setting and Narrative]] — Universe-specific Entanglement tables and faction conspyramids

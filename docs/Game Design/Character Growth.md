---
title: Character Growth
tags:
  - transversal
  - game-design
  - growth
  - advancement
  - entanglements
  - lifepath
aliases:
  - Growth
  - Advancement
  - Entanglements
status: canonical
---

# Character Growth

Character growth in Transversal is powered by three interconnected subsystems: the **life path system** (Traveller × Legends of the Wulin), **trait transfer** between entities, and **rated relationships** on the relationship graph.

## Design Principles

1. **One growth system, not two.** The life path system is the training mechanic. There is no separate "advancement challenge pool" on individual traits — terms in a life path are how traits improve.
2. **Growth always succeeds.** The Learn phase of a term always grants or steps up a trait. Risk is in the Survive and Event phases — complications, not failure-to-improve.
3. **Provenance matters.** Every trait carries a record of how it was acquired: which life path term, taught by whom, gifted by whom, taken from whom.
4. **Razmerit is the sole growth currency.** One pool fuels SFX, transversal, dice manipulation, and lifepath re-rolls.

---

## Life Paths (Lifepath)

### Overview

A **life path** is a structured narrative container — a sect, guild, career, or way of life in a specific universe. Each path is stored in the `life_paths` collection and defines a six-phase term loop. Terms can be taken during:

- **Character creation** — generating the morph-body's history
- **Downtime** — the player chooses to invest a cycle in a path
- **Narrative triggers** — the GM awards a term-equivalent when the story justifies it

### Discovery — How Paths Become Visible

Not all life paths are visible from the start. Paths can be gated behind locations, relationships, artifacts, and trait mastery — reflecting the xianxia pattern of finding a hidden valley, meeting an old master, inheriting a dao.

A LifePath has an optional `discovery` block. If absent, the path is always visible (Drifter, common paths). If present, **any one condition being met** makes the path discoverable. Once discovered, the path remains in the character's catalog permanently — you remember where the hidden valley is and who you met there. However, *taking a term* may still require conditions to be met (e.g., you must be at the sect's location to train there); the qualification phase enforces this separately.

**Discovery conditions:**

| Condition | Checks | Data accessed |
|-----------|--------|---------------|
| `at_location` | entity.current_location in [...] | `entities` doc, zero joins |
| `knows_entity` | entity.known_to ∩ [...] non-empty | `entities` doc, zero joins |
| `possesses_trait` | traitsetting with matching trait_id exists | `traitsettings` edge, indexed on entity_id |
| `has_trait_rating` | traitsetting matching trait_id AND dice ≥ threshold | `traitsettings` edge, indexed on entity_id |
| `has_relationship` | relationship edge between entity pairs exists | `relationships` edge, indexed on _from |

The discovery check is a single function with five branches, each a direct lookup or single-collection AQL query. All referenced IDs (trait IDs, entity IDs, location IDs) are validated at edit time — if a referenced entity is deleted later, the condition silently fails and the path stays hidden.

**Examples:**

```yaml
# Always visible — no discovery block
life_paths/lp-drifter-three-realms:
  name: "Rogue Cultivator"
  universe: three_realms
  # no discovery → always available

# Location-gated
life_paths/lp-verdant-disciple:
  name: "Verdant Steps Outer Disciple"
  universe: three_realms
  discovery:
    at_location: ["loc-valley-of-ascension"]

# Artifact-gated
life_paths/lp-still-water-heir:
  name: "Heir to the Still Water Legacy"
  universe: three_realms
  discovery:
    possesses_trait: ["trait-asset-jian"]

# Faction connection + trait mastery
life_paths/lp-elder-yun-disciple:
  name: "Elder Yun's Personal Disciple"
  universe: three_realms
  discovery:
    has_relationship: ["gmc-elder-yun"]
    has_trait_rating:
      "trait-3r-cultivation": "d10"
```

### Collection: `life_paths`

```
life_paths/
  _key: str              # "lp-{slug}"
  name: str              # e.g. "Verdant Steps Outer Disciple"
  universe: str          # e.g. "three_realms"
  description: str       # narrative flavor
  type: str              # "sect" | "guild" | "drifter" | "mercenary" | "trade" | "lineage"

  qualification:
    trait_id: str        # trait rolled for entry
    difficulty: DieType  # target for simplified roll
    must_be_at_location: str | null  # location entity ID required to take a term (null = anywhere)
    draft: str | null    # path _key to draft into on failure (null = must choose Drifter)

  discovery:             # null or absent → always visible; any one condition met → discovered
    at_location: [str]           # must be at one of these location entity IDs
    knows_entity: [str]          # one of these entity IDs must be in known_to
    possesses_trait: [str]       # must have a traitsetting for one of these trait IDs
    has_trait_rating: {str: DieType}  # trait_id → minimum die (e.g. "trait-cultivation": "d10")
    has_relationship: [str]      # must have a relationship edge to one of these entity IDs

  curriculum:
    - trait_id: str
      create_at: DieType         # rating if trait is new to the character
      step_up: bool              # if the character already has the trait, step up instead
      min_rank: int = 0          # rank required for this curriculum item

  survival:
    trait_ids: [str]                 # dice pool traits for the survival roll
    difficulty: DieType              # static difficulty (auto-rolled by the resolver)
    term_penalty_after: int = 4      # after N terms in this path, difficulty steps up
    mishaps: [{description, effect}] # what happens on failure

  events: [{description, effect, min_rank}]  # dN table (N = length of list)

  advancement:
    trait_ids: [str]
    difficulty: DieType
    ranks:
      - number: int
        name: str                    # e.g. "Inner Disciple"
        benefits: [{type, trait_id, create_at, step_up, ...}]

  muster_out:
    per_term_benefits: [{type, ...}]       # razmerit, asset traits, contacts
    at_ranks: {rank_number: [{type, ...}]} # extra benefits at specific ranks
```

### The Term Loop

Each term walks through six phases in sequence:

```
┌──────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Choose Path  │───▶│  Learn   │───▶│ Survive  │───▶│  Event   │───▶│ Advance  │───▶│  Mishap  │
└──────────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     ▲                                                                                   │
     │                                    Muster Out ◀───────────────────────────────────│
     │                                        │                                          │
     └────────────────────────────────────────┘ (take another term in same or new path)
```

#### Phase 1: Choose Path

**Prerequisite: the path must be discovered.** The player chooses from their catalog of known life paths (those in `discovered_life_paths` plus always-visible paths). Undiscovered paths are hidden.

**Location / condition gate for term eligibility:** even after discovery, some paths require the character to be in the right place. A `must_be_at_location` field on the path's qualification block enforces this:

```yaml
qualification:
  trait_id: "trait-cultivation"
  difficulty: "d4"
  must_be_at_location: "loc-valley-of-ascension"  # null → anywhere
  draft: "lp-drifter-three-realms"
```

If the character is not at that location, they cannot take a term — the path appears greyed out with a note: "Travel to the Valley of Ascension to train here."

**Qualification roll:**
- **First term in a new path**: roll qualification using the path's `qualification.trait_id` against `qualification.difficulty` (simplified pipeline).
- On **success**: enter the path.
- On **failure**: choose a different path, become a Drifter (always available, no qualification), or submit to the Draft (if the path has a `draft` target).
- Drifter paths have no qualification, weaker curriculum, no advancement ladder, but no obligations.
- **Razmerit spend**: a character may spend razmerit before rolling to step up their qualification die (1 razmerit per step, max +2 steps).

**Continuing a term:** characters already enrolled in a path skip the choose phase — they are locked in until they muster out. Switching paths is only possible between terms.

#### Phase 2: Learn

**Always succeeds.** The character gains one curriculum item from the path:

- **New trait**: if the character does not already have a `TraitSetting` for `trait_id`, create one at `create_at` rating with `source_type: "life_path_term"` and `source_life_path_id` pointing to the path.
- **Existing trait**: if the character already has the trait, step up its die (or add a die for resource pools).
- **Advanced curriculum**: items with `min_rank > 0` only become available once the character reaches that rank in this path.

The new or modified `TraitSetting` is tagged with provenance:
```yaml
source_type: "life_path_term"
source_life_path_id: "lp-verdant-disciple"
source_term_number: 2
```

#### Phase 3: Survive

The character rolls against the path's danger. Failure flags a mishap (resolved in Phase 6).

- **Character's pool**: assembled from the `survival.trait_ids` traits available in the current universe.
- **Opposition**: static difficulty at `survival.difficulty`, auto-rolled by the resolver as a single die.
- **Pipeline**: determined by pool size (simplified for 1–2 dice, pool for 3+).
- **Razmerit**: can be spent to add dice or step up dice before the roll.
- On **success**: no mishap. Continue to Event.
- On **failure**: flag a mishap; proceed to Event, then Phase 6 will resolve it.

#### Term Penalty (Aging / Accumulated Risk)

The more terms a character serves, the harder survival becomes. Two mechanisms stack:

1. **Per-path**: after `term_penalty_after` terms in a single path, the survival difficulty steps up by one die size for that path.
2. **Global**: the entity's `terms_served` counter. Every 7 total terms across all paths, all survival difficulties step up by one die size globally (representing age, accumulated enemies, cosmic wear).

A character with 10 terms served and 5 terms in one path would face `survival_difficulty` stepped up twice (once from per-path at 4, once from global at 7).

#### Phase 4: Event

Something interesting happens. Roll on the path's `events` list:

- The list has N entries. Roll a die with as many sides as the largest die ≤ N (a d10 for 11 entries, a d4 for 5 entries). Results > N become "special" — the GM narrates an unusual event.
- Events can:
  - Create a **contact** (relationship edge + GMC entity)
  - Grant an **asset trait** (a trait in the `assets` traitset)
  - Create or step up an **entanglement trait** (traits in the `entanglements` traitset)
  - Earn or lose **razmerit**
  - Create a **rival** or **enemy** (negative relationship + complication trait)
  - Unlock an **SFX** on an existing trait
  - Reveal **lore** or **knowledge** (step up or create a knowledge trait)
  - **Discover a new life path** — the event reveals a previously hidden path, adding it to `discovered_life_paths`
- Some events are gated by `min_rank` — higher ranks unlock juicier events.

#### Phase 5: Advance

The character attempts to rise in the life path:

- **Character's pool**: assembled from `advancement.trait_ids`.
- **Opposition**: static difficulty at `advancement.difficulty`, auto-rolled.
- On **success**: advance one rank. Gain the rank's benefits (new traits, SFX unlocks, access to advanced curriculum, bonus muster-out benefits).
- On **failure**: stay at current rank. The next advancement attempt in this path has its difficulty stepped up by one (cumulative until success resets it).

#### Phase 6: Mishap

If the survive roll failed, the mishap is resolved here. Roll on the path's `mishaps` table. Mishaps produce:

- **Complication traits** (negative traits in the `complications` traitset) — injuries, debts, enemies, curses
- **Razmerit loss**
- **Rank demotion**
- **Relationship edges** (a new enemy, a faction that wants you dead)
- In extreme cases, a **forced muster-out** (mishap muster-out resets rank to 0 if the character later returns)

Each mishap entry in the path's `mishaps` list has a `must_muster_out` flag and an `effect` block specifying the consequence (complication trait ID + die, razmerit loss amount, etc.). Mishap effects are applied immediately, and if `must_muster_out` is set, the character is forced into the Muster Out step.

After mishap resolution (or if no mishap was flagged), the player chooses: **Muster Out** (leave the path) or **take another term** in the same or a new path.

#### Muster Out

Between terms, a character may choose to muster out — leave the life path permanently (or at least indefinitely). Mustering out grants:

- **Per-term benefits** from `muster_out.per_term_benefits` — typically razmerit (1d6 per term), asset traits, or contacts. The total benefit scales with terms served in the path.
- **Rank bonuses** from `muster_out.at_ranks` — additional benefits for achieving specific ranks. An Inner Disciple (rank 2) might get a cultivation technique asset trait on top of per-term razmerit.

**Re-entry:**
- **Voluntary muster-out**: no re-entry penalty — the character can return to the path at their current rank in a later downtime.
- **Mishap muster-out** (forced out by a catastrophic survive failure): resets rank to 0. The character starts over from the bottom.

#### Drifter Paths

Every universe has a **Drifter** path that requires no qualification. Drifters have:

- A sparse curriculum (basic survival skills, street knowledge)
- Higher survival difficulty (no institutional protection)
- No advancement ladder (no ranks, no muster-out bonuses beyond per-term)
- Events weighted toward mishaps and hard luck
- A few unique benefits — drifters might stumble onto things careerists never see

### LotW Loresheets

A **loresheet** in Legends of the Wulin is a setting element the player buys into — a sect, a prophecy, a legendary weapon. Buying in costs Destiny and grants mechanical access.

In Transversal, **life paths are loresheets**. Entering a path is buying into that part of the world. The path's events and advancement unlock deeper access — secret techniques, hidden knowledge, faction connections. Even after mustering out, the character retains:

- The traits they learned
- The relationships they formed
- The entanglements that resulted
- Any SFX unlocked through the path

The path itself may remain as a trait in the `entanglements` trait set: "Former Inner Disciple of Verdant Steps d8" — carrying narrative permission to access sect resources, even if no longer a member.

### Entity Model Extensions

```python
class Entity(BaseModel):
    # ... existing fields ...

    # Life path tracking
    terms_served: int = 0                        # total terms across all paths
    current_life_path_id: Optional[str] = None   # _key of active path
    current_rank: int = 0                        # rank in current path
    life_history: list[LifeTerm] = Field(default_factory=list)
    drifter_terms: int = 0                       # terms spent as a drifter
    discovered_life_paths: list[str] = Field(default_factory=list)  # _keys of discovered paths

class LifeTerm(BaseModel):
    path_id: str
    path_name: str
    universe: str
    terms_served: int
    final_rank: int
    mustered_out: bool
    mishap_muster: bool = False   # true if forced out by mishap → re-entry at rank 0
```

---

## Trait Transfer — Teach / Gift / Take

Trait transfer is driven by flags on traits and traitsets, not by fixed procedural rules. A trait (or its parent traitset) declares whether it can be taught, gifted, or taken. The UI surfaces the appropriate button based on context: own sheet shows teach/gift, foreign sheet shows take.

### Flags on Traits and TraitSets

Two levels of declaration:

**On `TraitSet`** (broad default):
```yaml
traitset:
  name: "Assets"
  transfer_flags:
    teachable: false
    giftable: true
    takable: true
```
All traits in the set inherit the set's flags unless overridden.

**On `Trait`** (registry, per-trait override):
```yaml
trait:
  name: "The Jian of Still Waters"
  traitset_id: "ts-assets"
  transfer_flags:
    teachable: false    # you cannot teach someone to have the jian
    giftable: true      # you can hand it over
    takable: true       # it can be stolen
```
Per-trait flags override per-traitset flags. A trait with no flags inherits.

### UI Behavior

**Own character sheet** — for each trait with `teachable: true`:
- A "Teach" button appears. Clicking opens a target selector (who to teach). On confirm, the `teachTrait` mutation fires.

**Own character sheet** — for each trait with `giftable: true`:
- A "Gift" button appears. Clicking opens a target selector. On confirm, the `giftTrait` mutation fires.

**Foreign character sheet** — for each trait on the viewed character with `takable: true`:
- A "Take" button appears. Clicking opens a method selector (stealth, combat, social, technical). On confirm, the `takeTrait` mutation fires — a contest against the victim.

### Teach

A character with a trait at rating X teaches it to a student at reduced rating. Teaching does not diminish the teacher's own trait.

| Teacher rating | Student receives |
|----------------|-----------------|
| d4 | d4 |
| d6 | d4 |
| d8 | d6 |
| d10 | d6 |
| d12 | d8 |

The student's new `TraitSetting` carries `source_type: "taught"`, `source_entity_id`, and `source_trait_setting_id`. The student advances the trait normally through life path terms.

Teacher pays 1 razmerit. Teacher and student must be in the same location (or communicating through established narrative means — the system does not enforce this, it's a narrative constraint).

### Gift

The `TraitSetting.entity_id` changes from giver to recipient. Tagged with `source_type: "gifted"` and `source_entity_id`. A `relationships` edge of type `gifted` connects giver and recipient.

Both characters must be in the same location. Giver voluntarily initiates.

### Take

Contested transfer. Covers theft, confiscation, salvage, and hostile acquisition.

1. Taker selects a method (stealth, combat, social, technical)
2. Taker assembles pool from method-relevant traits; victim assembles opposing pool
3. Contest resolution determines outcome
4. On success: trait transfers, tagged `source_type: "taken"`, `source_entity_id`, `stolen: true`
5. On failure: victim may gain awareness. A `suspects` or `hostile_to` relationship edge may be created.

A `stolen` trait is "hot" — openly using it in certain locations or universes may trigger consequences (faction hostility, legal trouble, bounty hunters). The system tracks the flag; the GM and narrative enforce the consequences.

### Transfer Flags (Trait and TraitSet Registry)

```python
class TransferFlags(BaseModel):
    """Declares whether traits in a set or a specific trait can be transferred."""
    teachable: bool = False
    giftable: bool = False
    takable: bool = False

# On TraitSet (broad default for all traits in the set):
class TraitSet(BaseModel):
    # ... existing fields ...
    transfer_flags: Optional[TransferFlags] = None

# On Trait (per-trait override of the set default):
class Trait(BaseModel):
    # ... existing fields ...
    transfer_flags: Optional[TransferFlags] = None
```
Resolution: a trait's effective flags are its own `transfer_flags` if set, otherwise the parent traitset's `transfer_flags` if set, otherwise all `false`.

### TraitSetting Provenance Extensions

```python
class TraitSetting(BaseModel):
    # ... existing fields ...

    # Provenance — how this trait was acquired
    source_type: Optional[str] = None
        # "taught" | "gifted" | "taken" | "life_path_term" | "event" | null
    source_entity_id: Optional[str] = None
        # who taught/gifted it, or who it was taken from
    source_trait_setting_id: Optional[str] = None
        # the original TraitSetting this was derived from (teach)
    source_life_path_id: Optional[str] = None
        # which life path generated this (life_path_term)
    source_term_number: Optional[int] = None
        # which term in that path (life_path_term)
    stolen: bool = False
        # trait was taken — may have narrative consequences
```

---

## Relationship Ratings

Relationships in Transversal can carry mechanical weight — die ratings that flow into the dice pool when relevant.

### How It Works

A relationship edge (`edge:{from}:{to}:{type}`) can have `TraitSetting` edges attached to it. The `_from` field of `TraitSetting` accepts both `entities/{id}` and `relationships/{edge_key}`, following the model from the old app.

### Registry: `relations` Traitset

A new traitset `ts-relations` holds the registry of relationship trait types:

| Trait ID | Name | Default Rating | Description |
|----------|------|---------------|-------------|
| `trait-relation-trust` | Trust | d6 | "I trust them" — adds to cooperative pools |
| `trait-relation-debt` | Debt | d4 | Resource pool — razmerit or favors owed |
| `trait-relation-rivalry` | Rivalry | d6 | "We push each other" — adds to opposed pools |
| `trait-relation-loyalty` | Loyalty | d6 | "I would die for them" — adds to protective pools |
| `trait-relation-fear` | Fear | d6 | Negative — opponent uses it against you |
| `trait-relation-love` | Love | d6 | Adds to pools involving that person |
| `trait-relation-duty` | Duty | d6 | "I owe them my service" — obligation |

### Dice Pool Integration

When assembling a pool and the action involves a related entity, the relationship's rated traits become available:

- Kael attacking his rival Wei Zhao: can add `rivalry d6` to his attack pool
- Mira trying to persuade Kael: Mira can add Kael's `trust d8` toward her to her persuasion pool
- Kael defending Mira from an attack: Kael can add `loyalty d10` to his defense pool

The resolver already assembles pools from `get_effective_traitsettings(entity_id, universe)`. To include relationship traits, the assembly step also queries relationship edges where either entity is involved and includes any `TraitSetting` edges attached to those relationships.

### Creation Flow

1. Player opens foreign character sheet
2. Clicks the relationship button (existing UI)
3. UI offers: "Create relationship" → type (trust, rivalry, debt, etc.) → initial rating (d4–d8)
4. System creates:
   - A `relationships` edge: `edge:{viewer}:{target}:{relation}`
   - A `TraitSetting` edge: `_from = relationships/{edge_key}`, `_to = traits/{relation_trait_id}`, with the chosen dice
5. Trait appears on both characters' sheets when viewing the relationship

---

## API Surface

### Life Path Queries

```graphql
lifePaths(universe: String!, entityId: ID): [LifePath!]!
lifePath(id: ID!): LifePath!

type LifePath {
  id: ID!
  name: String!
  universe: String!
  description: String!
  type: String!
  discovered: Boolean!             # has the entity discovered this path?
  qualification: QualificationInfo
  curriculum: [CurriculumItem!]!
  survival: SurvivalInfo
  events: [EventItem!]!
  advancement: AdvancementInfo
  musterOut: MusterOutInfo
  canTakeTerm: Boolean!            # are current conditions met for taking a term?
  termBlockReason: String           # null if canTakeTerm, otherwise explains why not
}
```
When `entityId` is provided, the resolver runs discovery checks and returns only discovered paths + always-visible paths, annotated with `discovered` and `canTakeTerm`.

### Term Execution

```graphql
takeTerm(
  entityId: ID!
  lifePathId: ID!
  razmeritSpent: Int = 0
): TermResult!

type TermResult {
  # Per-phase results
  qualification: QualificationResult       # null if continuing in same path
  learn: LearnResult!
  survive: SurviveResult!
  event: EventResult!
  advance: AdvanceResult!

  # Aggregate changes
  newTraitSettings: [TraitSetting!]!
  modifiedTraitSettings: [TraitSetting!]!
  newRelationships: [Relationship!]!
  newEntities: [Entity!]!                   # contacts, GMCs created by events
  razmeritChange: Int!
  termNumber: Int!                          # which term this was for the entity
}

type LearnResult {
  traitGained: TraitSetting!
  wasSteppedUp: Boolean!
}

type SurviveResult {
  success: Boolean!
  rollResult: RollResult!
  mishap: MishapResult              # null if success
}

type MishapResult {
  description: String!
  complicationTrait: TraitSetting   # null if other mishap type
  razmeritLost: Int
  relationshipCreated: Relationship
}

type EventResult {
  eventIndex: Int!
  description: String!
  effects: [EffectDescription!]!
  discoveredLifePath: LifePath      # null unless this event reveals a new path
}

type AdvanceResult {
  success: Boolean!
  newRank: Int
  rankName: String
  benefits: [EffectDescription!]!
  nextDifficulty: DieType             # difficulty for next advancement attempt
}

type QualificationResult {
  success: Boolean!
  drafted: Boolean                    # true if drafted into fallback path
  draftedPathId: String
  locationBlocked: Boolean            # true if must_be_at_location prevents entry
}
```

### Muster Out

```graphql
musterOut(entityId: ID!): MusterOutResult!

type MusterOutResult {
  pathId: String!
  pathName: String!
  termsServed: Int!
  finalRank: Int!
  mishapMuster: Boolean!
  benefits: [EffectDescription!]!
  razmeritGained: Int!
  newTraitSettings: [TraitSetting!]!
  entity: Entity!                     # updated terms_served, life_history, etc.
}
```

### Teach / Gift / Take

```graphql
teachTrait(
  teacherId: ID!
  studentId: ID!
  traitSettingId: ID!
  razmeritSpent: Int = 0
): TeachResult!

type TeachResult {
  studentTraitSetting: TraitSetting!
  razmeritCost: Int!
}

giftTrait(
  giverId: ID!
  recipientId: ID!
  traitSettingId: ID!
): GiftResult!

type GiftResult {
  transferredTrait: TraitSetting!      # now owned by recipient
  relationshipCreated: Relationship    # "gifted" edge
}

takeTrait(
  takerId: ID!
  victimId: ID!
  traitSettingId: ID!
  method: String!
  razmeritSpent: Int = 0
): TakeResult!

type TakeResult {
  success: Boolean!
  contestResult: ContestResult!
  transferredTrait: TraitSetting       # null if failed
  stolen: Boolean!
}
```

---

## Implementation Order

The recommended build sequence follows dependency edges:

| Step | What | Depends On |
|------|------|------------|
| 1 | `life_paths` collection + domain model (LifePath, DiscoveryBlock, LifeTerm) | Nothing |
| 2 | `Entity` model extensions (terms_served, life_history, discovered_life_paths, current_life_path_id) | Nothing |
| 3 | Discovery check function — 5-condition check against entity state | 1, 2 |
| 4 | `TransferFlags` on `Trait` and `TraitSet` + `TraitSetting` provenance extensions | Nothing |
| 5 | `takeTerm` mutation — bare loop with qualification + learn + location gate | 1, 2, 3 |
| 6 | Survive phase — mishap tables, term penalties, complication traits | 5 |
| 7 | Event phase — event tables, random selection, effect application (incl. path discovery) | 5 |
| 8 | Advance phase — ranks, benefits, difficulty tracking | 5 |
| 9 | Muster out — benefits calculation, life_history recording (voluntary vs. mishap) | 5, 8 |
| 10 | `teachTrait` mutation — target selector, reduced-rating transfer | 4 |
| 11 | `giftTrait` mutation — entity_id reassignment | 4 |
| 12 | `takeTrait` mutation — method selector + contest resolution | 4 |
| 13 | `traitsettings._from` extended to accept relationship edge keys | Nothing |
| 14 | `relations` traitset + relationship trait creation in UI | 13 |
| 15 | Dice pool assembly includes relationship traits | 13, 14 |
| 16 | Transfer buttons on CharacterSheet (own: teach/gift, foreign: take) | 4, 10, 11, 12 |
| 17 | `takeTerm` — Drifter path (no qualification, no advancement) | 5 |
| 18 | Term wizard UI — step-wise Vue component flow | 5, 6, 7, 8 |

---

## Resolved Design Decisions

1. **Character creation term count**: Default 3 terms for a starting morph-body, with push-your-luck — the player can take additional terms, but each extra term increases global term penalty immediately. GMs can override the default per campaign.

2. **Muster-out re-entry**: Voluntary muster-out has no re-entry penalty — the character can return to the path at their current rank in a later downtime. A mishap-based muster-out (forced out by a catastrophic survive failure) resets rank to 0. The path remembers the character; the character starts over from the bottom.

3. **Drifter paths**: Per-universe. A Three Realms Drifter (rogue cultivator) has different curriculum, events, and survival traits than an Earth Drifter (homeless veteran). Each universe seeds at least one Drifter path as the always-available fallback.

4. **Life path content authoring**: Agent-assisted via MCP tools. Path creation (event tables, mishap tables, curriculum, discovery conditions) is a content-authoring workflow — agents can generate, validate, and seed life paths based on universe lore and GM direction. Separate discussion from implementation.

5. **Term UI visualization**: Wizard-like step-wise flow. Each phase is a Vue component that follows the previous — only relevant information and options are shown at each step. The player sees qualification results before choosing to commit razmerit to survival, sees the event outcome before deciding whether to push for advancement, etc. Matches the existing dice roller animation patterns.

6. **Discovery persistence**: Once a path is discovered, it remains in the character's catalog permanently (`discovered_life_paths` on the entity). Taking a term may still require the character to meet location/condition gates — the qualification phase has a `must_be_at_location` field separate from discovery. Discovery is about *knowing* the path exists; qualification + location gates are about *accessing* it.

## Open Design Decisions

1. **Transfer flag granularity**: Should `teachable`/`giftable`/`takable` be booleans or support conditional logic? A trait might be giftable only to faction members, or takable only with a specific SFX. Start simple (booleans) and condition support can be added later if needed.

2. **Take method resolution**: When taking a trait, how is the victim's opposing pool assembled? Automatic (best relevant trait) or chosen by the victim's player (if present)? Auto-resolution keeps it fast for downtime; player-chosen is fairer in live play. Default to auto with an opt-out for contested live scenes.

---

## References

- [[Core Mechanics]] — Trait sets, rating types, dice pools
- [[Entities and Traits]] — Entity model, trait registry, trait settings
- [[Dice Mechanics]] — Dual-pipeline resolution, simplified and pool pipelines
- [[SFX and Effects]] — Effect types, trigger system
- [[Inspired Mechanics]] — Original Entanglements design (superseded by this document)
- [[Data Model]] — Collection schemas, edge patterns
- [[API Contract]] — GraphQL schema conventions

---
title: SFX Reference
date: 2026-10-16
tags:
  - transversal
  - manual
  - sfx
  - effects
  - gm
  - reference
aliases:
  - SFX Reference
  - Effect Reference
  - Trigger Reference
  - Condition Reference
  - Effect Action Reference
status: draft
---

# SFX Reference

The vocabulary you choose from when authoring an SFX: every trigger, condition, source, target-path step and effect action the editor offers, and what each one does. [[SFX Authoring]] teaches how to put them together — start there if this is your first rule. This page is the lookup you keep open beside it.

**These tables are generated from the editor's own declarations**, so they cannot drift from what the picker offers in front of you. If a table here ever disagrees with the editor, **the editor is right and this page is stale.**

Notes that apply to the whole page:

- **`{name}` in a field is a variable** — a value the rule named, or one the trigger or source hands it. The "Variables it declares" column below lists what a trigger puts in scope.
- **A backticked value is the stored key.** You never type it; it is here so a card line or a report can be read back to the editor's word for the same thing.

## Triggers

What starts the rule. The card line quotes the **Fires when** phrase; Group is the heading the picker shows.

| Trigger | Label | Fires when | Group | Variables it declares |
|---|---|---|---|---|
| `manual` | Manual (player activates) | Activated | Manual | — |
| `menu` | Post-roll menu (player picks) | Picked from the post-roll menu | Manual | — |
| `on_roll` | On Roll | Whenever a roll happens | Dice pool | `{margin}`, `{purpose}` |
| `on_result` | On Result | When a roll is resolved | Dice pool | `{effect_die}`, `{total}`, `{margin}`, `{purpose}` |
| `on_complication` | On Complication (hitch) | When a complication is rolled | Dice pool | — |
| `on_botch` | On Botch | When you botch | Dice pool | — |
| `on_success` | On Success | When a roll succeeds | Dice pool | `{margin}`, `{purpose}` |
| `on_failure` | On Failure | When a roll fails | Dice pool | `{margin}`, `{purpose}` |
| `on_contest_win` | On Contest Win | When you win a contest | Dice pool | `{contest_entity_opponent}`, `{contest_projection_opponent}`, `{effect_die}`, `{own_effect_die}`, `{opponent_effect_die}`, `{margin}`, `{high_stakes}`, `{taken_out}` |
| `on_contest_loss` | On Contest Loss | When you lose a contest | Dice pool | `{contest_entity_opponent}`, `{contest_projection_opponent}`, `{effect_die}`, `{own_effect_die}`, `{opponent_effect_die}`, `{margin}`, `{high_stakes}`, `{taken_out}` |
| `on_give_in` | On Give In | When you give in | Dice pool | `{contest_entity_opponent}`, `{gave_in}` |
| `on_push` | On Push | When you push | Dice pool | `{pushed}` |
| `on_taken_out` | On Taken Out | When you are taken out | Dice pool | `{contest_entity_opponent}`, `{taken_out}` |
| `on_prevent_taken_out` | On Prevent Taken Out | When you would be taken out | Dice pool | `{effect_die}`, `{prevented}` |
| `on_pool_change` | On Pool Change | Whenever your dice pool changes | Dice pool | `{dice_pool}`, `{contest_entity_opponent}` |
| `on_pool_add` | On Added To Pool | When this trait is added to your dice pool | Dice pool | `{dice_pool}`, `{contest_entity_opponent}` |
| `on_location_change` | On Location Change | When you arrive somewhere | Auto-fire | `{from_location}`, `{to_location}`, `{universe}`, `{arrival_kind}` |
| `on_trait_change` | On Trait Change | When a trait changes | Auto-fire | `{trait}`, `{traitset}`, `{trait_setting}` |
| `on_trait_learn` | On Trait Learned | When a trait is learned | Auto-fire | `{trait}`, `{trait_setting}`, `{owner}`, `{learner}` |
| `on_trait_offered` | On Trait Offered | When a trait is offered | Auto-fire | `{trait}`, `{trait_setting}`, `{owner}`, `{opponent}`, `{newly_revealed}` |
| `on_relationship_create` | On Relationship Create | When a relationship is created | Auto-fire | `{target_entity}`, `{relationship_type}` |
| `on_character_create` | On Character Created | When a character is created | Auto-fire | `{entity_created}` |
| `on_projection_create` | On Projection Created | When a projection is created | Auto-fire | `{entity_created}`, `{projection_created}`, `{universe}` |
| `on_set` | On Set | When a die is set | Dice pool | `{effect_die}`, `{total}`, `{margin}`, `{purpose}` |
| `on_beat` | On Beat Advance | At the end of each beat | Auto-fire | — |
| `on_scene` | On Scene Advance | At the end of each scene | Auto-fire | — |
| `on_session_start` | On Session Start | At the start of each session | Auto-fire | — |
| `on_session_end` | On Session End | At the end of each session | Auto-fire | — |
| `on_challenge_completed` | On Challenge Completed | When a challenge is completed | Auto-fire | `{entity_id}`, `{trait_setting_id}`, `{trait_id}`, `{capacity}` |
| `assumed` | On Assume (took control) | When someone takes control of this entity | Auto-fire | — |

_Count: 30._

- `on_pool_add` requires a **traitsetting** source.
- `on_location_change` is an arrival trigger (`fires_on_arrival`).


## Conditions

Gates that must all pass for the rule to fire. **Target** and **Value** are the inputs the editor asks for; **Needs context** is the fire-time key the condition reads, which is why some are greyed out at a boundary.

| Condition | Key | Group | Target | Value | Operators | Needs context |
|---|---|---|---|---|---|---|
| **Always** | `ALWAYS` | No gate | `` | — | — | — |
| **At location** | `AT_LOCATION` | Character state | location `location id` | — | — | — |
| **Has trait** | `HAS_TRAIT` | Character state | trait `trait id` | — | — | — |
| **Has effective trait** | `HAS_EFFECTIVE_TRAIT` | Character state | trait `trait id` | — | — | — |
| **Has trait in traitset** | `HAS_TRAIT_IN_TRAITSET` | Character state | traitset `traitset id` | — | — | — |
| **Has relationship** | `HAS_RELATIONSHIP` | Character state | entity `entity id` | — | — | — |
| **Trait rating** | `TRAIT_RATING` | Character state | trait `trait id` | die | `<`, `<=`, `==`, `!=`, `>=`, `>` | — |
| **Has razmerit** | `HAS_RAZMERIT` | Character state | `` | number | `<`, `<=`, `==`, `!=`, `>=`, `>` | — |
| **Entity type** | `ENTITY_TYPE` | Character state | character / gmc / asset | — | — | — |
| **User role** | `USER_ROLE` | The moment it fires | player / architect | — | — | — |
| **Unplaced (no location)** | `UNPLACED` | Character state | `` | — | — | — |
| **In a contest as the challenger** | `CONTEST_CHALLENGER` | Character state | `` | — | — | — |
| **In a contest as the defendant** | `CONTEST_DEFENDANT` | Character state | `` | — | — | — |
| **In universe** | `IN_UNIVERSE` | Character state | universe `universe key` | — | — | — |
| **Phase** | `PHASE` | The moment it fires | adding / rolling / picking / resolved | — | — | `phase` |
| **Contest outcome** | `CONTEST_OUTCOME` | The moment it fires | player / opponent / give_in | — | — | `contest_winner`, `gave_in` |
| **Hitch** | `HITCH` | The moment it fires | `` | — | — | `hitch` |
| **High stakes** | `HIGH_STAKES` | The moment it fires | high / low | — | — | `high_stakes` |
| **Session** | `SESSION` | The moment it fires | active / inactive | — | — | — |
| **Arrival kind** | `ARRIVAL_KIND` | The moment it fires | transversal / hierarchy / move / effect | — | — | `arrival_kind` |
| **Roll tier** | `ROLL_TIER` | The moment it fires | `` | tier | `>=`, `>`, `==`, `!=`, `<=`, `<` | `tier` |
| **Roll purpose** | `ROLL_PURPOSE` | The moment it fires | `tag` | — | `contains`, `not contains` | `purpose` |
| **Margin** | `MARGIN` | The moment it fires | `` | number | `<`, `<=`, `==`, `!=`, `>=`, `>` | `margin` |
| **Test outcome** | `TEST_OUTCOME` | The moment it fires | success / fail | — | — | `tier` |
| **Source rating** | `SOURCE_RATING` | This rule | `` | die | `<`, `<=`, `==`, `!=`, `>=`, `>` | — |
| **Targeting path** | `TARGET_PATH` | This rule | path builder | — | — | — |
| **Narrative** | `NARRATIVE` | No gate | `` | — | — | — |

_Count: 27._

**Trait rating** and **Source rating** also take a **mode**, which is how a rating gate reads a *pool* rather than one die: **any die** (the default), **every die**, or **a number of dice**. The default asks *"is some die a d8"*, so `== d8` is true of a `1d8` trait and a `2d8` one alike — the **a number of dice** mode is the only way to say *exactly two d8*, and the number then compares with the operator you picked. That is what lets two rungs of a ladder be gated apart ([[B317]]); most gates want the default.


## Source kinds

What kind of thing may carry the rule. This is the panel's **Lives on** field, and it decides which `{variables}` the rest of the form can use.

| Source | Resolves to | Variable | Owner surfaces |
|---|---|---|---|
| **Trait setting** (`trait_setting`) | `traitsetting` | `{trait_setting}` | trait_instance, trait |
| **Trait set setting** (`traitset_setting`) | `traitsetsetting` | `{traitset_setting}` | trait_set |
| **Entity** (`entity`) | `entity` | `{entity}` | entity |
| **Location** (`location`) | `location` | `{location}` | location |
| **Projection** (`projection`) | `projection` | `{projection}` | projection |
| **Faction** (`faction`) | `entity` | `{faction}` | entity |
| **Table** (`table`) | nothing (non-resolving) | — | table |
| **GM** (`gm`) | nothing (non-resolving) | — | gm |

_Count: 8._


## Target paths

A path is an ordered pipeline of steps that resolves to something. The wizard only offers steps that are legal from where the path currently stands, so the tables below are what it draws from.


### Step kinds

| Step | Editor label | What it does | Fields |
|---|---|---|---|
| `select` | **Select** | Seed the path from a collection, the rule's `source`, or a named variable. Only the first step selects. | `collection`, `variable`, `output` |
| `literal` | **Pick one thing** | Name one specific thing by id — a pin, not a query. | `element`, `value`, `output` |
| `filter` | **Filter** | Keep the items whose field matches. A field only offers the operators it can answer. | `field`, `operator`, `value`, `output` |
| `navigate` | **Navigate** | Hop an edge to something related (a trait instance to its owner, an entity to its location). `dedup` collapses repeats. | `edge`, `dedup`, `output` |
| `aggregate` | **Aggregate** | Collapse the collection to one value or element — a count, a random sample, the highest or lowest, an average, or a die's tier. | `fn`, `field`, `count`, `output` |
| `choose` | **Choose** | Ask the player to pick from the collection. Never offered inside a condition: there is nobody to answer. | `count`, `output` |
| `evaluate` | **Evaluate** | A terminal true/false test — does anything exist, or does a count or field compare to a value. This is how a condition path ends. | `operator`, `field`, `value` |

**Filter operators** (the `filter` step):


`==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not in`, `contains`, `not contains`

`==` / `!=` / `>` / `>=` / `<` / `<=` compare a single value; the four ordering ones are offered only for numeric, die and date fields. `in` / `not in` compare against **several values at once** — *is one of them* / *is none of them*. `contains` / `not contains` are for a field that **is itself a list** (`tags`, `universes`, `known_to`): *has this among its entries* / *has none of them*.

The two directions are not interchangeable, and choosing the wrong one **fails silently**: a list field is matched with `contains`, never with `==` or `in`. The wizard only offers the operators a field can actually answer, which is why the choice is usually made for you. A flat `{name}` that holds several values counts as a list for `in` / `not in` — but `==` still compares only its first value.

**Evaluate operators** (the `evaluate` step):

`exists`, `==`, `!=`, `>`, `>=`, `<`, `<=`

### Seeds a `select` step may start from

| Seed | What it is | Element |
|---|---|---|
| `self` | The acting entity | `entity` |
| `rolled_dice` | Dice in the current roll | `die` |
| `opposing_dice` | Dice in the opposing pool | `die` |
| `added_dice` | Dice just added to the pool | `die` |
| `occupants` | Entities at the current location | `entity` |
| `locations` | All locations | `location` |
| `entities` | All entities | `entity` |
| `traits` | Traits in the registry | `trait` |
| `universes` | All universes | `universe` |
| `self_traitsettings` | The acting entity's trait instances | `traitsetting` |
| `self_traitsetsettings` | The acting entity's trait set instances | `traitsetsetting` |
| `sfxs` | Rules in the registry | `sfx` |
| `traitsets` | Trait sets in the registry | `traitset` |
| `life_paths` | Life paths | `life_path` |
| `roll_tables` | Roll tables | `roll_table` |
| `die_types` | Die sizes | `rating_die` |

_Count: 16._

### Navigation edges (`navigate`)

| From | Step (`navigate`) | To | Cardinality | Label |
|---|---|---|---|---|
| `die` | `traitsetting` | traitsetting | one | Owning trait instance |
| `die` | `owner` | entity | one | Pool owner |
| `traitsetting` | `rating_dice` | rating_die | many | Rating dice |
| `rating_die` | `traitsetting` | traitsetting | one | Trait instance |
| `traitsetting` | `capacity_dice` | capacity_die | many | Capacity dice |
| `capacity_die` | `traitsetting` | traitsetting | one | Challenge |
| `traitsetting` | `trait` | trait | one | Registry trait |
| `traitsetting` | `traitset` | traitset | one | Trait set |
| `traitsetting` | `entity` | entity | one | Owning entity |
| `traitsetting` | `projection` | projection | one | Owning projection |
| `traitsetting` | `traitsetsetting` | traitsetsetting | one | Trait set instance |
| `entity` | `traitsetsettings` | traitsetsetting | many | Trait set instances |
| `traitset` | `traitsetsettings` | traitsetsetting | many | Trait set instances |
| `traitsetsetting` | `entity` | entity | one | Owning entity |
| `traitsetsetting` | `traitsettings` | traitsetting | many | Trait instances |
| `traitsetting` | `parent` | traitsetting | one | Owning container |
| `traitsetting` | `subtraits` | traitsetting | many | Sub-traits |
| `entity` | `location` | location | one | Current location |
| `entity` | `universe` | universe | one | Current universe |
| `entity` | `projection` | projection | one | Current projection |
| `entity` | `projections` | projection | many | All projections |
| `entity` | `traitsettings` | traitsetting | many | Trait instances |
| `projection` | `entity` | entity | one | Owning entity |
| `projection` | `location` | location | one | Current location |
| `projection` | `universe` | universe | one | Current universe |
| `entity` | `relationships` | relationship | many | Relationships |
| `relationship` | `traitsettings` | traitsetting | many | Trait instances |
| `relationship` | `entity` | entity | one | Holding entity |
| `relationship` | `contact` | entity | one | Other party |
| `traitsetting` | `relationship` | relationship | one | Owning relationship |
| `location` | `universe` | universe | one | Universe |
| `location` | `occupants` | entity | many | Occupants |
| `universe` | `locations` | location | many | Locations |
| `pool` | `contest` | contest | one | Contest |
| `entity` | `contest` | contest | one | Contest in |
| `location` | `contests` | contest | many | Contests |
| `contest` | `entities` | entity | many | Participants |
| `contest` | `pools` | pool | many | Their dice pools |
| `entity` | `pool` | pool | one | Dice pool |
| `location` | `difficulty_pool` | pool | one | GM difficulty pool |
| `pool` | `dice` | die | many | Dice in the pool |
| `traitset` | `traits` | trait | many | Traits |
| `trait` | `traitset` | traitset | one | Trait set |
| `trait` | `universes` | universe | many | Universes |
| `trait` | `traitsettings` | traitsetting | many | Trait instances |
| `location` | `subtree` | location | many | Sub-locations |
| `location` | `projections` | projection | many | Projections here |
| `entity` | `members` | entity | many | Members |
| `entity` | `factions` | entity | many | Factions |
| `entity` | `life_paths` | life_path | many | Suitable life paths |
| `life_path` | `roll_tables` | roll_table | many | Roll tables |
| `roll_table` | `life_path` | life_path | one | Life path |
| `entity` | `scheduled_events` | scheduled_event | many | Pending timers |
| `traitsetting` | `sfxs` | sfx | many | Rules |
| `traitsetsetting` | `sfxs` | sfx | many | Rules |
| `entity` | `sfxs` | sfx | many | Rules |
| `location` | `sfxs` | sfx | many | Rules |
| `projection` | `sfxs` | sfx | many | Rules |
| `trait` | `possible_sfxs` | sfx | many | Rules it offers |
| `trait` | `default_sfxs` | sfx | many | Rules it grants |

_Count: 60._

> [!note] Rules are now reachable, not only searchable ([[B327]])
> `select sfxs` seeds the whole registry, so a path could always **search** every rule. What it could not do was **walk to one** — no edge ended on `sfx`. Now "the rule this trait carries" (`instance → sfxs`), "the rules this trait offers / grants" (`trait → possible_sfxs` / `default_sfxs`), and "this entity's, place's or body's rules" are all hops.

### Fields a `filter` may compare

*Where **Operators** says "default by type": a comparable field — `int`, `number`, `die`, `datetime` — offers `== != > >= < <= in not in`; every other field offers `== != in not in`. A field listed with explicit operators offers only those.*

| Element | Field | Type | Values / options | Operators |
|---|---|---|---|---|
| `die` | `result` | int | — | default by type |
| `die` | `rating` | die | `d4`, `d6`, `d8`, `d10`, `d12` | default by type |
| `die` | `effect_die` | die | `d4`, `d6`, `d8`, `d10`, `d12` | default by type |
| `die` | `tier` | string | `fail`, `marginal`, `success`, `exceptional`, `perfect` | default by type |
| `die` | `role` | string | — | default by type |
| `die` | `source_kind` | string | `trait`, `difficulty`, `manual`, `entity`, `projection`, `location`, `resource`, `challenge` | default by type |
| `die` | `ts_id` | string | — | default by type |
| `die` | `armed_sfx_ids` | string | — | `contains`, `==`, `!=` |
| `rating_die` | `rating` | die | `d4`, `d6`, `d8`, `d10`, `d12` | default by type |
| `rating_die` | `index` | int | — | default by type |
| `rating_die` | `ts_id` | string | refs `traitsetting` | default by type |
| `capacity_die` | `rating` | die | `d4`, `d6`, `d8`, `d10`, `d12` | default by type |
| `capacity_die` | `index` | int | — | default by type |
| `capacity_die` | `ts_id` | string | refs `traitsetting` | default by type |
| `traitsetting` | `id` | string | refs `traitsetting` | default by type |
| `traitsetting` | `rating` | die | `d4`, `d6`, `d8`, `d10`, `d12` | default by type |
| `traitsetting` | `rating_type` | string | `static`, `resource`, `challenge`, `empty` | default by type |
| `traitsetting` | `polarity` | string | `positive`, `negative` | default by type |
| `traitsetting` | `trait_id` | string | refs `trait` | default by type |
| `traitsetting` | `traitset_id` | string | refs `traitset` | default by type |
| `traitsetting` | `entity_id` | string | refs `entity` | default by type |
| `traitsetting` | `projection_id` | string | refs `projection` | default by type |
| `traitsetting` | `from_type` | string | `entity`, `projection` | default by type |
| `traitsetting` | `enabled` | boolean | — | default by type |
| `traitsetting` | `order` | int | — | default by type |
| `traitsetting` | `capacity` | die | — | `contains`, `==`, `!=` |
| `traitsetting` | `tags` | string | — | `contains`, `==`, `!=` |
| `traitsetting` | `universes` | string | — | `contains`, `==`, `!=` |
| `contest` | `location_id` | string | refs `location` | default by type |
| `contest` | `entity_id` | string | refs `entity` | default by type |
| `contest` | `opposition_id` | string | refs `entity` | default by type |
| `contest` | `initiative` | string | refs `entity` | default by type |
| `contest` | `pending` | string | refs `entity` | default by type |
| `contest` | `stakes` | string | `high`, `low` | default by type |
| `contest` | `kind` | string | `test`, `contest` | default by type |
| `contest` | `phase` | string | `adding`, `rolling`, `picking`, `resolved` | default by type |
| `traitsetsetting` | `entity_id` | string | refs `entity` | default by type |
| `traitsetsetting` | `traitset_id` | string | refs `traitset` | default by type |
| `traitsetsetting` | `projection_id` | string | refs `projection` | default by type |
| `traitsetsetting` | `from_type` | string | `entity`, `projection` | default by type |
| `traitsetsetting` | `limit` | int | — | default by type |
| `traitsetsetting` | `sfx_ids` | string | refs `sfx` | `contains`, `==`, `!=` |
| `trait` | `id` | string | refs `trait` | default by type |
| `trait` | `name` | string | — | default by type |
| `trait` | `traitset_id` | string | refs `traitset` | default by type |
| `trait` | `default_die_type` | die | — | default by type |
| `trait` | `tags` | string | — | `contains`, `==`, `!=` |
| `trait` | `universes` | string | — | `contains`, `==`, `!=` |
| `traitset` | `id` | string | refs `traitset` | default by type |
| `traitset` | `name` | string | — | default by type |
| `traitset` | `universes` | string | — | `contains`, `==`, `!=` |
| `traitset` | `limit` | int | — | default by type |
| `life_path` | `id` | string | refs `life_path` | default by type |
| `life_path` | `name` | string | — | default by type |
| `life_path` | `universe` | string | refs `universe` | default by type |
| `roll_table` | `id` | string | refs `roll_table` | default by type |
| `roll_table` | `name` | string | — | default by type |
| `roll_table` | `universe` | string | refs `universe` | default by type |
| `roll_table` | `life_path` | string | refs `life_path` | default by type |
| `scheduled_event` | `id` | string | refs `scheduled_event` | default by type |
| `entity` | `id` | string | refs `entity` | default by type |
| `entity` | `name` | string | — | default by type |
| `entity` | `razmerit` | int | — | default by type |
| `entity` | `starter_location` | boolean | — | default by type |
| `entity` | `hidden` | boolean | — | default by type |
| `entity` | `known_to` | string | refs `entity` | `contains`, `not contains` |
| `entity` | `type` | string | `character`, `location`, `faction`, `asset`, `gmc`, `universe`, `subtrait`, `relation` | default by type |
| `entity` | `current_location` | string | refs `location` | default by type |
| `entity` | `current_universe` | string | refs `universe` | default by type |
| `projection` | `type` | string | — | default by type |
| `projection` | `universe` | string | refs `universe` | default by type |
| `projection` | `origin_universe` | string | refs `universe` | default by type |
| `projection` | `entity_id` | string | refs `entity` | default by type |
| `projection` | `current_location` | string | refs `location` | default by type |
| `projection` | `last_used_at` | datetime | — | default by type |
| `location` | `id` | string | refs `location` | default by type |
| `location` | `name` | string | — | default by type |
| `location` | `type` | string | — | default by type |
| `location` | `universe` | string | refs `universe` | default by type |
| `location` | `starter_location` | boolean | — | default by type |
| `relationship` | `id` | string | refs `relationship` | default by type |
| `relationship` | `type` | string | — | default by type |
| `relationship` | `description` | string | — | default by type |
| `relationship` | `owner_id` | string | refs `entity` | default by type |
| `relationship` | `contact_id` | string | refs `entity` | default by type |
| `relationship` | `contact_name` | string | — | default by type |
| `universe` | `id` | string | refs `universe` | default by type |
| `universe` | `name` | string | — | default by type |
| `sfx` | `id` | string | — | default by type |
| `sfx` | `name` | string | — | default by type |
| `sfx` | `trigger` | string | — | default by type |
| `sfx` | `source_kind` | string | — | default by type |

_Count: 92 fields across 17 elements._

### Aggregations (`aggregate`)

| Function | Label | Gives |
|---|---|---|
| `count` | Count | int |
| `random` | Random | element |
| `tier` | Tier | int |
| `min` | Lowest value | same |
| `max` | Highest value | same |
| `top` | Highest element | element |
| `bottom` | Lowest element | element |
| `mean` | Mean | number |
| `avg_floor` | Average (floor) | number |
| `avg_ceil` | Average (ceil) | number |

_Count: 10._



## Effect actions

**Reading the sign column.** *cost* / *benefit* / *either* is the editor's hint — it groups the picker and colours the row, and stores nothing. A rule is free to use a cost verb for a benefit. *Refs* names the inputs the action declares; the editor labels each one, and a target is normally written as a targeting path.

_Count: 84._


**Change a Die**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Set Die** <br>`set_die` | Set a die to a specific size. On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait <br>Refs: `die` | either | — |
| **Step Up Die** <br>`step_up_die` | Increase a die by N steps (d8 + 2 → d12, clamped at d12). On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait <br>Refs: `die` | benefit | — |
| **Step Down Die** <br>`step_down_die` | Decrease a die by N steps (d8 − 2 → d4); a d4 stepped down is removed. On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait <br>Refs: `die` | cost | — |
| **Double Die** <br>`double_die` | Add N copies of a die at the same size (d8 + 2 → 3d8). On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait <br>Refs: `die` | benefit | — |
| **Split Die** <br>`split_die` | Split a die into N+1 dice one step smaller (d8 + 2 → 3d6), gaining extra dice to choose from. On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait <br>Refs: `die` | benefit | — |
| **Consolidate Dice** <br>`consolidate_dice` | Merge two dice of the same size into one die a step larger (2d8 → d10) — Split Die's inverse. On a die in the pool this lasts the roll; on a die of a trait's rating it changes the trait. Refused when the named die has no same-size partner, or is already a d12 <br>Refs: `die` | either | — |
| **Remove Die** <br>`remove_die` | Remove a die. On a die in the pool this lasts the roll; on a die of a trait's rating the trait loses that die — a rating with no dice left is still a trait <br>Refs: `die` | cost | — |
| **Reroll Die** <br>`reroll_die` | Reroll a die in the pool and keep the new result <br>Refs: `die` | benefit | — |
| **Restore Die** <br>`restore_die` | Put a die back to the size it had before a change. The engine writes this when a timed change reverts, recording the prior itself; authored directly it restores the size you give <br>Refs: `die` | either | — |
| **Reduce by Effect Die** <br>`reduce_by_effect_die` | Compare the effect die to a die: remove it if the effect die is larger, else step it down. Targets a die in either home — a rating die (which persists) or a die in the pool (which lasts the roll) <br>Refs: `die` | benefit | — |
| **Increase by Effect Die** <br>`increase_by_effect_die` | Compare the effect die to a die: set it to the effect die if the effect die is larger, else step it up. Targets a die in either home — a rating die (which persists) or a die in the pool (which lasts the roll) <br>Refs: `die` | benefit | — |

**Dice Pool**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Play as Rating** <br>`play_as_rating` | Play a trait instance at a named die size for this roll instead of its own rating — the dice already in the pool follow it | cost | — |
| **Add Dice** <br>`add_dice` | Add dice to a target dice pool (the GM difficulty pool or an entity's pool) <br>Refs: `pool` | benefit | — |
| **Add Trait Rating Dice** <br>`add_trait_rating_dice` | Add a target trait instance's rating dice to a target dice pool <br>Refs: `trait`, `pool` | either | — |
| **Roll Dice Pool** <br>`roll_pool` | Roll a target dice pool immediately (e.g. auto-roll the difficulty pool) <br>Refs: `pool` | either | — |
| **Resolve Dice Pool** <br>`resolve_pool` | Auto-resolve a target dice pool: roll it, pick the two highest as the total, and set the difficulty <br>Refs: `pool` | either | — |
| **Remove Added Dice** <br>`remove_added_dice` | Take back the dice a rule added to a pool. The engine records which ones; authored directly it removes what the pool records as added <br>Refs: `pool` | cost | — |

**Outcome**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Increase Dice Limit** <br>`increase_dice_limit` | Increase how many dice can be kept as the total or effect die (e.g. +1 total die) <br>Refs: `pool` | benefit | — |
| **Decrease Dice Limit** <br>`decrease_dice_limit` | Decrease how many dice can be kept as the total or effect die (e.g. -1 total die) <br>Refs: `pool` | cost | — |
| **Widen Hitches** <br>`set_hitch_threshold` | Make more of this entity's dice count as hitches — "both 1s and 2s count as hitches" is hitch on 2. A hitched die cannot be kept in the total or taken as an effect die, so this is a real drawback; a duration puts the range back <br>Refs: `recipient` | either | — |
| **Step Up Effect** <br>`step_up_effect` | Increase the effect die by one step | benefit | — |
| **Step Up Outcome** <br>`step_up_outcome` | Bump the outcome tier by one level | benefit | — |
| **Negate Complication** <br>`negate_complication` | Cancel one triggering complication | benefit | **retired** |
| **Convert Complication** <br>`convert_complication` | Turn a complication into a bonus die (adds d6 to a future roll) | benefit | **retired** |
| **Reroll Highest** <br>`reroll_highest` | Reroll the highest die and keep the new result | either | **retired** |

**Trait**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Step Up Trait** <br>`step_up_trait` | Increase a trait die by one step permanently (or for duration) <br>Refs: `trait`, `recipient` | benefit | **retired** |
| **Step Down Trait** <br>`step_down_trait` | Decrease a trait die by one step <br>Refs: `trait`, `recipient` | cost | **retired** |
| **Set Trait Rating** <br>`set_trait` | Set a trait to a specific die value <br>Refs: `trait` | either | — |
| **Add Die to Rating** <br>`add_rating_die` | Add a die to a trait's rating (any rating type: static, resource, or challenge) <br>Refs: `trait` | benefit | — |
| **Remove Die from Rating** <br>`remove_rating_die` | Remove a die from a trait's rating (any rating type) <br>Refs: `trait`, `recipient` | cost | **retired** |
| **Change Rating Type** <br>`set_trait_rating_type` | Change what the trait instance's rating is: a static die, a spendable resource, a challenge filling toward its capacity, or empty <br>Refs: `trait` | either | — |
| **Remove Trait** <br>`delete_trait` | Remove a trait instance from its owner — the trait burns away, is lost or destroyed (the same removal a temporary grant does when it expires) <br>Refs: `trait` | cost | — |
| **Copy Trait** <br>`copy_trait` | Give another entity a copy of a trait instance — its dice, rating type, polarity, statement and notes. Teaching hands over what you have, not the trait's default <br>Refs: `trait`, `recipient` | either | — |
| **Move Trait** <br>`move_trait` | Take a trait instance from another entity and give it to this one — stealing an asset, transferring a bond. The instance keeps its dice, grants and spent dice <br>Refs: `trait`, `recipient` | cost | — |
| **Change Trait** <br>`change_trait` | Point a trait instance at a different registry trait — the instance keeps its owner, dice, rating type, polarity, statement and grants, but it *is* the other trait now. 'Your blade' becomes 'a blade of fire' <br>Refs: `trait`, `instance` | either | — |
| **Invert Polarity** <br>`invert_polarity` | Flip a trait instance between complication and asset. The instance keeps its id, traitset and grants; only its polarity moves — pair it with *Change Trait* when it should also become a different definition <br>Refs: `trait` | either | — |
| **Disable Trait** <br>`disable_trait` | Disable a trait so it contributes no dice (until re-enabled or the duration ends) <br>Refs: `trait` | cost | — |
| **Enable Trait** <br>`enable_trait` | Bring a disabled trait back into play, so it contributes its dice again (the counterpart of Disable Trait; needed by the portent agenda) <br>Refs: `trait` | benefit | — |
| **Set Polarity** <br>`set_polarity` | Set a trait instance's polarity outright, rather than flipping it — the same change as Invert Polarity when the other value is known <br>Refs: `trait` | either | — |
| **Toggle Trait** <br>`toggle_trait` | Flip a trait between enabled and disabled <br>Refs: `trait` | either | — |
| **Set Trait-set Limit** <br>`set_traitset_limit` | Override how many traits this entity can hold in a trait set (set to a number) <br>Refs: `recipient`, `traitset` | either | — |
| **Gain Trait** <br>`gain_trait` | Add a new trait at a die rating (no-op if already present) <br>Refs: `trait`, `recipient`, `owner` | either | — |
| **Gain Relationship Trait** <br>`gain_relationship_trait` | Add a new trait anchored to a relationship edge — a tie to someone (a rank on a membership, a bond on a relation), rather than a trait you hold yourself <br>Refs: `trait`, `recipient` | either | **retired** |
| **Gain Sub-trait** <br>`gain_subtrait` | Add a new trait instance nested under another one — a facet of a trait (an elemental root under Spiritual Power, the next step of an agenda) rather than something the entity holds <br>Refs: `trait`, `owner` | either | — |
| **Gain or Step Up Trait** <br>`gain_or_step_up_trait` | Create the trait at the rating if absent, otherwise step it up <br>Refs: `trait`, `recipient`, `owner` | either | — |
| **Cortex Gain Trait** <br>`cortex_gain_trait` | Create the trait at the effect die if absent; if present, jump to the effect die when higher, else step up one step <br>Refs: `trait`, `recipient`, `owner` | either | — |
| **Reveal Trait (Learn)** <br>`reveal_trait` | Add the learner to a trait's known_to list so it stops showing as ??? on their sheet <br>Refs: `learner`, `trait` | benefit | — |

**Other**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Set Trait Statement** <br>`set_trait_statement` | Rewrite the statement on an existing trait instance — what the trait *is* (a challenge redefined) rather than what it is rated. The prior statement is recorded, so a duration can put it back. <br>Refs: `trait`, `owner` | either | — |
| **Choice (branch)** <br>`choose_branch` | Offer the player a labelled choice and run the chosen option's effects. At a boundary (end of beat/scene/session) it is asked there, so the rule holds its place instead of re-deriving what was chosen. | either | — |

**Razmerit**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Earn Razmerit** <br>`earn_razmerit` | Gain razmerit from the system pool <br>Refs: `recipient` | benefit | — |
| **Spend Razmerit** <br>`spend_razmerit` | Pay razmerit as an activation or ongoing cost <br>Refs: `recipient` | cost | — |
| **Transfer Razmerit** <br>`transfer_razmerit` | Move razmerit from one entity to another <br>Refs: `entity` | either | — |

**Entity**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Create Asset** <br>`create_asset` | Create a temporary asset entity at a location (duration-scoped; deleted on revert) | benefit | — |
| **Spawn Entity** <br>`duplicate_entity` | Spawn a copy of an entity — a mob from a template. The copy owns its own traits, edges and set settings; the template is left untouched <br>Refs: `template`, `owner` | benefit | — |
| **End Active Effect** <br>`end_active_effect` | End a running temporary effect now: its change is reverted (a deferred part is dropped) instead of waiting for the timer <br>Refs: `recipient`, `effect` | either | — |
| **Temporary Projection (Disguise)** <br>`create_projection` | Create and activate a temporary alternate body in the current universe/location; reverts to the prior body on expiry <br>Refs: `recipient` | benefit | — |
| **Delete Entity** <br>`delete_entity` | Remove an entity from the world. The engine writes this when a created entity's rule reverts <br>Refs: `entity` | cost | — |
| **Learn** <br>`learn_entities` | Someone learns about the resolved entity: they join its known_to list, deduped, without disturbing who already knew it <br>Refs: `learner`, `entity` | benefit | — |
| **Remove Targeting Ban** <br>`remove_targeting_ban` | Lift the ban that stops a character contesting an entity — the inverse of Targeting Ban <br>Refs: `entity` | benefit | — |

**Attunement**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Attune** <br>`attune` | Add a universe to an entity's effective universes until a timing expires. Context scope 'self' (entity) or 'domain' (location subtree). <br>Refs: `universe`, `projection`, `applies_to` | benefit | — |
| **Suppress** <br>`suppress` | Cut a specific body out of the character's active set until a timing expires — it can never name 'whatever is current' <br>Refs: `projection`, `applies_to` | cost | — |
| **Disable Attunement** <br>`disable_attunement` | Take a body out of the character's active set — the inverse of Attune <br>Refs: `entity` | cost | — |
| **Restore Attunement** <br>`unsuppress_attunement` | Put a suppressed body back into the character's active set — the inverse of Suppress <br>Refs: `entity` | benefit | — |
| **Restore Body** <br>`restore_projection` | Point the character back at the body they were in. The prior body is the recorded one | benefit | — |

**Travel**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Travel** <br>`travel` | Move an entity across a universal boundary (inapposite relocates the body; consciousness transfers the mind) <br>Refs: `recipient`, `location`, `projection` | benefit | — |
| **Set Location** <br>`set_location` | Place the entity at a specific or random location (its active body relocates in sync) <br>Refs: `recipient`, `location` | either | — |
| **Set Destination** <br>`set_destination` | Grant directions: name the place they are trying to reach, and the map lights the next hop <br>Refs: `recipient`, `location` | benefit | — |
| **Set Portal Destination** <br>`set_portal_destination` | Point a portal somewhere for now: the next time it is fired it goes there, without asking. Session state — a restart forgets it <br>Refs: `portal`, `owner` | benefit | — |
| **Clear Destination** <br>`clear_destination` | End an entity's directions. The engine writes this when guidance expires, restoring whatever the guidance replaced; authored directly, name that destination or leave it blank to clear outright | either | — |

**Life Path**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Discover Life Path** <br>`discover_life_path` | Add a life path to the entity's discovered paths <br>Refs: `life_path` | benefit | — |
| **Enter Life Path** <br>`enter_life_path` | Begin a term in a life path for the entity — the door the life-path wizard's own chooser opens. Writes the cursor, so a rule can drop a character straight into the path's first table; pair it with Show Life Path to put that table in front of the player, ready to roll <br>Refs: `life_path` | either | — |
| **Next Step** <br>`next_step` | Advance the term to a roll table (target = table id, empty to continue) <br>Refs: `table` | either | — |
| **Draft Into Life Path** <br>`draft_life_path` | Draft the entity into another life path <br>Refs: `life_path` | either | — |
| **Force Muster Out** <br>`force_muster` | Force the entity out of the current life path (dishonorable) | cost | — |
| **Muster Out** <br>`muster` | End the current life path term on respectful terms | either | — |
| **Enroll In Life Path** <br>`enroll_life_path` | Record the entity's membership in the current faction path | either | — |
| **Show Life Path** <br>`show_life_path` | Put a life path in front of the player, embedded — in the settings overlay when they created the character there, otherwise in that character's sheet. Nothing is granted or discovered: the path is shown, and whether they may walk it stays the path's own business <br>Refs: `life_path` | either | — |

**Roll Table**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Open Roll Table (Menu)** <br>`open_roll_table` | Open a roll table as an interactive menu: pick an entry, pay its cost effects, then gain its effects <br>Refs: `table` | either | — |

**Relationship**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Create Relationship** <br>`create_relationship` | Create a directional relationship edge to another entity <br>Refs: `contact` | either | — |
| **Targeting Ban** <br>`entity_targeting_ban` | Prevent the entity from targeting another entity (e.g. re-challenging after giving in) <br>Refs: `entity` | cost | — |

**Contest**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Start Contest** <br>`start_contest` | Oppose another entity: this starts a fresh contest between them at the acting entity's location (their rolls become contests until it resolves) <br>Refs: `opponent` | either | — |

**Rules**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Grant SFX** <br>`grant_sfx` | Grant a rule from the registry to a target owner: an entity, a place, a body, a trait definition (its default rules), or a trait / trait-set instance. The teacher case: a place's rule hands a technique to whoever it applies to. <br>Refs: `sfx`, `recipient` (`entity`, `location`, `projection`, `traitsetting`, `traitsetsetting`, `trait`) | benefit | — |

**Client**

| Action | What it does | Sign | Retired |
|---|---|---|---|
| **Open Character Sheet** <br>`open_sheet` | Bring a character sheet up on the recipient's screen — their own when no target is named, otherwise somebody else's <br>Refs: `recipient`, `owner` | either | — |
| **Show Toast** <br>`show_toast` | Show a message on the recipient's screen; sticky keeps it until it is dismissed, and a tap can open a chosen entity's sheet <br>Refs: `recipient`, `tap_target` | either | — |

**Retired actions.** A retired action is hidden from the picker but **still works**: rules already using it keep firing and keep reverting, and nothing is rewritten under you. Author new rules with its replacement — the retired rows above say what they do, and the modern equivalent sits in the same group.

## Related

- [[SFX Authoring]] — how to author a rule: the form, targeting paths, and a worked example
- [[Targeting Model]] — how a path is resolved and type-checked
- [[SFX Source Model]] — what "Lives on" decides
- [[Dynamic SFX Reach]] — how a rule becomes available to the owners it reaches
- [[Dice Mechanics]] — pools, totals, and effect dice
- [[User Manual]] — the player/GM how-to index

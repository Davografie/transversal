---
title: SFX Authoring
date: 2026-09-09
tags:
  - transversal
  - manual
  - sfx
  - effects
  - gm
aliases:
  - Authoring SFX
  - SFX Editor
  - How to write SFX
status: draft
---

# SFX Authoring

A practical guide to writing **SFX** (Special Effects) in the GM/architect SFX editor. SFX are the rule exceptions that make abilities work: a medicine skill that heals, a technique that steps up a die, a faction perk that triggers when you win a contest.

For the *rules* behind SFX, see [[SFX and Effects]] (technical reference) and the [[Transversal Hub#📖 Game Design|Game Design]] docs. This page is the "how to use the editor" guide.

> [!note] Where it lives
> SFX are authored in the GM panels: open the **SFX editor** from the GM panel tree. The editor has a shared form for the SFX itself, and each effect opens in its own child panel.

---

## The mental model

An SFX has four moving parts:

1. **When it activates** — the *trigger* (a game event, a button click, or a menu entry).
2. **Who carries it** — the *source* (a trait, a trait set, the entity, or a projection).
3. **When it is allowed** — *conditions* that gate activation.
4. **What it does** — a list of *effects*, each of which is an operation (`step up a die`, `earn razmerit`, `travel`, …).

Most authoring work is picking the right **trigger** + **effect action**, then scoping the effect with **targeting** and **conditions**.

---

## The SFX form

### Name & Description

- **Name** — the display name (e.g. `Heal`).
- **Description** — free text shown on the card/menu. The editor also renders a live plain-English summary at the top of the panel.

The SFX **id** is generated from the name (a slug like `sfx-heal`); it is not edited by hand.

### Trigger

The single activation axis. Choose from the trigger vocabulary (see [[#Trigger reference]]). Broadly:

- **`manual`** — a button the player clicks (the SFX shows on the owner's card/sheet).
- **`on_*` dice-pool events** — `on_roll`, `on_result`, `on_contest_win`, `on_taken_out`, … fire automatically when that event happens.
- **`on_beat` / `on_scene` / `on_session_start`** — fire on time/state boundaries.

Some triggers expose **variables** (e.g. `on_contest_win` provides `{effect_die}`, `{taken_out}`, `{contest_entity_opponent}`). The editor lists them under "Available variables" so you can reference them in effect fields as `{variable}`.

### Placement

Where the SFX appears. **Auto (from trigger)** derives it for you:

- `manual` → **sheet** (owner card)
- `on_*` → **auto** (event-driven, no button)
- legacy menu triggers → **menu** (post-roll consequence menu)

Override it only when you want to force a surface (e.g. a `manual` trigger shown in the consequence menu instead of the sheet).

### Source

What kind of thing *carries* the SFX — its activation origin. This determines what `select source` and `{source_*}` resolve to, and what a **Source rating** condition measures.

| Source | Meaning | `select source` resolves to |
|--------|---------|------------------------------|
| *(none)* | Not yet attached (orphan) | — |
| **Trait setting** | A trait instance on the entity (e.g. Phaos' *Medicine*) | the trait instance |
| **Trait set setting** | A trait-set instance | the set instance |
| **Entity** | The character/entity itself | the entity |
| **Projection** | The active projection | the projection |
| **Table** | Available to every entity (the table bucket) | — (non-resolving) |
| **GM** | GM-only contexts | — (non-resolving) |

Set **Trait setting** when the SFX is granted by and scales with a trait (so `source_rating` conditions can gate on that trait's rating). **Table**/**GM** are *bucket* sources — they have no single instance, so `select source` / `source_rating` don't apply to them.

### Arming scope

Who the armed SFX **listens to** once it fires its delayed (roll/outcome-timed) effects. **Auto (from trigger)** derives it:

- `on_session_start` → **global** (a passive rule — listens to every entity's rolls)
- anything else → **self** (listens to the triggering entity)

The **Listens to** control overrides it:

| Scope | Listens to |
|-------|-----------|
| **Self** | The triggering entity |
| **Global** | Every entity's rolls |
| **A targeting path** | The entity set resolved from a targeting path (`select self → navigate relationships → filter type == curse_bind → navigate target`) |

You only need this for cross-entity listening (e.g. a curse that binds two entities). Normal SFX leave it on **Auto**. See [[SFX Activation Model Plan]] for the design.

### Conditions

SFX-level conditions must **all** pass for the SFX to fire. They gate *when the SFX is allowed*, not what it does. See [[#Condition reference]].

Two important subtleties:

- **Static conditions** (entity type, source rating, in-universe, has-trait, …) also gate *availability* — the SFX shows as "conditions not met" on the sheet until they pass.
- **Context conditions** (`phase`, `contest_outcome`, `roll_tier`, `test_outcome`, `user_role`, `hitch`) are only checked at fire time, when the event context exists.

### Effects

The list of operations the SFX performs, in order. Effects are executed **sequentially**: if an effect needs a runtime choice (`choose`), later effects wait for that choice to resolve. Add, reorder, and edit effects here; each effect's form opens in a child panel.

### Duration — the *listening window*

How long the SFX stays **armed** (listening for the next roll/outcome event) after it triggers.

Two things matter:

- **It only affects *delayed* effects** — those with an `On roll` / `On set` / `On result` / `On contest …` timing. `Immediate` effects fire once at trigger time and ignore this entirely.
- **It is *not* an undo timer.** It controls *when the SFX stops listening*, not when a change reverts — that is each effect's own **effect duration** (see below).

Timers:

- `rolls: N` — fire on the next **N** matching roll events, then drop. The default is `rolls: 1` (fire once).
- `beat` / `scene` / `session` / a state-change event — drop the armed SFX when that boundary fires; until then it keeps firing on every matching roll.
- no timer — armed indefinitely.

---

## The effect form

Each effect is an operation. The fields depend on the chosen action (the editor only shows what that action needs).

### Action

Pick from the effect vocabulary (see [[#Effect action reference]]). The action fixes the operation (`type`/`action` behind the scenes), its target kind, and whether it shows a duration/polarity toggle.

### Timing

When this effect fires **relative to the SFX's trigger**:

- **Immediate** — applies the moment the SFX triggers.
- **On roll / On set / On result** — armed now, fired at the next matching roll event (roll-timed).
- **On contest win / loss / success / failure** — armed now, fired when the roll/contest *resolves* with that outcome.
- **End of beat / scene / session**, **After beats** — persisted timers that fire on the time boundary.

> [!tip] Trigger vs timing
> The SFX **trigger** says *when the SFX wakes up*; the effect **timing** says *when this effect lands*. A `manual` SFX usually has `immediate` effects. A passive rule like *One Trick* uses `on_session_start` trigger + an `on_roll` effect (armed at session start, fired on every later roll).

> [!note] Session-start and session-end SFX have two halves
> `on_session_start` fans out in two directions, decided per effect by its timing:
> - **Timed effects** (`on_roll`, `on_set`, `on_result`, `on_contest_win`/`loss`, `on_success`/`failure`) arm **once, globally** for the session — a passive rule listening to every entity, including characters who join mid-session. These carry no per-entity stamp.
> - **Non-timed effects** (`immediate`, `end_of_beat`/`scene`/`session`, `after_beats`) fire **per entity** when the session starts — "every character gains X".
>
> `on_session_end` fires its effects **per entity** at the session's far boundary, after the session's armed passives are dropped.

### Target

What the effect points at. Five modes:

1. **Pick specific** — a literal id (self, a named trait, a location). The `{choose:kind}` legacy form.
2. **Choose at runtime** — `{choose:kind}`; the player picks at resolution time.
3. **Random** — `{random:kind}`; a random in-scope candidate.
4. **Named exit** — `{return:name}` for shared roll tables (only when the action supports it).
5. **Targeting path** — a structured `target_spec` pipeline (see [[#Targeting path]]).

The **scope** (`target_scope`) narrows choose/random candidates (`traitset:…`, `universe:…`, `location:…`, etc.).

### Entity (subject)

Who the effect applies to. Default `self`. Mirror of Target: literal, choose, random, or a targeting path (`entity_spec`). For most trait effects this stays `self`.

### Result & context fields

Action-specific inputs — a die rating, an amount, a pool, `{variable}` tokens, and context fields like `steps`, `rating_type`, `statement`, `notes`, `relationship`. The editor renders the right controls per action.

### Polarity (negative toggle)

For trait-granting effects, toggles whether the granted trait is a **complication** (negative) vs a benefit.

### Effect duration — the *undo timer*

Schedules the **inverse** of this effect to revert it later: `step_up` with a `beat` timer means "step up now, step back down at end of beat."

This is a **different clock** from the SFX-level **listening window**. The SFX duration says *how long the SFX keeps listening*; the effect duration says *how long the resulting change lasts*. A single SFX can be "armed for 1 roll" (listening window) while one of its effects is "1 scene" (undo timer) — the change it makes is reverted at end of scene, but the SFX itself stopped listening after that one roll.

### Effect conditions

Per-effect gates. If an effect has conditions and they fail at apply time, **that effect is skipped** (the SFX still fires its other effects). Useful for rating-scaled SFX: five `modify_dice_limit` effects, each gated `source_rating == d4/d6/d8/d10/d12`, so only the matching one applies.

---

## Targeting path

The structured way to target. A **path** is an ordered pipeline of steps that resolves to a typed value (an entity, a list of trait instances, a die, a count, …). The editor's wizard is catalog-driven and type-checked — it only offers legal next steps and highlights whether the path matches the field's expected type.

### Step types

| Step | What it does |
|------|--------------|
| **Select** | Seed the working set from a collection (`self`, `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`), the SFX `source`, or a bound `variable`. |
| **Filter** | Keep items whose field matches a predicate (`polarity == negative`, `rating_type == static`, `traitset_id == …`). Operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `contains`. |
| **Navigate** | Hop an edge to related elements (a trait instance → its entity, an entity → its current location, …). `dedup` collapses duplicates by identity. |
| **Aggregate** | Collapse a collection to a scalar: `count`, `min`, `max`, `mean`, `avg_floor`, `avg_ceil`. |
| **Literal** | Name one object by id directly. |
| **Evaluate** | Terminal boolean test — `exists` (non-empty), or compare `count` / a scalar field against a value. Produces true/false (used by **Targeting path** conditions). |

Resolution modes **choose** (interactive pick) and **random** (non-interactive sample) collapse a many-cardinality collection to one (or a subset when `count > 1`).

### Useful seeds & edges

- **Collections:** `self`, `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`.
- **Common edges:** trait instance → `trait` (registry trait) / `traitset` / `entity` / `projection`; entity → `traitsettings` / `location` / `universe` / `projections`; location → `occupants` / `difficulty_pool`; entity → `pool`.
- **Common fields:** trait instances expose `rating`, `rating_type`, `polarity`, `trait_id`, `traitset_id`; entities expose `type`, `current_location`, `current_universe`, `razmerit`; dice expose `result`, `rating`, `effect_die`, `tier`, `role`, `source_kind`, `ts_id`.

### Output variables

Any step can declare an `output` name, binding its resolved value into the activation scope so a later effect references it as `{name}` (scalar) or `select variable {name}` (a `many` collection). This is how one effect hands a result to the next.

---

## Trigger reference

| Trigger | Fires when… | Group | Notable variables |
|---------|-------------|-------|-------------------|
| `manual` | The player activates it | manual | — |
| `on_roll` | A roll happens | dicepool | — |
| `on_result` | A roll result is produced | dicepool | `{effect_die}`, `{total}` |
| `on_complication` | A hitch/complication occurs | dicepool | — |
| `on_botch` | A botch occurs | dicepool | — |
| `on_success` / `on_failure` | A roll succeeds / fails | dicepool | — |
| `on_contest_win` / `on_contest_loss` | A contest resolves | dicepool | `{contest_entity_opponent}`, `{effect_die}`, `{high_stakes}`, `{taken_out}` |
| `on_give_in` | A side gives in | dicepool | `{contest_entity_opponent}`, `{gave_in}` |
| `on_push` | The pool is pushed | dicepool | `{pushed}` |
| `on_taken_out` | A side is taken out | dicepool | `{contest_entity_opponent}`, `{taken_out}` |
| `on_prevent_taken_out` | A take-out is prevented | dicepool | `{effect_die}`, `{prevented}` |
| `on_set` | Dice are set | dicepool | `{effect_die}`, `{total}` |
| `on_location_change` | Entity changes location | — | `{from_location}`, `{to_location}`, `{universe}` |
| `on_trait_change` | A trait changes | — | `{trait}`, `{traitset}` |
| `on_trait_learn` / `on_trait_offered` | A trait is learned / offered | — | `{trait}`, `{trait_setting}`, `{owner}`, `{learner}` / `{opponent}` |
| `on_relationship_create` | A relationship is created | — | `{target_entity}`, `{relationship_type}` |
| `on_character_create` / `on_projection_create` | A character / projection is created | — | `{entity_created}` / `{projection_created}`, `{universe}` |
| `on_beat` / `on_scene` | Beat / scene advances | auto | — |
| `on_session_start` | A session starts | auto | — |
| `on_session_end` | A session ends | auto | — |
| `on_challenge_completed` | A challenge completes | — | `{entity_id}`, `{trait_setting_id}` |

---

## Condition reference

| Condition | Passes when… |
|-----------|--------------|
| **Always** | Always (no gate). |
| **Narrative** | Never auto-blocks; free-text limit/description. |
| **At location** | The subject is at the given location. |
| **Has trait** | The subject owns the given trait. |
| **Has effective trait** | The subject owns the trait *and* it is enabled. |
| **Has trait in traitset** | The subject has any trait in the given trait set. |
| **Has relationship** | The subject has the given relationship. |
| **Trait rating** | A trait's rating compares to a die (`rating >= d8`). |
| **Has razmerit** | The subject's razmerit compares to a number. |
| **Entity type** | The subject is `character` / `gmc` / `asset`. |
| **User role** | The acting user is `player` / `architect`. |
| **Unplaced (no location)** | The subject has no current location. |
| **In universe** | The subject is in the given universe. |
| **Phase** | The roll is in `adding` / `rolling` / `picking` / `resolved` (fire-time only). |
| **Contest outcome** | The contest resolved `player` / `opponent` / `give_in` (fire-time only). |
| **Hitch** | The current context is a hitch-buying menu (fire-time only). |
| **Roll tier** | The roll's outcome tier compares to a tier (fire-time only). |
| **Test outcome** | A test succeeded / failed (fire-time only). |
| **Source rating** | The SFX's source trait rating compares to a die. |
| **Targeting path** | The authored targeting path resolves non-empty (or its terminal `evaluate` is true). |

---

## Effect action reference

The editor shows these as labeled actions; each maps to a `type`/`action` pair behind the scenes. The sign hint (cost / benefit / either) is a UI aid, not a stored field.

**Roll & dice**

| Action | What it does | Sign |
|--------|--------------|------|
| Play as Rating | Use a trait's rating as the roll rating | cost |
| Step Up Die / Step Down Die | Shift a die in the pool | benefit / cost |
| Double Die | Duplicate a die | benefit |
| Reroll Die / Reroll Highest | Re-roll a die / the highest die | benefit / either |
| Remove Die / Split Die | Remove / split a die | cost / benefit |
| Add Dice | Add explicit dice to a pool | benefit |
| Add Trait Rating Dice | Add a trait's rating dice to a pool | either |
| Roll Dice Pool / Resolve Dice Pool | Roll / auto-resolve a pool | either |
| Increase / Decrease Dice Limit | Change the keep-2 total (or effect) dice limit | benefit / cost |
| Step Up Effect / Outcome | Improve the effect die / outcome | benefit |
| Negate / Convert Complication | Neutralize or transform a complication | benefit |

**Traits**

| Action | What it does | Sign |
|--------|--------------|------|
| Step Up Trait / Step Down Trait | Shift a trait rating | benefit / cost |
| Reduce by Effect Die | Step a trait down by the effect die | benefit |
| Set Trait Rating | Set a trait to a fixed rating | either |
| Add Die to Rating / Remove Die from Rating | Change a multi-die rating | benefit / cost |
| Disable Trait / Toggle Trait | Turn a trait off / flip it | cost / either |
| Gain Trait / Gain or Step Up Trait / Cortex Gain Trait | Acquire a trait (or step it up) | either |
| Reveal Trait (Learn) | Reveal a trait to another entity | benefit |
| Set Trait-set Limit | Change a trait set's size limit | either |

**Razmerit**

| Action | What it does | Sign |
|--------|--------------|------|
| Earn Razmerit | Gain razmerit | benefit |
| Spend Razmerit | Pay razmerit | cost |
| Transfer Razmerit | Move razmerit between entities | either |

**Entities, travel & relationships**

| Action | What it does | Sign |
|--------|--------------|------|
| Create Asset | Create an asset/GMC | benefit |
| Temporary Projection (Disguise) | Create a temporary projection | benefit |
| Attune | Temporarily add a universe | benefit |
| Travel | Cross a universal boundary | benefit |
| Set Location | Move to a location | either |
| Create Relationship | Add a relationship edge | either |
| Targeting Ban | Prevent re-targeting an opponent | cost |
| End Active Effect | Cancel a scheduled effect | either |

**Life paths & roll tables**

| Action | What it does | Sign |
|--------|--------------|------|
| Discover Life Path | Open a life path for the entity | benefit |
| Open Roll Table (Menu) | Open a roll table as a menu | either |
| Next Step / Draft Into Life Path | Advance / draft into a life path | either |
| Muster Out / Force Muster Out / Enroll In Life Path | Leave / force-leave / enroll a life path | either / cost / either |

---

## Worked example — a rating-scaled passive

Goal: *Qi Condensation* — while active, add dice to the pool limit based on the cultivation-stage rating (`d4 → +1`, `d6 → +2`, …, `d12 → +5`).

1. **Name** `Qi Condensation`. **Trigger** `on_roll`. **Source** `Trait setting` (the cultivation-stage trait).
2. Add five effects, each `Increase Dice Limit` with `timing: immediate` and a per-effect **condition** `Source rating == d4` (then d6, d8, d10, d12), result `1..5`, limit `total`.
3. Only the effect whose `source_rating` matches the trait's current rating applies; the others are skipped.

## Worked example — a heal that targets a complication

Goal: *Heal* — pick an occupant, pick one of their complications, step it down by the effect die.

1. **Trigger** `manual` (a button on Phaos' Medicine trait). **Source** `Trait setting`.
2. Effect 1: `Add Trait Rating Dice` → the location's difficulty pool (so healing is a test).
3. Effect 2: `Resolve Dice Pool` (auto-roll + set the difficulty).
4. Effect 3: `Reduce by Effect Die`, target set to a **targeting path**: `select occupants → choose 1 → navigate traitsettings → filter traitset_id == <complications set> → choose 1`.

Because effects run sequentially, the resolution effect waits for the dice-adding effect, and the final reduce effect waits for the trait choice.

---

## Gotchas

- **Effect conditions need a source.** `source_rating` / `target_path` conditions on an *effect* only work when the SFX declares a matching **Source**. Without it, `source` is empty and the condition fails silently.
- **Trigger ≠ timing.** `manual` SFX are `immediate`; passive rules pair an `on_session_start`/`on_*` trigger with a roll/outcome timing effect.
- **SFX duration ≠ effect duration.** The SFX duration is a *listening window* (how long the SFX stays armed); the effect duration is an *undo timer* (when a change reverts). They don't influence each other.
- **Sequential execution.** If an effect needs a `choose`, the effects after it pause until the choice resolves.
- **Legacy vs structured targeting.** Old effects used `target`/`entity` strings; new effects use the **Targeting path** (`target_spec`/`entity_spec`). When both exist, the spec wins. Prefer the targeting path for anything that needs drillthrough or multi-target fan-out (see [[Targeting Model]]).

---

## Related

- [[SFX and Effects]] — the implementation reference (modules, model fields, identifiers).
- [[Targeting Model]] — the structured targeting spec, catalog, and wizard.
- [[Dice Mechanics]] — how pools, totals, and effect dice work.
- [[User Manual]] — the player/GM how-to index.

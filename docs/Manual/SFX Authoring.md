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
| **Top** | Keep *one* element — the highest or lowest by a comparable field (a number, a die, or a **timestamp**). For a timestamp, `desc` reads as "the most recently used" and `asc` as "the least recently used"; otherwise "the highest/lowest …". This is how you ask for *the body you were last in*: `select self → navigate projections → top last used at`. |
| **Literal** | Name one object by id directly. |
| **Evaluate** | Terminal boolean test — `exists` (non-empty), or compare `count` / a scalar field against a value. Produces true/false (used by **Targeting path** conditions). |

Resolution modes **choose** (interactive pick) and **random** (non-interactive sample) collapse a many-cardinality collection to one (or a subset when `count > 1`).

### Useful seeds & edges

- **Collections:** `self`, `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`.
- **Common edges:** trait instance → `trait` (registry trait) / `traitset` / `entity` / `projection`; entity → `traitsettings` / `location` / `universe` / `projections`; location → `occupants` / `difficulty_pool`; entity → `pool`.
- **Common fields:** trait instances expose `rating`, `rating_type`, `polarity`, `trait_id`, `traitset_id`; entities expose `type`, `current_location`, `current_universe`, `razmerit`; dice expose `result`, `rating`, `effect_die`, `tier`, `role`, `source_kind`, `ts_id`.

### Output variables

Any step can declare an `output` name, binding its resolved value into the activation scope so a later effect references it as `{name}` (scalar) or `select variable {name}` (a `many` collection). This is how one effect hands a result to the next.

**Conditions share that scope, and are traced first.** A **Targeting path** condition runs before any effect, so the names its steps output are offered in the effect editor's variable picker alongside the effects' own outputs. That lets a gate do the finding and the effect do the acting on it:

> **Worked example — "When rolling a d4 trait, gain 1 razmerit"** (`sfx-d4-bonus`)
>
> *Condition* (Targeting path): `select rolled_dice` → `navigate traitsetting (dedup)` → `filter rating == d4`, **output `d4_traits`** → `evaluate count >= 1`.
>
> *Effect*: `earn razmerit 1`, entity targeting path `select variable d4_traits` → `navigate entity`.
>
> The condition decides *whether* (and names what it matched); the effect walks those trait instances to their owning entities and credits one. Neither step is implicit: the entity the razmerit lands on comes from the path, not from a hidden default.
>
> Two things to know: a roll-inspecting path only resolves on a roll-bearing trigger (`on_roll`/`on_result`), which is what puts the dice in context — and a condition seeded from `rolled_dice` is skipped when availability is computed for *listing*, so it still shows up as available and only gates at fire time.

---

## How your SFX reads

The editor shows a **card line** under the name field — the SFX in plain language: *"Whenever a roll happens, if there is at least one d4 trait: gain 1 razmerit."* It is derived from what you authored (trigger → conditions → effects), not from the Description field, and it is recomputed as you edit.

Read it as a sanity check. If the card line does not say what you meant, the SFX probably does not do what you meant.

### What it says

- **The trigger** first: *Whenever a roll happens* / *Activated* / *At the start of each session*.
- **Then the gates**: *if you are not at a location yet and you are in Earth*.
- **Then the effects**, in authored order, each with its timing: *whenever a roll is resolved, step down each static trait instance you rolled by one step*.
- **Effect-level conditions gate that effect**: *if this trait is rated d6, increase the dice limit by 2*. A narrative condition on an effect trails in parentheses instead (flavour, like the SFX-level one).
- **Effects scoped to a subset of dice say so**: an effect with a die-role filter reads *for each unchosen die, …* — the dice a player didn't assign. Inside such an effect the die being processed **is** the roll, so a path seeded from `rolled_dice` reads *that die* rather than *each die in your roll*. That is what makes "for each unchosen die, give its owner's location a hazard" land once per die.
- **A step's value can be a name.** Where a filter wants a value, pick it from the autosuggest list — or press the small `{ }` button to compare against a **bound name** instead (`{universe}`), which is how one path joins to a choice made in another. Picking a universe stores its handle (`earth`), which is what a life records.
- **Attune carries two paths, and path 2 starts from path 1 by name.** Give path 1's last step an `output` name (e.g. `attune_target`), then open path 2 and add a `select variable` step — that name is in the list. Name it for the reader, because the name is both how path 2 starts and what the card shows.
- **An effect that lands somewhere other than its target says where**: *gain the environmental hazard trait **on the location of each owner of each trait instance you rolled*** — that clause comes from the effect's subject (`entity_spec`), so if you author a subject, expect to see it.
- **Effects that share framing are grouped.** Consecutive effects with the same timing, die scope and duration read as one list with the framing stated once:

  > *…if this trait is rated d4, increase the dice limit by 1; if this trait is rated d6, increase the dice limit by 2; … (each reverts at the next roll).*

  So five rating-gated bumps revert *together*, and the card says so once rather than five times.
- **A narrative condition trails in parentheses.** It is flavour the engine never checks, so it is kept visually apart from the rules text.
- **Effect durations** read as *reverts at the end of the scene* — the **undo timer**. This is a different thing from the SFX's own listening window, and the two are phrased differently on purpose (see [[SFX and Effects]]).

### Naming a step is how you keep it readable

Long paths make long sentences. The fix is naming: **any step with an `output` name contributes that name to the card line instead of the pipeline behind it.**

| Step output | Reads as |
|---|---|
| `d4_traits` | *…at least one d4 trait* |
| `gritty_dice` | *each gritty die* |

So `d4_traits` is not just a variable for later effects — it is what the reader sees. Name steps for the person reading the card, not for the machine: `d4_traits` reads better than `filtered_1`, and either can be referenced by later effects.

> **Rule of thumb:** if the card line has grown into a paragraph, name the step where the meaning becomes clear and the sentence will shorten itself.

### What it does not say

- It is a rendering of the *machine* reading, not a rules interpretation. A `NARRATIVE` condition appears as flavour because that is all it is.
- **A die filter is silently inert on an effect that also has a target path.** The applier checks `refs` and `target_spec` before the die filter, so such an effect runs once for the whole roll and its dice scope never applies. The card text stays silent about that scope rather than claiming it — so if you filter dice and see no *"for each \u2026 die"* clause, that is the reason, and the fix is to move the dice logic into the path.
- Unresolved ids show raw (`trait-environmental-hazard-58be`). If you see one, the effect points at something that no longer exists — worth fixing.
- It describes effects in authored order, even when they are grouped by timing on the card.
- It does not currently read an effect's `context` (e.g. `limit: total` vs `limit: effect` on the dice-limit actions), so two effects that differ only there will read the same.

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
| **High stakes** | The contest in play is high-stakes (`high`) or not (`low`); fire-time only. |
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
| Copy Trait | Give another entity a copy of a trait instance — its dice, statement, notes, polarity are carried over; the recipient's trait-set rules apply | either |
| Move Trait | Take a trait instance from another entity (a steal): the instance changes hands with its grants and spent dice | cost |
| Delete Trait | Remove a trait instance from its owner — the trait burns away, is lost or destroyed | cost |
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
| Attune | Give the target temporary use of another universe's capabilities. Two paths: **Who It Applies To**, and **Attunes To (projection)** — which walks from each of them to their counterpart life, and takes the universe from it. A path resolving to many entities attunes each of them. | benefit |
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
- **A gate can only read what its moment supplies.** Each evaluation point brings a specific set of context: a roll-timed effect brings the roll (`tier`, `effect_die`, `total`, `rolls`, stakes), a manual activation brings `phase` and stakes, a consequence-menu move brings the outcome it was assembled for (contest win / give-in / test result / hitch), and a beat, scene or session fire brings **nothing at all**. The editor keeps a condition out of a point that supplies none of the keys it reads, and `validateSfx` names the missing key — *"it reads 'phase', and there is no context at this moment"* — so a gate that could never pass is visible while you author it, not after.
- **Two that surprise people.** *User role* needs no context (it falls back to the entity's controlling player), so it works anywhere including boundaries. And a *targeting path* only needs the roll when it actually reads it — a path that seeds from `rolled dice` needs a moment that has dice (a roll trigger, a roll-timed effect), while a path over the entity's own traits works anywhere.
- **SFX duration ≠ effect duration.** The SFX duration is a *listening window* (how long the SFX stays armed); the effect duration is an *undo timer* (when a change reverts). They don't influence each other.
- **Sequential execution.** If an effect needs a `choose`, the effects after it pause until the choice resolves.
- **Legacy vs structured targeting.** Old effects used `target`/`entity` strings; new effects use the **Targeting path** (`target_spec`/`entity_spec`). When both exist, the spec wins. Prefer the targeting path for anything that needs drillthrough or multi-target fan-out (see [[Targeting Model]]).

---

## Related

- [[SFX and Effects]] — the implementation reference (modules, model fields, identifiers).
- [[Targeting Model]] — the structured targeting spec, catalog, and wizard.
- [[Dice Mechanics]] — how pools, totals, and effect dice work.
- [[User Manual]] — the player/GM how-to index.

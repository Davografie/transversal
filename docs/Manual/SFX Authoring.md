---
title: SFX Authoring
date: 2026-10-16
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

An **SFX** is a rule that bends the normal rules for one character, place or thing — a technique that steps a die up, a medicine skill that heals, a curse that binds whoever it is cast on. You write them in the GM panels; players then meet them as buttons and cards on their sheets.

There are two levels to every rule:

- The **rule itself** — its name, where it lives, what starts it, and how long it lasts.
- Its **effects** — the things it actually does, one row per operation, run in order.

This page walks through both, then builds one real rule end to end. [[SFX Reference]] is the lookup for every trigger, condition, source and action the editor offers; keep it open beside you.

> [!note] Where it lives
> In the GM panel, press **Manage SFX**. That opens the rule library together with an **owner filter**: pick the thing a rule belongs to — a character, a place, a trait — to see what it carries and to attach more. **+ New SFX** starts a blank rule, and the **⧉** on a row makes a copy of one.

## The four questions

Every rule answers four questions, in this order. The order matters, because each answer decides which of the later ones you are offered:

1. **Where does it live?** — the **Source**. A rule living on a trait can use that trait; a rule living on a place can reach the people standing in it.
2. **What starts it?** — the **Trigger**. A button the player presses, or something that happens during play.
3. **What does it do?** — the **Effects**. One row per operation, applied in order.
4. **Who may have it?** — **Who it reaches**. Usually nobody: you attach the rule by hand. The paths here are for a rule that hands itself out.

The panel asks them in that order. Three more fields appear only when a rule needs them — **Listens to**, **Duration**, and **Bound variables** — and each is explained where it comes up below.

## Writing the rule

### Name and description

- **Name** — what the rule is called on the card and in the library. Its id is worked out from the name.
- **Description** — the line shown on the card. Free text.

Press **Create SFX** and the rule now exists; from that point every edit saves itself, and the panel becomes the rule's editor rather than closing.

### Where it lives — Source

Pick the kind of thing that may carry this rule. This is the panel's first field because everything below depends on it: it decides which surfaces the rule can be attached to, and it puts a **variable** in scope naming the thing it lives on.

| Source | The rule lives on | You get |
|---|---|---|
| *(none)* | nothing yet — an unattached rule | nothing |
| **Trait setting** | one trait instance (a character's *Medicine*) | `{trait_setting}` |
| **Trait set setting** | one trait-set instance | `{traitset_setting}` |
| **Entity** | a character, GMC or asset | `{entity}` |
| **Location** | a place — the rule reaches whoever is inside it | `{location}` |
| **Faction** | an organisation — and so its members | `{faction}` |
| **Projection** | one body | `{projection}` |
| **Table** / **GM** | everyone, or the GM's own contexts | nothing |

The available names are listed under the field as **Available variables**. `Table` and `GM` are *buckets* rather than a single thing, so they name nothing and offer no source variable.

**`Entity` and `Location` are not interchangeable.** A location is an entity, but a rule sourced on `Entity` resolves to whoever is *acting* — for a place-owned rule, the character who walked in — while `Location` resolves to the place itself. If the rule is about the ground, source it `Location`.

Set **Source** to match wherever you attach the rule. A trait-sourced rule belongs on a trait instance; attaching it to a character instead is refused rather than quietly resolving to the wrong thing later.

### What starts it — Trigger

The single thing that wakes the rule up. The picker groups them:

- **Manual** — a button the player presses on the rule's card.
- **Dice pool** — something that happens around a roll: `On Roll`, `On Result`, `On Contest Win`, `On Added To Pool`, `On Pool Change`, and the rest. `On Added To Pool` is the odd one out: it needs a **Trait setting** source, because "this trait was added" has to know which trait *this* is. The picker greys it out and says so otherwise.
- **Auto-fire** — something that happens in the fiction: arriving somewhere, a trait being learned, a session or scene boundary.

A trigger often carries **variables** with it — `On Result` brings `{effect_die}` and `{total}`, `On Contest Win` brings the opponent and the stakes. They are listed under the field and can be used in any effect, and a targeting path may also start from one.

> [!tip] The roll-family triggers are gated by the source
> A rule sourced on a trait instance only fires on a roll-family trigger when a die from **that instance** is in the pool. This is deliberate: a rule that says "when I roll my sword" should not fire when someone else rolls. Nothing extra to author — put the die in the pool and the rule is live.

### Who it's about — Listens to

This field appears only when part of the rule **waits for a roll** — that is, when it has an effect timed `On Roll`, `On Set`, `On Result`, `On Success`, `On Failure` or `On Contest …`. With nothing waiting there is nobody to listen to, so the panel leaves the field out.

When it does appear, it says whose rolls feed that waiting part:

- **From the trigger** — the default, shown already resolved: whoever activated the rule, except a session-start passive, which watches everyone.
- **Self** / **Global** — the same two answers, stated outright.
- **A targeting path** — the waiting part listens to *the entities that path names*, which is how a curse listens to whoever it is bound to rather than to whoever cast it. The path is resolved **once, when the rule arms**, so a relationship that changes afterwards does not re-target. If the path names nobody, the rule arms on nobody and simply does nothing.

### How long it's held — Duration

Sits directly under *Listens to*, because it answers the same question one step later: *Listens to* says whose rolls feed the waiting part, **Duration** says how long it waits for them.

- **A number of rolls** — fire on the next N matching rolls, then stop.
- **A boundary or an event** — scene, beat, session, a change of location, or a trait being updated: keep going until that happens, then stop.
- **Empty** — no limit. The rule stays armed until something else drops it.

> [!warning] Empty does not mean "once"
> A rule with no duration stays armed **indefinitely**, so its waiting part keeps firing on every matching roll. To make it happen once, give it a **Rolls: 1** timer — or give the effect an **Immediate** timing, so it lands when the rule triggers instead of waiting for a roll.

**This is not an undo timer.** It controls *when the rule stops listening*. When a change it made is reversed is a separate question, answered by each effect's own duration — see below.

### What it's about — Bound variables

Optional. A place to **name a value before anything is checked**, so the rest of the rule can refer to it by name. Each row is a name plus the same targeting path every other field uses:

```
name: cultivation_tier
path: select source → aggregate (tier of the rating)
```

From then on `{cultivation_tier}` is usable in a condition, in any effect's paths, and as a plain value in a field. That is what lets a rating-scaled rule be one effect instead of five.

Rows resolve **in order**, and a later row may start from an earlier one. You cannot reuse a name the activation already binds (`{trait_setting}`, `{order}`) — the engine keeps the earlier one and the editor warns.

**Naming a value here is what makes it a variable.** A bare `{name}` in a field only works if something bound that name: a bound variable, a step's **Output name**, or the trigger or source. If nothing did, the effect is **skipped at fire time** and the outcome says so — it does not run against the literal text. When you are not sure a name exists, use `select variable` in a path instead; the picker lists what is really in scope.

### Limits — Conditions

Conditions narrow **where a rule is allowed to run**. They are not a second trigger: the trigger decides *when* the rule fires, and every condition must then pass for it to go ahead.

The picker bands them by the question they answer — **Character state**, **The moment it fires**, **This rule**, **No gate** — and a type that cannot pass where you are authoring (a source-rating gate with no trait source, a moment-reading gate at a beat boundary) is greyed out with the reason.

**A rating gate can read a pool's shape.** *Trait rating* and *Source rating* compare *some* die by default — `== d8` is true of a 1d8 trait and a 2d8 one alike. Switch the **mode** to *every die*, or to *a number of dice*, when the shape is what matters: "exactly two d8" is a gate the default cannot express, which is what keeps two rungs of a cultivation ladder apart.

Conditions also decide **availability**, but only the ones that can be judged without the moment — character state and this-rule gates. A rule those exclude shows on the sheet as *conditions not met* rather than vanishing. Gates that need the moment are only checked when the rule actually fires.

### Costs & Effects

The ordered list of what the rule does. The rows run **top to bottom**, so the order is the execution order. Add, reorder and edit them here; each effect opens its own panel. The next section covers a single effect.

### Who it reaches

Optional, and mostly for rules that hand themselves out. A row here is a **targeting path that names the owners** — the entities or instances the rule should be available to — with one of two relationships:

- **Has it** (granted) — those owners simply have the rule. Nothing is written onto them; it is resolved from live data each time it is read, so an owner that stops matching stops having it.
- **Offered** — those owners get a chip and may take the rule.

The path must land on the kind of thing your **Source** is — the row tells you which, and warns when no source is set. Several rows combine: the reach is all of them together, and **Has it** wins where both apply.

Two other things make a rule available, and they are separate from this:

- A trait definition's own possible-rule list (the hand-picked offer), shown at the bottom of this section as **Declared by**.
- Attaching it by hand in **Manage SFX**.

## Writing an effect

Each effect is one operation. Pick the **Action** first; the form then shows only the fields that action needs.

- **Timing** — when this effect lands, relative to the rule's trigger. **Immediate** applies it the moment the rule fires. The roll and outcome timings (`On Roll`, `On Result`, `On Contest Win`, …) arm it now and fire it later, which is what makes the *Listens to* and *Duration* fields matter. The boundary timings (`End of beat/scene/session`) are persisted timers.
- **Condition** — an optional gate on *this* effect alone. If it fails at apply time the effect is skipped and the rule's other effects still run. This is how five rating-gated effects can share one rule.
- **Roll dice** — on a roll-timed effect, which dice it acts on: any, the **unchosen** ones, the dice kept for the **result**, or the **effect** die.
- **The action's own inputs** — each action declares what it needs. A target, a die, an amount, a pool. Where a target is asked for you can usually pick something specific or write a **targeting path**; the path is the general answer and is worth learning.
- **Rating** — on an action that creates a trait, the rating is asked for **inside the trait instance editor**, under its rating type. The **Dice** mode is a *row*, because a rating is a row: a resource holds several dice where a challenge usually has three. Add as many as it should have. **Variable** names a rating the rule already has — `{formation_rating}` — and takes **the whole of it**, however many dice that is, so "gain this at the rating my source already has" is one word. It is offered whenever your rule has such a name. **Path** is the same thing said as a walk (`select source → navigate rating dice`) and is worth knowing for a rating nothing has named. Whatever `result` carries is the row's first die, so a one-die rating reads the same as it always did.
- **Anchored to** — where the thing this effect *creates* lives, when that is not simply the subject: a trait nested under another trait, or a trait hanging on a relationship. Only actions that make something ask this.
- **Duration (undo timer)** — how long before this change is **reverted**. Step a die up with `beat` here and it steps back down at the end of the beat. A duration is offered only where reversing makes sense: a change to a die in a *pool* is gone at the next roll anyway, so it is not offered there.
- **Negative** — for trait-granting actions, whether what is granted is a complication rather than a benefit.
- **Output name** — names what this effect produced, so a later effect can reach it with `select variable`. Only offered on actions that produce something.
- **Activate effect** — under the form, a **test run**: it applies *this one effect* to the entity you are acting as and tells you what it did — what changed, how many questions it *would* ask, and where the entity now is. It broadcasts nothing, so a run never pops a picker on anyone else's screen; and it runs the effect as you have it now, which is the point. Firing the rule would run its neighbours too and answer a different question.

> [!tip] Two clocks, easy to confuse
> The rule's own **Duration** is a *listening window*: how long the rule stays armed for its waiting part. An **effect's** Duration is an *undo timer*: when the change it made is reversed. They are independent — a rule can stop listening after one roll while the change it made lasts the scene.

## Targeting paths

A path is how you say *which* thing an effect acts on, when the answer is not a single named object. It is an ordered pipeline of steps that resolves to one value or a collection of them, and the builder only offers steps that are legal from where the path currently stands.

The steps you will use:

| Step | What it does |
|---|---|
| **Select** | Start from a collection — `self`, `rolled_dice`, `occupants`, `locations`, `entities`, `self_traitsettings`, `sfxs` — or from the rule's `source`, or from a named variable. Only the first step selects. |
| **Filter** | Keep the items whose field matches — `polarity == negative`, `rating_type == static`, `tags contains fire`. |
| **Navigate** | Hop to something related: a trait instance to its owner, an entity to its location, a pool to its dice. |
| **Aggregate** | Collapse the collection: `count`, a `random` sample, the highest or lowest **element**, or a `tier`. |
| **Pick one thing** | Name one specific object directly. This is the only step that uses an id. |
| **Choose** | Ask the player to pick. Not offered inside a condition — there is nobody to answer. |
| **Evaluate** | End a condition path with a true/false test: does anything exist, or does a count compare. |

Three habits make paths work:

- **No ids.** Everywhere else you name things by name. A `Filter` offers the field's real values, and only a *Pick one thing* step takes an id. An id you see on a card is a sign the effect points at something that no longer exists.
- **Filter on the list field's own operator.** A field that *is* a list (`tags`, `universes`, `known_to`) is matched with `contains` / `not contains`, not `==` or `in` — the wrong one is silently always false. The picker only offers what the field can answer.
- **A type test narrows the path.** `entity.type == location` proves the thing is a location, so location-only steps (`occupants`) become available after it. That is what lets you write *the owner of this trait, if the owner is a place, and then everyone inside it*.

### Naming a step

Any producing step can take an **Output name**. The name then works in three places: a later step can start from it with `select variable`, a field can use it as `{name}`, and the card line uses the name instead of the whole pipeline — which is how a long path becomes a short sentence. Name steps for the reader: `d4_traits` reads better than `filtered_1`.

A name declared in **Bound variables** does the same job from the other end. Reach for an output name when you are already writing the path and want to remember a step; reach for a bound variable when the rule is *about* that value and a condition needs to read it too.

## A worked example — Hinder

**Hinder** (`sfx-hinder`) is a small real rule: *play a trait at d4, and gain 1 razmerit for the trouble.* Its card reads:

> Activated: play the trait instance this SFX sits on as d4; gain 1 razmerit.

Here it is, field by field.

1. **Name** `Hinder`, **Description** `Play as d4, gain 1 razmerit.`
2. **Source** → **Trait setting**. The rule lives on a trait instance, so `{trait_setting}` is in scope and the rule can only be attached to a trait instance.
3. **Trigger** → **Manual**. It becomes a button on that trait's card.
4. **Effects** → two rows, both `Immediate`:
   - **Play as Rating**, target path `select source`, die `d4`. The path starts from the rule's own source, so the trait it plays is the trait it lives on — the rule needs no other input.
   - **Earn Razmerit**, amount `1`, Entity `select self`. The razmerit goes to whoever pressed the button.

That is the whole rule. Nothing listens for a roll, so the panel shows no *Listens to* and no *Duration*; nothing is worth naming, so there are no bound variables; and it is attached by hand, so *Who it reaches* stays empty.

To put it in the world: open **Manage SFX**, filter by *Trait instance*, pick the trait it belongs to, and attach it. It now shows as a button on that trait's card.

## Patterns worth knowing

**A passive that watches every roll.** Trigger `On Session Start` with an effect timed `On Roll`. It arms once for the whole table — including characters who join later — and the *Listens to* field stays on its default, which for a session-start rule is everyone.

**A rule that lives on a place.** Attach it to the location in **Manage SFX** and set **Source** to `Location`. It applies to the entities inside, and inside its sub-locations, however deep — nothing is written onto them, so walking out ends it by itself. A path can walk straight to the people there with `select source → occupants`.

**Spawning a mob from a template.** Use **Spawn Entity**: it makes a *copy* of an entity — its traits, its edges and its set settings — and leaves the original alone, so you can throw eight bandits at the table without touching the bandit you authored. Give the effect a **Template** (a path, or a **Choose** step so the table picks), and optionally a **Spawn At** place; with neither, the copy stands wherever the rule is activated — which for a rule on the GM bucket is the place you are looking at. Name it if you want to; otherwise it keeps the template's name. The copy is nobody's unless you fill in **Owner**, so a spawned mob is neutral by default.

**Teaching — handing a rule to someone.** Use the **Grant SFX** action: the rule to grant is itself a targeting path seeded from the registry (`select sfxs`), and the **Owner** is whatever the grant should land on. It is a *path*, so it reaches more than a character:

- **a character or place** — `select source → occupants → choose` hands the rule to whoever is there;
- **a trait instance** — the sect-training case: a technique lands on the trait it is studied on, so it travels with that trait and not with the person holding it;
- **a trait set instance** — the whole set as a unit;
- **a trait definition** — the rule becomes one of that trait's **default** rules: every future holder is offered it, and everyone who already holds it gains it now. This is the widest form: write the rule once, on the trait, and it follows the trait everywhere.

Granting obeys the same gate as attaching in **Manage SFX**: a rule that declares a source can only land on a matching surface, and a rule with an acquire condition still has to satisfy it. So a `Location`-sourced rule granted to a character is refused — by name, not silently.

**An airport with a departure board.** A portal normally asks *where to?* — its effect has a **Choose** step, and the picker opens when someone steps through. If you would rather it just go somewhere, **Set Portal Destination** points the portal at a place and the next step through takes it, without asking. Author the pointing as its own rule: trigger **On Location Change**, source **Location** (the airport), one effect whose **Portal** is the edge you want to point and whose **Destination** is where that flight goes.

- The board belongs to **that portal**, not to the airport: two doors out of one hall are two boards.
- It is **session state** — nothing is written to the portal itself, so a restart forgets the board and your content is never rewritten by play. Everyone at the table sees the same board, because it lives on the server.
- With no board set, a portal goes where it points, exactly as before. You can mix: some portals on a board, others still asking.
- To *rotate* the board, have the arrival rule set it again each time — that is all "rotating" is. Set it once and it stays set until something sets it again.

**Offering a rule to many owners at once.** Author a row under **Who it reaches** with the *Offered* relationship and a path naming the owners — for instance every trait in a set, reached by going from the definition to its instances. The owners get the chip; taking it attaches the rule to them.

**Writing the rule from the trait that grants it.** A trait's **Possible SFXs** list (in **Manage Traits**) is the *static* half of reach: the rules a holder of that trait can buy. That list authors as well as picks — **+ New SFX** opens the rule editor on top of the trait and attaches the result to it as you create it, so a technique is written from the trait it belongs to instead of being found again later in Manage SFX. Tick **✓** on the row if every holder should get it automatically; leave it ✗ and the rule is offered, not granted.

**Writing the rule from the thing that owns it.** Any entity's editor — a place, a faction, a GMC, an asset, a universe — carries an **SFX** section listing the rules attached to *it*, with **+ Add SFX** to attach an existing one and **+ New SFX** to write one there and then. This is the list the sheet shows for a character and the list a place spends when someone walks in. A place also has **Fires on arrival** above it: that is the narrower view — its arrival rules *plus* those it inherits from the places around it — so a rule attached here appears there too once its trigger fires on arrival, and a rule inherited from a parent appears only there.

## How your rule reads

The top of the panel shows a **card line**: your rule in plain language, recomputed as you edit. The d4 Bonus rule reads:

> At the start of each session: whenever a roll happens, for each d4 trait instance you rolled, gain 1 razmerit.

Read it as a sanity check. It is derived from what you actually authored — trigger, then conditions, then effects — not from the Description field. **If the card does not say what you meant, the rule probably does not do what you meant.** Two things it is especially good at catching:

- A limit says *which* limit: *increase the **total** dice limit* is not the same as the effect dice limit.
- An effect scoped to some of the dice says so: *for each unchosen die, …*.

Naming a step shortens it. If the card has grown into a paragraph, name the step where the meaning becomes clear and the sentence will shorten itself.

## Gotchas

- **A `{name}` must be bound by something.** Bound variable, a step's output name, or what the trigger and source provide. Otherwise the effect is skipped and the outcome notes it — nothing runs against the literal text. When in doubt, use `select variable` and let the picker show you what is really in scope.
- **Trigger is not Timing.** The trigger says when the rule wakes up; each effect's timing says when that effect lands. A `Manual` rule usually has `Immediate` effects. A passive pairs a boundary trigger with a roll-timed effect.
- **Source must match where you attach it.** A rule that never fires is often a `Trait setting` rule attached to a character, or a `Location` rule attached to an entity.
- **A roll-family trigger is gated by the source.** A trait-sourced rule fires only while a die from that instance is in the pool.
- **Empty duration means indefinite**, not "once".
- **Effect duration is an undo timer; rule duration is a listening window.** Different clocks.
- **Effects run in order.** If one needs a choice, the effects after it wait for that choice.
- **A gate can only read what its moment supplies.** A roll-timed effect brings the roll; a manual activation brings the phase and stakes; a beat, scene or session boundary brings nothing at all. The picker greys out conditions that could never pass where you are.
- **A condition on availability is not a condition on firing.** Character-state gates also hide the rule on the sheet; moment gates are only checked when it fires.

## Related

- [[SFX Reference]] — every trigger, condition, source, step and effect action
- [[SFX and Effects]] — the design overview of rules and exceptions
- [[Targeting Model]] — how a path is resolved and type-checked
- [[SFX Source Model]] — what "Lives on" decides
- [[Dynamic SFX Reach]] — how a rule becomes available to the owners it reaches
- [[Roll Table and Life Path Authoring]] — the other authoring surfaces
- [[User Manual]] — the player/GM how-to index

---
title: Elements and Spiritual Roots
date: 2026-09-12
tags:
  - transversal
  - game-design
  - sfx
  - effects
  - elements
  - cultivation
aliases:
  - Elemental Interaction
  - Spiritual Roots
  - Five Elements
status: proposal
---

# Elements and Spiritual Roots

How an element attaches to a technique, a place or a person; how the five-element
cycle turns into effects; and which of the pieces already exist. Written down
after a long design conversation so the reasoning outlives the chat — the
verified findings below were checked against the running app, not recalled.

Related: [[SFX and Effects]], [[Place-Owned Rules]], [[Targeting Model]],
[[SFX Source Model]], [[SFX Authoring]].

## The idea, in the author's terms

- A cultivator has **spiritual roots**: one element (pure), two (dual), or four
  to five (false), each at a **rating**. In the old app these were elemental
  sub-traits of Spiritual Power — a d12 single root, 2d10 dual root — so the
  character had an actual d10 wood they could use to power their techniques.
  A root can also be **negative**: a d6 negative water root.
- **Techniques carry an element.** Using a technique that matches one of your
  roots **empowers** it.
- Elements interact: **suppression** and **generation** (the five-element cycle),
  both in contests and against a *place's* element — the Heartflame Mire has
  fire and hurts wood-aspected cultivators.
- **Qi can be aspected**, so aspectedness is a state a rule can change, not a
  fixed label.

## The model

**An element is a tag on the trait's definition.** Techniques are tagged
(`wood`, `fire`, …), and `tags contains <element>` is already a matchable filter
on both trait definitions and trait instances. One rule for everything that can
carry an element:

| Carrier | Where the element lives | Why |
|---|---|---|
| Technique | tag on the **trait definition** | intrinsic — every instance of "Verdant Palm" is wood, with no second trait to keep in sync |
| Place | a **trait instance** on the location | situational — a place's element can change, be suppressed, be contested |
| Person | the **root sub-traits** under Spiritual Power | mutable state, and the rating is the thing that gets added to a pool |

**A spiritual root is a set of element trait instances under Spiritual Power**
(`trait-138364703`), one instance per element:

- **element** → the definition's tag
- **rating** → the instance's dice (d10 fire, d8 metal, d6 negative water = three
  instances)
- **positive/negative** → the instance's `polarity`
- **pure / dual / false** → a *reading* of how many instances there are, never an
  authored field. The content sets the ratings; the model counts.

Sub-traits (a trait instance whose parent is another trait instance —
`parent_traitsetting_id`, `from_type: "traitsetting"`) are the right home for
roots specifically: a root is a *facet of* Spiritual Power, not an independent
thing you hold. The sheet already creates them.

**The cycle is not data. It is ten rules** — five suppressing, five generating —
one per relation, each with a static element filter on each side. A cycle table
in code would hardcode a cosmology; this project's habit is content over code,
and one rule per relation also lets an element behave differently from its
siblings.

## The mechanics, as rules

### 1. A matching technique is empowered

The condition is a path, and it **traced valid** against the live app:

```
select rolled_dice → navigate traitsetting      (the technique that gave the die)
  → navigate entity                             (its owner)
  → navigate traitsettings                      (what they hold)
  → filter tags contains wood
  → filter polarity == positive
```

Reads as: *a die in this roll came from a wood technique whose owner has a
positive wood root.* Note the polarity filter — without it a **d6 negative water
root would empower water techniques by accident**. With it, the negative root
instead feeds a second rule (the complication one), which is the dynamic the
author described.

The empower itself is already built: `modify_pool → add_trait_rating` adds a
trait instance's rating dice to a pool.

### 2. Elements against each other (the cycle)

**Conditions are ANDed, and each condition gets its own path** — which is how two
sides get compared without any value-to-value comparison. One rule per relation:

```
condition ①  select <my dice>      → traitsetting → filter tags contains fire
condition ②  select <their dice>   → traitsetting → filter tags contains metal
effect:      step_up / step_down on the played technique
```

### 3. A place's element

If the rule *is* the place's fire (a rule owned by Heartflame Mire, reaching its
occupants, testing `self → traitsettings → tags contains wood`), that works with
what is built — place scope, tag filters, `step_down`, the place strip.

If the place's element must be **readable data** — so several rules can read it,
and it can be suppressed or contested — it needs the location → traitsettings
edge (see below).

## What is verified, and what is missing

Checked through the live tracer (`traceTargetSpec`) and the running app:

**Works today.**
- `rolled_dice → traitsetting → tags contains <element>` — valid.
- `rolled_dice → traitsetting → entity → traitsettings → tags → polarity` — valid
  (the empower match above).
- `self → traitsettings → tags contains <element>` — valid.
- Tag matching on traits and trait instances; `polarity`, `rating`, `rating_type`
  as filters; `step_up`/`step_down`; `add_trait_rating`; the global-passive
  pattern (`on_session_start` + roll-timing effect + global scope, proven by
  *One-Trick* and *d4 Bonus*).

**Missing — four pieces, smallest first.**

1. **`traitsetting → its sub-traits` has no edge.** A path cannot reach
   sub-traits at all, so roots-as-sub-traits are *decorative* until this exists:
   a rule can find a root only by its trait definition, never "under my Spiritual
   Power". One catalog edge plus one repo read.
2. **A fire site for "the pool changed".** `PUT /api/v1/locations/{loc}/pools/{entity}`
   is the real server moment — it already persists the assembled pool with every
   die's `ts_id` — and it currently only **broadcasts**; it fires no SFX event.
   One `fire_state_sfx` call makes the moment listenable. It fires on *every*
   pool change, so it should only fire while an opposition exists.
3. **The opposition is not in the fire context.** The contest tracker records the
   opponent (`set_opposition`) and `contest_entity_opponent` reaches win/loss/give-in
   events — but not the pool-change moment. Needed for `condition ②` above.
4. **The opposition's dice are not in the fire context** either — the scene store
   holds them (`get_pool(location, opponent)`), keyed exactly like your own. They
   need to ride the event as a second dice collection so a path can walk into them.

**Also relevant, verified earlier:** `select variable {contest_entity_opponent}`
fails today — trigger variables are declared but never bound as typed seeds, so a
path cannot *start* from the other party of an event. Binding them would be a
second way to reach the opponent (and would help every two-party rule in the
game, not just elements).

**And one boundary-trigger trap:** `on_session_start` is a boundary trigger and
carries **no fire-time context**, so a roll-reading path cannot hang on the SFX's
own conditions there. It goes on the **effect's** conditions — which *are*
evaluated when the armed effect fires. That is not a workaround; it is where the
existing passives put it.

## Open decisions

1. **Does the pool-change rule fire on every pool save, or only when a *technique*
   die is added?** Simpler and noisier vs. needs the die's role (already on the
   pool).
2. **Do roots live as sub-traits of Spiritual Power (nesting, parent-aware rules)
   or as a trait set?** Sub-traits match the old app and the fiction; they need
   piece 1.
3. **Does a root's *rating* enter the pool** (add_trait_rating) or only modify the
   technique (step_up)? The author's description says both at different moments.
4. **The place's element as data** — worth the location edge, or does the rule
   suffice?

## Suggested order

1. Sub-trait edge (unblocks roots; one row + one read; independent of the rest).
2. The pool-change fire site + the opponent and their dice in its context
   (unblocks the cycle).
3. Author **fire-suppresses-metal** end to end as the proof, then the other nine.

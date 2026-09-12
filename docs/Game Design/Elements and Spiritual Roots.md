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
status: partly implemented  # 4 gaps landed 2026-09-12; the rules are the author's
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
  → filter trait_id == trait-138364703           (their Spiritual Power)
  → navigate subtraits                          (its elemental roots)
  → filter tags contains wood
  → filter polarity == positive
```

Reads as: *a die in this roll came from a wood technique whose owner has a
positive wood root.* The two extra hops are the shape of a root: it is reached
**through** Spiritual Power, because `entity → traitsettings` deliberately leaves
nested instances out (a root is a facet of the trait it hangs from, not a thing
the character holds). Note the polarity filter too — without it a **d6 negative
water root would empower water techniques by accident**. With it, the negative
root instead feeds a second rule (the complication one), which is the dynamic
the author described.

The empower itself is already built: `modify_pool → add_trait_rating` adds a
trait instance's rating dice to a pool.

### 2. Elements against each other (the cycle)

**Conditions are ANDed, and each condition gets its own path** — which is how two
sides get compared without any value-to-value comparison. One rule per relation:

```
condition ①  select rolled_dice    → traitsetting → filter tags contains fire
condition ②  select opposing_dice  → traitsetting → filter tags contains metal
effect:      step_up / step_down on the played technique
```

Both seeds are real as of 2026-09-12: they are the actor's assembled pool and
the other side's, at the moment a pool is saved (`on_pool_change`). Both
conditions must pass, so the two sides are compared without any step that
compares one value to another.

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
- `rolled_dice → traitsetting → entity → traitsettings → filter trait_id ==
  <Spiritual Power> → subtraits → tags / polarity` — valid, live. That is the
  empower match: *a die in this roll came from a wood technique whose owner has a
  positive wood root*.
- `opposing_dice → traitsetting → tags contains <element>` and
  `rolled_dice → …` side by side — valid, live. This is `condition ①` and
  `condition ②` of the cycle, both expressible.
- `self → traitsettings → tags contains <element>`; tag matching on traits and
  instances; `polarity`, `rating`, `rating_type` as filters; `step_up`/
  `step_down`; `add_trait_rating`; the global-passive pattern
  (`on_session_start` + roll-timing effect + global scope, proven by *One-Trick*
  and *d4 Bonus*).

**The four pieces landed 2026-09-12** (`73caf9e`, `ba1182c`, `134e9f7`):

1. **`traitsetting → subtraits` is an edge.** Roots are reachable *from their
   parent*, which is the only correct way: they are deliberately absent from
   `entity → traitsettings` (that read filters `from_type != 'traitsetting'`), so
   a root is never mistaken for something the entity holds on its own.
2. **The pool save is a listenable moment.** `PUT /api/v1/locations/{loc}/pools/{entity}`
   fires `pool_changed` → the new **`on_pool_change`** trigger ("Whenever your
   dice pool changes"). It fires on *every* save, not only contested ones — the
   moment is the moment, and a rule that wants a contest gates on the opposition
   being there.
3. **The opposition is in that context** — `contest_entity_opponent`, resolved
   from the contest tracker (either side's save works; the defendant sees the
   challenger).
4. **Their dice ride with it** as `opposing_rolls`, seeded into the new
   **`opposing_dice`** collection — so a path can *start* from the other side,
   not merely be compared against. The card keeps the parties apart: a hop from a
   dice seed reads *you rolled* / *they rolled* by which seed it came from.

**Landed after them, 2026-09-12 (later the same day): the activation's own names
are path seeds.** `{contest_entity_opponent}` and the source token
(`{trait_setting}`, `{location}`) were authorable but never *bound*, so a path
could not start from either — the wizard had nothing to offer. Now one
declaration types them (`target_catalog.scope_seed_names`) and the engine binds
the same names from the live event, so `select variable {contest_entity_opponent}
→ navigate location` (or `{trait_setting} → navigate entity`) resolves. A name the
moment does not carry is left unbound, and a deferred effect keeps the seeds it
armed with.

**Still open.**
- **Open decision 4** (below): a place's element as *readable data* — the
  `location → traitsettings` edge.
- **Decision 4 below is unanswered**, so a place's element is readable only by
  the rule that *is* the place's element, not as data on the location.

**And one boundary-trigger trap:** `on_session_start` is a boundary trigger and
carries **no fire-time context**, so a roll-reading path cannot hang on the SFX's
own conditions there. It goes on the **effect's** conditions — which *are*
evaluated when the armed effect fires. That is not a workaround; it is where the
existing passives put it.

## Open decisions

1. **Does the pool-change rule fire on every pool save, or only when a *technique*
   die is added?** *(Answered by construction, 2026-09-12: the **event** fires on
   every save — the moment is the moment — and the **rule** narrows itself. A
   path can filter the dice it reads (`source_kind`, `role`, `ts_id`), so "only
   when a technique die is in the pool" is an authoring choice, not a mechanism
   one. What is still the author's call is whether their rules bother.)*
2. **Do roots live as sub-traits of Spiritual Power (nesting, parent-aware rules)
   or as a trait set?** *(Answered by the author: sub-traits. Piece 1 landed, so
   a rule can now say "under my Spiritual Power" literally.)*
3. **Does a root's *rating* enter the pool** (`add_trait_rating`) or only modify
   the technique (`step_up`)? Both are buildable today; the choice is content.
4. **The place's element as data** — worth the `location → traitsettings` edge, or
   does the rule suffice? Still open: today a place's element works as *the rule
   the place owns* (place scope + tag filter + `step_down`, all built), but it is
   not readable data several rules could share, suppress or contest.

## Suggested order

1. ~~Sub-trait edge (unblocks roots).~~ **Landed `73caf9e`.**
2. ~~The pool-change fire site + the opponent and their dice in its context.~~
   **Landed `ba1182c` + `134e9f7`.**
3. **Author *fire-suppresses-metal* end to end as the proof**, then the other
   nine — this is the author's, not the platform's: the machine is now able to
   express it, and nothing has been written into their world.
4. (New, optional) **Bind trigger variables as typed seeds** — the second route
   to the other party, for every two-party rule.

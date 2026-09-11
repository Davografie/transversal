---
title: Place-Owned Rules
date: 2026-09-11
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
  - proposal
aliases:
  - Audience-Scoped SFX
  - Lair Actions
  - Location SFX
status: partly implemented
---

# Place-Owned Rules

A rule that lives on a *thing in the world* — a location, a faction, an asset, a
portal — and reaches whoever that thing is about. Today an SFX can only be owned
by the entity it fires for, which is why attaching one to Azure Dawn silently
does nothing. This is the design for the other case.

Related: [[Effect Holders and Owners]] (the owner/source vocabulary this
extends), [[SFX Source Model]], [[Targeting Model]], [[Passive Rules and
Multi-Target References]] (passive arming), [[Portal Transversal Effect]].

## The gap, concretely

Availability is computed for the **actor**: their own SFX, their active
projection's, their trait instances' and trait sets', plus the `table` and `gm`
buckets. Nothing else is consulted — not the room they are standing in, not the
thing they are holding, not the portal they just walked through.

So "anyone who steps onto sect grounds gets access to the Azure Dawn life path"
cannot be authored on the location. The Entity owner list *offers* all 410
locations, the SFX validates cleanly, and it never fires — a silent no-op
(`validate_sfx` only warns when a declared `source_kind` matches no owner, and
the location does own it).

The workaround is the `table` bucket plus an `At location` condition. It works,
but it is a global rule wearing a place's name: every entity pays for it on every
event, every roll and every sheet refresh (see **Cost** below), and one bucket
accumulates every such rule in the game.

## The one idea: separate owner from audience

- **Owner** — where the rule lives and is authored (unchanged concept).
- **Audience** — who it is *about*: the entities it can fire for.

Today they are the same thing by construction: a rule on your trait instance is
about you. Place-owned rules break that identity, and the break is the whole
feature.

The audience is **resolved per owner type**, because "who is this about?" is a
different question for each kind of thing:

| Owner | Audience | Reads as |
|---|---|---|
| Location | its occupants (and sub-location occupants, if authored to include them) | *everyone standing here* |
| Universe | entities currently in it | *everyone in the Three Realms* |
| Faction | its members | *every member* |
| Asset | its owner | *whoever holds it* |
| Projection | the entity it is the active body of | *whoever wears this life* |
| Relation (`transversal` / portal) | entities at either endpoint — or just the traverser, when the rule is traversal-triggered | *whoever crosses* |
| Entity / trait instance / trait set / table / gm | itself / itself / itself / everyone / GM-context only | (unchanged) |

The audience rule is *structure*, not authoring: an author says "this rule lives
on this place", and the type decides who it reaches. Where a type has more than
one sensible answer (a location's sub-locations; a portal's two ends), the
narrower one is the default and the other is an authoring choice.

## Two modes

They are the same mechanic at different moments, and both fall out of the
audience resolution:

- **Arrival** — fires once, on the event that brings an audience member into
  relation with the owner: *stepping onto the grounds* (Azure Dawn → grant the
  life path), *entering the room* (a hazard), *crossing the portal*. Uses the
  existing event triggers, and can gate on **Arrival kind** so a GM placement
  does not count as stepping foot.
- **Standing** — held while the relation lasts, and offered while it does: the
  Formation trait the author described, where a rule sitting on a location reacts
  to *anyone using Movement while at that location*, or a lair action a GM
  activates because the party is in the lair. This is passive arming
  ([[Passive Rules and Multi-Target References]]) with the place as the owner.

> [!note] The place is the source, the audience member is the subject
> A place-owned rule already has both halves in the model. The owner resolves as
> the **source** (`select source`, `SOURCE_RATING`, and the card's *this place*),
> while the audience member is the **subject/actor** the conditions test and the
> effects land on by default. That is exactly the split `source_kind` +
> `Effect.entity`/subject already implement — this feature adds *who*, not a new
> axis.

## Cost — and why this is also the fix

Availability runs on every state event, every roll and every "what can I do"
query. It used to read each candidate's record from the database, which made the
cost linear in the whole catalogue; that half is now cached and narrowed
(measured live: 18 reads → 0, ~15 ms → ~5 ms per call).

What caching does **not** fix is the algorithmic half: a `table` bucket holding
5000 rules still walks 5000 candidates in memory for *every* entity, because
scoping by place is the only thing that can shrink the candidate set. Audience
resolution is what does it:

- Today, with 5000 rules on `table`: every entity, every event, walks all 5000.
- Place-owned: Azure Dawn's twenty rules are candidates only for the entities
  *at* Azure Dawn. The other 870 entities pay nothing for them.

The cost becomes proportional to the room, not the world — which is what makes a
world full of lair actions, faction rules and portal effects affordable.

## What it takes (rough shape)

1. ~~**Availability grows a place scope.**~~ **Landed 2026-09-11 for locations:**
   availability now also asks which of the places above the entity (its own
   location and its ancestors) carry rules, and offers those. Read-time —
   nothing is written onto the occupant, so walking out ends the rule by itself.
   The scope query returns only the places that *own* rules, so a world with no
   place-owned rules costs one empty read; and it follows `super` edges upward
   only, so a portal does not drag another location into scope. This is what
   makes all three of the author's cases reachable: *put the rule on the place*.
2. **A source kind + catalog element per new owner type**, so `select source`,
   targeting paths and card text can name the place ("this location", "this
   portal"). **Still open** — for now a place-owned rule resolves like any other
   entity-owned one.
3. **Authoring surfaces**: the owner panel already lists entities (locations
   included) and attaching an SFX to one now does what it looks like it does.
4. **Validation honesty**, in both directions: until a type is supported, a rule
   attached to it should warn that it cannot fire; once supported, it should not.
   **Partly stale now** — locations fire, so the old silent no-op is gone.

## Open questions (need the author)

1. **Standing rules on the sheet** — does a place's rule appear in the character
   sheet's SFX list while they are there, or in a separate "the place offers…"
   row? (It changes what "I have this SFX" means at the table.)
2. **Arrival breadth** — should an arrival rule fire for *every* arrival by
   default, or should the platform default to excluding GM placements? (The
   **Arrival kind** condition can express either; this is about the default.)
3. **Projection ownership** — is a projection-owned rule about the entity
   wearing it, or about everyone at the body's location? (The two readings
   suggest the projection is really "the body" — in which case a location rule
   already covers the room.)
4. **Audience authoring** — fixed by type (recommended, simple), or authorable
   as a targeting path ("who it applies to"), as `attune` already does?
5. **Leaving** — does a standing rule need an explicit exit moment (the author's
   "walk away and the portal re-rolls")? If yes, departure is the mirror of
   arrival and needs the same audience resolution at the *previous* location.

## Sequencing

1. ~~**Locations, arrival-only, audience = occupants.**~~ **Landed 2026-09-11**, as
   *availability* rather than arrival-only: a location's rules reach the entities
   in it (and in its sub-locations) the whole time they are there — which covers
   both the arrival case (Azure Dawn's life path) and the standing case (the
   Formation trait, a lair action). The arrival/mode distinction now lives in how
   the author writes the rule (a trigger + conditions), not in the mechanism.
2. **Standing**, with the sheet surface decided (open question 1). **Partially
   answered by the author's read-time reading:** the rule is simply in the
   occupant's list while they are there.
3. **The other owner types** — asset, faction, universe, projection — each a row
   in the table above.
4. **Relations/portals**, reusing the same seam for the portal brief (randomised
   destination + approach/departure).

Steps 1 and 4 are the two the author is blocked on; the middle ones are content
enablement rather than new mechanism.

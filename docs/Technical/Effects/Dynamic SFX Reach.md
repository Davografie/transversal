---
title: Dynamic SFX Reach
date: 2026-09-26
tags:
  - transversal
  - effects
  - sfx
  - targeting
aliases:
  - Acquire Path Selector
  - SFX Reach Declarations
  - Granted and Offered
---

# Dynamic SFX Reach

> [!abstract] The one idea
> A rule declares **who it reaches** with one or more **targeting paths**, each
> carrying its own flavour: **granted** (they simply have it) or **offered** (they
> may learn it). Resolved against live data at read time. Nothing is written onto
> anyone.

Agreed with the author 2026-09-26, replacing a first attempt (`SFX.offer_traitsets`,
a static list of trait-set ids — [[B228]]) that was the wrong shape: static where
this is dynamic.

## Vocabulary

| Term | Meaning |
|---|---|
| **Source** ("Lives on") | The kind of thing the rule lives on. Declares **the element the reach path must land on**, and stays the seed the other fields start from (`select source` = the owner). |
| **Reach path** | A targeting path (the ordinary wizard) that **yields the owners** — *selectors*, not gates. |
| **Granted** | Every resolved owner simply *has* the rule: it is available from them, fires from them, no learn-chip. |
| **Offered** | Every resolved owner is *offered* the rule: a learn-chip; taking it attaches the rule to that instance (as `addOwnerSfx` does today). |
| **Exposed surface** | An owner kind with a UI surface: trait setting, trait-set setting, entity, location, projection, table, gm. |

## The model

- A rule holds a **list of reach declarations**, each `{ path, flavour }`. One rule
  can be granted from one surface and offered by another.
- **`Source` must be the element the path lands on.** A path that ends anywhere
  else is not a reach declaration.
- **Granted** and **offered** are the two relationships [[B131]] already has *per
  trait definition* — `defaultSfxIds` is the grant, `possibleSfxIds` is the offer.
  The hand-picked lists **stay** and keep those fixed meanings; the paths are their
  dynamic form, and availability reads both.
- **The rule-level `implicit` flag retires.** Flavour lives on each path. A trait's
  two fields are separate fields, so each already carries its flavour.
- **There is no separate gate.** The old per-candidate reading of the acquire path
  ("does this resolve *for this owner*?") is gone; it was a gate for a candidate
  list that the selector now generates itself.

## Worked examples

| The sentence | Source | Path | Flavour |
|---|---|---|---|
| all traits of the assets trait set | Trait setting | `select traits → filter traitset_id == ts-3 → navigate traitsettings` | offered |
| all traits tagged `utility` | Trait setting | `select traits → filter tags contains utility → navigate traitsettings` | offered |
| all locations with ≥3 occupants | Location | `select locations` + *condition* `select source → navigate occupants → evaluate count >= 3` | granted |
| all traitsets with limit 2 | Trait setting | `select traitsets → filter limit == 2 → navigate traits → navigate traitsettings` | offered |
| Azure Dawn's occupants (the v2 of `sfx-sect-cultivation`) | Entity | `select locations → filter id == loc-74560187 → navigate occupants` | granted |

- **A definition cannot be a reach target.** `trait` and `traitset` definitions have
  no exposed surface, so the path takes an **extra step from the definition to its
  instances** — which is the `traitsettings` hop in the table above and the one
  thing missing from the catalog today.
- **Crowd-count is a condition, not a criterion** (the author's resolution). The
  path selects *all* locations; a condition narrows to ≥3 occupants. Consequence,
  and it is intended: such membership is **evaluated**, so a place that fills up
  gains the rule and stops qualifying again — it is live, not a one-time grant.

## What is missing to build it

1. ~~**`trait → traitsettings`**~~ **Landed 2026-09-26.** One catalog edge
   (`target_catalog.EDGES`, `("traitsettings", "trait", …)` — the mirror of the
   existing `traitsetting → trait` hop) plus its registration in
   `target_resolver.register_default_edges`. The repo read it needs **already
   existed**: `get_traitsettings_by_trait`, the same read
   `propagate_trait_default_sfx` uses to provision a trait's defaults onto its
   instances. There is no global `traitsettings` collection (only
   `self_traitsettings`), so this edge is the only route from a definition to its
   instances.
   - **What it measures live (the number step 3 turns on):** the author's "all
     traits of the assets set" sentence traces clean
     (`trait/many → trait/many → traitsetting/many`) and resolves to **889**
     instances across **261** owners — **not** the **881** the reverted offer
     reached. The difference is exactly the **8 sub-trait instances** of assets
     traits: items nested under a container trait (a jade slip, a manual, a melee
     weapon, a set of clothes, a tool), on one GMC and one CHARACTER. **The author
     has confirmed this is right** — a nested instance is reached iff its *own*
     trait is in the selection (decision 4), which is what the edge does, since the
     filter runs on definitions before the hop.
   - **Tags go through the same hop:** "all traits tagged `utility`" (14
     definitions) resolves to **164** instances.
2. **The reach declarations on `SFX`** — a list of `{spec, flavour}`, replacing
   `acquire_spec`/`acquireSpec` (one field) and `offer_traitsets` (the wrong
   attempt). Domain → schema → resolvers → converter → MCP document.
3. **Availability and the chip** read both the hand-picked lists and the
   declarations. Granted reach means "available from them"; offered reach means
   "a learn-chip for them".
4. **Editor** — a list of reach declarations: each a path (`PathField`, so it opens
   in a child panel) plus a granted/offered control. Replaces the "Offered by"
   trait-set picker and the single "Acquire path" field.
5. **Later, and explicitly deferred by the author:** `traitset.limit` as a catalog
   field, and validating/filtering on trait-definition and trait-instance tags.
   (Definition and instance `tags` *do* exist as fields; `traitset` exposes only
   `id`, `name`, `universes`, so `limit` is a one-line catalog addition.)

## Cost (the one engineering risk)

A reach declaration is a **set-producing** query where the old offer was a lookup.
The read must not become "walk every owner and run a path". Proposal: resolve each
declaration **once** into a set of owner ids, cached with the SFX records (same
invalidation, already wired), and membership-test against it. Sizes are modest —
`ts-3` is 65 definitions → **889** trait-setting instances, `utility` is 14
definitions → **164** — and conditions layer on top exactly as they do now.

**Decision 3 makes this a measurement, not an assumption:** the author does not know
how intensive it will be, so the implementation measures the ownership read against
the live data (a rule with the assets declaration, resolving for an actor) **before**
the shape is trusted, and records the number here. Revisit if a declaration is
authored against a much larger collection — the whole registry is only 808 traits.

## Migration and revert plan

**The revert is DONE** (`3af9873f`, 2026-09-26) — 2065 pass, 0 failures, frontend
builds. `sfx-gift` has no reach until the selectors land; the author accepted that.
**The `trait → traitsettings` edge is DONE too** (same day — see §What is missing,
item 1); **next is the reach declarations on `SFX` itself (item 2).**

What came out of `92babf6c` and its follow-ups, and what deliberately survived:

- **Out:** `SFX.offer_traitsets` (domain, `SfxRef`/`SfxInput`/`SfxUpdateInput`,
  create/update resolvers, `_sfx_ref`), the `acquireTraitsets`-style reads in
  `sfx_owner.traitset_offer_index` / `trait_traitset_id` and their caches, the
  `acquirableSfxIds` and `get_available_sfx_ids` offer reads, the MCP document
  field, the "Offered by" picker and its `useSfxEdit` wiring, and the
  offer-specific tests.
- **Kept:** the **`validateSfx` warnings** (the no-offer one reworded to *"no trait
  lists this rule as possible"*, and it becomes *"this rule reaches nobody"* when the
  selectors land), the **validate-on-open** fix (`69bcf611`), `implicit` surviving
  the `validateSfx` draft conversion, and the `invalidate_sfx_cache()` calls being
  unconditional (correct regardless).
- **Live data:** clear the stored key on `sfx-gift` so no ghost field lingers, and
  keep its `source_kind` fixed at `trait_setting` (it had drifted to `table`, under
  which the rule could not be taken at all — see [[B228]]).

**`implicit` retirement — decided (see §Decisions 1).** The flag is only meaningful
for a rule declared in a trait's `possibleSfxIds`. `defaultSfxIds` *provisions* onto
the instance at create time (write-time), while `implicit` was **read-time** reach,
so moving a live implicit rule into `defaultSfxIds` would change its nature — the
author's call is the **generated granted path**
(`select traits → filter id in [...] → navigate traitsettings`), which preserves
read-time semantics.

**Content to re-author (the author's):** `sfx-sect-cultivation` as an Entity-sourced
selector (above), and `sfx-gift`'s path with the extra `traitsettings` step.

## Decisions (author, 2026-09-26)

1. **`implicit` retires into a generated *granted* path** — not into
   `defaultSfxIds`. `defaultSfxIds` *provisions* onto the instance at create time
   (write-time), while `implicit` was **read-time** reach, so moving a live
   implicit rule there would change its nature. The migration generates, for each
   rule a trait declares implicit, a granted reach declaration
   `select traits → filter id in [<those traits>] → navigate traitsettings`,
   which preserves the read-time semantics.
2. **Reach declarations combine with OR.** The union *is* the reach, and
   **granted wins over offered** for an owner both reach (they simply have it — no
   chip). Because OR is a union, "several paths in one declaration" and "several
   declarations" are the same thing — so a declaration carries **one path**, and a
   second criterion is a second declaration. (Flavour is per declaration; grouping
   several same-flavour paths under one row would change presentation only.)
3. **Performance is the implementation's call, to be measured rather than
   assumed** — the author does not know how intensive it will be. The proposal
   stands (resolve a declaration once into a set of owner ids, cached with the SFX
   records, then membership-test it), but the measurement goes in this doc before
   the shape is trusted (§Cost).
4. **A definition's reach includes its sub-trait instances iff they are part of the
   selection.** The author: *"no, unless the sub-traits are part of the selection
   (if I have a sub-trait that sits in the asset traitset, then Gift acquire path
   should still target it)"*. **The edge already does exactly this**, because the
   filter runs on definitions *before* the hop: a nested instance is reached iff
   *its own* trait is selected, never because its parent's is. Measured live: 926
   nested instances exist, **8** have a trait in the assets set and **918** do not;
   the assets sentence returns those 8 and **0** results whose trait is outside the
   set. So "all assets traits" is **889**, and 881 was the top-level-only reading
   the author has now declined. **No catalog change is needed** — `from_type`'s
   options stay as they are.

## See also

[[SFX and Effects]] · [[Targeting Model]] · [[Place-Owned Rules]] (owner vs audience,
the structural half of the same idea) · [[SFX Source Model]] · [[B228]]

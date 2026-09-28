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

## Where a granted rule is seen

A **granted** declaration makes a rule *available* to an owner without attaching
anything, so it lands in no list by itself: not `TraitSetting.sfx_ids` (that is what is
attached), not a chip (granted is never a chip), and not a place rule. Left there it is
usable and **invisible** — the same dead end the place-owned rules hit before they got
their own strip.

**Landed 2026-09-26.** `TraitSetting.grantedSfxIds`, a read-time field resolved from a
new inverse of the granted reach index (`sfx_owner.granted_sfx_by_owner` — one
aggregate per cache fill, so a per-row read on a sheet is a dict lookup).
`TraitRow` and `TraitDetailPanel` render it beside the attached cards, fully readable
and activatable (never dimmed — that is the B189 mistake) and marked with a dashed edge
plus a title saying it is granted rather than attached.

**Why a separate field rather than merged into `sfxIds`.** That list is what is
*attached*, and the trait editor writes it back **wholesale**
(`updateTraitSetting(sfxIds: editSfxIds)`). Folding reach into it would **materialise**
the rule onto the instance the first time anything saved a trait — turning a live read
into a one-time grant, which is the exact objection that retired `implicit` — and it
would have made the rule look removable in the edit panel while removing it did nothing.

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
2. ~~**The reach declarations on `SFX`**~~ **Landed 2026-09-26 (model + surface).**
   `SFX.reach` is a list of `{spec, flavour}` (`ReachDeclaration` /
   `ReachFlavour` in `domain/sfx.py`), threaded through the GraphQL types
   (`SfxRef` / `SfxInput` / `SfxUpdateInput` as JSON, the same wire shape
   `listenerSpec` uses), the converter (`_reach_from_input` / `_reach_to_json`),
   the create/update resolvers, and the MCP document. **`acquire_spec` and
   `implicit` are gone** — from the domain, the SDL, the resolver, the attach and
   the editor. What replaced the gate's *enforcement* is the offered-set
   membership check (item 3, in progress); what replaced its *warning* is
   `validateSfx`'s **"reaches nobody"**, which fires only when no trait declares
   the rule, it declares no reach, **and** nothing owns it.
3. ~~**Availability and the chip** read both the hand-picked lists and the
   declarations.~~ **Landed 2026-09-26.** **Granted** reach is read by
   `get_available_sfx_ids` (`sfx_owner.reach_index(repo, "granted")`, membership-tested
   against the entity's own id, its projection's, its trait instances' and its trait-set
   settings'); it sets `sfx_sources` when the matched owner is a trait instance, so a
   source-aware condition still reads the right trait. **Offered** reach is read by
   `acquirableSfxIds`, alongside the trait's `possibleSfxIds`. And the gate's
   *enforcement* is back as `sfx_owner.reach_refusal` — a rule that declares reach is
   not attached outside the set it selects (`add_sfx_to_owner` and `attach_refusal`
   both consult it); a rule with no declaration is unrestricted, as before.
4. ~~**Editor**~~ **Landed 2026-09-26.** `ReachEditor.vue` — a list of declarations,
   each a row with a `SegmentedControl` (**Has it** = granted / **Offered**) and a
   `PathField`, which keeps the child-panel convention (B72) so a deep path cannot
   make the SFX panel tall again. It replaces both the "Offered by" trait-set picker
   and the single "Acquire path" field, and sits in the SFX panel under **Who it
   reaches** (`<ReachEditor v-model="draft.reach" :source-element="sourceElement" />`).
   - **The typed destination reaches the wizard**, which is the part the acquire
     field could not do: the row passes `destination = { elements: [sourceElement] }`,
     so the builder highlights a path landing on the source and refuses one that ends
     elsewhere. **No cardinality** — `literal` selects one owner and `select locations`
     selects many, and both are legitimate declarations.
   - **The panel says which element the path must land on**, in the catalog's own
     words, and warns instead when no `Source` is set (nothing to type the path
     against) or when nothing reaches the rule yet.
   - **Verified by rendering**, not by the build: a throwaway probe mounted the real
     component and drove it through the DOM (22 assertions) and then ran the whole
     chain — `draft.reach` → `save()` → server → read back, on a temporary rule
     selecting one GMC's instance, deleted again (6 more, **28/28**).
5. **`traitset.limit` — LANDED (2026-09-27).** One catalog line (`ScalarField("traitset", "limit", "int")`),
   so "the sets that allow more than one" is `select traitsets → filter limit > 1` — **4 of 36** live sets,
   measured. The other half of this deferral, **filtering on trait-definition and trait-instance tags, needed
   no work**: `trait.tags` and `traitsetting.tags` are both catalog fields already (matched with `contains`,
   `suggest="trait_tags"`), which is what the "all traits tagged `utility`" example above relies on. Still
   open and deliberately not built: **validating** a tag — nothing yet warns that an authored tag matches no
   trait.
   - **`entity.hidden` landed in the same pass**, for the same reason: a reach selector needs a flag to select
     *on*. It is a `boolean` field — the type already existed (`starter_location` uses it) — so
     `select entities → filter type == gmc → filter hidden == true` traces and resolves. **The live count is
     the thing to know: 0 hidden GMCs.** One entity in the whole database is hidden and it is an *asset*, so a
     rule reaching "every hidden GMC" reaches nobody until the flag is set on one.
   - **What `hidden` does today, which is narrower than it sounds:** its only functional readers are the
     canvas location graph (`exclude_hidden` pathfinding, `from_hidden`/`to_hidden` edges) and
     `trait_visible_to` (a hidden *owner* gates its traits' visibility, read against the **trait's** own
     `known_to`). Nothing hides a GMC from a player-facing read, so flagging one is currently inert outside
     the map.
6. ~~**Retire `implicit`.**~~ **Landed with item 2 — and it needed no migration.**
   Measured on the live DB before writing anything: **0 of 46 rules** set
   `implicit`, so the flag was retired outright and the "generated granted path"
   of decision 1 is a *rule for how the relationship is expressed*, not a backfill
   anyone has to run. (Had any rule used it, the generated declaration would be
   `select traits → filter id in [<declaring traits>] → navigate traitsettings`,
   flavour granted.)
   - **The same measurement put the acquire path's blast radius at 3 rules:**
     `sfx-gift` (a dead, constant-true path — being re-authored anyway),
     `sfx-expose-trait` (dead twice over: a bad `select` seed and no offer), and
     `sfx-sect-cultivation` (the one real gate). Only the last changes behaviour by
     the gate's removal, and its v2 is already on the author's list.

## Cost — measured, not assumed (decision 3)

A reach declaration is a **set-producing** query where the old offer was a lookup, so
the read must not become "walk every owner and run a path". The shape that avoids it,
and what is implemented: resolve each declaration **once** into a set of owner ids,
cache it beside the SFX records (`sfx_owner._REACH_INDEX_CACHE`, cleared by
`invalidate_sfx_cache` exactly like the other caches), and **membership-test** it
against the owner ids an entity already has in hand.

**Measured on the live DB** — 46 rules, an actor holding an assets-trait instance, a
synthetic *granted* declaration over the assets set, nothing written to content:

| | time |
|---|---|
| index fill, **no** declaration (one registry pass) | **1.6 ms** |
| index fill, **one** declaration over the assets set (resolves **889** owners) | **47.6 ms** |
| index read, warm (cached) | **0.0 ms** |
| availability read, warm index, **with** the declaration | **53.9 ms** |
| availability read, warm index, **without** any reach (baseline) | **52.3 ms** |
| an actor the declaration does **not** reach | correctly excluded |

So the per-event cost of a rule reaching 889 owners is **≈ +1.6 ms** — the membership
test — and the set-producing half is paid **once per cache fill**: at most once per
`_SFX_CACHE_TTL` (30 s) or per rule write, and never per entity. The fill scales with
what a declaration *selects*, not with how many entities are read. Revisit if a
declaration is authored against something much larger: the whole trait-definition
registry is 808 rows and the widest collection the catalog offers is `entities`
(~1000), so 889 owners is close to the worst case available today.

## Migration and revert plan

**The revert is DONE** (`3af9873f`, 2026-09-26) — 2065 pass, 0 failures, frontend
builds. **All of items 1–4 and 6 are landed and merged** (same day); item 5 is the
author's explicit deferral. `sfx-gift` still has no reach — see
§Content to re-author below, which is now the only thing between the model and the
author's original sentence working.

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

**Content to re-author (the author's, and now authorable in the panel):**
`sfx-gift` needs its `acquireSpec` replaced by a reach declaration —
**offered**, path `select traits → filter traitset_id == ts-3 → navigate
traitsettings` (the author's original sentence: *all traits of the assets set*),
which resolves to the **889** owners measured above. And `sfx-sect-cultivation`
becomes an Entity-sourced **granted** selector over Azure Dawn's occupants:
`select locations → filter id == loc-74560187 → navigate occupants`. Neither is
written until the author does it — the mechanism is built and verified, the content
is theirs.

## Decisions (author, 2026-09-26)

1. **`implicit` retires into a generated *granted* path** — not into
   `defaultSfxIds`. `defaultSfxIds` *provisions* onto the instance at create time
   (write-time), while `implicit` was **read-time** reach, so moving a live
   implicit rule there would change its nature. The generated declaration is
   `select traits → filter id in [<those traits>] → navigate traitsettings`,
   flavour granted, which preserves the read-time semantics. **No live rule used
   `implicit` (0 of 46), so nothing had to be migrated** — see item 6.
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

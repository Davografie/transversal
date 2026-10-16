---
title: Content Bundles
date: 2026-09-29
last-updated: 2026-09-29
tags:
  - transversal
  - technical
  - content
  - data-model
  - api
aliases:
  - Content Bundle
  - Bundle Export
  - Portable Content
---

# Content Bundles

> [!info] Built 2026-09-29 ([[B301]]) — the **export half**
> `services/content_bundle.py`, the document reads in
> `db/repository_mixins/bundles.py`, and three REST routes under `/api/v1/bundles`.
> **Import is not built.** The format is designed so it can be.

A **bundle** is one JSON file holding whole documents for a set of authored
elements, so a GM can hand content to another world. The human's ask was
*"export/import functions for different game elements (entities (+ projection if
occupant), trait sets, traits, SFX's, life paths, roll tables)"*, and three design
calls followed:

1. **Purpose — share authored content as a file.**
2. **Ids — reassign, and recompute derived keys.**
3. **Closure — report it and let the chooser decide.**

## What a bundle is not

- **Not [[B251]]'s package mechanism.** No registry, no publish, no acquisition
  record, no closure *validation*. That design is retained future work with
  recorded triggers ([[Global Multiverse and Forks]] §7). This is the narrow
  prerequisite it always assumed, and building it does not commit the project to
  it.
- **Not the whole-world path.** A fork already copies a database **verbatim** —
  no handle remapping, no dependency closure, no reference audit — because every
  `_key` is a string (`services/provisioner.py`). What a bundle buys over a fork is
  the one thing a fork cannot do: share **part** of a world.
- **Not [[B89]].** That ticket is a universe-granular `.zip`, is `pending`, and is
  `data-migration`'s. Nothing here overlaps it except the word "export".

## The two phases, and why

`plan` is a **read** and writes nothing; `export` serialises. The report comes
first because the closure is bigger than people expect — a trait set reaches its
traits, their SFX, and the traits those name — and because the live world already
carries **204** trait settings pointing at **13** traits that do not exist.

```graphql
# not GraphQL — the routes, for shape
POST /api/v1/bundles/plan     → the report, no documents
POST /api/v1/bundles/export   → the file
GET  /api/v1/bundles/kinds    → the vocabulary a picker reads
```

Every reference is classified into one of three buckets, and the class is a
statement about *meaning*:

| class | meaning | followed? |
|---|---|---|
| **required** | the element is incoherent without it — a trait needs its set, an SFX needs the trait its path names | yes, this *is* the closure |
| **invited** | content-shaped but separable — a relationship whose far endpoint is outside the bundle | no; reported with that endpoint |
| **incidental** | placement and play state — `current_location`, `known_to`, `owned_by`, attunements, in-progress terms | no; shown so the chooser sees what it is leaving behind |

`depth` says how many frontier rounds to walk. `1` (the default) reports the
frontier so the caller can widen the selection and ask again; `0` walks to a
fixpoint for a caller that wants *take everything it needs*.

## The reference map: meaning declared, identity resolved

`RULES` is one declaration per collection, by document path — `("entries", "[]",
"cost_effects", "[]") → the Effect rule set`, `("current_location",) → entity,
incidental`. Paths match with `[]` for every list item and `*` for every map key.

**The map does not decide whether a value is a reference.** That goes to the
database: `RepositoryBundles.locate_documents` asks, in one round trip, which
collection holds each candidate key. Three consequences, and they are the design:

- **A missed rule cannot silently truncate the closure** — the value lands in
  `unruled` instead, and a test asserts that set is empty over the whole live
  database. That is the failure mode that produced [[B156]]'s 50 dangling targets,
  and it is now a red test rather than a hope.
- **A dangling reference is still reported by kind**, because a `literal` targeting
  step names its own `element`. Three live SFX name
  `ts-complications-a190`, which does not exist; a bundle says so at export rather
  than arriving cleanly and breaking at the table.
- **A declared path whose value nothing holds is a finding, not a gap in the map.**
  It is reported as `kind: "unknown"` — *this names a document nothing holds, and
  the field does not say what it should have been.*

### Four shapes that are easy to get wrong, all found by measuring

1. **A wildcard path never matches literally.** The walker reports
   `refs.trait.value`, not `refs.*.value`, so a flat lookup misses every `*` rule.
   The map is a trie that tries the literal segment first and `*` second.
2. **`_key` and `id` are the key, and are id-shaped.** Without an explicit skip,
   every element reports a required reference to itself.
3. **An anchor is a handle.** `_from`/`_to` are `entities/x`; existence is a
   question about `x`, and a bundle carries `x`.
4. **Both spellings are live.** GraphQL inputs are camelCase on the wire, so a
   document can carry `targetSpec` where the model says `target_spec` — measured:
   one live relationship edge does. Every declared path is registered under its
   wire spelling too, and it was the completeness guard that found it.

### References that are not values

- **A set's traits are reached *backwards*.** `traits.traitset_id` points *up* at
  the set, so a closure that followed only what a document carries would ship a
  trait set as an empty grouping. `raw_traits_for_traitsets` is the reverse read.
- **An edge is carried iff both endpoints are.** An edge with one end missing is
  not a fact, and following one end would walk the whole world.
- **Anchored kinds are not optional.** A trait setting *is* an entity's trait
  surface; asking a chooser whether to include it would be a footgun. They arrive
  with their owner, and they are marked `anchored` so they cannot be selected
  directly.
- **The read is anchored on `_from`, never on `entity_id`.** The indexed
  `entity_id` is denormalized and would over-pull: a projection's settings share
  the owning entity's `entity_id`, so asking for the entity returns its other
  bodies' settings too.
- **A document's own identity does not travel as a reference.** `_id` and `_rev`
  are database-local and are stripped; `_key` is kept because edges and derived ids
  are keyed by it.

## Ids, and what an importer will have to recompute

Four collections mint keys as **pure functions of their references**:

```
projections         {entity}:{universe}
traitsettings       {anchor}:{trait}
traitsetsettings    {entity}:{set}
relationships       edge:{from}:{to}:{type}
```

An id-preserving import into the same world is nearly free — the documents rewrite
and the derived keys recompute to themselves. An **id-reassigning** import must
*recompute* them from the remapped parts. The precedent already exists:
`migrate_common.build_entity_key_map`, and `PlanService.promote`'s
draft-then-promote with fresh ids.

**Three phases, and no dependency ordering:** assign every new key first (a pure
map, no writes), rewrite every reference through it, then write. Derived keys are
computable before the write because both halves are known — which is also what
sidesteps the trait↔SFX cycle (`trait.possible_sfx_ids` ↔
`sfx.effects[].refs.trait`).

Two things a bundle distinguishes that an id remap must not conflate:

- **universe handles** (`universes[]`, `current_universe`, `universe`) are
  *strings*, not documents. They are not remapped; they are declared in
  `expects.universes`, because a bundle can expect a world the target does not
  have. 16 of 38 live trait sets declare 15 universes, so this fires constantly.
- **media filenames** are *files*, not rows. `expects.media` declares them. The
  bytes live under `media/` (1.1 GB, 446 files) and the bundle does not carry them.

## The file

```jsonc
{
  "format": "transversal.bundle/1",
  "bundleId": "…",
  "createdAt": "…",
  "source": { "database": "…", "selection": [...], "depth": 0 },
  "documents": [ { "kind": "trait", "key": "…", "label": "…", "document": {…} } ],
  "counts": { "trait": 208 },
  "expects": { "universes": ["earth"], "media": ["/media/loc-1.webp"] },
  "unresolved": [ … ],   // required, carried, and not found — refuse or drop loudly
  "leftBehind": [ … ],   // incidental: placement and play state
  "invited":    [ … ],   // edges whose far endpoint is outside
  "unruled":    [ … ]    // an id-shaped path with no rule: a map gap, reported
}
```

Documents travel **verbatim** apart from `_id`/`_rev`. That is the point of the
document-level read: the Pydantic models are a *view*, and a model-based export
drops what the model does not know — measured: `traits.location_restricted` on
**642** documents after the field was removed end-to-end, and
`roll_tables.entries[].cost_effects` on **169** rows while [[Data Model]] did not
document it.

## The actor boundary

A bundle reaches the whole authored surface of a campaign, so both write-free
routes are **owner-gated** — GM material, not player material. One consequence is
deliberate and worth stating: a bundle that carries `entities` can carry a
**player character**, which is a player's data. Importing must require an explicit
opt-in for `character`-typed entities rather than letting "export entities" quietly
become "export Andy's sheet".

## What is still needed

- **Import.** The other half. Three phases as above, with `plan` used as its
  dry run, and an explicit merge-or-duplicate answer when a bundle's trait set
  already exists by name in the target world (the registry keys are
  `md5(slug + ":" + universes)`, so a re-import collides *by design*).
- **Media.** `expects.media` declares what is needed and carries nothing. Whether
  bytes travel in the file, or alongside it, is a [[media]] decision.
- **A surface.** `/api/v1/bundles/*` is the mechanism; no panel or MCP tool drives
  it yet.
- **The clean-up this work made visible but did not do:** 204 trait settings
  pointing at 13 missing traits; 11 `images` rows whose owner id is an *old-app*
  key (`kael-1`, `elena-1`, `loc-mistwood`); 2 entities standing in a
  nonexistent `loc-2`.

## Related

- [[B301]] — the ticket.
- [[Data Model]] — the collections and fields a bundle carries; corrected under
  this ticket (`images` not the dead `entity_images`; `cost_effects`;
  `pending_terms`; the live index set).
- [[Content Packages]] — the parked mechanism this is the prerequisite of.
- [[Targeting Model]] — the spec shapes the reference map walks.

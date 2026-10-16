---
title: Content Packages
date: 2026-09-29
last-updated: 2026-09-29
tags:
  - transversal
  - technical
  - content
  - registry
  - multi-tenancy
  - design
aliases:
  - Content Packages
  - Package Model
  - Pristine Packages
  - Registry Sandbox Playroom
status: draft
---

# Content Packages

How authored content is **packaged**, **versioned**, **referenced** and **acquired** — the mechanism
behind the read-only content registry, the sandbox, and the pristine packages the owner wants for
**Earth** and **Three Realms**.

Sibling designs: [[Content Registry]] (the cross-campaign catalog, sandbox and GPU entitlement),
[[Identity Programme]] (tenancy, identity, invites, recovery). This doc refines Content Registry §4,
which described publication in the abstract ("build → share → load"); here is the concrete unit.

> [!warning] RETAINED AS FUTURE WORK — this is not the current direction
> As of **2026-10-15** the multi-tenancy direction is the simpler **[[Global Multiverse and Forks]]**
> model: one shared global multiverse, accounts, and a **verbatim fork** per campaign. That model
> needs none of the machinery here — its §2 shows why (all 20,443 `_key`s are strings, so a fork
> copies without remapping *any* handle).
>
> This document is **kept deliberately**, at the owner's explicit instruction, because packages buy
> things a fork cannot: sharing content instead of duplicating it, receiving updates after acquiring,
> partial acquisition, versions and a curated catalog. [[Global Multiverse and Forks]] §7 records the
> concrete triggers that would bring it back. **Do not build from this document without checking
> that trigger first.**

> [!warning] Design under review — nothing is implemented
> Written 2026-09-29 from the owner's direction, refined through review with the [[Overseer]].
> No code and no data has changed. Every measurement in §9 was taken read-only against the live
> `transversal` database on 2026-09-29.

## 1. The three spaces

The owner's framing, and the reason the separation is needed at all: content must be authorable and
pinnable **without** touching the database the players are playing in.

| space | what it is | mutable by |
|---|---|---|
| **Registry** | the read-only store of authored packages — the single source of truth for shared content, and the foundation package DBs build on | authors, by publishing |
| **Sandbox** | a Transversal database containing **only the elements applicable to one package**; where a package is authored and frozen | its author |
| **Playroom** | a live campaign database where players act | players and their architect |

The load-bearing property: **a package is authored in a database that contains nothing but that
package.** The package boundary is therefore a *database* boundary, not a query. A package is
**materialised, not filtered** — there is no publish-time selection rule that can drift from intent,
because the database *is* the definition. This reuses the isolation primitive [[Identity Programme]]
already chose for campaigns, so it introduces no new concept.

## 2. Decisions taken

| decision | chosen |
|---|---|
| the unit | a **package** — a named, versioned, immutable set of authored documents |
| membership representation | a **`packages` list on the document**, meaning *"these packages must be active for me to be present"* |
| what that list holds | **foreign packages only** — membership in its own package is implicit in which database the document lives in |
| who populates it | **computed automatically** from reference closure; never hand-maintained |
| the closure | **transitive, to a fixpoint** — A→B→C means A must list both B's and C's packages |
| where the list lives | **the package DBs and the registry** — *not* the playroom (§7) |
| versioning | **the document names the package; the version pins the frozen set** — documents are never edited to ship a new version |
| registry↔package relation | **reference for authorship and provenance; copy for runtime** (§6) |
| acquisition | a per-copied-document **acquisition record**, enabling update-by-id (§7) |
| the two packages | **Earth** (a reflection of reality) and **Three Realms** (the Three Realms *plus* every Earth element that bridges to it) |

## 3. The package field

Every authored document that is not player-owned carries a list of the **foreign** packages it
depends on:

| document | `packages` | why |
|---|---|---|
| New York | `[]` | pure Earth content — lives in the Earth package, depends on nothing foreign |
| Jianxin Fireheart (+ traits) | `[]` | pure Three Realms content |
| the Jian | `[Earth]` | **Three Realms-owned**, but it holds a projection into Earth, so it needs Earth active |

That last row is the case that defines the model, and it is worth being precise about it, because the
naive reading is wrong. The Jian is **not a member of two packages** — it is a Three Realms document
that *depends on* Earth. The distinction is observable: if it were a member of Earth, then loading
`Earth v1` alone would hand you a supernatural sword, which contradicts the owner's definition of the
Earth package as *"just a reflection of reality."*

So the field means **"must be active"**, and true membership is implicit in the authoring database.
This is a dependency list, not a membership list.

## 4. The dependency closure — the load-bearing mechanism

The `packages` list is **computed**, not curated, and it is **transitive**:

```
A (Earth) references B (Three Realms) references C (Varenya)
  ⇒ A.packages = [Three Realms, Varenya]
```

It is therefore a **fixpoint computation**, not a one-shot tagging pass, and it must be recomputed
whenever a reference changes — at save or publish time. It is the same mechanism as a **publish-time
closure check**, viewed from the other side: *automatic tagging* computes the list, *closure
validation* refuses a package whose outgoing references escape it.

**The cost is the reference map.** "A reference" is not one shape in this schema. Every one of these
must be walked, per document type, or the closure is silently incomplete:

- `traitsettings` and `relationships` and `traitsetsettings` — **edges**, and the largest surface by far
- `sfx_ids`, `sfx_owners`, `life_paths`, `discovered_life_paths`, `suitable_life_path_ids`
- `roll_tables` entry targets and `next_step` links
- image ids (`background_image`, role images), `owned_by`, `current_location`, `current_projection`
- `known_to`, `traitsetId`, `node_ids`, `zones`, `plan_entities` / `plan_relationships`

**Why this is not optional:** this project has already been bitten twice by unvalidated references —
[[B156]] measured **50** `modify_trait` targets across 7 roll tables naming trait ids that do not
exist, and [[B157]] exists because roll-table and life-path structure is checked by nothing. A
package copied with a dangling reference arrives *cleanly* and is broken on use, which is the worst
possible failure mode: no error at publish, no error at copy, a fault only the player sees.

## 5. What this dissolves

The [[Overseer]]'s earlier finding was that **a pristine origin cannot be derived** — there is no
authorship provenance in the data, `owned_by` is *character* ownership rather than "who edited this",
and the obvious fallback does not exist (§9.4). The conclusion was that pristine content must either
be declared or recovered from a snapshot.

**Authoring in a package-sized database dissolves that problem rather than solving it.** If `Earth`
is built in its own clean database, **no live document ever has to be classified**. The package is
**re-authored, not carved out of the playroom** — which is the cheaper gate, because it needs no
provenance, no snapshot, and no archaeology on 1,011 entities.

### And authoring can begin before any of this is built

Worth stating plainly, because it is easy to assume the whole design is a prerequisite: **it is not.**
A sandbox is an ordinary Transversal database, and both switches already exist.

- `ARANGO_DATABASE` is already read — `db/arango.py:43`, defaulting to `transversal`. It is simply
  **not set in `docker-compose.yaml`**, so the API defaults to the playroom.
- `get_db()` **creates the database and every collection on first connect**
  (`db/arango.py:87-88`: `if not sys_db.has_database(...): sys_db.create_database(...)`), so a new
  name needs no bootstrap script and no migration.

So a sandbox is **one environment variable and a second API instance** — no closure engine, no
registry, no acquisition record, and no SEC-3. What this document specifies is the *second* stage:
sharing between packages, and acquiring into a playroom. The first stage — authoring `Earth` and
`Three Realms` in their own clean databases — is available today.

Two caveats before that is treated as finished: **images are files, not rows** (§7), so a package
shares the playroom's media namespace; and **nothing routes by campaign**, so two databases means two
instances reached by port rather than one API serving both.

## 6. Copy or reference — the split

The owner's instinct was **reference**: New York should exist once and both packages point at it. That
instinct is right about *authorship* and wrong about *runtime*, for four reasons.

**a. Arango cannot join or draw an edge across databases.** This is structural, not a preference.
`traitsettings`, `relationships` and `traitsetsettings` are **edges**, and an edge's `_from`/`_to`
are database-local handles. A foreign reference therefore **cannot be a graph edge at all**. Either
the target is materialised locally — which *is* copy-on-author — or cross-package relationships stop
being edges and become application-level re-resolution. There is no third option, and the middle one
is a rewrite of how the graph works. [[Identity Programme]] §2 already established the premise:
`_id` handles are database-local, so sharing authored content "is a **deep copy with every handle
remapped**."

**b. It reintroduces exactly the discipline problem DB-per-campaign was chosen to avoid.** Identity
Programme §2: *"isolation would rest entirely on every resolver, every query and every MCP tool
filtering by campaign, in a codebase where SEC-1 was a raw AQL string interpolation. Arango has no
row-level security."* Read-through reference resolution is that same problem one layer down — every
read path must know to consult the registry, and every one that forgets returns **silently partial**
data. And with no cross-database join it is not a query written once: it is a Python fan-out per
reference, per resolver, per MCP read.

**c. It makes the registry a hard runtime dependency, which breaks per-campaign export, backup and
delete.** The stated benefit of database-per-campaign is that a campaign can be exported, backed up
and dropped independently (`drop_database`). A read-through dependency means a package DB cannot be
restored elsewhere without the registry at the right version — the property is lost.

**d. Version skew destroys "pristine".** If a package reads through to the registry, the registry
moving silently changes every dependent package. A *pristine* Earth that mutates when someone edits a
shared trait is not pinned, and "before-player-interference" stops meaning anything.

**What reference is genuinely good for is the single source of truth**, and that is what the split
preserves:

- **Registry — reference semantics.** Authors edit shared content in one place. New York exists once,
  and fixing a typo in it is one edit rather than a republish of every package.
- **Package DBs — copy semantics, frozen at publish.** Self-contained; no runtime dependency on the
  registry; reads are local; and the package cannot drift.
- **Updates flow as an explicit pull** (§7), never at read time. This is what [[Identity Programme]]
  §2 already decided for acquired universes: *"a version-pinned snapshot with an explicit 'update
  available' pull."*

## 7. Acquisition, and update-by-id

**The playroom does not carry the `packages` field.** It does not need to: the field exists to compute
what to copy *at publish*, which is a registry/package-DB concern.

What the playroom needs instead is **one record per acquired document**:

```
acquisitions: { local_id, source_db, source_id, source_package, source_version,
                source_rev, local_rev_at_copy }
```

**Why id alone is not enough** — the owner proposed matching on id, and it is the right key, but it
supplies only one of the three things update propagation needs:

| what is needed | where it comes from |
|---|---|
| **identity** — which local document corresponds to which source document | `source_id` — **but ids are remapped on copy** (§6a), so the mapping must be *recorded*, not assumed |
| **pristine-ness** — has the playroom touched it? | `local_rev_at_copy` vs the local `_rev` |
| **version** — which package version it came from, i.e. what an "update" is | `source_package` + `source_version` + `source_rev` |

Because Arango revisions every document, **update detection needs no content hashing**:

- **untouched** ⇔ `local._rev == local_rev_at_copy`
- **source moved** ⇔ `source._rev != source_rev`
- **conflict** ⇔ both moved

Note the asymmetry that makes this work: the source is **immutable once published**, so its `_rev`
is a stable version marker; the local copy's `_rev` is a reliable "has anyone touched this" flag. The
record is one collection with one purpose, in place of a field on **19,685 documents across 19
collections** (§9.3) — and it keeps the players' database out of the migration entirely.

> [!warning] A gap found 2026-09-29: **images are not in the database**
> `MEDIA_DIR = Path("/app/media")` (`api/rest/media.py:38`) and compose mounts it as
> `./media:/app/media` — so every image is a **file on a shared volume**, and only the *rows* that
> reference it live in Arango. Two consequences for this design, neither covered by the copy/reference
> split above:
> - **A package database is not self-contained.** Copying it copies references to files the playroom
>   also sees, so a package and a playroom **share one image namespace** — the isolation is
>   database-deep, not content-deep.
> - **Dumping a package's database loses every image.** No export of a package is complete without the
>   media it points at, which means a package needs a **media manifest** (the ids/files it owns) and a
>   way to carry them — the same class of problem as the acquisition record, one layer out.
>
> This is `MEDIA_DIR`-specific and is recorded rather than designed. It is the strongest argument yet
> that "pristine package" has to mean *content* rather than *a database dump*.

## 8. The two packages

| package | contains | excludes |
|---|---|---|
| **Earth** | a reflection of reality — the real-world Earth, mundane | anything bridging to the Three Realms |
| **Three Realms** | the Three Realms universe, **plus** the Jian, the boat crew, and **every Earth element that bridges to the Three Realms** | — |

The bridge is deliberately **Earth-universe content that belongs to the Three Realms package**: Amber
Shoal, The Sunken Temple, Lantau Salvage Yard, Krasnoyarsk-45, the Institute of Applied Harmonics,
The Resonance Chamber, The Mountain Road, the *KM Seri Mutiara*, and the factions and GMCs around
them. The package is an **authoring decision, not a universe derivation** — which is exactly why a
per-document tag is the right representation and a `universe` filter is not (§9.1).

Two consequences worth stating so they are not discovered later:

- **A campaign wanting both loads both packages, and they compose.** The Three Realms package is
  self-contained — it carries the Earth-side content it needs — so no campaign has to load Earth
  merely to satisfy it.
- **The playroom your players are in is neither package.** It is reality **+** bridge **+** Three
  Realms **+** player edits. Three things and a delta, not two things.

## 9. What the data says

Measured read-only against the live `transversal` database, 2026-09-29.

1. **`universe` is not on the entity.** `entities.universe` is `null` for all **1,011** entities. The
   real structure is `current_universe` (`three_realms` 577, `earth` 211, …) plus **967 projections**
   carrying `origin_universe` (immutable) and `universe` (mutable by travel). A package therefore
   **cannot** be a `universe` filter.
2. **The mutation trap is real but has barely bitten.** Only **2 of 967** projections have drifted
   (`three_realms → earth`, `three_realms → the-floating-vagabond`). Adopting `origin_universe` as the
   authoring-universe key is cheap **now** and gets expensive as drift accumulates.
3. **The scale of the field is real, and it is mostly edges.** 19 collections, **19,685** documents,
   of which **12,659 are edges** — `traitsettings` alone is **10,965**, `relationships` 1,561. This is
   the strongest argument for confining the field to the package DBs (§7).
4. **There is no pristine origin to recover.** The deleted `db/seed.py` (`5b6a561b`) is **610 lines**
   with ~33 names and 25 universe references — a thin bootstrap, not the source of 1,011 entities.
   Recovering it from git history would not produce Earth. Combined with the absence of any edit
   provenance, this is what forces re-authoring rather than extraction (§5).
5. **The existing `unpublished` flag is a near-miss and must not be overloaded.** 83 entities are
   `unpublished=true` (earth 73, three_realms 9, emberline 1) and they are almost exactly the bridge
   layer. But it **mis-classifies precisely where it matters**: Irina Antonova and Yuri Antonov are
   `unpublished=false`, so a flag-based split would file the family under "reality" and separate them
   from the narrative they exist for. [[Content Registry]] §4 already warns that `unpublished` means
   *GM-drafting visibility inside a campaign* and that catalog publication "should probably be its own
   field rather than an overload." This doc agrees.
6. **Entities are multi-universe by design, so packages overlap.** Professor Antonov holds **five**
   projections — `one-piece`, `aelor-citar`, `intergalactic-planetary`, `earth`, `three_realms`. The
   two packages both legitimately contain him. Packages are selections that **share** documents, never
   a partition.

## 10. Open items

1. **The bridge list is not yet written.** It is ~73 Earth entities today by the `unpublished` proxy
   (§9.5), but the authoritative list has to be authored and reviewed — that is the curation this
   design still requires, and it is content work rather than mechanism.
2. **Where the closure runs** — at save time (keeps `packages` always current, costs a walk on every
   write) or at publish time (batched, but a package can be momentarily stale). Publish-time is
   probably right, since only publication freezes anything.
3. **The reference map's completeness is unverifiable by construction** — a missed field produces a
   silently incomplete closure. It needs a test that walks every collection and asserts each
   reference-shaped field is either mapped or explicitly listed as not-a-reference.
4. **Media does not travel with a database** (§7) — images are files on a shared volume, so a
   package needs a **media manifest** and a way to carry it before "pristine package" can mean
   *portable*. This is a hole in the design, not a detail of it.
5. **Package dependency cycles** — Three Realms depends on Earth; can Earth ever depend on Three
   Realms? If yes, the closure needs cycle handling, and the "load both" case needs defining.
6. **What an acquisition does about *removals*** — if `Earth v2` drops a document, does a pull delete
   the local copy, or leave it orphaned? Deletion is destructive and needs a policy.
7. **Whether the two packages ship as `v1` content at all**, or whether this doc is only the
   mechanism and the content follows. The owner's framing ("at the moment, I just want to be able to")
   suggests the mechanism is the gate.
8. **Ownership of the two residues** — placed 2026-09-29: the mechanism is [[backend-platform]]'s
   ([[B251]]) with [[security]] reviewing. The **product** surface and the package **content** are
   deliberately unowned; see [[Division of Labor]] § *Unassigned*.

## 11. Where this sits

**Placed 2026-09-29.** The work arrived as a hand-off from [[security]], which identified the
pristine-universe split as a content/data question rather than application security and asked the
[[Overseer]] to place it. The human's call was **not** to create an `architecture` role: the design is
already written, so what remains is build — and the build is [[backend-platform]]'s craft, the same
craft [[Identity Programme]] §2 already assigns to them. So **[[B88]]'s primary and [[B251]] both moved
to [[backend-platform]]**, with [[security]] as reviewer and register-owner.

Two things were deliberately **not** absorbed by that move, and are recorded as unowned in
[[Division of Labor]] § *Unassigned*:

- the tenancy **product** surface — registry browsing and curation, who may create campaigns, pricing,
  throttling, and **moderation** of user-authored content, which [[Content Registry]] §6 calls a real
  go-online gate that no amount of sandboxing answers;
- the package **content** — the bridge list, and the two packages themselves.

This design and the campaign boundary in [[Identity Programme]] are the two halves of [[B88]].
[[B114]] (marketplace) sits on top of both, and remains deferred.

> [!note] Naming
> [[Content Registry]] already claims "Content Registry" and "Content Sandbox" as aliases. The three
> spaces named in §1 are the same objects seen from the packaging side; when the registry is built,
> these two docs should be reconciled rather than allowed to describe it twice.

## Log

- 2026-09-29 — written from the owner's direction, after two review rounds with the [[Overseer]].
  **The owner's design:** every non-player document carries a `packages` dependency list; a package is
  authored from a database containing only that package's elements; a read-only registry holds the
  authored packages and the pristine package databases build on it. **Settled in review:** the field
  holds *foreign* packages only and is **computed** from a transitive closure, not curated; the Jian is
  **Three Realms-owned and Earth-dependent** rather than a member of both; versioning puts the package
  name on the document and the version on the frozen set; and the registry↔package relation is
  **reference for authorship, copy for runtime** — with the four reasons against runtime reference
  recorded in §6, the decisive one being that Arango cannot draw an edge across databases. **Added by
  the [[Overseer]]:** the acquisition record and `_rev`-based update detection (§7), and the
  observation that package-sized authoring **dissolves** the pristine-origin problem instead of
  solving it (§5). Measurements in §9 taken read-only. Nothing implemented.
- 2026-09-29 — **placed, and two findings while placing it.** The [[Overseer]] put the mechanism on
  [[backend-platform]] ([[B251]]), moving [[B88]]'s primary with it and correcting B88 off `deferred`
  — the human's call was to re-own rather than create an `architecture` role, since the design is
  already written and what remains is build. Two conditions attached: **B88 had to move with B251** (a
  mechanism in one role and the boundary it builds on in another is how this went unowned), and **B88
  could not sit `deferred`** while SEC-8 calls it a hard precondition for going online. Both residues
  — the product surface and the package content — are recorded as deliberately unowned. Two things
  found in the same pass and now in the doc: **authoring does not depend on this document** (§5 — with
  `ARANGO_DATABASE` and `get_db()`'s bootstrap, a sandbox is one environment variable today), and
  **images do not travel with a database** (§7 — `MEDIA_DIR` is a shared filesystem volume, so a
  package dump loses its images, which is a hole in "portable pristine package" rather than a detail).

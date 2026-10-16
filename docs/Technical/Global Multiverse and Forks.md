---
title: Global Multiverse and Forks
date: 2026-10-15
last-updated: 2026-10-15
tags:
  - transversal
  - technical
  - tenancy
  - design
aliases:
  - Global Multiverse and Forks
  - Fork Model
  - Shared Multiverse
  - Clone Model
status: draft
---

# Global Multiverse and Forks

The **current** multi-tenancy direction, replacing the package/sandbox/registry design: one
**global shared multiverse** that a few trusted people may edit, and **accounts** that let anyone
**copy it and play in their own copy**.

> [!note] The package design is retained, not discarded
> [[Content Packages]], [[Content Registry]] and the package half of [[Identity Programme]] describe
> a **more capable** model — packages that share content rather than duplicate it, versions, a
> curated catalog, selective acquisition. That design is **kept as a possible future direction**;
> this document explains why it is not the *first* thing to build, and what would bring it back.
> See §7.

> [!warning] Design only — nothing is implemented
> Written 2026-10-15 from the owner's direction. Every number in §2 was measured read-only against
> the live `transversal` database the same day.

## 1. The model

| | |
|---|---|
| **The global multiverse** | one ArangoDB database, the canonical content. **Never played in.** |
| **Edit rights** | a few trusted accounts may edit it directly. v1 is **whole-world or nothing** (§5). |
| **An account** | how a person owns a copy, and how they hold their edit rights on the global. |
| **A fork** | a **verbatim copy** of the global's content collections into a new database — that copy is the campaign, and it is theirs. |
| **Playing** | happens **only in forks**. The existing player/architect model applies *inside* one. |

The one rule that keeps it coherent: **the global multiverse is never played in.** The moment it is,
it accumulates play state and stops being a clean source. A surface must not offer "play here".

## 2. Why this is cheap: a fork needs no handle remapping

This is the fact that decides it, and it is worth stating precisely, because the **package** model
could not avoid the same problem.

[[Identity Programme]] §2 established that sharing authored content is *"a **deep copy with every
handle remapped**"* — because `_id` handles are database-local. That remapping is the reason the
package design needed a transitive dependency closure, a per-type reference map, and dangling-
reference validation.

**A fork needs none of that.** Measured across all **20** collections (`_system` aside):

- **20,443 documents** in total *(measured 2026-10-15; **20,447** on 2026-10-16 — the content grows, and the figures below are the 10-15 set)*
- **zero numeric `_key`s** — every key is a stable string (`loc-409859`, `ts-3`, `character-kael-drift-e555ccde`)
- edges are `collection/key` strings: `{"from":"entities/faction-44351398","to":"traits/trait-description"}`

So copying documents **verbatim** into same-named collections preserves **every edge**, because the
`_key`s are already globally-unique strings. No remapping, no closure, no reference audit, no
dangling-edge risk. The whole class of problem that made the package design expensive does not arise.

## 3. The content/play split is a collection list, not a per-document field

The package design needed a `packages` field on every authored document — 20,443 of them — with a
computed transitive closure. The fork model needs a **short, legible list**:

| copy (≈ **17,640** docs) | skip (≈ **2,803** docs) |
|---|---|
| `entities` 1036 · `projections` 983 | `historical_records` 2673 |
| `traits` 809 · `traitsets` 36 · `traitsetsettings` 92 · `traitsettings` 10808 | `join_tokens` 36 |
| `relationships` 1532 · `sfxs` 51 · `sfx_owners` 2 | `messages` 61 |
| `roll_tables` 32 · `life_paths` 10 | `players` 29 |
| `images` 1023 · `entity_images` 1134 | `scheduled_events` 4 |
| `plan_entities` 51 · `plan_relationships` 41 | |

Two things to note while implementing it. **`traitsettings` is 61% of the content** (10,808 rows), so
a fork is dominated by one collection. And **`entity_images` (1134) and `images` (1023) are both
live** — the rename migration is in flight, so the fork must copy whichever is authoritative at the
time and must not resurrect the legacy one.

## 4. What this deletes, and what it keeps

**Gone from the first build** — all of it retained as future work (§7):

- the `packages` dependency field, its transitive closure and the per-type reference map ([[B251]])
- acquisition records, `_rev` update detection, version pinning
- the registry as a **catalog**: browsing, curation, publishing
- selective forking (for a subset of universes)
- GPU entitlement tiers and the marketplace ([[B114]])

**Kept, because a fork still needs it:**

- **accounts** and a small **routing/permissions table** (account → their fork → their rights on the
  global). This is roughly [[B255]] **minus the catalog** — small.
- **per-request database resolution** and the **`_db_cache` LRU bound** (`db/arango.py:94` holds one
  pool per database for the process lifetime — correct for one campaign, unbounded at a thousand).
  This is [[B88]]'s plumbing half, and it **survives the change**. What shrinks is the provisioning:
  **"clone the canonical database"** instead of "create empty + seed + acquire packages".
- **campaign-scoped admission and players** — [[Identity Programme]] §3–4 applies *inside* a fork
  essentially as written. SEC-3's sessions, join tokens and roles are already built.
- the **switcher**: my forks, create one, open one ([[B256]], reshaped).

## 5. The honest costs

1. **No updates after forking.** A fork is yours; the global moving on does not reach it. That is the
   central trade, and for *"play with my friends"* it is usually the right one. If updates are ever
   wanted, that is exactly when acquisition and `_rev` detection come back — and only for the people
   who want them.
2. **Edit rights are blunt.** "May edit the global" has no natural scope: whole-world or nothing. With
   a **few trusted contributors** that is fine, because collisions are rare. Scaling it needs subtree
   scoping — a location tree, a faction — which is the complexity being avoided. **v1 is few editors
   and whole-world, and that should be stated rather than discovered.**
3. **Migrations multiply.** A schema change must run across every fork, and a fork that has diverged
   cannot take a content update. Inherent to forking, not a defect of this design.
4. **The current database is the played-in one, not a clean source** — see §6. That is the first piece
   of real work, and it is a decision rather than a copy.
5. **It does not unblock the tenancy thread by itself.** [[B88]]'s plumbing is still required. This
   makes the thread *smaller*, not unnecessary.

## 6. The first migration, and why it is a decision

**`transversal` today is a live game, not a pristine source**: 29 players, 61 messages, 2,673
historical records, 36 join tokens. So before anything forks, one of these has to be chosen:

- **Fork first** — copy `transversal` into *your campaign* and keep playing there, then strip the play
  collections from `transversal` to make it the global multiverse; **or**
- **Clean a copy** — leave `transversal` as your game, and build the global multiverse from a cleaned
  copy of it.

Either way it is **one cleanup pass**, and it is the owner's call because it decides where their
existing game lives.

## 7. What the retained design is for

Kept deliberately, because it buys things this model cannot, and they are real:

- **Sharing content without duplicating it.** A fork duplicates the whole world; packages would let two
  campaigns *reference* one New York. Relevant the moment dozens of campaigns exist and the global
  multi-gigabyte.
- **Updates after acquiring.** The `_rev`-based pull in [[Content Packages]] §7 is the answer to §5.1.
- **Partial acquisition** — "I want this universe, not all of them."
- **A curated catalog**, versions, and the marketplace ([[B114]]).
- **GPU entitlement tiers** ([[Content Registry]] §5), which self-service campaign creation needs.

**What would bring it back**, stated so the trigger is visible rather than a matter of taste: many
simultaneous campaigns; a global too large to duplicate per campaign; users asking to *receive*
updates; or a paying tier. Until one of those is real, the fork model is strictly less work for the
same playable result.

## 8. Relationship to the existing documents

| document | becomes |
|---|---|
| [[Content Packages]] | **retained as future work** — superseded as the current direction |
| [[Content Registry]] | **retained as future work** — the catalog surface; the routing table it shared is all that survives now |
| [[Identity Programme]] | **mostly current** — accounts, campaigns and admission apply inside a fork; §5's platform consequences move to the future column |
| [[Tenancy Rollout Plan]] | revised — its Phase 1 stays, Phase 2 becomes **clone**, Phase 4 largely disappears |
| [[Content Packages]] §5's *one env var* note | **still true and still useful** — a sandbox exists today without any of this |

## 9. Open items

1. **Which way round the first migration goes** (§6) — the owner's, and it decides where the existing
   game lives.
2. **How a fork is invoked** — a button in an account UI, or an operator script at first? A script is
   much cheaper and may be all that is needed for the first few people.
3. **Whether edit rights are per-account or per-something-else**, and who the first editors are.
4. **What happens to a fork when the schema changes** — migrate all forks eagerly, or lazily on open?
5. **Whether the global is backed up on a schedule**, given it becomes the single source for everyone
   who forks after today.
6. **Does the account live in the global multiverse or beside it?** The routing table must not live in
   a database a fork is a copy of, or every fork gets a stale copy of the account list.

## Log

- 2026-10-15 — written from the owner's direction, who proposed it directly: *"what if for
  multi-tenancy we just start with a global shared multiverse that I can give rights to people to
  edit, and people can create an account in order to copy the global multiverse and start their own
  games in there? Instead of the whole package/sandbox story."* Verified the deciding fact before
  writing it up — **all 20,443 `_key`s are strings and edges are `collection/key`**, so a fork copies
  verbatim with **no handle remapping**, which is precisely the cost the package design could not
  avoid. The package design is **retained as a documented future direction** at the owner's explicit
  instruction, with the triggers that would bring it back recorded in §7. At the owner's direction the
  previous design is preserved rather than superseded-and-deleted.
- 2026-10-16 — **correction, found by [[multi-tenancy]] at its onboarding.** §2 said *"all **19**
  collections"* while §3's own table and the live database both enumerate **20** — an off-by-one in the
  label only; the copy/skip arithmetic was right. Fixed here, and the measurement dates are now marked
  because the counts move: 20,443 documents on 2026-10-15, **20,447** on 2026-10-16 (`historical_records`
  alone grew by 4). Worth recording that a fresh session reading this document found the error in its
  first hour — the numbers are only as good as the date beside them.

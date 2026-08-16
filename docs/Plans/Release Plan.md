---
title: Release Plan
tags:
  - transversal
  - plan
  - roadmap
  - game-design
  - technical
aliases:
  - Release
  - Roadmap
  - Phases
status: working
---

# Release Plan

> [!note] Status
> Working plan. Broad-strokes scope for the next release: what's in, what's cut, and the phased order. Captures the design decisions locked in the 2026-08-16 macro-design sessions.

## Goal

One release bar, stated as a player-visible sentence:

> A GM can prep a session (worlds, factions, GMCs, traits, SFX, life paths, starter locations) **and** a table can play it end-to-end — move, build pools, resolve tests *and* contests, apply the outcome to the world, and have SFX and the razmerit economy actually fire — with the earth-bond / full-native consequence loop live.

## The keystone

Almost every missing play-loop feature hangs off one primitive: **effect targeting + application**.

The backend already models it — `Effect.target` supports `{choose_*}` placeholders, `EffectActionMeta` carries `requires_choice` / `target_kind`, and `apply_effects` returns `pending_choices` for unresolved targets. What's missing is the **frontend that resolves those choices** and the **wizard that spends the effect die into a real state change**.

- **Effect targeting** = scoped, user-chosen target at resolution time (`select a location in universe X`, `select an occupant in this location`, `select a trait in this set`). Deliberate choice.
- **Roll tables** = fixed entries, random selection. For randomized outcomes (random scatter, random grogs).
- The two are complementary, not competing. The keystone is targeting; roll tables already work.

The second keystone is **contest wiring** — drive the existing `resolve_contest` resolver + per-location contest tracker from the UI (challenger/defender, opposition display, winner/loser). The backend resolves contests correctly; the frontend never calls it.

## Release scope (include)

### 1. Keystone — effect targeting & application
- Scoped picker dialogs: location / occupant / trait / rating-die, filtered by the effect's `target_kind` + `target_scope`.
- A wizard that chains effect-targeting dialogs into a single application.
- Effect-die application: after a test/contest, spend the effect die into a state change (step down a challenge, create a complication, apply the authored effect list below).

### 2. Contest wiring
- Show opposition in the dice pool (tabs).
- Differentiate challenger vs defendant.
- Declare winner/loser from the two assembled pools (drive the tracker + resolver).
- Style the dice pool per test / contest / challenger / defendant / roll-table.

### 3. Effects actually fire
- SFX triggers fire in the roll/contest flow (`on_roll` / `on_complication` / `on_success` / `on_botch`).
- Razmerit loop closes: hitches/botches earn razmerit that **persists** (today it's computed and discarded).
- Two new effect primitives required by the consequences layer (below):
  - **Switch projection type** effect — mutate a projection's `transversal_type`.
  - **Challenge trait emptied** trigger — when a challenge trait's rating reaches zero, fire its associated SFX.

### 4. Consequences — challenge pools + earth-bond
- Generic challenge / doom-pool loop (the resolver already compares effect-die vs challenge-die).
- **Earth-bond**: a trait with a challenge-type rating (negative polarity), with SFX targeting it. When it reaches zero it triggers an SFX whose effect switches the projection type to native (full-native). Composed from the primitives above — no special-purpose code.

### 5. Prep & content
- **MCP wrappers** over the existing GraphQL mutations (traits, traitsets, SFX, life paths, roll tables, relationships, projections). Thin, idempotent, no AQL.
- **Starter locations**: multiple per universe. Default spawn is a **roll table** (random scatter) — see [[#Locked decisions]].
- GM content-tool polish (fold in the relevant to-do items).

## Deferred (cut / post-release)

- **`modify_roll` / `modify_outcome` effects** — deferred. Also **hide from the editor** until implemented, so content can't author silent no-ops.
- **Controlled transversal (razmerit-tech)** — the player-built technology that overrides random scatter and lets you choose your destination. Post-release; it's the reward the random-scatter default is meant to incentivize.
- **Troupe play** — spotlight recency list, grog roll tables, companion GMCs, archetype instantiation. See [[Inspired Mechanics]] and the troupe discussion.
- **Auth / accounts** — out of scope. Not public; GM (architect) + known players only. `players` collection with `role` (`player` / `architect`) is sufficient for now.

## Locked decisions (this session)

- **Earth-bond** is a challenge trait (negative), not a dedicated entity field. Empty → trigger → "switch projection type" effect → native. *(The fuller full-native sequence — Earth projection decay, Earth-anchored traits step down — may be additional effects on the same SFX; TBD, don't over-specify.)*
- **Starter locations**: multiple per universe; **roll-table default** (random scatter). Players invent razmerit technology to control the scatter — deliberate destination is *earned*, not given.
- **Effect targeting vs roll tables**: targeting = deliberate choice within a scope; roll tables = fixed random entries. Both ship; targeting is the keystone.
- **Earth-bond as a resource** — rejected. It's a challenge (doom) pool, not a spendable resource.
- **Full-native** = identity shift, not death.
- **Troupe rotation** stays soft; spotlight aid is an ordered "who last played their main" recency list (not a hard rule).
- **Support cast** = two tiers: authored companion GMCs + disposable grogs from roll tables.
- **`modify_roll` / `modify_outcome`** = defer (above).

## Open questions / stubs

- Exact effect list on the full-native SFX (Earth projection decay, Earth-trait step-down) — TBD.
- Flashback SFX exact fill-in (still a stub in [[Projections and Transversal]]).
- Whether the release bar includes the full earth-bond loop or only the generic challenge-pool loop + a placeholder earth-bond trait (confirm during build).

## Mapping to to-do

The plan is the *sequencing* of the existing user-generated to-do list; it does not add to it.

- **Keystone** → "Create an effect targeting dialog", "Create a wizard that chains effect targeting dialogs", the Effects list (challenge rating, set/step up trait, step down, create complication, exorcise/banish/swap, temporary location asset), "Enable dicepool win effect die application wizard".
- **Contest** → "Show opposition during contest", "Differentiate challenger/defendant", "Style dicepool", "Own dice pool should persist after refresh".
- **Triggers** → "Reaching a specified-rating on a specified-trait" (the earth-bond trigger), "Visiting a specified-location", "Creating specified-relation", "Gaining a specified-trait".
- **Prep** → "Designate universe-scoped starter locations", "Create GMC creation MCP SKILL.md", "Do another migrate from the old app".

## See also

- [[Projections and Transversal]] — earth-bond, full-native, traversal model
- [[SFX and Effects]] — effects system and unified effect model
- [[Unified Effects Plan]] — the shared effect vocabulary
- [[Inspired Mechanics]] — troupe play, challenge pools
- [[to-do]] — the user-generated work list

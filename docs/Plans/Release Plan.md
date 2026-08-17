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
- **SFX owner model** — SFX gain an `owner` (trait / trait set / entity / projection / table / GM) so system moves become authored SFX. Today SFX attach only to traits; "push" is hardcoded in the contest tracker and "buy a hitch" isn't built.
- SFX triggers fire in the roll/contest flow (`on_roll` / `on_complication` / `on_success` / `on_botch`).
- Razmerit loop closes: hitches/botches earn razmerit that **persists** (today it's computed and discarded).
- Two new effect primitives required by the consequences layer (below):
  - **Switch projection type** effect — mutate a projection's `transversal_type`.
  - **Challenge trait emptied** trigger — when a challenge trait's rating reaches zero, fire its associated SFX.

### 4. Consequences — challenge pools + earth-bond
- Generic challenge / doom-pool loop (the resolver already compares effect-die vs challenge-die).
- **Earth-bond / tether**: a *sub-trait of the Origin distinction* (challenge/negative), with SFX targeting it. When it reaches zero it triggers an SFX whose effect switches the projection type to native (full-native). Composed from primitives — no special-purpose code.

### 5. Prep & content
- **MCP wrappers** over the existing GraphQL mutations (traits, traitsets, SFX, life paths, roll tables, relationships, projections). Thin, idempotent, no AQL.
- **Starter locations**: multiple per universe. Default spawn is a **roll table** (random scatter) — see [[#Locked decisions]].
- GM content-tool polish (fold in the relevant to-do items).

## Deferred (cut / post-release)

- **`modify_roll` / `modify_outcome` effects** — deferred. Also **hide from the editor** until implemented, so content can't author silent no-ops.
- **Heroic success** (beat the difficulty by 5+ → step up the effect die per 5) — deferred. Core in Cortex Prime, but feels too swingy here; ties-favor-initiator already rewards action. Revisit after the spine is playable.
- **Controlled transversal (razmerit-tech)** — the player-built technology that overrides random scatter and lets you choose your destination. Post-release; it's the reward the random-scatter default is meant to incentivize.
- **Troupe play** — spotlight recency list, grog roll tables, companion GMCs, archetype instantiation. See [[Inspired Mechanics]] and the troupe discussion.
- **Auth / accounts** — out of scope. Not public; GM (architect) + known players only. `players` collection with `role` (`player` / `architect`) is sufficient for now.

## Build order

Phases are dependency-ordered; each is a shippable slice. Detailed per-scenario findings live in [[Pressure-Test Log]]; the ticket-level breakdown (with per-ticket dependencies + context to load) lives in [[Tickets]].

### Phase 1 — Keystone: effect targeting & application

The one primitive everything else hangs off.

- Scoped target pickers: location / occupant / trait / rating-die, filtered by `target_kind` + `target_scope` — plus a **`random` mode** (for starter-location scatter).
- The **two-sided consequence menu** (the effect-application wizard): player options (proceed / decrease the doom pool / create a scene trait at effect-die rating) vs GM options (increase the doom pool / apply a complication / give a GMC an asset).
- Unblocks: starter locations, trait transfer, doom pools, and every SFX that applies a consequence.

### Phase 2 — Play spine: tests & contests actually resolve

- **Test vs contest as first-class** — a roll knows which it is (drives styling, SFX triggers, and the consequence menu).
- **Opposition UI** — GM test difficulty via preset buttons (**very easy 2d4 → very hard 2d12**) auto-added to the opposition pool, plus trait dice; the GM rolls first → threshold. **Stakes (opponent's effect die) are contest-only.**
- **Challenger/defendant** modeling — **ties favor the initiator** (Cortex Prime: the opponent must *beat* the initiator's total), so the winner isn't a positional artifact.
- **Contest resolve returns full rolls + effect dice**, not just `{winner, pipeline, pushed}`.
- **Razmerit persistence** — hitches/botches earn razmerit that's written back.
- **Dice pool persistence** — survives refresh / mobile memory eviction.
- **SFX triggers fire** in the roll/contest flow (wire `fire_contest_sfx`; `on_roll` / `on_complication` / `on_success` / `on_botch`).

### Phase 3 — Stakes & consequences: doom pools + earth-bond/tether

- **Looming doom dice** — prominent render + click model (left-click step down, right-click step up; GM can hand a challenge to a player).
- **Buy-hitch** — GM spends a doom die → escalate → complication.
- **Challenge resolution routes through the consequence menu → effect system** (the "challenge rating" effect), not resolver persistence.
- **Earth-bond/tether** — the tether is a *sub-trait of the Origin distinction* (challenge/negative); "challenge emptied" trigger → SFX → "switch projection type" effect → full-native. *(This supersedes the earlier "earth-bond = challenge trait" framing — see [[Pressure-Test Log]].)*
- Depends on sub-trait authoring (Phase 4) — or seed the tether as content in the meantime.

### Phase 4 — Character sheet: traits as first-class

- **Relationship traits inline** — render the `_to` portrait; the backend serves them like the character's own traits (folded into the character query).
- **Sub-traits** (the tether depends on this).
- **Empty/descriptive traits** = a "profile" surface (pronouns, nickname, appearance).
- **`duplicates_allowed`** flag (per trait-set/trait): two melee weapons OK, two strengths not.
- **Trait click behavior** — static = add, resource = spend, challenge = oppose; GM = step up/down.

### Phase 5 — Prep & content: GM can build + spawn

- **MCP wrappers** over the existing GraphQL mutations (traits, traitsets, SFX, life paths, roll tables, relationships, projections).
- **Starter locations** (multiple per universe) + **`location → universe` transversal edges** → random starter-location pipeline (roll table).
- **Reusable shared (unaffiliated) roll tables** — authoring UX (single-exit only; see [[Life Path Flow and Shared Roll Tables]]).
- **GM scene overview** — three groups: currently-played (entity + projection, incl. support characters), each player's main character(s), current-location GMCs. Needs **live-player tracking**.
- Fix create-entity panel bugs (parent context, unconditional razmerit, no universe creation).

### Phase 6 — Movement & projections

- **Projections as first-class** — nav dots render *projections*, not entities; ownership chain `projection → entity → agency → player`; GM sees all, players see live ones.
- **Live-player tracking** (unblocks Phase 5's GM overview + this).
- **Inapposite travel: dedicated REST endpoint** (currently only GraphQL; the UI falls back to a generic move).
- **Attunement expiry** — manual `attune disable` as a patch; the auto-scheduler at timing boundaries is still desired.
- **Starter-location spawn on arrival** (ties to Phase 5's `location → universe` edges).

---

## Locked decisions (this session)

- **Earth-bond / tether** is a *sub-trait of the Origin distinction* (challenge/negative), not a dedicated entity field. Empty → trigger → "switch projection type" effect → native. *(The fuller full-native sequence — Earth projection decay, Earth-anchored traits step down — may be additional effects on the same SFX; TBD, don't over-specify.)*
- **Starter locations**: multiple per universe; **roll-table default** (random scatter). Players invent razmerit technology to control the scatter — deliberate destination is *earned*, not given.
- **Effect targeting vs roll tables**: targeting = deliberate choice within a scope; roll tables = fixed random entries. Both ship; targeting is the keystone.
- **Earth-bond as a resource** — rejected. It's a challenge (doom) pool, not a spendable resource.
- **Full-native** = identity shift, not death.
- **Troupe rotation** stays soft; spotlight aid is an ordered "who last played their main" recency list (not a hard rule).
- **Support cast** = two tiers: authored companion GMCs + disposable grogs from roll tables.
- **`modify_roll` / `modify_outcome`** = defer (above).
- **SFX owner** — every SFX has one of six owners: `trait`, `trait set`, `entity` (characters, locations, factions, GMCs, assets, universes), `projection` (body), `table` (everyone), `GM`. System moves are SFX too — "push a contest" (table) and "buy a hitch" (GM) — not hardcoded rules. Universes are entities, so a universe move is just an entity SFX.
- **Tests don't create stakes** — a test is pass/fail plus the roller's own effect die sizing the outcome; the opponent's effect die only matters in contests (winner vs loser). We follow Cortex Prime here.
- **Ties favor the initiator** — the opponent must *beat* the initiator's total, so a tie means the initiator wins (not "ties go to the defender").
- **Simplified rolling stays** — the 1–2 die → tier pipeline remains for quick rolls; full pools for important beats. Challenge ratings are doom pools (separate Cortex chapter, not yet copied). GM test difficulty = preset buttons (very easy 2d4 → very hard 2d12) auto-added to the opposition pool, plus trait dice.
- **Heroic success is deferred** (see Deferred) — the beat-by-5 effect-die step-up feels too swingy.
- **Effect-die auto-selection excludes hitches** — auto-pick the largest leftover die that isn't a hitch, in both the resolver and the dice-pool UI.
- **Contest outcomes are first-class but phased** — give-in this release; high-stakes/taken-out, interference, multiway, and complication-over-d12-taken-out are later tickets in [[Tickets]].
- **GM manual test-difficulty selection** — the GM rolls the opposition pool and *picks* the two dice that set the difficulty (Cortex: "add together two dice from the roll"), rather than auto-keeping the top two. This is the two-step flow, and it needs `static_difficulty` support in the simplified pipeline.

## Open questions / stubs

- **`static_difficulty` opposition type** — now a Cortex *mod*, not the default test (preset difficulty dice are). Keep it available or drop it? TBD.
- Exact effect list on the full-native SFX (Earth projection decay, Earth-trait step-down) — TBD.
- Flashback SFX exact fill-in (still a stub in [[Projections and Transversal]]).
- **Events / trigger-condition-limit unification** — "hooks" became "events" (a condition + effects). Decide whether `trigger` and `condition` are one concept and whether `limit` folds into `condition`. Resolve in Phase 2 (SFX triggers).
- **`effective_universes` divergence** — the code unions all NATIVE projection universes when the entity has more than one (a "multiversal being" rule) that [[Projections and Transversal]] doesn't document. Decide: document it or revert it.
- **[[SFX and Effects]] top half is stale** — prune the old `effect`/`cost`/`modify_roll` model; keep the "Unified Effect Model" section.

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

---
title: Tickets
tags:
  - transversal
  - plan
  - tickets
  - build-order
  - work-items
aliases:
  - Work Items
  - Ticket List
  - Breakdown
status: working
---

# Tickets

The [[Release Plan#Build order]] broken into independently shippable work items. Each ticket records **what**, **done** (acceptance), **depends**, and **load** (the context to consult for that work — docs and code files). Evidence behind each item lives in [[Pressure-Test Log]].

> [!note] How to use
> One ticket (or a tight 2-ticket batch) per session/compaction. Load the "load" list, do the work, check "done". Phases are review checkpoints, not work units.

## Phase 1 — Keystone: effect targeting & application

### P1.1 — Backend: complete `{choose_*}` target resolution
- **What:** finish resolving `{choose_*}` targets and returning clean `pending_choices` (partly modeled).
- **Done:** an effect with `target="{choose_location}"` yields a pending choice the caller can resolve and re-apply.
- **Depends:** — (foundation)
- **Load:** `services/effects_applier.py` (`_resolve_target`, `PendingChoice`), `services/effects_commit.py`, `domain/__init__.py` (Effect), [[Unified Effects Plan]].

### P1.2 — Backend: `random` target mode
- **What:** add a `random` target resolution (pick a random in-scope entity/trait).
- **Done:** a `{random:…}` target resolves to a random candidate (basis for starter-location scatter).
- **Depends:** P1.1
- **Load:** `effects_applier.py`, `domain/__init__.py`, [[Pressure-Test Log]] § Scenarios 3 & 6.

### P1.3 — Frontend: scoped target picker dialogs
- **What:** location / occupant / trait / rating-die pickers filtered by `target_kind` + `target_scope`.
- **Done:** a picker shows the right candidates for a scope and returns a resolved id.
- **Depends:** P1.1
- **Load:** `components/gm/GmLocationPicker.vue`, `GmTraitPicker.vue`, `SearchDropdown.vue`, to-do "Create additional pickers".

### P1.4 — Frontend: effect-application wizard
- **What:** chain P1.3 pickers into one step-by-step application flow.
- **Done:** a multi-target effect can be authored/run through the wizard.
- **Depends:** P1.3
- **Load:** `components/gm/EffectEditor.vue`, `composables/useEffectActions.js`, to-do "Create a wizard that chains effect targeting dialogs".

### P1.5 — Frontend: two-sided consequence menu
- **What:** after a test/contest, offer player options (proceed / decrease doom / create scene trait) or GM options (increase doom / apply complication / give asset), wired to effects.
- **Done:** a resolved roll offers the correct menu and applying an option writes state via the effect system.
- **Depends:** P1.3, P1.4
- **Load:** `components/DiceRoller.vue` (PICKING/RESOLVED), [[Pressure-Test Log]] § Scenario 3 target design.

## Phase 2 — Play spine: tests & contests resolve

### P2.1 — Backend: test vs contest as first-class
- **What:** a roll knows its kind (test / contest / roll-table), flowing through the resolver and results.
- **Done:** the roll/contest path carries an explicit kind, exposed to the UI and SFX triggers.
- **Depends:** —
- **Load:** `services/dice_resolver.py`, `api/rest/roll.py`, `services/contest_tracker.py`, [[Pressure-Test Log]] § Scenario 4.

### P2.2 — Backend: return the opponent's effect die (stakes)
- **What:** the resolver returns the opposition's effect die alongside the result.
- **Done:** a GMC/challenge opposition roll reports its effect die (the "stakes").
- **Depends:** P2.1
- **Load:** `services/dice_resolver.py` (`_resolve_simplified`/`_resolve_pool`), [[Pressure-Test Log]] § Scenario 3.

### P2.3 — Backend: contest resolve returns full rolls + effect dice
- **What:** `/locations/{id}/pools/{entity_id}/resolve` returns rolls and effect dice, not just `{winner, pipeline, pushed}`.
- **Done:** a contest result includes both sides' rolls and effect dice.
- **Depends:** P2.1
- **Load:** `api/rest/contest_pools.py`, `services/contest_tracker.py`, `services/dice_resolver.py`.

### P2.4 — Backend: challenger/defendant modeling
- **What:** a stored role distinguishes who initiated vs who defends (fixes positional "ties go to defender").
- **Done:** ties resolve against the modeled defendant, not whoever is the resolve argument.
- **Depends:** P2.1
- **Load:** `services/contest_tracker.py` (`set_opposition`), `domain/__init__.py` (PoolAssembly), [[Pressure-Test Log]] § Scenario 4.

### P2.5 — Frontend: opposition UI (GM rolls first)
- **What:** set static difficulty / GMC / challenge opposition; GM rolls first → threshold + stakes, then player rolls.
- **Done:** a test/contest can be set up with opposition and the GM's roll is a visible first step.
- **Depends:** P2.2
- **Load:** `components/DiceRoller.vue`, `components/LocationViewer.vue`, `composables/useApi.js` (`roll` opposition param).

### P2.6 — Backend: razmerit persistence
- **What:** hitches/botches earn razmerit that is written back (today computed and discarded).
- **Done:** a hitch increases the character's razmerit balance and publishes an SSE event.
- **Depends:** —
- **Load:** `services/razmerit.py`, `services/effects_commit.py`, [[Pressure-Test Log]] § Scenario 3.

### P2.7 — Backend + frontend: dice pool persistence
- **What:** an assembled pool survives refresh / mobile memory eviction (keyed by beat).
- **Done:** reloading the page shows the dice already added to the pool.
- **Depends:** —
- **Load:** `services/contest_tracker.py` (in-memory), to-do "Own dice pool should persist after refresh".

### P2.8 — Backend: wire SFX triggers into the roll/contest flow
- **What:** `on_roll` / `on_complication` / `on_success` / `on_botch` (and contest win/loss) fire automatically.
- **Done:** a roll/contest fires matching SFX without a manual `/effects/trigger` call.
- **Depends:** P2.1
- **Load:** `services/effects_engine.py` (`fire_contest_sfx`, `process_event`), `api/rest/effects.py`, [[Pressure-Test Log]] § Scenario 4.

## Phase 3 — Stakes & consequences

### P3.1 — Frontend: looming doom dice render
- **What:** a location-scoped challenge (doom) pool renders prominently at top of screen.
- **Done:** the GM sees the doom pool as a labeled dice cluster.
- **Depends:** —
- **Load:** [[Pressure-Test Log]] § Scenario 1 (doom pool) & 5, old `Rating.vue` (challenge rendering).

### P3.2 — Frontend: doom-pool click model
- **What:** left-click steps a doom die down, right-click steps up; GM can hand a challenge to a player.
- **Done:** the doom pool is manip: up/down/hand-off via clear affordances.
- **Depends:** P3.1
- **Load:** old `vue/src/components/Trait.vue` (`deplete_challenge`/`increase_challenge`), [[Pressure-Test Log]] § Scenario 5 UX note.

### P3.3 — Backend + frontend: buy-hitch
- **What:** GM spends a doom die to buy a player's hitch → escalate → apply a complication.
- **Done:** a hitch can be bought by spending doom-pool dice, producing a complication on the target.
- **Depends:** P3.1 (render), P2.8 (hitch trigger)
- **Load:** [[Pressure-Test Log]] § Scenario 5, `services/effects_applier.py` (complication effects).

### P3.4 — Backend + frontend: challenge resolution via effect system
- **What:** the consequence menu's "challenge rating" option applies effect-die-vs-challenge-die through the effect system, not resolver persistence.
- **Done:** picking the challenge option steps the doom pool down/up via an effect.
- **Depends:** P1.5, P3.1
- **Load:** `services/dice_resolver.py` (`_resolve_challenge`), `services/effects_commit.py`, to-do "challenge rating" effect.

### P3.5 — Backend + frontend: tether = sub-trait of Origin
- **What:** author the tether as a challenge/negative sub-trait of the Origin distinction (and seed it).
- **Done:** a character has a tether sub-trait under Origin that counts down.
- **Depends:** P4.2 (sub-traits)
- **Load:** [[Pressure-Test Log]] § Macro decisions (tether), `domain/__init__.py` (SubTraitRef, sub_trait_settings).

### P3.6 — Backend: "challenge emptied" trigger + "switch projection type" effect + full-native
- **What:** a challenge trait reaching zero fires its SFX; the effect switches `transversal_type`; full-native is authored from these.
- **Done:** emptying the tether triggers full-native via the event system.
- **Depends:** P3.5, P2.8
- **Load:** [[Projections and Transversal]], `services/effects_applier.py` (`_attune`, travel), `domain/__init__.py` (TransversalType).

## Phase 4 — Character sheet: traits as first-class

### P4.1 — Backend + frontend: relationship traits inline
- **What:** relationship traits render the `_to` portrait and are served like the character's own traits (folded into the character query).
- **Done:** a relationship trait shows up in the character sheet with the related entity's portrait.
- **Depends:** —
- **Load:** `db/repository.py` (`assemble_character`, relationship trait queries), [[Pressure-Test Log]] § Macro decisions.

### P4.2 — Backend + frontend: sub-traits
- **What:** full sub-trait support in the sheet (nesting, matching, edit).
- **Done:** a trait can carry sub-traits that behave per their rating type.
- **Depends:** —
- **Load:** `domain/__init__.py` (SubTraitRef), to-do "Sub-traits", old `SubTrait.vue`.

### P4.3 — Frontend: empty/descriptive traits = profile surface
- **What:** pronouns, nickname, appearance (empty traits) get a simple text "profile" surface, not the dice editor.
- **Done:** an empty trait is editable as plain text, respecting ego/morph.
- **Depends:** —
- **Load:** to-do "Profile traits (empty, but with ego/morph)", `domain/__init__.py` (RatingType.EMPTY).

### P4.4 — Backend + frontend: `duplicates_allowed`
- **What:** a per-trait-set/trait flag allows two of the same trait (two weapons) while defaulting to no-dupes.
- **Done:** a set flagged `duplicates_allowed` lets the picker add the same trait twice.
- **Depends:** —
- **Load:** `domain/__init__.py` (TraitSet, Trait), `components/CharacterSheet.vue` (picker filtering), [[Pressure-Test Log]] § Macro decisions.

### P4.5 — Frontend: trait click behavior
- **What:** static = add to pool, resource = spend, challenge = oppose; GM = step up/down.
- **Done:** clicking a trait does the right verb for its rating type, without view-mode gymnastics.
- **Depends:** P2.5 (pool), P4.2 (sub-traits)
- **Load:** old `vue/src/components/Trait.vue` (the "tangled mess"), [[Pressure-Test Log]] § Scenario 5 UX note.

## Phase 5 — Prep & content

### P5.1 — Backend: MCP wrappers
- **What:** thin MCP tools over existing GraphQL mutations (traits, traitsets, SFX, life paths, roll tables, relationships, projections).
- **Done:** the MCP server can create/edit these via standardized tools (no AQL).
- **Depends:** —
- **Load:** `mcp/server.py`, `api/graphql/schema.py`, [[Pressure-Test Log]] § Backend inventory (MCP drift).

### P5.2 — Backend + frontend: starter-location designation
- **What:** mark multiple locations per universe as "starter".
- **Done:** a universe has a set of starter locations queryable by the spawn flow.
- **Depends:** —
- **Load:** to-do "Designate universe-scoped starter locations", `domain/__init__.py` (Entity, location).

### P5.3 — Backend + frontend: `location → universe` transversal edges
- **What:** a transversal edge may target a universe (not just a location); traversing it triggers spawn.
- **Done:** a location can connect to a whole universe as a destination.
- **Depends:** —
- **Load:** `api/rest/locations.py` (`create_edge`), [[Pressure-Test Log]] § Scenario 6.

### P5.4 — Backend + frontend: random starter-location pipeline
- **What:** traversing to a universe rolls a random starter location (roll table), using P1.2's `random` mode.
- **Done:** arriving in a new universe spawns at a random starter location.
- **Depends:** P1.2, P5.2, P5.3
- **Load:** [[Pressure-Test Log]] § Scenario 6, `services/roll_table.py`.

### P5.5 — Frontend: shared roll-table authoring UX
- **What:** make linking a shared (unaffiliated) table into a life path obvious (single-exit only).
- **Done:** an author can link a shared table and set `return_to` without editing raw JSON.
- **Depends:** —
- **Load:** [[Life Path Flow and Shared Roll Tables]], `components/gm/EffectEditor.vue` (context textarea).

### P5.6 — Backend + frontend: live-player tracking + GM scene overview
- **What:** track which entity each player is actively playing; render the GM overview in three groups (currently-played incl. support, each player's mains, current-location GMCs).
- **Done:** the GM scene view shows live mains + local GMCs and can be reordered.
- **Depends:** —
- **Load:** `services/player_manager.py` (agency), [[Pressure-Test Log]] § Scenario 6 & 7.

### P5.7 — Frontend: create-entity panel fixes
- **What:** fix parent-context (tree selection), unconditional razmerit, and missing UNIVERSE type.
- **Done:** creating a child/zone uses the selected parent; razmerit hidden for non-razmerit types; universe creatable.
- **Depends:** —
- **Load:** `components/gm/GmEntityCreatePanel.vue`, `GmEntityForm.vue`, [[Pressure-Test Log]] § Scenario 1 bugs.

## Phase 6 — Movement & projections

### P6.1 — Backend + frontend: projections as first-class (nav dots)
- **What:** nav dots render projections (not entities); GM sees all, players see live ones; ownership `projection → entity → agency → player`.
- **Done:** nav dots reflect projections, filtered to live players.
- **Depends:** P5.6 (live tracking)
- **Load:** `api/rest/locations.py` (`navigate`, `_resolve_navdot`), [[Pressure-Test Log]] § Scenario 6.

### P6.2 — Backend + frontend: inapposite travel endpoint
- **What:** a dedicated REST endpoint for inapposite travel, wired into the movement flow.
- **Done:** an inapposite portal performs in-place universe/location mutation with `INAPPOSITE` type.
- **Depends:** —
- **Load:** `services/entity_manager.py` (`inapposite_travel`), `api/rest/locations.py`, [[Pressure-Test Log]] § Scenario 6.

### P6.3 — Backend: attunement expiry
- **What:** manual `attune disable` as a patch; wire the auto-scheduler (still desired) for timing-boundary expiry.
- **Done:** an attunement can be removed manually and (later) auto-expires.
- **Depends:** —
- **Load:** `services/effects_applier.py` (`_attune`), `services/effects_engine.py` (`tick_scene`), [[Pressure-Test Log]] § Backend inventory.

### P6.4 — Backend + frontend: starter-location spawn on arrival
- **What:** hook P5.4 into the travel flow so arriving in a new universe spawns at the rolled starter location.
- **Done:** consciousness/inapposite arrival in a fresh universe lands at a starter location.
- **Depends:** P5.4, P6.2
- **Load:** `services/entity_manager.py` (`consciousness_travel`, `inapposite_travel`), [[Pressure-Test Log]] § Scenario 6.

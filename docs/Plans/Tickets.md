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
>
> **Coverage guarantee:** every unchecked item in [[to-do]] maps to a ticket below or to the explicit deferred list at the bottom. Nothing is second-class or silently dropped.

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

### P1.6 — Frontend: effect-die application
- **What:** substitute the roll's effect die into a consequence option's effects before applying (the ``{effect_die}`` placeholder in ``result``).
- **Done:** "Create a scene trait" / "Apply a complication" / "Give an asset" land at the roll's actual effect-die rating, not a fixed die.
- **Depends:** P1.5
- **Load:** `services/consequence_menu.py` (base moves), `composables/useConsequences.js`, `components/gm/ConsequenceMenu.vue`, `components/DiceRoller.vue` (`effectDie`).

### P1.7 — Backend: duration-scoped trait effects
- **What:** implement the duration-carrying effects from the to-do Effects list: temporary location asset, disable a trait, and step-down (own / target-entity) with a ``duration`` context that schedules the revert.
- **Done:** these effects are appliable via the effect system and revert (or expire) at their duration boundary through the shared scheduler.
- **Depends:** P1.1, P6.3 (expiry scheduler)
- **Load:** to-do "Effects", `services/effects_applier.py` (`_MUTATION_HANDLERS`), `services/effects_engine.py` (`schedule_effect`), `services/effects_commit.py`.

### P1.8 — Backend: effect-die comparison + trait-set limit effects
- **What:** implement "set or step up target-trait rating" (set if effect die > target die, step up if ≤) and "increase/set trait set limit".
- **Done:** both are Effect actions; the comparison one takes the effect die and the target die and applies the correct operation.
- **Depends:** P1.1, P1.6
- **Load:** to-do "Effects" (set/step-up target-trait, increase/set trait set limit), `services/effects_applier.py`, `services/dice_resolver.py` (`_resolve_challenge` pattern).

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

### P2.9 — Backend: condition-based SFX triggers
- **What:** state-change triggers from the to-do Triggers list fire SFX: visiting a specified-location, creating a specified-relation, gaining a specified-trait, gaining from a specified-traitset, reaching a specified-rating.
- **Done:** each condition is authored and evaluated via the existing `Condition` machinery, firing matching SFX on the state change.
- **Depends:** P2.8
- **Load:** to-do "Triggers", `services/conditions.py`, `domain/__init__.py` (`Condition`, `ConditionType`), `services/effects_engine.py` (`_trigger_matches`).

### P2.10 — Frontend: dice-pool styling per roll kind
- **What:** the pool is visually distinguished by simple-test / cortex-test / challenger-contest / defendant-contest / roll-table.
- **Done:** a user can tell at a glance what they're rolling for from the pool styling.
- **Depends:** P2.1
- **Load:** to-do "Style dicepool", `components/DiceRoller.vue`, [[Pressure-Test Log]] § Scenario 4.

### P2.11 — Frontend: rolling dice animation
- **What:** a short animation on roll (blinking random faces or an infinite-scroll feel).
- **Done:** dice visibly animate before settling on the result.
- **Depends:** —
- **Load:** to-do "Rolling dice animation", `components/DieIcon.vue`, `components/DiceRoller.vue`.

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

### P5.8 — Frontend: create roll tables from the life-path canvas
- **What:** a new roll table can be created directly from the life-path canvas layout (not just linked).
- **Done:** an author creates and wires a fresh roll table without leaving the canvas.
- **Depends:** P5.5
- **Load:** to-do "Enable new roll table creation for life paths from the life path canvas layout", `components/gm/GmRollTableEditPanel.vue`, `composables/useLifePaths.js`.

### P5.9 — Content: GMC creation MCP SKILL.md
- **What:** a documented MCP skill for creating GMCs (and their traits/relationships) via the standardized mutation wrappers.
- **Done:** the skill exists and produces a playable GMC through MCP, no AQL.
- **Depends:** P5.1
- **Load:** to-do "Create GMC creation MCP SKILL.md", `skills/`, `mcp/server.py`.

### P5.10 — Migration: another migrate from the old app
- **What:** a new migration script pulling the current old-app data into Transversal2's v2 model.
- **Done:** a run produces entities/traits/SFX/life paths in the new collections.
- **Depends:** —
- **Load:** to-do "Do another migrate from the old app", `src/api/src/transversal/migrate_traits.py`, `arangodump/`.

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

### P6.5 — Backend + frontend: projection & travel effects
- **What:** implement exorcise (send a target's projection to another universe), banish (random inapposite travel), swap (swap two of a character's projections), and create temporary projection (disguise / alternative identity).
- **Done:** each is an Effect usable from the consequence menu / SFX, with ``{choose_*}`` targets for the involved entities and universes.
- **Depends:** P1.1, P6.1, P6.2
- **Load:** to-do "Effects" (exorcise / banish / swap / create temporary projection), `services/effects_applier.py`, `services/entity_manager.py` (travel), `domain/__init__.py` (Projection).

## Phase 7 — Polish & backlog

> Everything here is a real ticket with the same shape as Phase 1–6. They are post-release polish / backlog, not release blockers.

### P7.1 — Frontend: trait rendering & polarity polish
- **What:** empty traits not greyed out, morph traits highlighted (not ego), negative-polarity styling, hidden/visible trait hint, and ``[dX]`` → ``DieIcon``.
- **Done:** each rendering/affordance behaves as listed.
- **Depends:** P4.3
- **Load:** to-do "Character Sheet & Traits", `components/CharacterSheet.vue`, `components/DieIcon.vue`.

### P7.2 — Frontend: trait notes field
- **What:** statement/notes split — single-line statement for ≤7 words, a textarea for notes, and a second input so both can co-exist.
- **Done:** a trait can carry a short statement and longer notes together.
- **Depends:** —
- **Load:** to-do "Trait notes field", `components/CharacterSheet.vue`, `domain/__init__.py` (`TraitSetting.statement`).

### P7.3 — Frontend: phased trait picker
- **What:** replace the accordion-style trait set / trait listing with a phased picker.
- **Done:** picking a trait is a phased flow instead of nested accordions.
- **Depends:** —
- **Load:** to-do "Instead of an accordion style trait sets / traits, try a phased trait picker", `components/CharacterSheet.vue`.

### P7.4 — Frontend: unify drag-and-drop + longpress composable
- **What:** one composable drives both pointer drag-and-drop and long-press-and-drop.
- **Done:** both interactions route through a single composable.
- **Depends:** —
- **Load:** to-do "Unify drag-and-drop and longpress-and-drop into a composable", `components/gm/`, `composables/`.

### P7.5 — Frontend: universal picker
- **What:** unify location / occupant / trait / rating-die pickers into one picker over typed documents (extends ``ScopedTargetPicker``).
- **Done:** one picker handles all target document types.
- **Depends:** P1.3
- **Load:** to-do "Unify the pickers", `components/gm/ScopedTargetPicker.vue`, `components/gm/GmLocationPicker.vue`, `components/gm/GmTraitPicker.vue`.

### P7.6 — Frontend: GM panel management
- **What:** detach panels, open panels directly from outside the hierarchy, and collapse/expand panels (hide, not close; including children).
- **Done:** each panel-management affordance works.
- **Depends:** —
- **Load:** to-do "GM Panels", `components/gm/PanelStack.vue`, `composables/usePanel.js`.

### P7.7 — Frontend: longpress-drag reorder on location tree
- **What:** make tree reordering genuinely long-press initiated (currently not specifically long-press).
- **Done:** reorder on the location tree is long-press initiated.
- **Depends:** P7.4
- **Load:** to-do "apply longpress-and-drag to reorder on location tree", `components/gm/GmLocationTree.vue`.

### P7.8 — Frontend: shared image/video component
- **What:** unify background-image and ``<video>`` rendering into one component.
- **Done:** one component renders either media type.
- **Depends:** —
- **Load:** to-do "Unify background-image/video images into a shared component", `components/gm/ImageViewer.vue`.

### P7.9 — Frontend: image viewer & portrait UX
- **What:** image-viewer delete-button styling, open viewer on character-sheet portrait click, clarify which image (background / sheet / navdot) renders where, and make projections own their images.
- **Done:** portrait → viewer works and image-role overlap is resolved.
- **Depends:** P6.1
- **Load:** to-do "Images, Media & Generation", `components/gm/ImageViewer.vue`, `components/CharacterSheet.vue`.

### P7.10 — Media: portrait processing
- **What:** remove portrait background (transparent) and switch circular app portraits to semi-circular bottom / uncropped top.
- **Done:** generated/uploaded portraits render with the new crop + transparency.
- **Depends:** —
- **Load:** to-do "Delete the background... semi-circular", imagen pipeline.

### P7.11 — Media: animation pipeline
- **What:** WEBM → MP4 (with alpha for portraits) and feed "idle pose" + traits into the Gemma hint.
- **Done:** animations output MP4 and use the richer hint.
- **Depends:** —
- **Load:** to-do "Change animate output from WEBM to MP4", `composables/useEntityCrud.js` (animate), `api/rest/imagen.py`.

### P7.12 — Media: sound + trait image workflow
- **What:** ComfyUI sound generation (ambient + SFX) and trait image workflow/rendering.
- **Done:** ambient/SFX audio and trait images can be generated.
- **Depends:** —
- **Load:** to-do "sound generation with ComfyUI... trait image workflow".

### P7.13 — Backend + frontend: Blue Book transversal logging
- **What:** log location changes (transversal) into the Blue Book.
- **Done:** transversal events appear in the Blue Book.
- **Depends:** —
- **Load:** to-do "Add transversal (location changing) logging, add to Blue Book", `services/change_log.py` / historical records.

### P7.14 — Frontend: Blue Book delete with undo
- **What:** entry deletion with a 3-second undo timer; show the timer for one item, queue size for many.
- **Done:** deletions are undoable within the window.
- **Depends:** —
- **Load:** to-do "Enable entry deletion from Blue Book", Blue Book component.

### P7.15 — Frontend: theming
- **What:** light/dark mode + universe-based styling.
- **Done:** theme switch + per-universe styling hooks.
- **Depends:** —
- **Load:** to-do "Theming & Styling", `App.vue` / theme CSS.

### P7.16 — Bug: navdot full-image
- **What:** location-viewer navdot sometimes shows the whole target background instead of a cropped panning part.
- **Done:** navdots always show the cropped pan.
- **Depends:** —
- **Load:** to-do "navdot ... shows the entire target background image", `components/LocationViewer.vue`.

### P7.17 — Bug: faction list refresh performance
- **What:** faction list in GM prep refreshes on faction click and causes a performance issue.
- **Done:** the list does not re-fetch/re-render unnecessarily on click.
- **Depends:** —
- **Load:** to-do "Why does the faction list in GM prep panel seems to refresh on faction click?", GM prep panel.

### P7.18 — Bug: location tree child-panel tracking
- **What:** the location tree tracks which child panel is open; when it closes, the highlight should update (currently it can believe a panel is open when none is).
- **Done:** tree highlight stays in sync with open child panels.
- **Depends:** —
- **Load:** to-do "The location tree should track which child panel is open", `components/gm/GmLocationTree.vue`, `composables/usePanel.js`.

## Deferred & out-of-scope

- **"Increase/decrease result/effect limit"** — deferred with `modify_roll` / `modify_outcome` (release-plan locked decision).
- **Foundry integration** — out of this release.
- **"Other third-party tools?"** — out of this release.

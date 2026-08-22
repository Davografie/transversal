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
>
> **Status values:** `done` · `pending` · `deferred` (the bottom section) · `abandoned` (superseded or wrong premise). Phase 1 (P1.1–P1.6) is `done`; everything later is `pending` until worked.
>
> **Current dice/contest conventions (post Phase 2):** a rolled die is a `DieSpec` (`die`, `source_kind`, `source_id`, `label`, `ts_id`) + `result`; `DicePoolRequest.dice` is `list[DieSpec]` (a validator still accepts legacy `(die, source)` tuples) and `DicePoolRequest.pipeline` can force `pool`/`simplified`. `ContestResult` carries `kind` + `stakes`; `ContestWinner` has no tie value (ties favor the initiator). Pools + difficulty persist in `SceneStateStore` keyed `(location_id, entity_id)`; `ContestTracker` holds only contest metadata (opposition/push/razmerit) and resolves by reading those pools. `pool_updated` / `difficulty_set` broadcast server-side on mutation.

## Phase 1 — Keystone: effect targeting & application

### P1.1 — Backend: complete `{choose_*}` target resolution
- **Status:** done
- **What:** finish resolving `{choose_*}` targets and returning clean `pending_choices` (partly modeled).
- **Done:** an effect with `target="{choose_location}"` yields a pending choice the caller can resolve and re-apply.
- **Depends:** — (foundation)
- **Load:** `services/effects_applier.py` (`_resolve_target`, `PendingChoice`), `services/effects_commit.py`, `domain/__init__.py` (Effect), [[Unified Effects Plan]].

### P1.2 — Backend: `random` target mode
- **Status:** done
- **What:** add a `random` target resolution (pick a random in-scope entity/trait).
- **Done:** a `{random:…}` target resolves to a random candidate (basis for starter-location scatter).
- **Depends:** P1.1
- **Load:** `effects_applier.py`, `domain/__init__.py`, [[Pressure-Test Log]] § Scenarios 3 & 6.

### P1.3 — Frontend: scoped target picker dialogs
- **Status:** done
- **What:** location / occupant / trait / rating-die pickers filtered by `target_kind` + `target_scope`.
- **Done:** a picker shows the right candidates for a scope and returns a resolved id.
- **Depends:** P1.1
- **Load:** `services/effect_targets.py` (`resolve_candidates`, `register_scope`), `components/gm/ScopedTargetPicker.vue`, `composables/useEffectTargets.js`, `components/gm/EffectEditor.vue`.

### P1.4 — Frontend: effect-application wizard
- **Status:** done
- **What:** chain P1.3 pickers into one step-by-step application flow.
- **Done:** a multi-target effect can be authored/run through the wizard.
- **Depends:** P1.3
- **Load:** `components/gm/EffectTargetWizard.vue`, `composables/useEffectApplication.js`, `api/graphql/schema.py` (`applyEffects` / `resolveEffectTargets`).

### P1.5 — Frontend: two-sided consequence menu
- **Status:** done
- **What:** after a test/contest, offer player options (proceed / decrease doom / create scene trait) or GM options (increase doom / apply complication / give asset), wired to effects.
- **Done:** a resolved roll offers the correct menu and applying an option writes state via the effect system.
- **Depends:** P1.3, P1.4
- **Load:** `services/consequence_menu.py` (`assemble_consequence_menu`), `components/gm/ConsequenceMenu.vue`, `composables/useConsequences.js`, `components/DiceRoller.vue` (PICKING/RESOLVED).

### P1.6 — Frontend: effect-die application
- **Status:** done
- **What:** substitute the roll's effect die into a consequence option's effects before applying (the ``{effect_die}`` placeholder in ``result``).
- **Done:** "Create a scene trait" / "Apply a complication" / "Give an asset" land at the roll's actual effect-die rating, not a fixed die.
- **Depends:** P1.5
- **Load:** `services/consequence_menu.py` (base moves), `composables/useConsequences.js`, `components/gm/ConsequenceMenu.vue`, `components/DiceRoller.vue` (`effectDie`).

### P1.7 — Backend: duration-scoped trait effects
- **Status:** pending
- **What:** implement the duration-carrying effects from the to-do Effects list: temporary location asset, disable a trait, and step-down (own / target-entity) with a ``duration`` context that schedules the revert.
- **Done:** these effects are appliable via the effect system and revert (or expire) at their duration boundary through the shared scheduler.
- **Depends:** P1.1, P6.3 (expiry scheduler)
- **Load:** to-do "Effects", `services/effects_applier.py` (`_MUTATION_HANDLERS`), `services/effects_engine.py` (`schedule_effect`), `services/effects_commit.py`, `services/effect_targets.py`.

### P1.8 — Backend: effect-die comparison + trait-set limit effects
- **Status:** pending
- **What:** implement "set or step up target-trait rating" (set if effect die > target die, step up if ≤) and "increase/set trait set limit".
- **Done:** both are Effect actions; the comparison one takes the effect die and the target die and applies the correct operation.
- **Depends:** P1.1, P1.6
- **Load:** to-do "Effects" (set/step-up target-trait, increase/set trait set limit), `services/effects_applier.py`, `services/dice_resolver.py` (`_resolve_challenge` pattern), `services/consequence_menu.py` (base moves + `{effect_die}`), `composables/useConsequences.js` (substitution).

## Phase 2 — Play spine: tests & contests resolve

### P2.1 — Backend: test vs contest as first-class
- **Status:** done
- **What:** a roll knows its kind (test / contest / roll-table), flowing through the resolver and results.
- **Done:** `RollKind` (test/contest/roll_table) on `DicePoolRequest` + result models; `resolve()` echoes it, `resolve_contest()` forces `contest`, REST contest response carries `kind`.
- **Depends:** —
- **Load:** `domain/__init__.py` (RollKind), `services/dice_resolver.py`, `api/rest/roll.py`, `api/rest/contest_pools.py`, [[Pressure-Test Log]] § Scenario 4.

### P2.2 — Backend: return the opponent's effect die (contest stakes only)
- **Status:** done
- **What:** the resolver returns the opposition's effect die for *contests*; tests don't produce stakes.
- **Done:** `ContestResult.stakes` carries the opponent's effect die (set in `resolve_contest`); single-side tests carry no stakes field.
- **Depends:** P2.1
- **Load:** `domain/__init__.py` (`ContestResult.stakes`), `services/dice_resolver.py` (`resolve_contest`), [[Pressure-Test Log]] § Scenarios 3 & 4.

### P2.3 — Backend: contest resolve returns full rolls + effect dice
- **Status:** done
- **What:** `/locations/{id}/pools/{entity_id}/resolve` returns rolls and effect dice, not just `{winner, pipeline, pushed}`.
- **Done:** endpoint returns the full `ContestResult` (`response_model=ContestResult`) — both sides' rolls, totals, effect dice, and `stakes`.
- **Depends:** P2.1
- **Load:** `api/rest/contest_pools.py`, `services/contest_tracker.py`, `services/dice_resolver.py`.

### P2.4 — Backend: challenger/defendant modeling
- **Status:** done
- **What:** a stored role distinguishes who initiated vs who defends, so a tie resolves in favor of the *initiator* (Cortex Prime), not the resolve argument.
- **Done:** ties favor the challenger (initiator); `ContestTracker.get_contestants` resolves from either side; `ContestWinner.TIE_DEFENDER` removed; `_trigger_matches`/`contest_to_events` updated.
- **Depends:** P2.1
- **Load:** `services/contest_tracker.py` (`get_contestants`, `set_opposition`), `domain/__init__.py` (ContestWinner, PoolAssembly), `services/dice_resolver.py` (`resolve_contest`), `services/effects_engine.py` (`contest_to_events`), [[Pressure-Test Log]] § Scenario 4.

### P2.5 — Frontend: opposition UI (difficulty presets + verdict)
- **Status:** done
- **What:** GM test difficulty via preset buttons (very easy 2d4 → very hard 2d12) auto-added to the opposition pool, plus trait dice; the opposition rolls with the player's pool and the result shows the difficulty and a success/failure verdict.
- **Done:** opposition can be set up (presets + extra dice), sent as `gmc` opposition, and rendered as "vs difficulty N → Success/Failure".
- **Note:** superseded by P2.5b — the inline `gmc` opposition UI was replaced by a role-aware `DiceRoller` (GM difficulty on the GM's device, player rolls against it on theirs).
- **Depends:** P2.2
- **Load:** `components/DiceRoller.vue`, `composables/useApi.js` (`roll` opposition param).

### P2.5b — Backend + frontend: GM manual test-difficulty selection (two-step)
- **Status:** done
- **What:** the GM rolls the opposition pool, picks the two dice that set the difficulty, and the player rolls against it on their own client (SSE in between).
- **Done:** `DiceRoller` is role-aware (`gmMode`): GM mode rolls the opposition pool and picks two via the result slots, publishing the difficulty over SSE (`difficulty_set`); player mode receives it and rolls against `static_difficulty`. Simplified pipeline returns `opposition_total` for static difficulty.
- **Note:** difficulty is ephemeral (session-scoped) until P2.7. A pure 2-die difficulty now forces the pool pipeline via `DicePoolRequest.pipeline` (option A) so the GM always gets the keep-two result slots; the GM's roll purpose is chosen by how the pool starts (generic dice → difficulty, trait → GMC roll).
- **Depends:** P2.5
- **Load:** `services/dice_resolver.py` (`_resolve_simplified` static_difficulty), `domain/__init__.py` (SimplifiedResult.opposition_total), `components/DiceRoller.vue` (`gmMode`/`difficulty`), `App.vue` (`difficulty_set`), `composables/useSSE.js`.

### P2.6 — Backend: razmerit persistence
- **Status:** abandoned
- **What:** *(superseded)* — razmerit is earned when the GM *buys* a hitch (a GM-owned SFX), not automatically on a hitch.
- **Done:** —
- **Depends:** —
- **Note:** the persistence (`RazmeritService.earn`) and the `earn_razmerit` effect already exist; the actual work is the buy-hitch SFX in P3.3.

### P2.7 — Backend + frontend: dice pool persistence (server-side, in-memory)
- **Status:** done
- **What:** an assembled pool survives refresh and same-user device switch. Server-side in-memory store keyed by `(location_id, entity_id)`. Dice carry a minimal, extensible source (`source_kind` / `source_id` / `label`). Also stores the current difficulty.
- **Done:** `SceneStateStore` + REST (`scene_state.py`) hold pools + difficulty; the roller saves on change and restores on mount/reconnect; App.vue round-trips the difficulty.
- **Depends:** —
- **Note:** keying flipped from player to entity in P2.10 (per-entity tabs + entity-vs-entity contests require it; cross-device continuity still holds via the stable player→entity claim). `ContestTracker` now holds only contest metadata (opposition / push / razmerit) and reads dice from this store — the earlier `PoolAssembly` conflation was removed.
- **Load:** `services/scene_state.py`, `api/rest/scene_state.py`, `components/DiceRoller.vue` (`persistPool`/`restorePool`), `App.vue` (`refreshDifficulty`), `composables/useApi.js`.

### P2.7b — Backend: SFX ownership model
- **Status:** pending
- **What:** SFX stay pure definitions; ownership lives on the owner side. Add `sfx_ids` to `Entity` and `Projection`, add a new `TraitSetSetting` edge (entity↔traitset, `sfx_ids` only) in a `traitsetsettings` collection, and add `table`/`gm` singleton owners in a new `sfx_owners` collection. Add a resolver `get_available_sfx_ids(entity_id, universe)` that unions all owner surfaces — `table`, `entity`, active `projection`, trait-level (`TraitSetting.sfx_ids` + `Trait.default_sfx_ids`), and set-as-unit (`TraitSetSetting.sfx_ids`) — universe-gated.
- **Done:** given an entity + universe, `get_available_sfx_ids` returns the full set of SFX ids the entity can use, and P2.8 consumes it. `consequence_menu._entity_sfx_ids` is retired in favor of the resolver.
- **Depends:** —
- **Load:** `services/sfx_owner.py` (`get_available_sfx_ids`, `ensure_sfx_owners`/`ensure_give_in_sfx`), `domain/__init__.py` (new `TraitSetSetting`; new `Entity.sfx_ids`/`Projection.sfx_ids`; existing `TraitSetting.sfx_ids`, `Trait.default_sfx_ids`), `db/repository.py` (`get_all_sfxs`, `get_effective_traitsettings`, `get_projections_for_entity`; new `traitsetsettings` + `sfx_owners` collections/CRUD), `services/consequence_menu.py` (`_entity_sfx_ids` — replace), `services/effects_engine.py` (`process_event` signature), `db/seed.py` (seed `table`/`gm` owners), [[Release Plan]] § "Effects actually fire" (locked six-owner decision).
- **Note:** `TraitSetSetting` carries only `sfx_ids` here; its limit/sort-order/order fields are Phase 4, not this ticket. `ContestTracker.push_contest` becomes a `table`-owned SFX (follow-on). P3.3 (buy-hitch) consumes the `gm` owner.

### P2.8 — Backend: wire SFX triggers into the roll/contest flow
- **Status:** done
- **What:** `on_roll` / `on_complication` / `on_success` / `on_botch` (and contest win/loss) fire automatically.
- **Done:** a roll/contest fires matching SFX without a manual `/effects/trigger` call.
- **Depends:** P2.1, P2.7b
- **Load:** `services/effects_engine.py` (`fire_contest_sfx`, `process_event`, `contest_to_events`), `api/rest/effects.py`, `services/effect_targets.py` + `services/effects_applier.py` (`resolve_choice`, pending choices), `domain/__init__.py` (`DieRoll`, `ContestResult.stakes`, `ContestWinner` — no tie), [[Pressure-Test Log]] § Scenario 4.

### P2.8b — Backend + frontend: auto-fired `{choose_*}` SFX prompt
- **Status:** done
- **What:** an auto-fired SFX whose effect has a `{choose_*}` target doesn't apply blindly — it surfaces a pending choice. Backend captures the `PendingChoice` and emits an SSE event (e.g. `sfx_choice_required`) for the acting entity; the effect is re-applied once the choice is resolved. Frontend listens for that SSE event and opens the existing choice dialog inline in the relevant component (DiceRoller / consequence surface), interrupting the user's flow.
- **Done:** a `{choose_*}`-targeted auto-fired SFX produces an SSE prompt on the acting player's device; choosing a target resolves the pending choice and applies the effect — no manual `/effects/trigger` and no blind apply.
- **Depends:** P2.8, P1.1, P1.3, P1.4
- **Load:** `services/effects_applier.py` (`apply_effects`, `_resolve_target`, `PendingChoice`, `resolve_choice`), `services/roll_orchestrator.py` (`fire_roll_sfx`, `fire_contest_sfx_auto`), `api/sse/bus.py` + `stream.py` (add `sfx_choice_required`), `App.vue` / `components/DiceRoller.vue` + `composables/useSSE.js` (receive + prompt), `components/gm/EffectTargetWizard.vue` (reuse picker).
- **Note:** the prompt must be asynchronous (SSE), not block the roll response — the player is on a separate device. The test-side prompt works today (test flow is live from P2.5b); the contest-side prompt is only exercisable end-to-end after P2.10 (play flow) — a sequencing note, not a hard build blocker, since the SSE handler + dialog are the same for both kinds.

### P2.9 — Backend: condition-based SFX triggers
- **Status:** done
- **What:** state-change triggers from the to-do Triggers list fire SFX: visiting a specified-location, creating a specified-relation, gaining a specified-trait, gaining from a specified-traitset, reaching a specified-rating.
- **Done:** each condition is authored and evaluated via the existing `Condition` machinery, firing matching SFX on the state change.
- **Depends:** P2.8
- **Load:** to-do "Triggers", `services/conditions.py`, `domain/__init__.py` (`Condition`, `ConditionType`), `services/effects_engine.py` (`_trigger_matches`).
- **Note:** trigger = event (`on_location_change` / `on_trait_change` / `on_relationship_create`); condition = filter (`AT_LOCATION` / `HAS_TRAIT` / `HAS_TRAIT_IN_TRAITSET` / `HAS_RELATIONSHIP` / `TRAIT_RATING` / `NARRATIVE`). `SFX.limit` folded into a NARRATIVE condition. Deferred: GraphQL `SfxInput`/`SfxRef` don't expose `conditions` yet (authoring still edits `limit`); direct `add_traitsetting` and `lifepath_executor` trait gains don't route through `fire_state_sfx`.

### P2.10 — Frontend: test & contest play flow (opponent + resolve wiring)
- **Status:** done
- **What:** the client runs both roll kinds end-to-end. Tests: GM sets difficulty on their device → player rolls against it on theirs → verdict (a pure 2-die difficulty now forces the pool pipeline so the GM always gets keep-two). Contests: a challenger designates an opponent, both sides assemble a pool, the client calls `/resolve`, and the verdict (winner, both totals, effect dice, `stakes`) renders.
- **Done:** a player can run a test against a GM-set difficulty and a two-sided contest against a designated opponent entirely through the client (no manual REST/GraphQL). DiceRoller gains per-entity pool tabs (read-only others), a contest opponent dropdown + resolve + verdict, and entity-keyed persistence; `pool_updated` / `difficulty_set` broadcast server-side.
- **Depends:** P2.4, P2.5b
- **Note:** follow-ons — the defendant sees the contest verdict only via the `roll_result` SSE summary (full cross-device verdict render is polish); GM-as-contestant (rolling a specific GMC) is not yet wired; give-in is P2.14; test `roll_result` is still client-published (a server-side roll broadcast can land separately).
- **Load:** `composables/useApi.js` (`setOpposition`/`resolveContest`/`listPools`), `api/rest/contest_pools.py` + `scene_state.py`, `services/contest_tracker.py` + `scene_state.py`, `services/dice_resolver.py` (`pipeline` hint), `components/DiceRoller.vue`, `App.vue`.

### P2.10b — Backend + frontend: manual concurrent contest flow (challenge / set / give-in)
- **Status:** pending
- **What:** replace the auto "Resolve contest" button with a manual, concurrent contest. Each side assembles independently (concurrency allowed); the initiator designates the opponent (challenge); either side commits its final total/effect with "Set"; once both sides have set, the backend compares and declares a winner; either side may give in before resolution (folds P2.14). The opponent's tab live-shows the initiator's pool/SFX unfolding via SSE. Contestants are entities, so PC-vs-PC, PC-vs-GMC, and GMC-vs-GMC are the same flow — the GM acts as a specific entity through the tab they're editing.
- **Done:** a two-sided contest runs challenge → concurrent assembly → set/set or give-in → resolved entirely through the client, with SFX cross-effects (e.g. an initiator SFX stepping an opponent's trait) still applying regardless of assembly order.
- **Depends:** P2.10, P2.4, P2.7b
- **Note:** folds P2.14. Give-in is available to either side once challenged and before resolution (the conceding side defines its own loss; an initiator give-in also blocks immediate re-initiation against the same opponent and earns the usual reward). Pool dice are **live references** to their source trait during assembly — a trait step up/down (e.g. an initiator SFX stepping the opponent's trait) re-syncs the matching die already in the open pool; once a side rolls/sets, the committed roll is frozen. `trait_updated` SSE must carry the trait-setting id + new rating so the client can re-sync.
- **Load:** `services/contest_tracker.py` (contest phase/state + SSE), `api/rest/contest_pools.py` (`challenge`/`set`/`give-in`/`resolve`), `services/state_events.py` (`fire_state_sfx` — give-in fires `on_give_in`), `services/sfx_owner.py` (`table`-owned `sfx-give-in-get-razmerit`), `api/sse/*`, `components/DiceRoller.vue` (phase machine, tabs as the acting entity, set/give-in buttons), `App.vue`, `composables/useApi.js`, [[Pressure-Test Log]] § Scenario 4.

### P2.10c — Backend + frontend: multi-die static traits
- **Status:** done
- **What:** a static trait with a multi-die rating (e.g. `TraitSetting.dice = [d10, d10]`, like "Law of the Dao") contributes **all** of its dice to the pool, not just the first. Add/remove toggles all dice of that trait-setting id as a group, and the trait→pool re-sync updates every matching die together.
- **Done:** adding a `[d10, d10]` static trait puts two `d10` pool dice in the pool (one `DieSpec` each, same `ts_id`); toggling removes both; a step up/down re-syncs the matching dice as a group.
- **Depends:** P2.10b (pool/trait model), P2.7 (SceneStateStore + `resync_trait_die`)
- **Note:** a pool die is a single `DieSpec` (per-die), so this is **not** a "string → array" change to the pool die. The work is: (1) `CharacterSheet.onTraitClick` emits the trait's full `dice` array; (2) `DiceRoller.addFromSheet`/`removeByTsId` toggle all dice sharing a `ts_id`; (3) `resync_trait_die`/`resyncTraitDie` re-sync all matching dice (and `trait_updated` should carry `new_dice`, not just `new_rating`). Resources remain P2.16.
- **Load:** `components/CharacterSheet.vue` (`onTraitClick`, `resolvedDieType`), `components/DiceRoller.vue` (`addFromSheet`, `removeByTsId`, `resyncTraitDie`), `App.vue` (`trait_updated` routing), `services/scene_state.py` (`resync_trait_die` + `resync_pool_dice_for_trait`), `services/effects_commit.py` / `entity_manager.py` (`trait_updated` payload).

### P2.10d — Backend + frontend: contest push loop (roll & compare)
- **Status:** done
- **What:** after both sides set, do not auto-finalize. Compare provisionally against the initiative holder (strictly-beat; tie → holder); the losing side may **give in** (+1 razmerit, plus a scene-scoped directional targeting ban) or **push** (free, once per side, rebuild/roll/set again). Loops until someone gives in or fails to beat.
- **Done:** initiative-based `ContestCompare`, `push` endpoint + `on_push` trigger, give-in gating, a waiting state for the holder, give-in → razmerit + `entity_targeting_ban` (1 scene), and a scene-advance trigger (GM `[Scene]` button + non-adjacent navigation) with SSE toasts.
- **Depends:** P2.10b
- **Note:** push is free (house ruling from Cortex "continue"); `pushed_this_beat` → `pushed_this_loop`. `razmerit_spent`/`push_cost` are stale leftovers of the old paid-push model. `push_contest` is dead code (retired `resolve()` path) — superseded by `ContestTracker.push`.
- **Load:** `services/contest_tracker.py` (`set_result`, `_compare`, `give_in`, `push`), `api/rest/contest_pools.py` (`set`/`give-in`/`push`), `api/rest/targeting_bans.py`, `services/targeting_bans.py`, `services/effects_applier.py` (`entity.targeting_ban`), `services/sfx_owner.py`, `db/seed.py`, `components/DiceRoller.vue`, `components/GmPanel.vue`, `App.vue`.

#### P2.10d working plan (updated 2026-08-19)
- **Landed:** initiative compare, push/give-in loop, waiting state, give-in razmerit + targeting ban, scene-advance trigger + toasts.
- **Landed — G4 effect resolution:** after the final winner, compare winner vs loser effect dice. Low stakes (default) → if winner's effect ≤ loser's, step it down one, then apply as a complication. High stakes → loser is taken out (spend-to-avoid is still a consequence-menu/SFX concern). GM `high_stakes` toggle lives on the roll-kind badge (fiery, GM-only).
- **Landed — P6 (folded into G4):** result widget shows the final (possibly stepped-down) effect via `DieIcon` (original die dimmed + `↓` + applied die), plus `taken out` on the loser for high-stakes takeout.
- **Landed — consequence menu:** complications are manual menu choices, not an auto-fired SFX (`sfx-contest-loss-complication` removed from seed/owners). Two `on_consequence` SFX owned by `table` (`apply-complication` / `take-complication`, identical `gain_complication` effect): the winner sees “Apply a complication” (applies to the opponent), the conceder sees “Take a complication” (applies to self), both at the winner's effect die. The frontend filters them by which end of the contest you're on.
- **Landed — G5 resolver decomposition:** `dice_resolver` split into callables (`roll_dice`, `detect_hitches`, `pick_total`, `pick_effect_die`, `compare_totals`). The roll flow is stateful: `/cortex-roll` / `/simplified-roll` / `/difficulty-roll` return rolled dice + hitches, `/select` flags result/effect dice client-side, `/hitches/mark-bought` buys hitches client-side. `ContestTracker.resolve` (auto-resolve) is dead; `resolve_contest` remains only for `trait_transfer`, and `/roll` is a legacy compat shim — neither is part of the contest push loop.
- **Deferred/optional:** heroic success; high-stakes spend-to-avoid takeout.
- **Related open tickets:** P2.15 (role-aware toasts), P2.16 (resource dice), P3.3 (buy-hitch).

### P2.11 — Frontend: dice-pool styling per roll kind
- **Status:** done
- **What:** the pool is visually distinguished by simple-test / cortex-test / challenger-contest / defendant-contest / roll-table.
- **Done:** a user can tell at a glance what they're rolling for from the pool styling.
- **Depends:** P2.1
- **Load:** to-do "Style dicepool", `components/DiceRoller.vue`, `domain/__init__.py` (`RollKind`: test/contest/roll_table — the five visual kinds are UI-level), [[Pressure-Test Log]] § Scenario 4.

### P2.12 — Frontend: rolling dice animation
- **Status:** done
- **What:** a short animation on roll (blinking random faces), plus folding in the ``[dX]`` → ``DieIcon`` trait-rating replacement.
- **Done:** dice blink random faces (~900ms) during ROLLING before settling on results; trait ratings in the character sheet render as `DieIcon` instead of ``[dX]`` text (resources/empty keep text).
- **Depends:** —
- **Note:** folds the ``[dX]`` → ``DieIcon`` item out of P7.1. Resource dice stay text (P2.16).
- **Load:** to-do "Rolling dice animation" + "Replace [dX] with DieIcon.vue", `components/DieIcon.vue`, `components/DiceRoller.vue`, `components/CharacterSheet.vue`.

### P2.13 — Backend + frontend: exclude hitches from effect-die selection
- **Status:** done
- **What:** auto-selection (resolver + dice-pool UI) never picks a die that rolled a 1 as the effect die.
- **Done:** the effect die can be chosen from leftover non-hitch dice (d4 fallback when none).
- **Depends:** —
- **Load:** `services/dice_resolver.py` (`_resolve_pool` effect-die block), `components/DiceRoller.vue` (result/effect click, `isHitch`), `components/DieIcon.vue`, `domain/__init__.py` (`DieSpec`/`DieRoll` — selection is by die type, not source).

### P2.14 — Backend + frontend: contest give-in
- **Status:** done
- **What:** *(folded into P2.10b)* — give-in is part of the manual concurrent contest flow.
- **Done:** either side can give in before resolution; the backend records `gave_in`, the other side wins, and the conceding side earns the give-in reward.
- **Depends:** —
- **Note:** see P2.10b for give-in semantics and the manual contest state machine.

### P2.15 — Frontend: role-aware toast system
- **Status:** in progress
- **What:** make the toast system available to all roles and filter which messages surface to whom. Each `addToast` declares an audience/scope (GM-only / player-only / all).
- **Done:** a player sees player-relevant toasts (e.g. "Difficulty set: N") and the GM sees GM-relevant toasts, without a second notification system.
- **Depends:** —
- **Note:** `ToastBar` no longer gates on `v-if="gmMode"` (renders for all roles), but `addToast(message, type)` has no audience/scope field yet — filtering is still ad-hoc `if (gmMode.value)` / `if (!gmMode.value)` at each call site in `App.vue`. Remaining: add an audience/scope to `addToast` and centralize the filtering.
- **Load:** `components/ToastBar.vue`, `App.vue` (`addToast`/`toasts`), `components/DiceRoller.vue` (difficulty flash).

### P2.16 — Backend + frontend: resource dice (spend / roll / recover)
- **Status:** pending
- **What:** resource traits are pools of dice that are committed to a test/contest and rolled *separately* from the main pool. Per the manual: players choose how many resource dice to roll; after they're rolled those dice are spent; if more than one is spent, only the highest applies and its result is added to the total; resources recover at session start, during downtime, or via one-for-one spend.
- **Done:** a resource trait's dice can be committed, rolled (highest applies, added to the total), spent, and recovered per the above rules.
- **Depends:** P2.10b (pool/trait model), P2.13 (effect-die/hitch interplay)
- **Note:** multi-die ratings are the *resource* case — a pool die is a single `DieSpec` (per-die), so there is no "string → array" change to pool dice; the work is the resource commit/roll-separately/recover mechanics and the trait-setting re-sync for multi-die arrays.
- **Load:** `domain/__init__.py` (`TraitSetting.dice`, `RatingType.RESOURCE`), `services/dice_resolver.py`, `services/entity_manager.py` (spend/recover), `api/rest/resource_pool.py`, `components/CharacterSheet.vue` (resource display/spend), `components/DiceRoller.vue`.

## Phase 3 — Stakes & consequences

### P3.1 — Frontend: looming doom dice render
- **Status:** pending
- **What:** a location-scoped challenge (doom) pool renders prominently at top of screen.
- **Done:** the GM sees the doom pool as a labeled dice cluster.
- **Depends:** —
- **Load:** [[Pressure-Test Log]] § Scenario 1 (doom pool) & 5, old `Rating.vue` (challenge rendering).

### P3.2 — Frontend: doom-pool click model
- **Status:** pending
- **What:** left-click steps a doom die down, right-click steps up; GM can hand a challenge to a player.
- **Done:** the doom pool is manip: up/down/hand-off via clear affordances.
- **Depends:** P3.1
- **Load:** old `vue/src/components/Trait.vue` (`deplete_challenge`/`increase_challenge`), [[Pressure-Test Log]] § Scenario 5 UX note.

### P3.3 — Backend + frontend: buy-hitch (GM SFX)
- **Status:** pending
- **What:** a GM-owned SFX that, triggered on a player-rolled hitch, earns the player razmerit and introduces a complication / steps up the doom pool.
- **Done:** buying a hitch applies `earn_razmerit` (to the player) + a complication effect via the SFX owner model.
- **Depends:** P3.1 (render), P2.8 (hitch trigger), P2.7b (SFX owner model)
- **Load:** [[Pressure-Test Log]] § Scenario 5, `services/razmerit.py` (earn), `services/effects_registry.py` (`earn_razmerit`), `services/effects_applier.py` (complication effects).
- **Note:** rename `dice_resolver.razmerit_earned` → `hitches_count` (or drop it) — it currently encodes the wrong "auto-earn" assumption; hitches are buyable, not earned.

### P3.4 — Backend + frontend: challenge resolution via effect system
- **Status:** pending
- **What:** the consequence menu's "challenge rating" option applies effect-die-vs-challenge-die through the effect system, not resolver persistence.
- **Done:** picking the challenge option steps the doom pool down/up via an effect.
- **Depends:** P1.5, P3.1
- **Load:** `services/dice_resolver.py` (`_resolve_challenge`), `services/effects_commit.py`, `services/consequence_menu.py` (base moves), `components/gm/ConsequenceMenu.vue` + `composables/useConsequences.js`, to-do "challenge rating" effect.

### P3.5 — Backend + frontend: tether = sub-trait of Origin
- **Status:** pending
- **What:** author the tether as a challenge/negative sub-trait of the Origin distinction (and seed it).
- **Done:** a character has a tether sub-trait under Origin that counts down.
- **Depends:** P4.2 (sub-traits)
- **Load:** [[Pressure-Test Log]] § Macro decisions (tether), `domain/__init__.py` (SubTraitRef, sub_trait_settings).

### P3.6 — Backend: "challenge emptied" trigger + "switch projection type" effect + full-native
- **Status:** pending
- **What:** a challenge trait reaching zero fires its SFX; the effect switches `transversal_type`; full-native is authored from these.
- **Done:** emptying the tether triggers full-native via the event system.
- **Depends:** P3.5, P2.8
- **Load:** [[Projections and Transversal]], `services/effects_applier.py` (registry `_attune`/travel + pure applier), `services/effect_targets.py`, `services/effects_engine.py` (`_trigger_matches`), `domain/__init__.py` (TransversalType).

### P3.7 — Backend + frontend: contest effect-die consequences (complication + taken-out) *(later)*
- **Status:** pending
- **What:** compare winner vs loser effect die to resolve a contest's consequence. Standard: loser takes a complication at the winner's effect die (stepped down one if the loser's effect die is equal or larger). High-stakes (GM flag): winner's effect die larger → loser taken out (or spend to avoid).
- **Done:** every contest resolves a consequence from the effect-die comparison; high-stakes contests can take a side out.
- **Depends:** P2.3
- **Load:** [[Pressure-Test Log]] § Scenario 4, `services/dice_resolver.py` (`resolve_contest`).

### P3.8 — Backend + frontend: complication stepped beyond d12 = taken out *(later)*
- **Status:** done
- **What:** stepping a complication above d12 automatically takes the character out of the scene.
- **Done:** a d12 complication stepped up marks the character taken out.
- **Depends:** P3.7
- **Load:** `services/effects_applier.py` (step-up complication effect), `domain/__init__.py` (DieType step_up).

### P3.9 — Backend + frontend: contest interference *(later)*
- **Status:** pending
- **What:** a third party spends to join a two-way contest; compare against the current total; win stops it, loss hands them a complication.
- **Done:** a third side can interfere and the contest tracks the interference outcome.
- **Depends:** P2.4
- **Load:** [[Pressure-Test Log]] § Scenario 4, `services/contest_tracker.py` (`get_contestants`, `resolve`).

### P3.10 — Backend + frontend: multiway contests *(later)*
- **Status:** pending
- **What:** 3+ parties vie for one goal; highest total wins; those who stay in and lose take a complication.
- **Done:** a contest accepts N participants and resolves winner-takes-all.
- **Depends:** P2.4
- **Load:** [[Pressure-Test Log]] § Scenario 4, `services/contest_tracker.py` (`get_contestants`, `resolve`).

## Phase 4 — Character sheet: traits as first-class

### P4.1 — Backend + frontend: relationship traits inline
- **Status:** pending
- **What:** relationship traits render the `_to` portrait and are served like the character's own traits (folded into the character query).
- **Done:** a relationship trait shows up in the character sheet with the related entity's portrait.
- **Depends:** —
- **Load:** `db/repository.py` (`assemble_character`, relationship trait queries), [[Pressure-Test Log]] § Macro decisions.

### P4.2 — Backend + frontend: sub-traits
- **Status:** pending
- **What:** full sub-trait support in the sheet (nesting, matching, edit).
- **Done:** a trait can carry sub-traits that behave per their rating type.
- **Depends:** —
- **Load:** `domain/__init__.py` (SubTraitRef), to-do "Sub-traits", old `SubTrait.vue`.

### P4.3 — Frontend: empty/descriptive traits = profile surface
- **Status:** pending
- **What:** pronouns, nickname, appearance (empty traits) get a simple text "profile" surface, not the dice editor.
- **Done:** an empty trait is editable as plain text, respecting ego/morph.
- **Depends:** —
- **Load:** to-do "Profile traits (empty, but with ego/morph)", `domain/__init__.py` (RatingType.EMPTY).

### P4.4 — Backend + frontend: `duplicates_allowed`
- **Status:** pending
- **What:** a per-trait-set/trait flag allows two of the same trait (two weapons) while defaulting to no-dupes.
- **Done:** a set flagged `duplicates_allowed` lets the picker add the same trait twice.
- **Depends:** —
- **Load:** `domain/__init__.py` (TraitSet, Trait), `components/CharacterSheet.vue` (picker filtering), [[Pressure-Test Log]] § Macro decisions.

### P4.5 — Frontend: trait click behavior
- **Status:** pending
- **What:** static = add to pool, resource = spend, challenge = oppose; GM = step up/down.
- **Done:** clicking a trait does the right verb for its rating type, without view-mode gymnastics.
- **Depends:** P2.5 (pool), P4.2 (sub-traits)
- **Load:** old `vue/src/components/Trait.vue` (the "tangled mess"), [[Pressure-Test Log]] § Scenario 5 UX note.

## Phase 5 — Prep & content

### P5.1 — Backend: MCP wrappers
- **Status:** pending
- **What:** thin MCP tools over existing GraphQL mutations (traits, traitsets, SFX, life paths, roll tables, relationships, projections).
- **Done:** the MCP server can create/edit these via standardized tools (no AQL).
- **Depends:** —
- **Load:** `mcp/server.py`, `api/graphql/schema.py`, [[Pressure-Test Log]] § Backend inventory (MCP drift).

### P5.2 — Backend + frontend: starter-location designation
- **Status:** pending
- **What:** mark multiple locations per universe as "starter".
- **Done:** a universe has a set of starter locations queryable by the spawn flow.
- **Depends:** —
- **Load:** to-do "Designate universe-scoped starter locations", `domain/__init__.py` (Entity, location).

### P5.3 — Backend + frontend: `location → universe` transversal edges
- **Status:** pending
- **What:** a transversal edge may target a universe (not just a location); traversing it triggers spawn.
- **Done:** a location can connect to a whole universe as a destination.
- **Depends:** —
- **Load:** `api/rest/locations.py` (`create_edge`), [[Pressure-Test Log]] § Scenario 6.

### P5.4 — Backend + frontend: random starter-location pipeline
- **Status:** pending
- **What:** traversing to a universe rolls a random starter location (roll table), using P1.2's `random` mode.
- **Done:** arriving in a new universe spawns at a random starter location.
- **Depends:** P1.2, P5.2, P5.3
- **Load:** [[Pressure-Test Log]] § Scenario 6, `services/roll_table.py`, `services/effect_targets.py` (`resolve_candidates`, random scope).

### P5.5 — Frontend: shared roll-table authoring UX
- **Status:** pending
- **What:** make linking a shared (unaffiliated) table into a life path obvious (single-exit only).
- **Done:** an author can link a shared table and set `return_to` without editing raw JSON.
- **Depends:** —
- **Load:** [[Life Path Flow and Shared Roll Tables]], `components/gm/EffectEditor.vue` (context textarea).

### P5.6 — Backend + frontend: live-player tracking + GM scene overview
- **Status:** pending
- **What:** track which entity each player is actively playing; render the GM overview in three groups (currently-played incl. support, each player's mains, current-location GMCs).
- **Done:** the GM scene view shows live mains + local GMCs and can be reordered.
- **Depends:** —
- **Load:** `services/player_manager.py` (agency), [[Pressure-Test Log]] § Scenario 6 & 7.

### P5.7 — Frontend: create-entity panel fixes
- **Status:** pending
- **What:** fix parent-context (tree selection), unconditional razmerit, and missing UNIVERSE type.
- **Done:** creating a child/zone uses the selected parent; razmerit hidden for non-razmerit types; universe creatable.
- **Depends:** —
- **Load:** `components/gm/GmEntityCreatePanel.vue`, `GmEntityForm.vue`, [[Pressure-Test Log]] § Scenario 1 bugs.

### P5.8 — Frontend: create roll tables from the life-path canvas
- **Status:** pending
- **What:** a new roll table can be created directly from the life-path canvas layout (not just linked).
- **Done:** an author creates and wires a fresh roll table without leaving the canvas.
- **Depends:** P5.5
- **Load:** to-do "Enable new roll table creation for life paths from the life path canvas layout", `components/gm/GmRollTableEditPanel.vue`, `composables/useLifePaths.js`.

### P5.9 — Content: GMC creation MCP SKILL.md
- **Status:** pending
- **What:** a documented MCP skill for creating GMCs (and their traits/relationships) via the standardized mutation wrappers.
- **Done:** the skill exists and produces a playable GMC through MCP, no AQL.
- **Depends:** P5.1
- **Load:** to-do "Create GMC creation MCP SKILL.md", `skills/`, `mcp/server.py`.

### P5.10 — Migration: another migrate from the old app
- **Status:** pending
- **What:** a new migration script pulling the current old-app data into Transversal2's v2 model.
- **Done:** a run produces entities/traits/SFX/life paths in the new collections.
- **Depends:** —
- **Load:** to-do "Do another migrate from the old app", `src/api/src/transversal/migrate_traits.py`, `arangodump/`.

## Phase 6 — Movement & projections

### P6.1 — Backend + frontend: projections as first-class (nav dots)
- **Status:** pending
- **What:** nav dots render projections (not entities); GM sees all, players see live ones; ownership `projection → entity → agency → player`.
- **Done:** nav dots reflect projections, filtered to live players.
- **Depends:** P5.6 (live tracking)
- **Load:** `api/rest/locations.py` (`navigate`, `_resolve_navdot`), [[Pressure-Test Log]] § Scenario 6.

### P6.2 — Backend + frontend: inapposite travel endpoint
- **Status:** done
- **What:** a dedicated REST endpoint for inapposite travel, wired into the movement flow.
- **Done:** an inapposite portal performs in-place universe/location mutation with `INAPPOSITE` type.
- **Depends:** —
- **Note:** satisfied by the travel consolidation — `inapposite_travel`/`consciousness_travel` were merged into `EntityManager.travel()`, which the GraphQL `inapposite_travel` mutation, the REST `consciousness-travel` endpoint, and `fire_portal`'s no-effects fallback all route through.
- **Load:** `services/entity_manager.py` (`travel`), `api/rest/locations.py`, [[Pressure-Test Log]] § Scenario 6.

### P6.3 — Backend: attunement expiry
- **Status:** pending
- **What:** manual `attune disable` as a patch; wire the auto-scheduler (still desired) for timing-boundary expiry.
- **Done:** an attunement can be removed manually and (later) auto-expires.
- **Depends:** —
- **Load:** `services/effects_applier.py` (`_attune`), `services/effects_engine.py` (`tick_scene`), [[Pressure-Test Log]] § Backend inventory.

### P6.4 — Backend + frontend: starter-location spawn on arrival
- **Status:** pending
- **What:** hook P5.4 into the travel flow so arriving in a new universe spawns at the rolled starter location.
- **Done:** consciousness/inapposite arrival in a fresh universe lands at a starter location.
- **Depends:** P5.4, P6.2
- **Load:** `services/entity_manager.py` (`consciousness_travel`, `inapposite_travel`), [[Pressure-Test Log]] § Scenario 6.

### P6.5 — Backend + frontend: projection & travel effects
- **Status:** pending
- **What:** implement exorcise (send a target's projection to another universe), banish (random inapposite travel), swap (swap two of a character's projections), and create temporary projection (disguise / alternative identity).
- **Done:** each is an Effect usable from the consequence menu / SFX, with ``{choose_*}`` targets for the involved entities and universes.
- **Depends:** P1.1, P6.1, P6.2
- **Load:** to-do "Effects" (exorcise / banish / swap / create temporary projection), `services/effects_applier.py` (pure applier + registry), `services/effect_targets.py`, `services/entity_manager.py` (travel), `domain/__init__.py` (Projection).

## Phase 7 — Polish & backlog

> Everything here is a real ticket with the same shape as Phase 1–6. They are post-release polish / backlog, not release blockers.

### P7.1 — Frontend: trait rendering & polarity polish
- **Status:** done
- **What:** empty traits not greyed out, morph traits highlighted (not ego), negative-polarity styling, hidden/visible trait hint. (The ``[dX]`` → ``DieIcon`` item was folded into P2.12.)
- **Done:** each rendering/affordance behaves as listed.
- **Depends:** P4.3
- **Load:** to-do "Character Sheet & Traits", `components/CharacterSheet.vue`, `components/DieIcon.vue`.

### P7.2 — Frontend: trait notes field
- **Status:** pending
- **What:** statement/notes split — single-line statement for ≤7 words, a textarea for notes, and a second input so both can co-exist.
- **Done:** a trait can carry a short statement and longer notes together.
- **Depends:** —
- **Load:** to-do "Trait notes field", `components/CharacterSheet.vue`, `domain/__init__.py` (`TraitSetting.statement`).

### P7.3 — Frontend: phased trait character sheet
- **Status:** done
- **What:** replace the character sheet accordion-style traitset / trait listing with separate screens for traitset list and traitset-scoped trait list.
- **Done:** picking a trait is a phased flow instead of nested accordions.
- **Depends:** —
- **Load:** to-do "Instead of an accordion style trait sets / traits, try a phased trait picker", `components/CharacterSheet.vue`.

### P7.4 — Frontend: unify drag-and-drop + longpress composable
- **Status:** pending
- **What:** one composable drives both pointer drag-and-drop and long-press-and-drop.
- **Done:** both interactions route through a single composable.
- **Depends:** —
- **Load:** to-do "Unify drag-and-drop and longpress-and-drop into a composable", `components/gm/`, `composables/`.

### P7.5 — Frontend: universal picker
- **Status:** pending
- **What:** unify location / occupant / trait / rating-die pickers into one picker over typed documents (extends ``ScopedTargetPicker``).
- **Done:** one picker handles all target document types.
- **Depends:** P1.3
- **Load:** to-do "Unify the pickers", `components/gm/ScopedTargetPicker.vue`, `components/gm/GmLocationPicker.vue`, `components/gm/GmTraitPicker.vue`.

### P7.6 — Frontend: GM panel management
- **Status:** pending
- **What:** detach panels, open panels directly from outside the hierarchy, and collapse/expand panels (hide, not close; including children).
- **Done:** each panel-management affordance works.
- **Depends:** —
- **Load:** to-do "GM Panels", `components/gm/PanelStack.vue`, `composables/usePanel.js`.

### P7.7 — Frontend: longpress-drag reorder on location tree
- **Status:** pending
- **What:** make tree reordering genuinely long-press initiated (currently not specifically long-press).
- **Done:** reorder on the location tree is long-press initiated.
- **Depends:** P7.4
- **Load:** to-do "apply longpress-and-drag to reorder on location tree", `components/gm/GmLocationTree.vue`.

### P7.8 — Frontend: shared image/video component
- **Status:** pending
- **What:** unify background-image and ``<video>`` rendering into one component.
- **Done:** one component renders either media type.
- **Depends:** —
- **Load:** to-do "Unify background-image/video images into a shared component", `components/gm/ImageViewer.vue`.

### P7.9 — Frontend: image viewer & portrait UX
- **Status:** pending
- **What:** image-viewer delete-button styling, open viewer on character-sheet portrait click, clarify which image (background / sheet / navdot) renders where, and make projections own their images.
- **Done:** portrait → viewer works and image-role overlap is resolved.
- **Depends:** P6.1
- **Load:** to-do "Images, Media & Generation", `components/gm/ImageViewer.vue`, `components/CharacterSheet.vue`.

### P7.10 — Media: portrait processing
- **Status:** pending
- **What:** remove portrait background (transparent) and switch circular app portraits to semi-circular bottom / uncropped top.
- **Done:** generated/uploaded portraits render with the new crop + transparency.
- **Depends:** —
- **Load:** to-do "Delete the background... semi-circular", imagen pipeline.

### P7.11 — Media: animation pipeline
- **Status:** pending
- **What:** WEBM → MP4 (with alpha for portraits) and feed "idle pose" + traits into the Gemma hint.
- **Done:** animations output MP4 and use the richer hint.
- **Depends:** —
- **Load:** to-do "Change animate output from WEBM to MP4", `composables/useEntityCrud.js` (animate), `api/rest/imagen.py`.

### P7.12 — Media: sound + trait image workflow
- **Status:** pending
- **What:** ComfyUI sound generation (ambient + SFX) and trait image workflow/rendering.
- **Done:** ambient/SFX audio and trait images can be generated.
- **Depends:** —
- **Load:** to-do "sound generation with ComfyUI... trait image workflow".

### P7.13 — Backend + frontend: Blue Book transversal logging
- **Status:** pending
- **What:** log location changes (transversal) into the Blue Book.
- **Done:** transversal events appear in the Blue Book.
- **Depends:** —
- **Load:** to-do "Add transversal (location changing) logging, add to Blue Book", `services/change_log.py` / historical records.

### P7.14 — Frontend: Blue Book delete with undo
- **Status:** pending
- **What:** entry deletion with a 3-second undo timer; show the timer for one item, queue size for many.
- **Done:** deletions are undoable within the window.
- **Depends:** —
- **Load:** to-do "Enable entry deletion from Blue Book", Blue Book component.

### P7.15 — Frontend: theming
- **Status:** pending
- **What:** light/dark mode + universe-based styling.
- **Done:** theme switch + per-universe styling hooks.
- **Depends:** —
- **Load:** to-do "Theming & Styling", `App.vue` / theme CSS.

### P7.16 — Bug: navdot full-image
- **Status:** pending
- **What:** location-viewer navdot sometimes shows the whole target background instead of a cropped panning part.
- **Done:** navdots always show the cropped pan.
- **Depends:** —
- **Load:** to-do "navdot ... shows the entire target background image", `components/LocationViewer.vue`.

### P7.17 — Bug: faction list refresh performance
- **Status:** pending
- **What:** faction list in GM prep refreshes on faction click and causes a performance issue.
- **Done:** the list does not re-fetch/re-render unnecessarily on click.
- **Depends:** —
- **Load:** to-do "Why does the faction list in GM prep panel seems to refresh on faction click?", GM prep panel.

### P7.18 — Bug: location tree child-panel tracking
- **Status:** pending
- **What:** the location tree tracks which child panel is open; when it closes, the highlight should update (currently it can believe a panel is open when none is).
- **Done:** tree highlight stays in sync with open child panels.
- **Depends:** —
- **Load:** to-do "The location tree should track which child panel is open", `components/gm/GmLocationTree.vue`, `composables/usePanel.js`.

## Deferred & out-of-scope

- **"Increase/decrease result/effect limit"** — deferred with `modify_roll` / `modify_outcome` (release-plan locked decision).
- **Heroic success** (beat by 5+ → step up effect die per 5) — deferred; too swingy, ties-favor-initiator already rewards action. Revisit after the spine is playable.
- **Foundry integration** — out of this release.
- **"Other third-party tools?"** — out of this release.

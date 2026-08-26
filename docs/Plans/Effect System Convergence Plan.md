---
title: Effect System Convergence Plan
tags:
  - transversal
  - technical
  - sfx
  - effects
  - architecture
  - plan
aliases:
  - Effects and SFX Plan
  - Effect Manager Plan
  - Effect Automation Plan
status: working
---

# Effect System Convergence Plan

The full forward plan for the effect/SFX layer — both **automation** (effects firing in play) and **management** (authoring and governing SFX). Follows on from [[Unified Effects Plan]] (which built the layer) and [[Effect Variables and Primitives]] (which hardened the primitives); this plan is what remains to converge them into a trustworthy system.

> [!note] Status
> Working plan, updated in-session 2026-08-26. Several items are already landed; the rest are sequenced below.

## Goal

Transversal's depth comes from a **small set of primitives composed into a large outcome space** — the "card layer" over the dice pool, traits, razmerit, locations/occupants, factions, and roll tables. This plan finishes that layer on two axes:

- **Automation** — effects fire correctly and predictably (trigger → condition → target → action → schedule → broadcast).
- **Management** — authoring is backend-driven and "foolproof": no raw JSON, no drift between vocabularies, searchable/filterable SFX.

## Current state (verified)

The effect layer is built and the primitives are largely in place. Verified by 591 backend tests + a passing frontend build.

**Five closed vocabularies, each owned by one backend module:**

1. **WHEN** — `menu_contexts.py` `TRIGGERS` (21 triggers + 5 menu contexts, typed `{variables}`).
2. **WHEN-gating** — `conditions.py` `CONDITION_TYPES` (`target_kind`, `value_kind`, `operators`).
3. **DO WHAT** — `effects_registry.py` `EFFECT_ACTION_REGISTRY` (40 actions, `group`, fields, timings, duration, polarity, inverse).
4. **TO WHAT** — `effect_targets.py` `resolve_candidates` + scope grammar + `FILTER_FIELDS`.
5. **LIFECYCLE** — `EffectTiming` + `Timer`.

**Supporting machinery:** `effects_engine.py` (trigger match + schedule), `effects_applier.py` (handlers + `{choose:*}`/`{random:*}`/`self.*` resolution), `effects_commit.py` (persist/broadcast), `sfx_owner.py` (availability), `state_events.py` (fire sites), `consequence_menu.py` (base moves).

**Frontend:** thin and generic — `useSfxMeta` / `useEffectActions` / `useEffectTargets` fetch vocabularies via GraphQL; `EffectEditor`, `ConditionEditor`, `TargetPicker`, `ScopeBuilder`, `EffectTargetWizard` render from backend metadata.

**Landed this session:** the full **Batch 3** action set — `enabled` flag + disable/toggle trait, `has_effective_trait` condition, end-active-effect (targeted timer cancel), temporary projection (disguise/restore), set trait-set limit (`TraitSetSetting.limit`), location-scoped temporary asset — plus the gain-trait inline editor (`statement`/`notes` + shared `TraitInstanceEditor`), and two play-surfaced fixes (Dice Pool trigger group restore, `useClipboard`).

## The full remaining scope

### Batch 3 — New effect actions (backend + registry + editor)

- [x] Create temporary location asset (context: duration) — `create_asset` + `location` context field, revert `delete_entity`
- [ ] Challenge rating (effect die vs challenge die) — deferred to a dice-pool/resolver pass
- [x] Step down target-entity's trait — verified: already expressible via `step_down_trait`'s `entity` field
- [x] Disable a trait (new `TraitSetting.enabled` flag — not location-scoped; + duration revert → `enable`)
- [x] Toggle trait (same `enabled` flag, self-inverse revert)
- [ ] Increase/decrease result/effect limit *(decision below)* — deferred to a dice-pool/resolver pass
- [x] Increase/set trait-set limit — `modify_traitset`/`set_limit` → `TraitSetSetting.limit` override
- [x] Create new/temporary projection (disguise / alt-ID) — `projection`/`create` + `projection`/`restore`
- [x] End entity/projection active effect — `end_active_effect` action (scoped `scheduled_event` picker)
- [x] Gain-trait inline trait editor (editor-only authoring; supersedes the auto-fill stopgap) — `statement`/`notes` context fields on gain actions

### Batch 4 — New triggers (fire sites + `menu_contexts` + `_trigger_matches`)

- [x] On scene advance — `on_scene` trigger, global fire in `dispatch_event` (fires for every entity)
- [x] On beat advance — `on_beat` trigger, global fire in `dispatch_event` (fires for every entity)
- [x] On set — `on_set` trigger + fire site in `set_result` (`/set`), context `{effect_die}`/`{total}`; contest set only, non-contest "Done" commit is local-only (follow-up if needed)
- [x] On result — `on_result` trigger + `fire_result_sfx`; context `{effect_die}`/`{total}` plus the roll state under `rolls` (dice with `role`/`tier`/`effect_die`/`ts_id`) — the foundation for Crimson Scars' "rolled but unchosen die" check. Contest set only (same caveat).

### Batch 5 — Cross-cutting behavior

- [ ] Detrimental/neutral/beneficial as a stored `Effect` field *(decision below)*
- [ ] Character-sheet live update when an SFX changes it
- [ ] Manual trigger of configurable effects
- [ ] Prevent automated loops (cycle detection + click/tap prompt)
- [ ] Location-arrival SFX visible on the location's GM panel
- [x] Owner model → `entity_type` condition + GM owner *(decided; see [[#Owner model]])*

### Batch 6 — SFX seeds (consume the above)

- [ ] Exorcise — after `entity_type` filter + universe-choice authoring
- [ ] Banish — after `entity_type` filter + universe-choice authoring
- [ ] Swap — after semantics decision + a new swap action
- [ ] Crimson Scars — after the die concept + a roll-state condition

### Management

- [ ] Rename "Manage SFX Owners" → "Manage SFX"; the SFX Owners panel becomes an SFX management panel with "Owners" as a filter type, plus SFX name search and primitive filters (trigger, condition, effect action).

## Decisions recorded

- **Detrimental/neutral/beneficial** = user input (a stored field on `Effect`), not derived from `(type, action)`.
- **On set** = fires at the roll → set → result boundary, when the user clicks Set and total/effect lock.
- **Result/effect limit** = standard 2 result dice + 1 effect die; scale dice raise the result limit, multi-opponent SFX raise the effect limit.
- **Owner model** = `entity_type` condition + `gm` owner (see below).
- **Drillthrough** = dynamic, target-type field schema (see below).
- **Disable/toggle trait** = a new `TraitSetting.enabled` boolean flag (not `locations_enabled`/`locations_disabled`); a disabled trait must not contribute dice to the pool.
- **`has_effective_trait`** = possession (`has_trait`) is unaffected by disable; a new `HAS_EFFECTIVE_TRAIT` condition gates on `enabled` (a disabled trait is still owned, just not effective).
- **Trait-set limit** = a per-entity `TraitSetSetting.limit` override (registry default when None); `TraitSetting.traitset_limit` resolves the effective limit (override ?? registry), which the sheet already consumes via `traitsetLimit`.

## Owner model → `entity_type` condition + GM owner

> [!note] Status: done (2026-08-26). `ConditionType.ENTITY_TYPE`, static-condition availability filtering, and the `players`→`table` migration are implemented; the "Manage SFX" panel filter is still pending.

Drop the `players` owner bucket and express "player-character-only" as an `entity_type` **condition**; keep `gm` as the GM-context bucket. Supersedes the "ownership stays as-is" note in [[Effect Variables and Primitives]].

- **Rationale:** ownership = *where granted*; conditions = *when it can fire*. A role is an entity property → a condition, not a grant surface. `players` and `table` both mean "every entity", so `players` folds into `table`.
- **Current shape:** `get_available_sfx_ids` unions seven surfaces (`table`/`players`/`gm` + entity/projection/trait/trait-set) and does **not** evaluate conditions — listing and fireability already diverge.
- **Changes:**
  1. `ConditionType.ENTITY_TYPE` + evaluation branch.
  2. `get_available_sfx_ids` evaluates entity-state conditions so listing matches fireability.
  3. Migrate `players` seeds → `table` + `ENTITY_TYPE=character`; remove the bucket.
  4. "Manage SFX" panel: **Owners becomes a filter type**, not the panel's sole axis.
- **Resolved:** `entity_type` gates both listing and firing — availability filters *static* (context-free) conditions, and the engine evaluates all conditions at fire time.

## Dynamic drillthrough → target-type field schema

Replace the hardcoded `self.location`/`self.universe`/`self.projection` with a data-driven schema where each target kind declares its fields and result kinds, enabling recursive `self.a.b.c` paths and a recursive targeting wizard.

- **Current shape:** `_SELF_FIELDS` in `effects_applier.py` hardcodes three fields; `self.location.owner` doesn't compose.
- **Target shape:** `TARGET_FIELD_SCHEMA` in `effect_targets.py` (kind → `(field, result_kind, cardinality)`), e.g. `entity → location/universe/projection/owner`, `location → universe/parent/occupants`, `trait → traitset/owner`.
- **Changes:**
  1. `TARGET_FIELD_SCHEMA` as the single source of truth.
  2. A path resolver replacing `_SELF_FIELDS`.
  3. Surface the schema via GraphQL so the wizard renders continuations.
  4. `{choose:*}`/`{random:*}` stays the terminal step; drillthrough picks the starting subject.
- **Open:** cardinality of set-valued fields (`occupants` → pick-one vs iterate-all); nail the field-name vocabulary once.

## Central Timers → one persisted scheduled-events repository

Consolidate the two timer mechanisms into a single persisted collection of running timers.

> [!note] Status: done (2026-08-26). One persisted `scheduled_events` collection with `target_type`/`target_id`; `EffectsEngine._schedule` removed; REST beat/scene endpoints advance via `dispatch_event`. Queryable + surfaced: `scheduledEvents(targetType, targetId, targetIds)` GraphQL query, `useScheduledEvents` frontend composable, and a `⏳` countdown on the character sheet (entity header + per-trait). Follow-up: migrate legacy owner-scoped `Entity`/`TraitSetting.scheduled_events` lists into the collection and drop the now-unused fields.

- **Current shape:** two parallel mechanisms — owner-scoped `ScheduledEvent` lists (`Entity.scheduled_events`, `TraitSetting.scheduled_events`, advanced by full-table scans in `dispatch_event`) plus an in-memory `EffectsEngine._schedule` (ticked by `tick_beat`/`tick_scene`/`tick_session`, lost on restart). `scheduled_events.py` claims to replace the in-memory schedule but hasn't.
- **Target shape:** one `scheduled_events` collection:

  ```
  ScheduledEvent:
    id
    target_type   ("entity" | "trait_setting" | …)
    target_id
    effect        # deferred/inverse effect to apply at fire time
    timers        [{event, remaining}]
    combine        (FIRST_TO_FIRE | ALL_TRANSPIRED)
    source_sfx_id
  ```

- **Why central wins:**
  - Fixes an existing split-brain (one mechanism, one persistence story).
  - Advancement becomes an indexed query on `timers[].event` instead of walking every entity + trait setting.
  - One query surfaces "what's running now" — needed by the GM active-effects view, debugging, and loop detection.
  - Timers are effect-system state, not entity/trait data (removes the owner-doc coupling).
- **Orphans:** store `target_type` + `target_id`; fire-time resolution is a no-op when the target is gone (plus an optional cascade delete).

## Sequencing & testing

**Build with contract tests, live-test in play.** No full-coverage manual matrix up front — it's deferred until the scope is built. Instead:

- **Contract test per primitive** — each new action/condition/trigger lands with a backend unit test asserting its contract (the 591-test suite grows this way).
- **Drift-proof test** — one automated test (from [[Effect Variables and Primitives]] Phase 1) asserting every trigger's fire-site context matches its declared `{variables}`; catches the "declared vs populated" bug class wholesale.
- **Live-test the SFX actually used in play** — focused, usage-driven manual verification as each SFX is wanted; this drives which scenarios get the attention.

Build order:

1. ~~**Owner model**~~ — done (condition + availability filtering + migration; panel filter pending).
2. ~~**Central timers**~~ — done (one persisted timer repository absorbing `EffectsEngine._schedule`; GraphQL `scheduledEvents` query + filters + sheet display). Foundation for duration-based actions + loop-prevention.
3. **Batch 3 actions** — disable/toggle trait first (already designed; duration reverts ride the new timers), then challenge rating, temporary projection, etc.
4. **Batch 4 triggers** (on set/beat/scene), then **Batch 5** cross-cutting.
5. **Drillthrough schema** (field schema + recursive resolver + wizard) — enhancement/polish, not on the critical path.
6. **Batch 6 SFX seeds** once their primitives exist.
7. **Full-coverage pass** — deferred; revisit only if a class of bugs surfaces that contract tests and live play keep missing.

## Related

- [[Effect Variables and Primitives]] — parent plan (typed references, drift-proofing).
- [[Unified Effects Plan]] — the layer that built the effect system.
- [[SFX and Effects]] — current canonical reference.
- [[to-do]] — the running checklist.

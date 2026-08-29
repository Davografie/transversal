---
title: Choose and Random Resolution
tags:
  - transversal
  - technical
  - sfx
  - effects
  - targeting
  - plan
aliases:
  - Resolution Modes
  - Choose Step
  - Random Step
  - Targeting Choose
status: in-progress
---

# Choose and Random Resolution

Plan to add `choose` and `random` resolution modes to the targeting path, so a path that resolves to *many* can collapse to a user-picked (or random) selection. This is the `choose` / `random` half of the resolution modes deferred in [[Passive Rules and Multi-Target References]] (`all` / `choose` / `random`).

## Context

The targeting path (`TargetSpec`) is a pipeline of steps (`select` / `filter` / `navigate` / `aggregate` / `literal`). Today the resolver returns **all** matches (`all` mode) and the caller fans out. This plan adds two collapsing modes:

- **`choose`** — interactive: resolve the candidate set, present a dialog, the user picks.
- **`random`** — non-interactive: pick from the set at random.

## Decisions (settled)

- **`choose` / `random` are ordinary steps, not terminal-only.** "Terminal" was a *cost* decision (single-shot resolution), not a type rule. The step grammar must allow them mid-path; a terminal `choose` is just the common case.
- **Cardinality.** Single `choose`/`random` collapse `many → one`; multi `choose`/`random` collapse `many → many` (a user-selected subset). `random` carries an optional count `N`.
- **Fan-out.** For a multi result, apply **once per element** (matches `all`).
- **`choose → filter` is type-valid but degenerate** (filtering the single chosen thing). The meaningful order is `filter → choose` (narrow, then pick). The type-checker does not forbid it.
- **Dialog is element-type-aware.** The picker renders per element type (trait shows rating/statement, entity shows universe, die shows size). Renderers are data-driven from `target_catalog` — each element type declares its display fields — rather than a bespoke component per type.

## Scope (phased)

### Phase 1 — `random` (no dialog, no staged resolution) — ✅ done

- `RandomStep` (single + count `N`) — implemented in `target_spec.py` + `target_resolver.py`.
- Type-checker: requires `many`, outputs `one` (or `many` for `N`); `count` must be ≥ 1.
- Resolver: resolve the set, sample `count` without replacement (graceful when the set is smaller than `count`).
- Reuses nothing new — pure backend, applies immediately. Wired into the GraphQL `TargetSpecStepInput.count` + the wizard's `Random` step.

### Phase 2 — terminal `choose` (dialog) — ✅ done

- `ChooseStep` (single + multi) + type-checker (mirrors `random`, allows a mid-path suffix).
- Resolver emits a `PendingTargetChoice` (resolved candidate set + count) and stops — `Resolution.pending_choices`.
- Candidate serialization — `serialize_candidates()` + `target_catalog.DISPLAY_FIELDS` (data-driven labels per element type).
- GraphQL `choose` step input + trace; authoring wizard `choose` step.
- **Runtime dialog**: `effects_engine.StructuredChoice` + `EventOutcome.structured`; `resolve_refs` and `_apply_immediate_spec` surface a terminal `choose` as a structured choice carrying the pre-resolved candidates; `_emit_pending_choices` serializes them into `sfx_choice_required`; `/effects/trigger` emits them; `resolveEffectTargets` accepts `field=target|entity|refs.<name>` and clears the resolved spec.
- Frontend: `EffectTargetWizard` renders structured candidates; `App.vue` captures the acting `entity_id` + shows the choice to the GM; `DiceRoller` resolves against the acting entity.

### Phase 3 — non-terminal / staged `choose` — ✅ done (resumable)

Mid-path `choose` now works: the resolver accepts `answers` (a `step_index →
candidate ids` map), injects the chosen candidates, and continues the suffix;
without an answer it emits a `PendingTargetChoice` carrying its `step_index`.
`StructuredChoice` carries `step_index` + `source_kind`/`source_id` +
`answers_so_far`, so the frontend echoes accumulated answers across steps and the
`resolveEffectTargets` mutation re-resolves the path and either applies or
surfaces the next `choose`. Roll-deferred `choose` surfaces through
`fire_armed` → `sfx_choice_required`.

## Remaining (dependency order)

1. ✅ **Fire-time collection seeding** — `select occupants` / `self_traitsettings`
   (and `locations`/`entities`) are now seeded lazily in the resolver from the
   subject + repo.
2. ✅ **Roll-deferred `choose` surfacing** — `_apply_spec_target` / `_apply_refs_roll`
   surface a `choose` as a `StructuredChoice` via `fire_armed`.
3. ✅ **Phase 3 staged resolution** — resumable `resolve(answers=…)` + resume mutation.
4. ✅ **Shared target across effects** — resolved via [[Effect Output Variables]]:
   an effect binds a chosen value to `{name}` and later effects reference it
   (no second dialog).
5. ✅ **Multi-`choose` fan-out** — `count > 1` fans out for `target_spec` (the
   resolver injects N chosen values and the applier emits one effect each).
   `refs.<name>` fan-out is also done: `resolve_refs` returns one effect per
   value combination (a ref resolving to many fans out, literal/token refs stay
   fixed).

## Implications / risks

- **Staged resolution is done.** Mid-path `choose` resumes via `answers`; the resolver is stateless (re-resolves from the spec + answers each step).
- **Candidate serialization.** Done in Phase 2 (`DISPLAY_FIELDS` + `serialize_candidates`).
- **Re-entrancy.** A mid-path `choose` re-resolves the same spec with accumulated answers rather than storing a half-applied effect; the frontend echoes `answers_so_far`.
- **Multi-choice fan-out.** Once per element — wired for both `target_spec` and
  `refs.<name>`.

## Files expected to touch (remaining)

- `src/api/src/transversal/services/target_resolver.py` — collection seeding + resumable resolver.
- `src/api/src/transversal/services/effects_engine.py` — staged `StructuredChoice` shape + surfacing.
- `src/api/src/transversal/services/roll_deferral.py` — roll-deferred `choose` surfacing.
- `src/api/src/transversal/api/graphql/schema.py` / `types.py` — resume mutation + staged choice payload.
- `src/frontend/src/components/gm/EffectTargetWizard.vue` — multi-step staged picker.

## Execution plan (concrete, ordered)

Settled additions since Phase 2: **context seeding** is the first blocker (also
needed by `sfx-heal` effects 2/3 which `select occupants` directly), and a
**`{effect_die}` substitution gap** in `_apply_spec_target` breaks
`reduce_by_effect` on the roll-deferred path.

1. **Seed collections.** `select occupants` (and `locations`/`entities`/
   `self_traitsettings`) resolve empty today because only `rolled_dice` is
   provided. Seed `occupants` from the subject's `current_location` and
   `self_traitsettings` from `get_traitsettings_for_entity` in *both* the
   immediate path (`_fire_context` / `_apply_immediate_spec`) and the
   roll-deferred path (`_apply_spec_target` / `_apply_refs_roll`).

2. **Substitute `{effect_die}` in the spec paths.** `_apply_spec_target` (and
   `_apply_immediate_spec`) must call `_substitute_effect_context` before
   applying, mirroring `_apply_refs_roll`. Unblocks `reduce_by_effect`
   (`context.effect_die = "{effect_die}"`).

3. **Roll-deferred `choose` surfacing.** `_apply_spec_target` / `_apply_refs_roll`
   must surface a `choose` as a `StructuredChoice` (through `fire_armed` → the
   roll orchestrator → `sfx_choice_required`), not silently no-op.

4. **Phase 3 — resumable mid-path `choose`.** Make `resolve()` accept
   `answers: dict[step_index, list[id]]`. On a `choose` with an answer, inject
   the chosen values (looked up by id) and continue the suffix; without an
   answer, emit a pending choice (carrying `step_index`). Extend
   `StructuredChoice`/`EffectTargetResolutionInput` with `answers`; the resume
   mutation re-resolves the spec and either emits the next choice or applies the
   final target.

5. **Shared target across effects.** *Design:* resolve each `choose` once per
   activation and reuse the answer across effects that reference the same
   `(spec, field)`. Decide the concrete mechanism before wiring `sfx-heal`.

6. **Multi-`choose` fan-out.** `count > 1` applies once per chosen element
   (frontend currently resolves only the first selection).

## Relationship to named refs (Step 3)

Resolution mode is fundamentally a property of the *reference* (each `TargetRef` collapsing its own set), so `choose`/`random` slot naturally onto the named-refs model rather than the legacy `target` string. `TargetRef` gains a resolution mode (or the mode is expressed as a trailing step); keep the two consistent during the Step 3 migration.

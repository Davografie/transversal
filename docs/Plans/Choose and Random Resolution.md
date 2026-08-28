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
status: planned
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

### Phase 1 — `random` (no dialog, no staged resolution)

- `RandomStep` (single + count `N`).
- Type-checker: requires `many`, outputs `one` (or `many` for `N`).
- Resolver: resolve the set, pick one (or `N`) at random.
- Reuses nothing new — pure backend, applies immediately.

### Phase 2 — terminal `choose` (dialog, no staged resolution)

- `ChooseStep` (single + multi).
- Resolver: resolve the full path to a set, then emit a `PendingChoice` carrying the **typed** candidate set; on the user's answer, apply.
- Dialog: element-type-aware renderer; reuse the existing `PendingChoice` + `_emit_pending_choices` flow.
- Covers the common `filter → choose` case without a resumable resolver.

### Phase 3 — non-terminal `choose` / `random` (deferred)

- **Staged/resumable resolution**: resolve the prefix → present candidates → resolve the suffix with the answer.
- Only worth building when a real effect needs mid-path choice (the expensive half).

## Implications / risks

- **Staged resolution is the real cost.** Mid-path `choose` forces the resolver to be resumable (prefix → candidates → suffix). Deferred to Phase 3.
- **Candidate serialization.** "Choose" resolves candidates on the backend but the dialog is frontend. Extend `TargetCandidate` to carry typed display fields per element type (not just `id`/`name`).
- **Re-entrancy.** A `choose` leaves an effect half-applied waiting on user input — same class as `PendingChoice`, plus a "rest of path" to store and resume in Phase 3.
- **Multi-choice fan-out.** Decided: once per element.

## Files expected to touch

- `src/api/src/transversal/services/target_spec.py` — `ChooseStep` / `RandomStep` + type-checker.
- `src/api/src/transversal/services/target_resolver.py` — resolve modes.
- `src/api/src/transversal/services/effect_targets.py` — element-aware candidates.
- `src/api/src/transversal/api/graphql/types.py` / `schema.py` — `TargetCandidate` + choose mutation.
- `src/frontend/src/components/gm/TargetSpecBuilder.vue` + a choose dialog component + `useTargetCatalog.js`.
- `src/api/src/transversal/services/effects_applier.py` / `roll_deferral.py` — fire-time `choose`/`random` wiring.

## Relationship to named refs (Step 3)

Resolution mode is fundamentally a property of the *reference* (each `TargetRef` collapsing its own set), so `choose`/`random` slot naturally onto the named-refs model rather than the legacy `target` string. `TargetRef` gains a resolution mode (or the mode is expressed as a trailing step); keep the two consistent during the Step 3 migration.

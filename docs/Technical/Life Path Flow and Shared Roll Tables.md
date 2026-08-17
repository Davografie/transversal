---
title: Life Path Flow and Shared Roll Tables
tags:
  - transversal
  - technical
  - life-path
  - roll-table
  - next-step
  - design
aliases:
  - Shared Roll Tables
  - Unaffiliated Roll Tables
  - Roll Table Flow
  - next_step return addresses
status: working
---

# Life Path Flow and Shared Roll Tables

How a life-path term moves between roll tables, and how **unaffiliated (shared) roll tables** — tables reused by more than one life path, e.g. a single `Survive` table — carry the information needed to advance the term correctly.

> [!summary] TL;DR
> A term is a graph of roll tables linked by `next_step` effects. Shared tables don't hard-code a per-path next table; instead the *caller* pushes a **return address** onto `pending_term.continuation`, and the shared table returns with `next_step("")` / `next_step("{continue}")`, which pops that address. This is a clean call/return model for **single-exit** shared tables (e.g. `Continue`/Muster). **Multi-exit** shared tables (e.g. `Survive`, where "injured" and "survived" diverge) are *not* solved by the simple stack — see [[#The multi-exit caveat]].

## Background

- A life path is an entry point (`LifePath.entry_table_id`) into a graph of roll tables (see [[Unified Effects Plan]]).
- Each table entry carries effects. **Flow effects** move the term forward: `next_step`, `draft`, `force_muster`, `muster`, `enroll` (see [[Data Model]]).
- `RollTable.life_path` marks ownership: a non-null value = affiliated with one path; `null` = shared/general, reusable by any path.
- `resolve_step` resolves the current table's entry, applies its effects, and processes the flow effects to compute the next table.

## The problem

`next_step` needs a target table id. For a path-specific table the author can write the literal next table. A shared table can't, because its "next table" differs per calling path.

The solution for the simple case: the shared table doesn't *choose* — it **returns** to whoever called it.

## Return-address model (implemented)

`PendingTerm.continuation` is a LIFO stack (`list[str]`) of table ids. `next_step` interprets its fields as:

| `target` | meaning |
| --- | --- |
| literal id (e.g. `"rt-survive"`) | advance to that table |
| `""` or `"{continue}"` | pop `continuation` and advance to it; if the stack is empty, end the term (`done`) |
| `"{choose…}"` | player chooses the next table (deferred — Phase 5 target-choice) |

`Effect.context.return_to` (a dict field) is pushed onto `continuation` **when making a call**, so a later `{continue}` inside the callee returns to it.

The two halves:

- **Caller (affiliated table):** `next_step(target="rt-shared", context={"return_to": "rt-verdant-advance"})` → push `rt-verdant-advance`, enter `rt-shared`.
- **Callee (shared table):** entries use `next_step("")` or `next_step("{continue}")` → pop and return to `rt-verdant-advance`.

Nesting works because `continuation` is a stack: a shared table can itself call another shared table.

## Worked example — single-exit shared table (`Continue`)

Two paths share one terminal `rt-continue` table, which always returns to the same place per path.

- Verdant Steps: `Advancement` → `next_step("rt-continue", return_to="rt-verdant-learn")`.
- Rogue Cultivator: `Advancement` → `next_step("rt-continue", return_to="rt-drifter-3r-learn")`.

`rt-continue` has one exit, e.g.:

- `Continue` → `next_step("")` (returns to whichever Learn table called it).

Flow: `rt-verdant-advance` → call `rt-continue` (`continuation = ["rt-verdant-learn"]`) → resolve → pop → `rt-verdant-learn`.

## The multi-exit caveat

A single return address is enough only when **every outcome returns to the same place**. `Survive` is the hard case:

- `Injured` → the path's *mishap* table.
- `Survived` → the path's *advance* table.

If `Survive` is shared, those two outcomes diverge, but the caller only pushed one address. A LIFO stack can't say "injured pops the mishap address, survived pops the advance address."

Options (decide before wiring a shared multi-exit table):

1. **Only share single-exit tables** *(no backend change; recommended default)* — `Continue`/Muster and any table where all paths return to the same next table become shared; divergent tables (`Survive`, `Advancement`) stay per-path.
2. **Named return addresses** *(backend change)* — generalize the checkpoint so the caller pushes a small map keyed by outcome (e.g. `{"injured": "rt-verdant-mishap", "survived": "rt-verdant-advance"}`), and add a `next_step` target form like `"{return:injured}"` that looks the address up. `context.return_to` today pushes a single id; this generalizes it.
3. **`{choose}` indirection** *(reuses deferred Phase 5)* — the shared table emits `next_step("{choose:table}")` and the pending-choice resolver shows the path's eligible next tables.

Until one of 2/3 lands, keep multi-exit tables path-specific and only promote genuinely single-exit tables to shared.

## Status

- **Backend: implemented and tested.** `lifepath_executor._process_flow` / `_next_step` implement the semantics above; `test_lifepath_executor.test_return_to_continuation` covers call → shared → return.
- **Authoring: partial.** `return_to` lives in `Effect.context` (a dict), which round-trips through GraphQL and `saveRollTable`. Today it is only editable via the raw **"Context (JSON)"** textarea in `EffectEditor` (e.g. `{"return_to": "rt-verdant-advance"}`). The structured per-action context fields (a "Return to → roll-table dropdown") are deferred — see [[Life Path Editor and Wizard Plan]] § Deferred.
- **Seed: not wired yet.** Current `Survive` tables are per-path (`rt-verdant-survive`, `rt-drifter-3r-survive`); no seeded table uses `return_to`.

## Implementation pointers

- `src/api/src/transversal/services/lifepath_executor.py` — `_process_flow`, `_next_step` (return-address logic).
- `src/api/src/transversal/domain/__init__.py` — `PendingTerm` (`continuation`), `RollTable.life_path`, `Effect.context`.
- `src/api/src/transversal/services/effects_registry.py` — `next_step` action meta (target field, `target_kind="roll_table"`).
- `src/api/src/transversal/api/graphql/schema.py` — `rollTables(lifePathId?)`, `resolveStep`.
- Frontend — `EffectEditor.vue` (context textarea), `GmRollTablePicker.vue` (target picker).

## Open items

- Structured `context` UI (replace JSON textarea) — deferred in [[Life Path Editor and Wizard Plan]].
- Choose an approach for multi-exit shared tables (see [[#The multi-exit caveat]]).
- Decide whether to collapse `Continue` into a single shared table and add `return_to` wiring to seed.
- `{choose…}` target-choice resolution — Phase 5.

---
title: Life paths and roll tables — UI-UX handoff
tags:
  - transversal
  - plans
  - ui-ux
aliases:
  - Life-path flow handoff
  - Roll-table content handoff
---

# Life paths and roll tables — handoff for [[ui-ux]]

Companion to [[Unified menu surfaces — UI-UX handoff]] ([[Effects]], 2026-09-25). That note
covers the effect layer, the pick/cost/effect axes and the contracts already exposed. This one
is the **content and flow** side — what a life path *is*, what a roll-table row *means*, and the
gates that already exist around them. Read them together; neither is complete alone. Where
[[Effects]]' note says *"a flow is not a list"* and *"creating is not gaining"*, this is the
detail behind both.

## The flow, precisely — the part a picker cannot infer

A life path is a **checkpointed sequence**, and the checkpoint is a real object, not a UI stack:
`PendingTerm { faction_id, path_id, current_table_id, continuation[], return_map{} }`
(`domain/lifepath.py`). `continuation` is the legacy single-exit return stack; **`return_map` is
the live one** — a map of *named exit → table id*, deliberately **non-nesting**.

- The step verb is `next_step(target, return_to={exit: tableId})`. `target` is a literal table id
  **or a return-address token** — `"{return:next}"` means "go back out through my caller's `next`
  exit". So a shared table can be entered from many paths and leave by name.
- A term ends with `muster` (respectful) or `force_muster` (dishonorable); `enroll_life_path`
  records the membership and `draft_life_path` moves the character into another path. These are
  effect actions today (`services/effects_registry/actions_lifepath.py`).
- `LifePath.entry_table_id` is the path's first table; the rest of the graph is discovered by
  following `next_step`. **Nothing declares the path's table list** — a component that wants to
  render "the path" must walk it or ask the canvas, which does exactly that walk.

**Consequence for the component:** "back" is not a navigation stack. If the unified surface offers
a Back affordance it must be driven by `return_map`, and a step that lands in a shared table has
*more than one* valid way out.

## A row's `key` means a different thing per scheme

`RollTable.scheme` decides what a row *is*, so a presentational row cannot own the key column:

| scheme | a row is | the key cell shows | live tables |
|---|---|---|---|
| `RANGE` | a band of the roll | `min–max` | 12 |
| `INDEX` | one of N, in order | position | 9 |
| `TIER` | an outcome tier | the tier | 8 |
| `WEIGHT` | a slice of a weighted roll | `w` | **0** |

⚠ **`WEIGHT` is implemented and unused** — no live table carries weights, so the unified
component has no live example to test against and the weighted 🎲 path (`EntryPicker`'s
`allow-random`) is only exercised through test content.

Also on the table, not the row: `roll_source` (`FIXED_DIE` 27 / `TRAIT_DICE` 2) with
`trait_dice_count`, and `check { traitIds, difficulty, freeChoice }` for `TIER` tables. A
`TRAIT_DICE` table rolls **the character's own trait dice**, which is why `LifePathWizard` carries
a trait selector and a fixed-die table does not.

## The same table is a roll table *and* a character-creation surface

Character creation is **not a separate table type**. `RollTableMenu` takes `mode="create-support"`
and resolves the *same* entry a different way: pay `cost_effects` → `createSupportCharacter(
playerId, mainEntityId, tableId, index)` → the new entity is placed, owned and linked → the entry's
`effects` then land on the new character (`services/roll_table_menu.py`). Whether a pick *gains* or
*creates* is a **host mode**, not a property of the row.

The archetype tables are the live example — `rt-support-cast` (`universe="earth"`, no path) and
`rt-three_realms-support-cast`, resolved per universe with a fallback. [[B126]] extends this into
the multi-step, life-path-driven creation pipeline ending in a generated portrait, so the component
should not assume creation is one pick.

## Scope: fundamental / shared / per-path

Every roll table sits in exactly one of three scopes, and the GM panel groups by them:

- **fundamental** — `universe=""`, no `life_path`: available everywhere.
- **shared** — `universe` set, **no** `life_path`: offered within that universe (the support-cast
  tables are the live instances).
- **per-path** — `life_path` set: the path's own tables.

A unified list of "tables" is meaningless without this axis. The same vocabulary drives the
authoring surfaces ([[B41]] just moved the universe and entry-table fields onto the shared picker).

## Four gates already exist — do not conflate them

The component's "why not available" axis has more vocabulary than it looks:

1. **Row gating** — `RollTableEntry.conditions`, resolved per roll ([[B179]]): a failing entry falls
   back to the previous matching row, or is *refused by name* for a deliberate pick.
2. **Path walkability** — `LifePath.conditions`, **in flight** ([[B194]]–[[B197]]). The human's
   decision: **visible and disabled, carrying why** — not hidden.
3. **Path discovery** — `LifePath.discovery` (a one-time *reveal*, distinct from walkability).
   **Currently inert:** `check_discovery` has no production caller and there is no
   `discovered_paths` storage.
4. **Offering** — `LifePath.factionIds`, **derived read-only** from
   `faction.suitable_life_path_ids`; there is no mutation for it.

[[Effects]]' note lists gating as one axis; on this side it is four, of which one is dead and one
is being built now.

## One name-resolution contract, or the ids leak

This is a live defect, not a hypothetical. The runtime surfaces each resolve option and target
names from a *different* map, and the failure is silent:

- `LifePathWizard` resolves traits from `traitsByUniverse(<the path's universe>)`. `trait-rel-tenure`
  is stamped `universes: ["earth"]`, so in a `three_realms` path the name lookup misses and the
  wizard renders the **raw id** — for `rank` and `tenure`, the two traits the life-path ladder
  depends on.
- The canvas's `RollTableNode` resolves against **roll-table names only**, so *every* trait target
  there renders as raw text.
- `GmRollTableDetailPanel` resolved against the full traitset list and got it right. **That panel
  is gone** — [[B275]] collapsed it into `GmRollTableEditPanel`, which carries the same resolution
  (`useEffectActions().summarize` with the trait and table-name maps), so the one surface that got
  this right survives the merge. The two above are still wrong.

If the unified component inherits "the host passes a name map", it will reproduce this per-host.
It should take **one resolution contract** — an id → label resolver supplied once — and the hosts
should stop each carrying their own.

## Who gets recorded

`repo.add_historical_record` (the Blue Book) has exactly three callers: `entity_manager`,
`lifepath_executor` (a term step) and `contest_history`. So **a life-path step is recorded and a
menu pick is not** — `pick_roll_table_entry` and `{choose:*}` answers write nothing. Unifying the
surfaces is the moment to decide this once rather than inherit the gap; it is currently filed as an
unowned observability note.

## Retiring `LifePathWizard` — the affordances to absorb

[[ui-ux]]'s own note calls the wizard "the natural next adopter rather than something to force".
Concretely, these are the things it does that the current `EntryPicker` does not, and each is a
decision rather than a port:

- **scheme-aware rows** — the key column above, plus `conditions` rendered inline as `if …` and a
  per-row effect summary.
- **roll-then-confirm** — rows are *selected*, then `Continue` commits; the 🎲 (`WEIGHT`) is a
  separate act from picking. This is the "a roll is not a pick" rule in the UI.
- **`TRAIT_DICE` selector** — choose which trait dice are being rolled.
- **flow chrome** — `↩ Paths` (back through the flow), the term phases
  (`choose` → `table` → `wizard` → `done`), and the mustered-out states.
- **a result block** — `applied[]`, `scheduled` (deferred effects queued), `pendingChoices`, and a
  collapsible history. [[Effects]]' open question 5 asks what "what happened" should be; this is
  what exists today.

## This side

- **I own:** life-path and roll-table *content*, the flow semantics above, and the roll-table /
  life-path authoring surfaces ([[B41]], [[B197]]).
- **I will provide:** the flow driver's contract (`pending_term` in and out, `return_map` as the
  back model), and I am happy to be the first adopter if the component lands as a *presentational
  row surface + a driver* — which is what [[Effects]]' open question 1 proposes and what the
  evidence here supports.
- **I need from [[ui-ux]]:** the row vocabulary (is a row an entry, an option, or a step?) and the
  "why not" presentation, since four gates have to render through it.
- **Not mine to decide:** whether the *authoring* side unifies too. The same overlap exists in the
  editors (`GmRollTableEditPanel`'s entry list — which since [[B277]] owns each row's binding
  and its effects — plus the SFX menu editors); if the
  component is runtime-only, the *row vocabulary* should still be shared so the two sides do not
  drift.

## Source

Written 2026-09-25 by [[life-path]] at the author's request, from the surfaces' own code and the
live collection (29 roll tables, 802 traits) — every count above is measured, not estimated.
Related: [[B5]] (choice nodes), [[B126]] (the creation pipeline), [[B179]] (conditional entries),
[[B190]] (greyed rows), [[B194]]–[[B197]] (walkability), [[B41]] / [[B197]] (the authoring
surfaces).

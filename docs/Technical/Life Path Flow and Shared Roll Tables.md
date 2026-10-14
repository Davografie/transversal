---
title: Life Path Flow and Shared Roll Tables
tags:
  - transversal
  - technical
  - life-path
  - roll-table
  - wrapper
  - design
aliases:
  - Shared Roll Tables
  - Unaffiliated Roll Tables
  - Roll Table Flow
  - Life-path wrapper
  - next_step return addresses
status: working
---

# Life Path Flow and Shared Roll Tables

How a life-path term moves between roll tables, and how a table can be **shared** —
wrapped by several paths, or by none — without the table knowing anything about them.

> [!summary] TL;DR
> A **roll table is content**: a roll selects a row, the row may carry effects, and that is
> all it knows. A **life path is a wrapper**: it declares the tables it wraps (`steps`) and
> what each of their rows means to it (`bindings` — where the row goes, what leaving means,
> whether it enrols you, and a delta of effects). The pointers live in the path. Sharing
> therefore needs no machinery: two paths wrap the same table and give its rows different
> meanings, and neither edits it.
>
> **This replaces the return-address model.** `continuation` / `return_map` /
> `{return:<name>}` existed because a shared table could not name its own next table and had
> to "return to its caller". Measured 2026-10-09: **0 of 103 live `next_step` targets were
> tokens.** Nothing used it. The wrapper makes the question disappear rather than answering
> it better — see [[#Why the return addresses are gone]].

## The model

```
LifePath {
  entry_step        # the step a term begins at
  steps: [
    { id          # the STEP's identity — not the table's
      table_id    # the roll table this step wraps
      label
      next        # default step id for rows with no binding; "" ends the term
      effects     # applied ONCE for any row this step resolves — the effects
                  # counterpart of `next`. Runs after the row's effects and the
                  # binding's, in the same scope, so it can read a name the picked
                  # row exposed; a name only some rows expose resolves on those and
                  # is a clean no-op on the rest.
      bindings: [
        { key       # names one row of that table (RollTableEntry.key)
          next      # step id in THIS path; "" leaves the path
          exit_kind # "" | "muster" | "force_muster" | "draft"
          exit_path # destination path when exit_kind == "draft"
          enroll    # taking this row admits the character to the path
          effects   # delta, applied AFTER the row's own effects
        }
      ]
    }
  ]
}
```

Three consequences worth stating plainly:

- **A step is not a table.** `id` belongs to the step, so a path may wrap the *same table
  twice* (two steps, one table) — impossible when the table was the node — and a step
  survives its table being re-pointed. The canvas keys its nodes by step id for exactly
  this reason.
- **Scope is derived, not declared.** `RollTable.life_path` used to say which path owned a
  table. Now a table is *fundamental* (wrapped by nobody), *shared* (wrapped, universe set)
  or *per-path* (wrapped by a path) purely as a fact about the paths that wrap it.
- **A row has one identity and many meanings.** `RollTableEntry.key` is stable and stored,
  deliberately **not** derived from the row's band: a binding naming a row must survive that
  row's band being re-cut from `1–12` to `1–10`.

## A step's own effects

`LifePathStep.effects` is where a path says *what this step does whatever row resolved*,
as against `next`, which says *where it goes*. It exists so an effect that every row
would otherwise repeat is written once.

Two properties carry it:

- **It reads the whole scope,** including whatever the resolved row exposed, because
  `resolve_step` applies the row's effects, the binding's delta and the step's in one
  `effect_context`. A name only some rows expose therefore resolves on those rows and
  does nothing on the others — which is the point, not a defect.
- **It is applied by path, never by a flat `{token}`.** `select variable <name>` in a
  `target_spec`/`owner_spec` resolves to *zero targets* when the name is unbound and
  the effect is applied zero times. Writing `{name}` into a flat field such as
  `target` does **not** behave that way: `_substitute_effect_context` rewrites only the
  tokens it can resolve and leaves the rest verbatim, so the effect runs against the
  literal string `"{name}"` ([[B282]]).

Flow is deliberately *not* read from a step's `effects`: a step's destinations are
`next` and its bindings, which keeps "flow is structure, not effects" true.

## Flow is structure, not effects

What used to be `life_path`-type effects on a row is now declared by the path. The split was
**measured against the live content**, and the measurement overruled the first design:

| verb | live uses | alone on its row | with a `next_step` | verdict |
| --- | --- | --- | --- | --- |
| `next_step` | 103 | 34 | — | **edge** → `next` |
| `muster` | 6 | 6 | never | **destination** → `exit_kind` |
| `force_muster` | 9 | 9 | never | **destination** → `exit_kind` |
| `enroll` | 24 | 6 | always | **admission** → `enroll` flag |
| `draft` | 0 | 0 | — | destination → `exit_kind` + `exit_path` |

- **`muster` / `force_muster` are destinations, not effects.** All 15 such rows carry
  *nothing else*, and none of them carries a `next_step`. They are not effects that happen
  to end a term — they are where the row goes, and the kind carries the payload
  (honourable / dishonourable).
- **`enroll` is per-row, never per-path.** `enroll` appears on a row 24 times and **never
  once without a move**, so it is a flag on the edge. It cannot be a path-level flag:
  `rt-verdant-qualify` enrols its *Accepted* rows and not its *Rejected* ones, so a
  path-level flag would enrol the rejected.
- **`draft` has no live use**, so it was free to design; it stays an exit kind that hands
  the term to another path.

**No live roll table carries a `life_path` effect after the migration.** The actions stay
registered — an SFX may still draft someone into a path — but a table's flow is the path's
business now.

## Two regimes, and why the shim exists

`resolve_step` distinguishes them by whether the path declares steps:

- **Wrapped** — the path owns its graph. The binding for the row that resolved supplies the
  edge (or the step's default when the row is unbound), and **any `next_step` effect still
  sitting in the entry is ignored**. Two sources of truth for one edge is how a canvas and
  a runtime end up disagreeing.
- **Unwrapped / unmigrated** — the executor synthesises a one-table step from
  `entry_table_id` and the entries' effects drive the flow exactly as they did before. This
  is what let the code land before the migration ran, and what keeps an old database
  working.

Term verbs run in **both** regimes: they are what a row *does*, not where it goes.

## Why the return addresses are gone

The old model is preserved here only so the reasoning survives, because it was not wrong —
it was solving a problem the wrapper removes.

`next_step` needs a target. A path-specific table could hard-code one. A **shared** table
could not, because "the next table" differed per calling path — so the caller pushed a
return address onto the checkpoint and the shared table returned through it. A single LIFO
stack was enough only when every outcome returned to the same place; `Survive` (injured →
mishap, survived → advance) needed a *map* of named exits, and `{return:<name>}` resolved
against it.

Under the wrapper a shared table does not choose or return — it does not know it is in a
path at all. **The path says where each of its rows goes.** `Survive`'s two diverging
outcomes become two bindings, and there is nothing to return *to*.

`PendingTerm.current_step_id` is the checkpoint. `current_table_id` is **derived** from it
and kept because the surfaces read it to display. `continuation` / `return_map` remain as
empty fields purely because `LifePathWizard` still selects them; they are dead, and they go
when that wizard is retired into the unified surface ([[ui-ux]]).

## Validation

`services/lifepath_validation.py` — `validate_life_path(path, repo)` returns the structural
problems the wrapper makes possible: an edge naming a step the path does not have, an entry
step that is not a step, a row bound twice, a binding naming a row the table lacks, a
`draft` to a path that does not exist, both `next` and `exit_kind` set on one binding.

It deliberately does **not** check effect targets — that is [[B156]]'s carrier-agnostic job,
and a second copy of the resolution rules is how the two drift.

The executor's failure mode when it meets a bad edge is to **end the term** rather than loop
on an unresolvable step; the validator is what should have caught it, and a silent loop is
the worse failure.

## Authoring a table outside a path

A row's effects land on the **subject the table was rolled for**. A roll table declares what
that may be with `RollTable.subject_kind` (`entity` / `projection` / … , from the same
vocabulary the effect system uses for owners) — a roll table's answer to an SFX's
`source_kind`. Without it, a row effect naming a trait silently assumes a character was
rolled for, and means something else or nothing when the table is rolled for a projection.

A table with no effects and no `subject_kind` — `rt-earth-regions` is the live example — is
pure content and can be rolled for anything.

## Implementation pointers

- `domain/lifepath.py` — `LifePath`, `LifePathStep`, `LifePathBinding`, `PendingTerm`.
- `domain/rolltables.py` — `RollTableEntry.key`, `RollTable.subject_kind`.
- `services/lifepath_executor.py` — `start_term`, `resolve_step`, `find_step`, `_process_flow`,
  `_advance`, `_exit`. `_next_step` survives **only** for the unwrapped regime.
- `services/roll_table.py` — `row_key`, `entry_key_for`, `table_bindings` (the scope a row's
  conditions and effects resolve against; it walks the declared layers `path → step → table → row`
  in that order, with `path`/`step` optional, and `override_names` is the one definition of what an
  override means), `entry_applies` / `resolve_applicable_entry` (which build the table's scope so a
  row's *conditions* can read it), and — for reservations ([[B285]]) — `declared_type_of`,
  `is_reservation`, `traced_type` and `roll_table_problems` (the pure write-boundary check, called
  by `saveRollTable`).
- `services/lifepath_validation.py` — `validate_life_path`.
- `migrate_lifepath_wrapper.py` — the one-way migration off the old model.
- Frontend — `composables/lifePathGraph.js` (draws from steps); `composables/useBoundVariableScope.js`
  (resolves one declaration layer into a scope — shared by every layer, so none can drift from the
  engine — refusing a shadowed name as the engine does, plus `reservationsOf`, the slot list);
  `GmLifePathDetailPanel.vue` authors the path, its **declarations** and its **steps**;
  `GmStepVariablesPanel.vue` authors one step's declarations in a child panel ([[B290]]);
  `GmRollTableEditPanel.vue` authors the table's declarations (values **and reserved slots**), a row and its **binding**
  (next / exit / draft / enrol / binding effects); `GmRollTableEntryEditPanel.vue` authors a row's
  own declarations (the **assignments** of the table's slots). The split is by ownership, not by verb — [[B277]] collapsed the old
  `GmLifePathEditPanel` for the opposite reason: it and the table panel both rendered rows, so the
  same bindings had two editors.

## Open items

- **`RollTable.life_path` is not yet deleted** ([[B270]]). An earlier version of this line
  claimed nothing in the backend reads it; **that was wrong**. `table_bindings` reads it, and
  deliberately **prefers** it over the invoking term's path — a table that names its own path
  must not be re-anchored by whatever term is running. Two tests assert that, so B270 has to
  unpick the precedence, not merely delete a field. The GM detail panel and the canvas's
  drag-to-link are the other two readers.
- **`useCanvas.linkRollTable` still writes legacy `next_step` effects**, so drag-to-link in
  the life-path canvas is inert under the wrapper.
- **Forbidding a row** — a path declining a row it does not want — is designed for but not
  built (the human: *"paths forbidding rows sounds interesting, maybe later"*).
- **Bound variables are declared at four levels, and the resolution order is the point**
  ([[B279]], [[B281]], [[B290]]). The wrapper nests — `path → step → table → row` — and the
  layers resolve outermost first, into one scope. A **table's** declarations resolve once per
  activation, *before any row is chosen* — so every row shares one value, and, precisely because
  they exist before a row does, a row's **conditions** can read them (one declaration instead of
  an elaborate targeting path repeated on every row). A **row's** own declarations resolve once
  that row has applied, so a value only one row has — a location, a rival — can be exposed; a
  row's conditions cannot read *those*, which would be circular, since which row applies is the
  question being asked. A later layer's name may start from an earlier one, and an existing name
  wins: a collision is refused and logged rather than silently rebound, and the editors mark it.
  The **path's** and the **step's** layers are the caller's, and are what let a *shared* table
  read the context of whichever path wraps it — see the [[B290]] entry below.
  The *consumption* half is proven end to end: a declared name is typed by its traced path, and a
  life path's **binding effects** read it because `resolve_step` hands one scope to both the row's
  effects and the binding's. The form is a path (`select variable X`), not a `{token}` in a
  positional field.
- **A name's type can be *declared* instead of only traced** ([[B285]]). `BoundVariable` gained
  `element`/`cardinality`, optional and empty by default, and a table declaration that states them
  **with no path** is a **reservation**: a typed slot, binding no value, that every row's
  assignment is checked against. Without one a name's type is only as consistent as every
  hand-written path that happens to use it — one row starting from a collection where the rest
  pinned a value makes the same name `many` for that row alone, and nothing objects. The rules:
  - a reservation **binds nothing**; the name stays unbound until a row assigns it;
  - an assignment that reaches a different type is **refused** — left unbound, not coerced and not
    rebound, because the reservation is what a downstream effect was written against;
  - a **table that reserves anything** must have every row assignment name a reserved name, and
    `saveRollTable` refuses one that does not. Scoped that way deliberately: refusing every
    free-form row would refuse the next save of any table that has one, and the panel writes the
    whole table, so it would take the author's unrelated edits with it. A table that reserves
    nothing is the free-form table that existed before, and it cannot break a promise it never made;
  - the check is `services/roll_table.roll_table_problems`, pure and catalog-driven, run at the
    **write** boundary. The **read** tolerates a stored unreserved name — the same "enforce on
    write, keep reading old data" split the unwrapped-path and legacy-term shims use.
  A reservation's type is stated **once**, on the table: a row assigns a name and states no type of
  its own (`_entry_input_to_domain` clears the fields), because two places to state one type is two
  places to disagree.
  **Authoring it:** the table panel's section takes `allow-reservations` — a declaration with no path
  becomes a slot, edited as an element from the targeting catalog plus `one`/`many` — and the row
  editor is handed the slots (`context.reservedVariables`) so its name field becomes a **picker** and
  a mismatched path is shown in the same red a shadowed name uses. `reservationsOf()` in
  `useBoundVariableScope.js` is the one definition of "what is a slot", the frontend twin of
  `is_reservation`; `useCanvas.linkRollTable` and both panels' whole-document maps carry the two
  fields, so a save that never touched a reservation cannot erase it.
- **A path and a step supply the context a shared table reads** ([[B290]], landed 2026-10-13). The
  wrapper nests — a path wraps steps, a step wraps a table, a table wraps rows — so the declaration
  layers resolve outermost first, and a table wrapped by several paths reads whichever one is
  walking it:

  ```
  path  →  step  →  table  →  row
  ```

  `table_bindings` walks its `layers` tuple in order, so this is the same rule over a larger
  nesting rather than a new one ([[B285]] left one definition of what a declaration is).
  `LifePath.bound_variables` and `LifePathStep.bound_variables` are the two new holders, the same
  shape as a table's and a row's; **declarations only** in v1 — a path or step does not reserve a
  typed slot for its rows to fill, which is the identical shape and can follow if a path wants it.

  What it buys, measured rather than assumed: `rt-verdant-advance` and `rt-ironroots-standing` are
  **mechanically identical row for row** once the faction id is masked — same bands, same effects,
  five rows each — differing only in that id and the row labels. One shared `rt-advance` reading
  `{sect}` replaces both, and the 15 effects that hardcode `faction-41014575` can stop. That is the
  content half of the wrapper, and what [[P5.5]]'s shared tables have been waiting on.

  **Precedence is *not* "the more specific wins", and the reason is structural.** On a collision the
  earlier layer wins and the later declaration is refused, because for **table → row** the general
  value has *already been read*: a row's conditions are evaluated against the table's scope (built
  with no entry — which row applies is the question being asked), so a row that rebound the name
  would make the condition and the effect disagree about what `{name}` means inside one activation.
  That is the guarantee the table layer exists for. For **step/path → table**, "which is more
  specific" cuts the other way — the path's value is specific to the term, the table's to the table
  — and the rule already gives the **caller** precedence over the shared content, which is what
  sharing wants; flipping it would hand precedence to the callee. So:
  1. **values — outer resolves first and wins**, one value per name per activation;
  2. **slots — the inner layer fills the outer's reservation**: a reservation binds no value, so an
     assignment is a *fill*, never a shadow. This is the one place where "the specific overrules the
     general" is unambiguous, and it works at table → row;
  3. **plus an explicit override** for path and step over table — `BoundVariable.override`, a
     declaration marked as such which **replaces the table's own declaration of that name before any
     layer resolves**. Outer-first already wins *while the caller's path resolves*; what the override
     adds is the case where it resolves **nothing**, where the table's value would otherwise surface
     and the same `{name}` would mean two things across activations. The editor states it as
     *"replaces the wrapped table's `{name}`"* — informational, not the red *"will not bind"*, because
     there is nothing wrong. It cannot work for row-over-table, for the structural reason above: the
     row does not exist yet when its conditions run, so the flag is **cleared** on a table's or a
     row's declaration where no layer could keep the promise.

  **Two implementation facts.** `table_bindings` is *handed the step* (a table may be two steps in
  one path, so it cannot be inferred), and `roll_table_menu` has no step and may run outside any term
  — so the path/step layers are **optional, absent rather than empty**, like the ambient facts. And
  `resolve_step` hands them to **both** `resolve_applicable_entry` (which builds the scope a row's
  *conditions* read) and the effect scope: one of them alone would let a condition test a name the
  effect after it does not have, inside one activation.

  **Authoring it.** The path panel gains a **Path variables** section; a step's own declarations open
  in a **child panel** (`GmStepVariablesPanel`), because the step list is already table + label +
  next + effects — the same reasoning that moved a step's effects out. `BoundVariablesEditor` gained
  `allowOverride` and `overridable`, both additive and off by default, so the SFX and roll-table
  callers are unchanged. The round trip is where this surface keeps losing data, and there are now
  **three** writers to keep in step: `LIFE_PATH_FIELDS` selects the declarations at both levels, the
  path panel's save sends them (per step, in a map that replaces the whole list), and the roll-table
  panel's **connector** — which rebuilds every step by hand — carries them too. `stepScopeFor()`
  folds the path's and the step's layers in ahead of the table's, which is what makes the names
  authorable in the effects that consume them ([[B281]]'s bug otherwise). `resolveLayer` in
  `useBoundVariableScope.js` now **refuses a shadowed name** as the engine does; it used to write the
  later value into the offered scope, so an editor offered a name that resolves to the outer value at
  run time.

  Row labels stay per-table (the human's call): two paths wanting the same mechanics under different
  fiction get different tables.
- **The offering gate is not the same thing as the enrolling faction** (measured 2026-10-13, on
  [[B41]]). `LifePath.factionIds` is derived read-only from each faction's `suitable_life_path_ids`,
  which is **write-only on the wire**; `LifePathWizard` locks a path that no faction offers — **7 of
  10 live paths** — and that is currently the *only* gate on the player surface, because nothing in
  the frontend reads `walkable` while [[B196]] is pending. But `startTerm` *requires* a `factionId`,
  and on an enrolling row `_ensure_enrollment` uses it to create the `entity → faction`
  `membership` edge that rank and tenure hang off (3 live settings, 15 effects). So the gate is
  removable and the faction is not: it wants a picker over the character's memberships, or a
  `startTerm` that takes the membership edge.
- Row gating (`RollTableEntry.conditions`, [[B179]]) and path walkability
  ([[B194]]–[[B197]]) are unchanged by this and remain separate gates.

---
title: Effect Targeting Coverage
date: 2026-09-15
tags:
  - transversal
  - sfx
  - effects
  - targeting
  - reference
aliases:
  - Targeting Coverage
  - Effect Target Audit
status: current
---

# Effect Targeting Coverage

Which effect actions can be authored with a **targeting path**, and which still
fall back to a flat text field. Regenerate with the snippet at the bottom — the
counts move as the registry grows.

## The three axes

An effect can say three different things, and each is authored differently:

- **Target** — *what it acts on*. A path is offered when the action declares a
  destination: `target_kind` (a picker kind, which also names the destination) or
  `path_elements` (the catalog elements a path may reach, when there is no picker
  — a die has no picker, and the change-die family accepts **either** a pool die
  or a rating die). The field must be named `target`.
- **Subject** — *who it lands on*. Available whenever the action declares a
  field named `entity`; the picker/path row is automatic
  (`EffectForm.isEntityField`). No extra declaration needed.
- **References** — *extra things it resolves for itself* (an Attune's universe
  and projection, an Add-Trait-Rating-Dice's trait and pool). Each
  `EffectActionMeta.refs` entry renders its own path builder.

A fourth thing, **`die_filter`**, scopes *which* dice a roll-deferred effect runs
for. It runs the effect **once per matching die**, and inside that effect the die
*is* the roll: the effect's `target_spec`, `entity_spec` and `refs` all resolve
against it (the filter is checked before the spec/ref branches for exactly that
reason). The card states the scope (*"for each unchosen die, …"*).

## Coverage today (55 registered, 51 offered)

> Numerals from the regeneration recipe at the end of this note (re-run
> 2026-09-15, after the sweep to paths): **55 registered, 51 offered** — the other
> 4 are retired from authoring but kept resolvable. Of the 51 offered, **31** have
> a path-capable target (`target` **and** a declared destination), 6 declare
> `refs`, **3 flat targets** (names, not references — see item 4), **17 with no
> `target` field at all**.
>
> **Every offered target is a path**, and no offered action declares a picker kind
> for its target any more. The `{choose_*}` / `{random:*}` placeholder strings and
> the `target_scope` / `target_filter` fields beside them are **deleted** (2026-09-17):
> a runtime pick is a `choose` step in the path, and a candidate filter is a
> `filter` step.

- **Target offers a path — 35.** All the trait actions (including **Change Trait**,
  whose *second* question — what the instance becomes — is a reference path of its
  own, so one effect answers *which instance* and *what definition* separately; it
  reverts through the same action carrying the prior definition),
  the change-die family
  (which accepts *either* a pool die or a rating die), the location/travel ones,
  `transfer_razmerit`, `attune`, `create_relationship`, `entity_targeting_ban`,
  `set_traitset_limit`, `discover_life_path`, `draft_life_path`,
  `open_roll_table`, `next_step`, `add_dice`, `end_active_effect`.
- **Subject available — 20.** The trait actions plus `earn_razmerit`,
  `spend_razmerit`, `travel`, `set_location`, `set_traitset_limit`,
  `end_active_effect`, and two of the *name* actions (you can path who receives
  an asset; you just cannot path what it is called).
- **Own path builders (refs) — 7.** `add_trait_rating_dice` (trait + pool),
  `roll_pool` (pool), `resolve_pool` (pool), `attune` (universe + projection),
  `copy_trait` and `move_trait` (the trait instance), and **`change_trait`**
  (the *definition* the instance becomes). Copy/move take the recipient from their
  `entity`/subject field, so the thing being handed over is a path while *who gets
  it* is the ordinary subject target; `change_trait`'s primary target is the
  instance, and the definition reads second.
- **Removal is authorable.** `delete_trait` — now labelled **Remove Trait** —
  exposes `modify_trait`/`remove` and names the instance, which is why
  `negate_complication` is retired in its favour.

## Gaps, and what each actually needs

**1. Strategy keywords — 1 action left.** `convert_complication`
(`botch_to_hitch`) names a *rule* for choosing a die, not a thing, and nothing
applies it. *`reroll_die` came off this list 2026-09-15:* it declares a
pool-die destination (`path_element=("die",)`) and its `the_hitch_die` default is
a named meaning rather than unexplained text. It still has no applier, because
rerolling writes a new **result** — the resolver's business, not a state
mutation. *`step_up_die` / `step_down_die` came off it 2026-09-12.*

**2. Die references — landed 2026-09-15.** `double_die`, `split_die` and
`remove_die` are applied for real, in either home, with a `count`
(`double 2` on a d8 makes 3d8; `split 2` makes 3d6). One rule
(`handlers_change_die._plan_change`) and two appliers — the rating list and the
pool list — so the two homes cannot drift. `_apply_step_die` is retired with them.

`reduce_by_effect_die` and `increase_by_effect_die` joined the family too: the
effect die is their reference instead of a number, and their target is a
**targeting spec** naming a die in either home — there is no die picker, so the
spec is the only way to name one. The `entity` and `relationship` fields they
carried are gone with the trait form: the spec resolves the instance, so *whose*
die and which membership anchor are already in the reference rather than separate
questions.

**3. Trait-instance references — landed 2026-09-15.** `split_die` was the
blocker; it now takes a path to either locus, and the `target_kind` /
`path_element` split this note asked for is what made that writable.

**4. Names, not targets — 2 actions.** `create_asset` ("Asset Name"),
`create_projection` ("Disguise Name"). Correctly flat: these are labels, not
references. No change wanted.

**5. No target at all — 18 actions.** Mostly correct (dice limits, steps,
outcomes, muster). Five of them (`add_trait_rating_dice`, `roll_pool`,
`resolve_pool`, `copy_trait`, `move_trait`) resolve their real inputs through
`refs` already, so they are path-capable in the way that matters.

**6. Retired, not deleted — 4 actions.** `step_up_trait`, `step_down_trait`,
`remove_rating_die` (the change-die family on a rating die) and
`negate_complication` (Remove Trait). They are filtered out of the editor's
`effectActions` and stay in the registry, because that is where an existing
effect's inverse, card and dispatch come from — so stored content keeps working.

**7. The trait picker and the strategy keyword — gone, 2026-09-15.** The last
non-path targets, swept at the author's direction (*"Make path the only way …
sweep the non-path targets"*):

- The **instance-targeting** trait actions (`set_trait`, `add_rating_die`,
  `delete_trait`, `disable_trait`, `toggle_trait`, `reveal_trait`) declare
  `path_element=("traitsetting",)`; the **definition-targeting** ones
  (`gain_trait` and its siblings) declare `("trait",)`, named with the new
  `select traits` seed.
- Their `entity` and `relationship` fields went with the picker, except on the
  gain actions — where `entity` is a genuine **subject** and `relationship` an
  **anchor** a subject-spec cannot yet express.
- The **strategy keyword** is deleted from the applier too, not just hidden:
  `highest_trait_die` and `the_hitch_die` were the last two, and both are paths
  now (`select rolled_dice → filter source_kind == trait → aggregate Highest
  element field=rating`, and the same filtered to `tier == fail`). A step's
  `output` + `select variable` is how one is reused.
- `convert_complication` (`botch_to_hitch`) is the last keyword in the registry,
  and it is blocked on the **Invert Polarity** decision rather than on this work.


## Regenerating this

```bash
docker run --rm -v <worktree>/src/api/src:/app/src -w /app transversal2-api:latest python -c "
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY as R
for m in R:
    names = {f.name for f in m.fields}
    has = 'target' in names
    dest = m.target_kind or ','.join(m.path_element)
    tag = 'RETIRED' if m.retired else ''
    if has and dest: print('path  ', m.action_id, dest, tag)
    elif has:        print('FLAT  ', m.action_id, next(f.label for f in m.fields if f.name=='target'), tag)
    else:            print('none  ', m.action_id, sorted(names), [r.name for r in m.refs], tag)
"
```

## Related

- [[Targeting Model]] — paths, refs, fan-out, the type-checker.
- [[SFX Authoring]] — the author-facing view of the same actions.
- [[Attune Rewrite Plan]] — the most recent action brought up to date.

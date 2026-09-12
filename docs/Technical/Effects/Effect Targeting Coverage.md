---
title: Effect Targeting Coverage
date: 2026-09-11
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

- **Target** — *what it acts on*. A path is offered when the action declares
  `target_kind` (`EffectForm.isScopedTargetField`). The field must be named
  `target`.
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

## Coverage today (53 actions)

> Numerals below are from the regeneration recipe at the end of this note
> (re-run 2026-09-11, when `increase_by_effect_die` landed): 53 actions total, 27
> with a path-capable target (`target` **and** `target_kind`), 6 declaring
> `refs`, 9 flat targets, 17 with no `target` field at all.

- **Target offers a path — 27.** All the trait actions, the location/travel
  ones, `transfer_razmerit`, `attune`, `create_relationship`,
  `entity_targeting_ban`, `set_traitset_limit`, `discover_life_path`,
  `draft_life_path`, `open_roll_table`, `next_step`, `add_dice`,
  `end_active_effect`.
- **Subject available — 20.** The trait actions plus `earn_razmerit`,
  `spend_razmerit`, `travel`, `set_location`, `set_traitset_limit`,
  `end_active_effect`, and the two *name* actions below (you can path who
  receives an asset; you just cannot path what it is called).
- **Own path builders (refs) — 6.** `add_trait_rating_dice` (trait + pool),
  `roll_pool` (pool), `resolve_pool` (pool), `attune` (universe + projection),
  `copy_trait` and `move_trait` (the trait instance). The last two take the
  recipient from their `entity`/subject field, so the thing being handed over is
  a path while *who gets it* is the ordinary subject target.
- **Deletion is authorable.** `delete_trait` exposes `modify_trait`/`remove`
  (previously only the internal inverse of `gain`), so a steal can be authored as
  copy + delete when that reads better than `move_trait`.

## Gaps, and what each actually needs

**1. Strategy keywords — 2 actions left.** `reroll_die` (`the_hitch_die`) and
`convert_complication` (`botch_to_hitch`) name a *rule* for choosing a die, not a
thing, and nothing applies them (they are resolver-context passthroughs).
*`step_up_die` / `step_down_die` came off this list 2026-09-12:* they now take a
**targeting path to a die** (`path_element="die"` — the picker-kind/path-element
split this note asked for) and are applied for real (`effects_applier`'s
`_apply_step_die` writes the stepped rating back to the scene store). The
keyword `highest_trait_die` is still honoured, and now has a meaning.

**2. Die references — 2 actions.** `double_die`, `remove_die` name a die in the
pool. The vocabulary now exists — `pool → dice` (with each die carrying its
provenance) and `path_element` — so these are a declaration plus an applier each,
not a design question. **Needs the same treatment `step_up_die` got.**

**3. Trait-instance references — 1 action.** `split_die` ("Source Trait",
default `{source_trait}`) is genuinely a thing that could be pathed — the catalog
has a `traitsetting` element. The blocker was that **`target_kind` served two
purposes** (the picker kind *and* the path's destination element); that is now
split (`path_element`), so this is a declaration plus an applier.

**4. Names, not targets — 2 actions.** `create_asset` ("Asset Name"),
`create_projection` ("Disguise Name"). Correctly flat: these are labels, not
references. No change wanted.

**5. No target at all — 17 actions.** Mostly correct (dice limits, steps,
outcomes, muster). Five of them (`add_trait_rating_dice`, `roll_pool`,
`resolve_pool`, `copy_trait`, `move_trait`) resolve their real inputs through
`refs` already, so they are path-capable in the way that matters.

## Regenerating this

```bash
docker run --rm -v <worktree>/src/api/src:/app/src -w /app transversal2-api:latest python -c "
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY as R
for m in R:
    names = {f.name for f in m.fields}
    has = 'target' in names
    kind = m.target_kind or ''
    if has and kind: print('path  ', m.action_id, kind)
    elif has:        print('FLAT  ', m.action_id, next(f.label for f in m.fields if f.name=='target'))
    else:            print('none  ', m.action_id, sorted(names), [r.name for r in m.refs])
"
```

## Related

- [[Targeting Model]] — paths, refs, fan-out, the type-checker.
- [[SFX Authoring]] — the author-facing view of the same actions.
- [[Attune Rewrite Plan]] — the most recent action brought up to date.

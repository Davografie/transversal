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
for. It is inert on an effect that also carries a `target_spec` or `refs`
(`_apply_armed` checks those first), and the card text stays silent about a scope
the applier ignores.

## Coverage today (51 actions)

- **Target offers a path — 25.** All the trait actions, the location/travel
  ones, `transfer_razmerit`, `attune`, `create_relationship`,
  `entity_targeting_ban`, `set_traitset_limit`, `discover_life_path`,
  `draft_life_path`, `open_roll_table`, `next_step`, `add_dice`,
  `end_active_effect`.
- **Subject available — 19.** The trait actions plus `earn_razmerit`,
  `spend_razmerit`, `travel`, `set_location`, `set_traitset_limit`,
  `end_active_effect`, and the two *name* actions below (you can path who
  receives an asset; you just cannot path what it is called).
- **Own path builders (refs) — 6.** `add_trait_rating_dice` (trait + pool),
  `roll_pool` (pool), `resolve_pool` (pool), `attune` (universe + projection),
  `copy_trait` and `move_trait` (the trait instance). The last two take the
  recipient from their `entity`/subject field, so the thing being handed over is
  a path while *who gets it* is the ordinary subject target.

## Gaps, and what each actually needs

**1. Strategy keywords — 4 actions.** `step_up_die` / `step_down_die`
(`highest_trait_die`), `reroll_die` (`the_hitch_die`), `convert_complication`
(`botch_to_hitch`). Their target is not a *thing* but a *rule* for choosing one.
Turning these into paths is not a declaration — the vocabulary has no way to say
"the highest die" or "the die that hitched". **Needs vocabulary, then design.**

**2. Die references — 2 actions.** `double_die`, `remove_die` name a die in the
pool. A `pool` element exists but there is no *die* picker kind and no "dice in
the pool" collection outside a roll. **Needs vocabulary.**

**3. Trait-instance references — 1 action.** `split_die` ("Source Trait",
default `{source_trait}`) is genuinely a thing that could be pathed — the catalog
has a `traitsetting` element. It is not a one-liner because **`target_kind`
serves two purposes**: it names the picker kind *and* the path's destination
element. There is no `traitsetting` picker kind, so declaring one for the path
would leave the literal mode offering the wrong thing. **Needs the two concepts
separated** (`path_element` vs `picker_kind`).

**4. Names, not targets — 2 actions.** `create_asset` ("Asset Name"),
`create_projection` ("Disguise Name"). Correctly flat: these are labels, not
references. No change wanted.

**5. No target at all — 15 actions,** mostly correct (dice limits, steps,
outcomes, muster). Three of them resolve their real inputs through `refs`
already, so they are path-capable in the way that matters.

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

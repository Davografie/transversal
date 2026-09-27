---
name: lifepath
description: Create Transversal2 life paths, roll tables, and roll table entries — plus the faction and universe wiring they need. Use when adding new life-path content.
---

# LifePath Skill

## Purpose

Author a life path: a `LifePath`, its `RollTable`s, and their
`RollTableEntry`s (with effects). This skill only covers writing content — not
how the app runs a term or how to test it.

A life path is an **entry point into a graph of linked roll tables**. Each table
selects an entry; each entry runs **effects**; `next_step` effects move to the
next table.

## Files you touch

- `src/api/src/transversal/domain/__init__.py` — the models below.
- The authoring surface is the **API**, not a seed module: `save_life_path` and
  `save_roll_table` (MCP tools and the equivalent GraphQL mutations). Both are
  full saves and idempotent — re-running a save with the same ids updates in
  place. `db/seed.py` was **removed 2026-09-27**; it was never the authoring
  path and its content had been superseded twice over.

## Models to write

### LifePath
```python
LifePath(
    id="lp-{slug}",
    name="…",
    universe="three_realms",       # must match RollTable/Trait/TraitSet universe
    description="…",
    entry_table_id="rt-{first}",   # id of the first RollTable
    discovery=None,                # DiscoveryBlock | None (None = always visible)
)
```

### RollTable
```python
RollTable(
    id="rt-{slug}",
    name="…",
    universe="three_realms",
    life_path="lp-{slug}",         # owning path
    scheme=RollTableScheme.INDEX,  # RANGE | WEIGHT | TIER | INDEX
    die=DieType.D6,                # die size for RANGE/INDEX
    check=None,                    # RollTableCheck for TIER tables
    entries=[…],
)
```

Schemes and their entry keys:

| scheme | entry key |
|--------|-----------|
| `RANGE` | `min_value` / `max_value` |
| `WEIGHT` | `weight` |
| `TIER` | `tier` (`FAIL`..`PERFECT`), plus a `RollTableCheck` |
| `INDEX` | position in the `entries` list |

### RollTableEntry
```python
RollTableEntry(
    label="…",
    description="",
    min_value=None, max_value=None,   # RANGE
    weight=None,                      # WEIGHT
    tier=None,                        # TIER
    conditions=[],                    # optional gates (rare)
    effects=[…],                      # see effect reference
)
```

### RollTableCheck (TIER only)
```python
RollTableCheck(
    trait_ids=["trait-…"],           # may include trait-rel-rank / trait-rel-tenure
    difficulty=DieType.D6,
    free_choice=False,
)
```

## Effect reference

Every entry effect is an `Effect(timing, type, action, target, result, context)`.
For life-path content, timing is almost always `EffectTiming.IMMEDIATE`.

### Flow — `type: "life_path"`

| action | target | what it does |
|--------|--------|--------------|
| `next_step` | next table id | move the term to that table |
| `muster` | — | respectful muster out (end) |
| `force_muster` | — | dishonorable muster out (end) |
| `enroll` | — | record enrollment + create the faction membership edge |
| `draft` | path id | jump to another path's entry table |
| `discover` | path id | reveal a hidden path |

Every non-terminal entry ends with a `next_step`. Terminal entries use
`muster` / `force_muster` (or `next_step("")` to end).

### Traits — `type: "modify_trait"`

| action | `result` | behavior |
|--------|----------|----------|
| `gain` | die | add trait at that die (no-op if present) |
| `gain_or_step_up` | die | add at that die, else step up (cap d12) |
| `step_up` | — | step up smallest die |
| `step_down` | — | step down smallest die (floor d4) |
| `set` | die | set dice to that die |
| `gain_complication` | die | add negative trait at that die (not idempotent) |
| `gain_or_step_up_complication` | die | add negative at that die, else step up |

`target` = trait id.

**Relationship scope:** set `context={"relationship": faction_id}` only for
**rank** (`trait-rel-rank`) and **tenure** (`trait-rel-tenure`) — these attach
to the `character↔faction` membership edge. Learn skills and personal
complications omit it (entity-level).

### Razmerit / relationships

- `transfer_razmerit` + `earn|spend|transfer` — `result` = amount, `target` = recipient (transfer only).
- `relationship` + `create` — `target` = entity id, `result` = relationship type.

## Faction & universe wiring

A path is offered by a faction entity:

```python
Entity(
    id="fac-{slug}", type=EntityType.FACTION,
    current_universe="three_realms",
    active_universes=["three_realms"],
    suitable_life_path_ids=["lp-{slug}"],   # the path(s) this faction offers
)
```

Keep `LifePath.universe`, `RollTable.universe`, and the traits' `universes`
consistent. Referenced `trait` ids must already exist in the `traits`
collection for that universe (including `trait-rel-rank` and `trait-rel-tenure`
when using rank/tenure).

## Authoring pattern

Build the effects with small helpers, then save each table and the path through
the API:

```python
def eff(type_, action, target="", result=None, context=None):
    return Effect(timing=EffectTiming.IMMEDIATE, type=type_, action=action,
                  target=target, result=result, context=context or {})

def flow(action, target="", context=None):
    return eff("life_path", action, target, context=context)

def next_step(target=""):
    return flow("next_step", target)

def trait(action, trait_id, die=None, relationship=None):
    ctx = {"relationship": relationship} if relationship else {}
    return eff("modify_trait", action, trait_id, result=die, context=ctx)
```

Then save them: `save_roll_table(table)` for each table, `save_life_path(path)`
last (its `entry_table_id` must already exist), and `update_entity` on the
offering faction to add the path to `suitable_life_path_ids`.

### Full example — drifter with learn → muster

```python
faction = Entity(id="fac-rogue", type=EntityType.FACTION,
    current_universe="three_realms", active_universes=["three_realms"],
    suitable_life_path_ids=["lp-drifter"])

path = LifePath(id="lp-drifter", name="Rogue Cultivator",
    universe="three_realms", description="Walk the land alone.",
    entry_table_id="rt-drifter-learn")

learn = RollTable(id="rt-drifter-learn", name="Learn", universe="three_realms",
    life_path="lp-drifter", scheme=RollTableScheme.INDEX,
    entries=[
        RollTableEntry(label="Qi Gong", effects=[
            trait("gain_or_step_up", "trait-movement", "d4"),   # entity-level
            next_step("rt-drifter-muster"),
        ]),
        RollTableEntry(label="Sword Intent", effects=[
            trait("gain_or_step_up", "trait-martial", "d4"),
            next_step("rt-drifter-muster"),
        ]),
    ])

muster = RollTable(id="rt-drifter-muster", name="Muster Out",
    universe="three_realms", life_path="lp-drifter",
    scheme=RollTableScheme.RANGE, die=DieType.D6,
    entries=[
        RollTableEntry(label="Serve another term", min_value=1, max_value=2, effects=[
            trait("gain_or_step_up", "trait-rel-tenure", "d4", relationship="fac-rogue"),
            next_step("rt-drifter-learn"),
        ]),
        RollTableEntry(label="Muster out (respectfully)", min_value=3, max_value=5,
            effects=[flow("muster")]),
        RollTableEntry(label="Muster out (dishonorably)", min_value=6, max_value=6,
            effects=[flow("force_muster")]),
    ])
```

## Content rules

- `entry_table_id` must point at an existing `RollTable`.
- Every non-terminal entry must end with a `next_step`; otherwise the term stalls.
- Referenced `trait` ids must exist in the right universe.
- Only `trait-rel-*` gets `context.relationship`.
- Prefer `gain_or_step_up_complication` over `gain_complication` for repeatable mishaps.
- `TIER` tables need a `RollTableCheck`.
- Saves are idempotent: a re-save with the same ids updates in place, so there is no separate create/update path to guard.

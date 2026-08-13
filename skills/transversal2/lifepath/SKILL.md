---
name: lifepath
description: Design, wire, and debug Transversal2 life paths — factions, universes, roll-table graphs, entries, conditions, effects, and the term executor. Use when creating or editing life paths, roll tables, factions, or debugging term flow.
---

# LifePath Skill

## Purpose

Design, wire, and debug a **life path** in Transversal — a faction-offered
"walk of life" a character takes terms in. In the current model a life path is
an **entry point into a graph of linked roll tables**, not a hard-coded
qualify/learn/survive/advance loop. Entries carry **effects**; a special
`life_path` effect family moves the term through the graph.

Use this skill when the task is:

- designing a new life path for an existing or new universe,
- creating the faction that offers it,
- authoring roll tables, entries, conditions, and effects,
- wiring `next_step` flow, muster-out, enrollment, or rank/tenure,
- debugging why an effect does not apply or a term stalls.

## Mental model

```
LifePath (life_paths)  ──entry_table_id──▶  RollTable (roll_tables)
                                               ├─ scheme / die / check
                                               └─ entries[]
                                                    ├─ conditions[]
                                                    └─ effects[]
```

- A `LifePath` is just metadata + the id of its **first** `RollTable`.
- A `RollTable` selects one `RollTableEntry` (by roll, weight, tier, or index).
- An entry's `effects` either **mutate state** (`modify_trait`,
  `transfer_razmerit`, `relationship`, …) or **advance the flow**
  (`life_path` type: `next_step`, `muster`, `force_muster`, `enroll`, `draft`,
  `discover`).
- A term is run by `startTerm` then repeated `resolveStep` calls until
  `done` (flow ended) or `mustered`.
- A **faction** (`EntityType.FACTION`) offers one or more paths via
  `suitable_life_path_ids`. Rank and tenure are **relationship traits** stored
  on the `character ↔ faction` `membership` edge — not on the character.

## Key Files

| File | Purpose |
|------|---------|
| `src/api/src/transversal/domain/__init__.py` | `LifePath`, `RollTable`, `RollTableEntry`, `RollTableCheck`, `Condition`, `Effect`, `EffectTiming`, `RollTableScheme`, `OutcomeTier`, `PendingTerm`, `Enrollment`, `DiscoveryBlock`, `Entity` (faction fields) |
| `src/api/src/transversal/db/repository.py` | `get/create/list/update/delete_lifepath`, `get/create/update/delete_roll_table`, `list_roll_tables`, relationship + traitsetting CRUD |
| `src/api/src/transversal/db/seed.py` | `seed_life_paths(repo)` — the reference authoring pattern (builders + idempotent upserts) |
| `src/api/src/transversal/services/lifepath_executor.py` | `start_term`, `resolve_step` + flow processing (`_process_flow`, `_next_step`) |
| `src/api/src/transversal/services/effects_applier.py` | Registry-based effect application (`apply_effects`, `_MUTATION_HANDLERS`) |
| `src/api/src/transversal/services/effects_registry.py` | `EFFECT_ACTION_REGISTRY` — editor metadata for every `EffectActionMeta` |
| `src/api/src/transversal/services/lifepath_discovery.py` | `check_discovery` — optional discovery gating |
| `src/api/src/transversal/api/graphql/types.py` | Strawberry types (`LifePath`, `RollTable`, `Effect`, `PendingTerm`, `LifePathStepResult`, …) |
| `src/api/src/transversal/api/graphql/schema.py` | Queries/mutations: `lifePaths`, `rollTables`, `rollTable`, `startTerm`, `resolveStep`, `saveLifePath`, `saveRollTable`, `traitsByUniverse`, `effectActions` |
| `src/frontend/src/composables/useLifePaths.js` | Frontend singleton state + queries/mutations for life paths |
| `src/frontend/src/composables/useRollTables.js` | Frontend singleton state + queries/mutations for roll tables |
| `src/frontend/src/components/gm/GmLifePathsPanel.vue`, `GmLifePathDetailPanel.vue`, `GmLifePathEditPanel.vue`, `GmRollTableDetailPanel.vue`, `GmRollTableEditPanel.vue`, `GmRollTableEntryEditPanel.vue` | GM authoring panels (thin renderers over the composables) |
| `src/frontend/src/components/LifePathWizard.vue` | Player-facing term runner (`startTerm` / `resolveStep`) |

## Data model quick reference

### LifePath
```python
LifePath(
    id="lp-{slug}",
    name="…",
    universe="three_realms",          # must match RollTable/Trait/TraitSet universe
    description="…",
    entry_table_id="rt-…",            # first RollTable in the flow
    discovery=None,                   # DiscoveryBlock | None (None = always visible)
)
```
No `qualification` / `curriculum` / `survival` / `events` / `advancement` /
`muster_out` fields — those are gone. Term structure is roll tables.

### RollTable
```python
RollTable(
    id="rt-{slug}",
    name="…",
    universe="three_realms",
    life_path="lp-{slug}",            # owning path; None = shared/general table
    scheme=RollTableScheme.INDEX,     # RANGE | WEIGHT | TIER | INDEX
    die=DieType.D6,                   # die size for RANGE/INDEX rolls
    check=None,                       # RollTableCheck when scheme == TIER
    entries=[…],
)
```

### RollTableEntry
```python
RollTableEntry(
    label="…",
    description="",
    min_value=None, max_value=None,   # RANGE
    weight=None,                      # WEIGHT
    tier=None,                        # TIER (OutcomeTier)
    conditions=[…],                   # optional gates
    effects=[…],                      # mutation + flow effects
)
```

### RollTableCheck (TIER tables only)
```python
RollTableCheck(
    trait_ids=["trait-…"],            # pool traits; may include trait-rel-rank/tenure
    difficulty=DieType.D6,
    free_choice=False,
)
```

### Effect
```python
Effect(
    timing=EffectTiming.IMMEDIATE,    # IMMEDIATE | END_OF_BEAT | END_OF_SCENE | END_OF_SESSION | AFTER_BEATS | ON_CONDITION
    type="modify_trait",              # see effect vocabulary
    action="gain_or_step_up",
    target="trait-…",                 # trait / entity / path / table id (action-dependent)
    result="d4",                      # die rating or amount (action-dependent)
    target_scope=None,                # runtime-choice narrowing (deferred)
    context={},                       # relationship / return_to / description
)
```

### PendingTerm (checkpoint)
```python
PendingTerm(
    faction_id="fac-…",
    path_id="lp-…",
    current_table_id="rt-…",
    continuation=[],                  # return-address stack for next_step{return_to}
)
```

### Enrollment (on the character `Entity`)
```python
Enrollment(faction_id="fac-…", path_id="lp-…", mustered=False, mishap_muster=False)
```

### Faction fields on `Entity`
```python
Entity(
    id="fac-…", type=EntityType.FACTION,
    current_universe="three_realms",
    active_universes=["three_realms"],
    suitable_life_path_ids=["lp-…"],  # the paths this faction offers
)
```
On a **character**: `life_paths` holds `Enrollment`s; `pending_term` holds the
mid-term checkpoint; `discovered_life_paths` holds discovery-gated paths.

### DiscoveryBlock (optional gating, unchanged)
Any one condition met → discovered:
```python
DiscoveryBlock(
    at_location=["loc-…"],
    knows_entity=["gmc-…"],
    possesses_trait=["trait-…"],
    has_trait_rating={"trait-…": DieType.D8},
    has_relationship=["entity-…"],
)
```

## Roll table schemes

| Scheme | Entry key | Roll needed | Notes |
|--------|-----------|-------------|-------|
| `RANGE` | `min_value`/`max_value` | 1..`die.max` | classic d6 table |
| `WEIGHT` | `weight` | any (normalized 1..total) | proportional pick |
| `TIER` | `tier` (`FAIL`..`PERFECT`) | dice-pool `check` | add a `check`; the resolver rolls it server-side |
| `INDEX` | position in list | 1..`len(entries)` or manual `index` | "roll or choose" pick list |

Manual selection (`resolveStep(index: n)`, 1-based) always wins over a roll.

## Effect vocabulary

### Flow effects — `type: "life_path"` (always `IMMEDIATE`)

| action | target | behavior |
|--------|--------|----------|
| `next_step` | roll table id | advance `current_table_id` to target. `context.return_to` pushes a return address; `""`/`{continue}` pops it or ends the term when empty |
| `muster` | — | respectful muster out (`mustered`, `mishap_muster=False`), clears `pending_term` |
| `force_muster` | — | dishonorable muster out (`mishap_muster=True`) |
| `enroll` | — | idempotently add `Enrollment` + create `character↔faction` `membership` edge |
| `draft` | path id | jump to another path's `entry_table_id` |
| `discover` | path id | add to `discovered_life_paths` |

`next_step` with `context={"return_to": "rt-…"}` supports subroutine-style loops:
call `next_step(target="rt-sub", context={"return_to": "rt-caller"})`, and inside
the sub end with `next_step(target="")` to pop the return address.

### Trait effects — `type: "modify_trait"`

| action | idempotent? | behavior |
|--------|-------------|----------|
| `gain` | yes (no-op if present) | create trait at `result` die |
| `gain_or_step_up` | yes | create at `result` die, else step up (cap d12) |
| `step_up` / `step_down` | — | step smallest die / floor d4 |
| `set` | — | set dice to `result` die |
| `gain_complication` | **no** (always insert) | create negative trait at `result` die |
| `gain_or_step_up_complication` | yes | create negative at `result` die, else step up |

`target` = trait id; `result` = `"d4"`..`"d12"`.

**Relationship scope:** `context.relationship` = faction id attaches the trait to
the `character↔faction` `membership` edge. **Only rank and tenure**
(`trait-rel-rank`, `trait-rel-tenure`) should carry `context.relationship`.
Learn-skill gains and personal complications must **omit** it (entity-level).

### Other mutation effects

- `transfer_razmerit` / `earn|spend|transfer` — `result` = amount, `target` = recipient (transfer).
- `relationship` / `create` — `target` = entity id, `result` = relationship type, `context.description`.
- `create_entity` / `create_asset` — `target`/`context.name`, `context.location`.
- `spoof_location` / `enable` — resolver passthrough.
- `modify_roll` / `modify_outcome` — resolver-context passthrough (dice-pool tweaks), not term state.

New actions must be registered in **both** `effects_applier.py`
(`_MUTATION_HANDLERS` + `_register_core_handlers`) and `effects_registry.py`
(`EFFECT_ACTION_REGISTRY`).

## Running a term

1. `startTerm(entityId, factionId, pathId)` → sets the entity's `pending_term` to
   the path's `entry_table_id`.
2. `resolveStep(entityId, …)`:
   - selects an entry (manual `index`, or `roll`, or auto-roll of the `check`),
   - applies `IMMEDIATE` mutation effects in memory, schedules non-immediate ones,
   - processes `life_path` flow effects,
   - persists the entity + new/updated trait settings + broadcasts SSE,
   - returns `LifePathStepResult { done, applied, scheduled, pendingChoices,
     mustered, mishapMuster, pendingTerm, tableId, entryLabel, error }`.
3. Repeat while `done` is false; the frontend reads `pendingTerm.currentTableId`
   to load the next table.

- A `TIER` table **must** have a `check`; with no explicit tier/roll/index the
  resolver assembles the pool (entity trait settings + `membership`-edge
  relationship traits matching `check.trait_ids`; untrained → d4) and rolls vs
  `check.difficulty`.
- `done` becomes true when the flow ends (`next_step("")` with empty
  continuation) or on `muster` / `force_muster`.

## Faction ↔ life path wiring

1. Faction `Entity(type=FACTION)` sets `suitable_life_path_ids=[…]`.
2. `LifePath.factionIds` (GraphQL) is resolved from faction entities'
   `suitable_life_path_ids` — a path can be offered by multiple factions.
3. `enroll` records `Enrollment(faction_id, path_id)` and creates the
   `membership` edge; rank/tenure relationship traits attach there.
4. A path with **no** offering faction is unusable from the wizard (it defaults
   to the first `factionIds` entry; multi-faction picker is deferred).

## Universe scoping

`LifePath.universe`, `RollTable.universe`, `Trait.universes`, and
`TraitSet.universes` must be consistent. `traitsByUniverse(universe)` is the
authoritative source for which trait ids exist in a universe. A path and its
tables live in one universe; a faction's `active_universes` lists where it is
active.

## Authoring recipe

1. Ensure the universe exists.
2. Ensure the traits exist (in the right `traitset_id` + `universes`):
   - any learn/complication traits (entity-level), and
   - `trait-rel-rank` + `trait-rel-tenure` (relationship traits).
3. Create the faction `Entity` with `suitable_life_path_ids`.
4. Create the `LifePath` with `entry_table_id` pointing at the first table.
5. Create each `RollTable` (scheme / die / check / entries).
6. On every non-terminal entry, add a `life_path/next_step` effect to advance;
   use `muster` / `force_muster` to end; `enroll` once at the entry gate.
7. Seed idempotently (guard every upsert with an existence check).

## Seed pattern (reference)

`seed_life_paths(repo)` uses small builders — copy this shape:

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

Minimal working example — a drifter with learn → muster:

```python
faction = Entity(id="fac-rogue", type=EntityType.FACTION,
    current_universe="three_realms", active_universes=["three_realms"],
    suitable_life_path_ids=["lp-drifter"])

paths = [LifePath(id="lp-drifter", name="Rogue Cultivator",
    universe="three_realms", description="…", entry_table_id="rt-drifter-learn")]

learn = RollTable(id="rt-drifter-learn", name="Learn", universe="three_realms",
    life_path="lp-drifter", scheme=RollTableScheme.INDEX,
    entries=[
        RollTableEntry(label="Qi Gong", effects=[
            trait("gain_or_step_up", "trait-movement", "d4"),   # entity-level
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

## GraphQL surface

Queries:
- `lifePaths(universe)` → `[LifePath]` (each has resolved `factionIds`).
- `rollTables(lifePathId)` → `[RollTable]` (lightweight).
- `rollTable(id)` → full `RollTable` (entries/conditions/effects).
- `traitsByUniverse(universe)` → `[TraitRef]`.
- `effectActions` → editor metadata.

Mutations:
- `startTerm(entityId, factionId, pathId)` → `PendingTerm`.
- `resolveStep(entityId, roll?, tier?, index?)` → `LifePathStepResult`.
- `saveLifePath(id, name, universe, description, entryTableId?, discovery?)` → `{ ok, id }`.
- `deleteLifePath(id)` → `{ ok }`.
- `saveRollTable(input: RollTableInput!)` → `RollTable`.
- `deleteRollTable(id)` → `Boolean`.

Trait registry authoring is separate (`createTrait`, `createTraitset`,
`createSfx`, `deleteTrait`, …) — use those to ensure referenced trait ids exist.

## Frontend surface

- GM authoring: `GmLifePathsPanel` → `GmLifePathDetailPanel` →
  `GmRollTableDetailPanel` → (`GmRollTableEditPanel` | `GmRollTableEntryEditPanel`).
  These are thin renderers over `useLifePaths` / `useRollTables` composables
  (singleton state, queries, and mutations live there — see
  `docs/Technical/GM Panel Development.md`).
- Player-facing: `LifePathWizard.vue` drives `startTerm` / `resolveStep` and
  renders the current table with clickable rows + roll/check buttons.

## Common pitfalls

- **Relationship scope** — only `trait-rel-*` gets `context.relationship`.
  Learn skills and complications are entity-level.
- **`gain_complication` is not idempotent** — re-gaining the same complication
  collides on the `_key`. Use `gain_or_step_up_complication` for repeatable mishaps.
- **Empty `traitset_id`** — resolve it from the trait registry (`repo.get_trait`);
  the applier falls back to `ts-complications` for negatives.
- **`TIER` without a `check`** — the table can't auto-resolve; add a
  `RollTableCheck`.
- **Non-existent trait ids** — every `modify_trait` target must exist in the
  `traits` collection (and be in the right universe), or the gain silently no-ops.
- **`entry_table_id` must point to an existing table** — `start_term` raises if it is empty; `resolve_step` errors if the current table is missing.
- **`LifePath.factionIds` empty** — no faction lists the path in
  `suitable_life_path_ids`; the wizard shows it disabled.

## Testing

```bash
docker compose exec api python -m pytest tests/test_graphql_lifepath.py \
  tests/test_lifepath_executor.py tests/test_roll_table.py \
  tests/test_seed_life_paths.py tests/test_effects_applier.py -v
```

Relevant suites: `test_lifepath_executor.py` (start/resolve/flow), `test_roll_table.py`
(resolve semantics), `test_effects_applier.py` (effect handlers),
`test_graphql_lifepath.py` (GraphQL wiring), `test_seed_life_paths.py` (seed),
`test_lifepath_discovery.py` (gating).

## Migrations

- `python -m transversal.migrate_life_paths` — normalize legacy `LifePath` docs
  (drops `qualification`/`curriculum`/… keys).
- `python -m transversal.migrate_lifepath_effects` — strip wrong
  `context.relationship` from non-`trait-rel-*` `modify_trait` effects and
  promote `gain_complication` → `gain_or_step_up_complication` (idempotent).

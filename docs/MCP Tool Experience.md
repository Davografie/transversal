---
title: MCP Tool Experience
tags:
  - mcp
  - authoring
  - transversal
  - worklog
aliases:
  - MCP friction log
  - Authoring tool log
status: living
---

# MCP Tool Experience

> [!note] Purpose
> Running log of what it's like to author Transversal content through the MCP
> tool layer ([[API Contract]]). Record what's missing, what's awkward, and what
> breaks — so the tools can be improved. Updated as I work.

## Session context

Authoring a small original universe ("The Emberline") end-to-end through the 32
MCP tools only (no direct DB writes). Scope: 1 universe, 2 factions, 12
locations, 32 GMCs, 4 assets, 3 life paths. All via `draft_entity` →
`draft_relationship` → `apply_plan` → `set_rank_role` / `save_life_path`.

## Findings

### Docs / semantics

- **`dry_run` docstring is inverted.** `src/api/src/transversal/mcp/server.py`
  module docstring says "With `dry_run=false` the tool returns the ordered
  GraphQL operations … without touching the database." The code does the
  opposite: `dry_run=true` returns the plan without executing; `dry_run=false`
  executes. The code is correct, the docstring is wrong. (One-word fix.)

### Creation / staging

- **No way to create an entity already-unpublished.** `CreateEntityInput` has no
  `unpublished` field, so `create_universe`/`create_location`/`create_gmc` etc.
  land visible to players immediately. To stage, you must either (a) use the
  plan workflow (`draft_entity` → `apply_plan`, which sets `unpublished=true`),
  or (b) create then immediately `unpublish_entity`. A `create-as-draft` flag
  would collapse this to one call.
- **Staging tools have no `dry_run`.** `draft_entity`, `draft_relationship`,
  `apply_plan`, `discard_plan` write immediately, unlike the `create_*` tools
  which default to `dry_run=true`. Inconsistent; no preview of a draft.
- **`draft_relationship` has no upsert/existence guard** (unlike
  `draft_entity`, which deletes-then-recreates by key). Re-running a draft
  silently duplicates edges.

### Conspyramid

- **Conspyramid authoring is a two-phase dance.** The plan workflow carries
  entities + `membership`/`commands` edges, but *not* rank/role. Those must be
  layered after `apply_plan` via `set_rank_role`, which needs the real ids from
  `apply_plan`'s `created` mapping. There is no single "author a conspyramid
  node with rank+role" call.
- **`set_rank_role` is stringly-typed on the role trait.** It hardcodes
  `trait-role-cd1b`, which is *referenced* (migrate_conspyramid.py, server.py,
  repository.py canvas read) but never *created* in any source I could find.
  `add_relationship_trait` doesn't validate trait existence, so it works, but
  the role trait id is an implicit contract, not a registered fact.
- **Two "relations" traitset ids in play.** `seed.py` creates `ts-relations`
  (display name "Relations"), but the live DB uses `ts-relations-b114`
  (display name "relations") — created outside current seed code.
  `set_rank_role` resolves by the *exact* name string `"relations"`, so a
  rename or a second "Relations" entry would silently break rank/role. Fragile
  coupling; should key on the traitset id.

### Read / discovery gaps

- **No MCP read tools for the registry**: no `list_traits`, `list_traitsets`,
  `list_roll_tables`, `list_life_paths`, or `get_roll_table`/`get_life_path`.
  To discover available trait ids or verify roll tables/life paths I had to
  reach past MCP to raw GraphQL (`traitsets`, `rollTables`, `lifePaths`
  queries). These belong in the toolset as first-class "eyes".
- **No delete/cleanup tools.** There is no `delete_entity`,
  `delete_relationship`, or `delete_roll_table` in MCP (GraphQL has
  `delete_roll_table`, but entities/edges have no exposed delete). Makes
  iterative authoring risky — no easy undo of a bad apply.

### Life paths / roll tables

- **Effects are hand-written JSON.** `save_roll_table` passes a full
  `RollTableInput` through; entry effects must be authored as raw `EffectInput`
  JSON. There are no helper conveniences (e.g. `next_step("rt-x")`,
  `gain_trait("trait-x", "d4")`). The [[Life Path Flow and Shared Roll Tables]]
  skill shows the Python `Effect` model; the MCP surface exposes none of that
  sugar.
- **Enum casing is uppercase member names** (empirically confirmed via
  `rollTables` query: `scheme` returns `"TIER"`/`"RANGE"`, `die` returns `"D6"`).
  Not documented on the tool schemas; easy to guess lowercase and get a schema
  error.
- **Universe-scoped trait grants are a rabbit hole.** Life-path `modify_trait`
  effects need trait ids that exist *for the target universe*. A new universe
  (e.g. "emberline") has no traits in the registry, so trait-granting life
  paths require first creating universe traits + a traitset. For this pass I
  kept life paths structural (flow-only) and deferred trait grants.

## Build findings — "The Emberline" universe (2026-08-23)

- **`API_URL` default breaks in-container use.** The server defaults to
  `http://localhost:8085` (the docker-compose *host* mapping), which is
  unreachable from *inside* the `api` container (the app listens on `8080`
  there). Every write failed with `Connection refused` until I set
  `TRANSVERSAL_API_URL=http://localhost:8080`. The default is only correct when
  the MCP client runs on the docker host — an easy trap.
- **`save_roll_table` expects GraphQL camelCase, not snake_case.** It's a raw
  passthrough to `RollTableInput`; I had to send `lifePath`, `minValue`,
  `maxValue` (not `life_path` / `min_value` / `max_value`). `save_life_path`
  *does* map its args (`entry_table_id` → `entryTableId`), so the two "save"
  tools are inconsistent about field casing, and neither schema states which
  dialect it wants.
- **Universe slug is derived from the name, ignoring the `universe` field.**
  `draft_entity(type="universe", universe="emberline", name="The Emberline")`
  produced `currentUniverse: "the_emberline"` (name-slugified), disconnecting
  the universe from its children (all `emberline`). There is no way to set the
  universe slug through the authoring path — you must rename to match.
- **No `update_entity` tool.** To fix the slug I had to call the API's
  `updateEntity` mutation directly (the same endpoint `reveal_entity` /
  `unpublish_entity` use internally). A general `update_entity` / `rename_entity`
  tool would have made this an MCP-only fix.
- **`type` casing is inconsistent across tools.** `draft_entity` wants lowercase
  (`"gmc"`), while `query_entities` / `create_*` want uppercase (`"GMC"`). Easy
  to get backwards; caused a false "0 results" on the first verify.

### What worked cleanly

Once `API_URL` was set, the whole build ran in one pass: 51 entities + 41 edges
(super/membership/commands) drafted → applied (all `unpublished=true`), 16/16
`set_rank_role` on membership edges, 3 life paths + 6 roll tables. `faction_canvas`
reads rank (`d4`…`d12`) and role back correctly; `location_tree` shows the
universe → region → city hierarchy. `apply_plan`'s `created` mapping makes the
`draft_ref` → real-id hop for post-apply tools straightforward.

## Resolved (2026-08-23)

Added 8 MCP tools: `update_entity`, `set_faction_life_paths`, `update_traitset`,
`delete_entity`, `list_traitsets`, `list_traits`, `list_life_paths`,
`list_roll_tables`. Plus `suitable_life_path_ids` on `UpdateEntityInput` (the
missing write-path for faction → life path). This closes the "no update", "no
life-path wiring", and "no registry read" gaps above.

Still open: zone/map-position authoring (no MCP tool; see the API-auto-register
question), and the frontend `GmTraitEditPanel` hardcodes universe options to
`earth`/`three_realms` (roll-table editor fetches them dynamically — inconsistent).

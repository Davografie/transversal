---
title: Performance and Resilience Plan
tags:
  - transversal
  - plan
  - performance
  - mobile
  - caching
  - technical
aliases:
  - Performance Plan
  - Caching Plan
status: planned
---

# Performance and Resilience Plan

Targets the mobile experience: client-side caching of entity/sheet data, draft persistence across standby-to-wake reloads, backend connection-churn + N+1 fixes, and multi-worker FastAPI.

## Context / Findings

- The dataset is small (~159 entities) — ArangoDB on-disk I/O is **not** the bottleneck. A caching layer between the API and Arango is explicitly out of scope.
- The real backend cost is accidental per-request connection churn: `get_db()` in [[System Architecture]]'s Arango layer re-runs `ArangoClient()` + `has_database` + `has_collection` ×16 + `_ensure_indexes` on every `EntityRepository()` construction, and the GraphQL media resolvers construct a fresh repository per field per entity (N+1 at the connection level).
- The frontend re-fetches on every interaction: `openSettings()` resets its caches and re-fetches the owned-entity list; `fetchPeers()` pulls every entity on every location change / SSE event / panel open; [[Location Viewer]]'s `navigate` endpoint runs one AQL query per occupant/child/transversal for navdot images.
- Standby-to-wake reloads (OS-driven tab suspension) destroy in-progress edits because the dice pool and sheet edit buffers are never persisted.

## Phase A — Backend latency (connection churn + N+1)

### A1. Memoize the ArangoDB connection
- `src/api/src/transversal/db/arango.py`
- Cache `get_db()` on the resolved config; the create-db/collection/index bootstrap runs once per process.

### A2. Reuse the injected repo in media resolvers
- `src/api/src/transversal/api/graphql/types.py`
- `Entity.background_image`, `Entity.sheet_portrait`, `Entity.image`, `Projection.sheet_image` build a fresh `EntityRepository()`. Inject `info` and use `info.context["entity_manager"].repo`.

### A3. Batch navdot image lookups in `navigate`
- `src/api/src/transversal/api/rest/locations.py` + `db/repository.py`
- Add `get_navdot_images(entity_ids) -> dict[str, str]` (one AQL `IN @ids` query) and use it instead of per-entity `_resolve_navdot`.

### A4. Add `ids` filter to the `entities` query
- `src/api/src/transversal/api/graphql/schema.py`
- Lets the frontend fetch the owned-entity list in one round-trip instead of N+1.

## Phase B — Client-side entity/sheet cache

### B1. Module-level cache (no new deps)
- New `src/frontend/src/composables/entityCache.js` — reactive `Map<id, {data, fetchedAt}>` with TTL + `invalidate`.

### B2. Settings overlay
- `src/frontend/src/App.vue`
- Stop resetting `allCharactersCache` / `locationNamesLoaded` in `openSettings()`; use the single `entities(ids:)` query and the cache.

### B3. Character sheet cache (incl. foreign sheets)
- `src/frontend/src/components/CharacterSheet.vue`
- Render cached sheet instantly, stale-while-revalidate; invalidate via existing SSE events instead of unconditional refetch; apply mutation payloads locally.

### B4. Peers/occupants
- `src/frontend/src/App.vue`
- Cache peers keyed by location; drop eager `image(role:"sheet")` from the list query; invalidate on SSE `entity_moved` / `location_changed` / `entity_updated`.

## Phase C — Draft persistence & reload safety

### C1. Persisted-state helper
- New `src/frontend/src/composables/usePersistedState.js` (write-through to `localStorage`, rehydrate on setup).

### C2. Dice pool survives reload
- `src/frontend/src/components/DiceRoller.vue` — persist `pool` + `phase` (+ `keepCount`/`effectCount` in `App.vue`).

### C3. Sheet edits survive reload
- `src/frontend/src/components/CharacterSheet.vue` — persist `editingTraitId`, edit form fields, `activeSheetView`, `activeSetName`.

### C4. Flush drafts on suspend
- `src/frontend/src/App.vue` — `visibilitychange`/`pagehide` handlers flush in-memory drafts (idempotent given write-through).

> [!note] Service worker update reload
> `registerType` stays `'autoUpdate'` (intentionally not switched to `'prompt'`).
> Follow-up idea: instead of an instant auto-reload on deploy, show a notice
> ("the app will reload in a minute") and reload after a grace period — better
> than either instant reload or a blocking prompt. Tracked separately.

## Phase D — Multi-worker FastAPI

Multi-worker requires moving the two in-process singletons (SSE `EventBus`, `SessionManager`) to Redis, already present in `docker-compose.yaml` but currently unused.

- **D1** — new `src/api/src/transversal/db/redis.py` (`redis.asyncio` wrapper: `publish` + async `subscribe`).
- **D2** — `api/sse/bus.py`: `EventBus.publish` fans out to Redis channel `sse:{session_id}` (call sites unchanged).
- **D3** — `main.py`: per-worker background subscriber injects remote events into the local bus (tagged `source_id` to skip echoes).
- **D4** — `services/session_manager.py` → Redis (JSON doc per session + active-id index).
- **D5** — `src/api/Dockerfile`: replace `--reload` with `--workers ${UVICORN_WORKERS}`.
- **D6** — caveat: python-arango is synchronous inside `async def` routes; workers give process-level parallelism, threadpool/async driver is future work.

## Deferred / Out of scope

- Caching layer between API and ArangoDB — unnecessary at this scale; would add invalidation complexity without benefit.
- Switching `registerType` to `'prompt'` — keeping `autoUpdate`; the reload-notice idea replaces it (see Phase C note).

## Ordering

A → B → C → D, committing after each verified sub-step. Phase D is the largest/riskiest and is gated on the Redis migration.

## Verification

- Backend: `pytest` in the api container (84 tests) + targeted tests for batched navdot and `entities(ids:)`.
- Frontend: `docker exec tv2_frontend npm run build`; dev smoke for cached settings/sheet and edit persistence across a suspend/wake.
- Multi-worker: two clients on different workers still receive each other's SSE events; sessions visible across workers.

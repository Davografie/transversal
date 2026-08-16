---
title: Transversal Mechanics — Working Plan
tags:
  - transversal
  - mechanics
  - implementation
  - projections
  - wip
aliases:
  - Transversal Mechanics Plan
  - Transversal Spec
  - Projection Model
  - Effective Universes
status: superseded
---

# Transversal Mechanics — Working Plan

> [!note] Working document
> Single source of truth for the projection / transversal model. Supersedes all
> earlier locked decisions (see "Superseded"). Update as work lands so it
> survives compaction / session switching.

## Why this exists

Multiversal behaviour needs a clean home for "who am I, where am I, and in
what form." The model makes **projections** first-class containers (per-universe
body: name, image, location, morph traits) and collapses the ad-hoc
`transversal` / `home_universes` flags into the **attunement** mechanism. Most
of this is invisible data/logic work that unblocks richer behaviour
(consciousness travel, multiversal characters, per-universe images, domain
projection).

## The model

- **Entity (occupant: character/gmc/asset)** — identity + ego traits +
  relationships + `current_projection` (active body) + `attunements`.
- **Entity (non-occupant: location/universe/faction)** — identity + `current_universe`
  (which universe it is in / associated with). No projection.
- **Projection** — one per `(entity, origin-universe)`:
  - `id` = `"{entity_id}:{origin_universe}"` — **immutable key**.
  - `origin_universe` — the universe this body is native to (immutable).
  - `universe` — current universe (mutable).
  - `current_location` — where the body is now (mutable).
  - `name` (fallback → entity name), `background_image` (fallback → entity image).
  - `transversal_type` — provenance/lifecycle.
  - morph traits (`from_type="projection"`).
- **TraitSetting** — ego anchored to the entity; morph anchored to a projection.
  `from_type` gains a third value: `"entity" | "projection" | "relationship"`.
- **Attunement** — `{universe, scope (self|domain), until (None = permanent), source_sfx_id}`.
- **effective_universes** — `{current_projection.universe}` ∪ unexpired attunement universes.
- **Trait availability** — ego always; morph iff `origin_universe ∈ effective_universes`.

### `current_projection` vs `current_universe` vs `origin_universe`

- `Entity.current_projection` = the **active body** (which projection my
  consciousness inhabits). Authoritative for occupants; `universe` and
  `location` are *derived* from it, not stored on the entity.
- `Projection.universe` = **current** universe (where the body is now), mutable.
- `Projection.origin_universe` = **native** universe (what the body is), immutable;
  encoded in the projection key.
- `Entity.current_universe` = kept **only for non-occupants** (location/universe/
  faction) that don't project.

Trait determination is gated by `origin_universe` (identity), not the current
universe (position). Occupancy and return-travel use the current universe/location.

### Inapposite travel is an in-place update

Inapposite travel **never copies/deletes** a projection. It updates the active
projection's `universe` + `current_location` in place and sets
`transversal_type = INAPPOSITE`. The projection key stays `"{entity_id}:{origin_universe}"`,
so the body keeps its identity/history while its position changes.

### `transversal_type` on a projection — provenance + lifecycle

Kept as a **narrative/lifecycle record**, never a trait gate:

- **NATIVE** — permanent; "who I am." Never auto-deleted; the return target
  for consciousness travel.
- **CONSCIOUSNESS** — transient; cleaned up on return to the body or when the
  attunement ends.
- **INAPPOSITE** — a physically relocated body; `universe`/`current_location`
  mutate in place (key unchanged).

Trait availability never reads this field; it only reads `effective_universes`.
So no two-source drift.

### `transversal` / `home_universes` are gone

"Multiversal being" = entity with **permanent self-attunements** (`until=None`,
no `source_sfx_id`). "Accumulating universes" = adding permanent attunements
over time. The `transversal` boolean and `home_universes` list are removed and
migrated into permanent attunements.

### The Jian is a trait, not a transversal entity

Narrative anchor: the Jian is an **artifact trait** (statement + SFX),
switchable via take/gift — a mcguffin. The portal in Antonov's basement is a
*separate* machine/feature whose SFX *borrow* the Jian's power. Multiversal
characters/GMCs are "entity with permanent attunements + a projection per
universe," not a special flag.

## Locked decisions (this model)

1. Projections own `name`, `image` (fallback → entity), and `location`.
2. Entity gallery shows the entity image + every projection image (fallback badge).
3. `TraitSetting.from_type` is the single source of truth for ego/morph:
   ego → `entities/{id}`; morph → `projections/{id}`. `ego` becomes derived/UI-only.
4. `effective_universes = {current_projection.universe} ∪ unexpired attunements`.
   No location-chain derivation, no `transversal`/`home_universes` branch.
5. Morph trait active iff `origin_universe ∈ effective_universes`
   (plus a defensive registry check — see trait gating).
6. Attunement `until=None` = permanent (native/home); no separate `transversal` field.
7. `Projection.transversal_type` kept as provenance/lifecycle only.
8. Transversal **edges** carry a `transversal_type` (`consciousness | inapposite`).
9. Inapposite travel = **in-place update** (no copy/delete); key stays origin.
10. GM-drag across universes = inapposite travel (in-place relocate).
11. Domain projection = `attune` with `scope="domain"` over the projection's
    location subtree.
12. Assets are placeable occupants (unchanged).
13. Carried gear = the "assets" trait set (unchanged).
14. `Entity.zones` stays as the sub-location render-position record (unchanged).

## Superseded (from the earlier plan)

- ~~`Entity.transversal: bool`~~ → permanent attunements.
- ~~`Entity.home_universes: list[str]`~~ → permanent attunements (NATIVE projections).
- ~~`physical_universe` derived from location chain~~ → `Entity.current_projection.universe`.
- ~~`ego` boolean as the persisted discriminator~~ → `from_type` anchor.
- ~~inapposite travel = delete old projection + create new~~ → in-place update, key = origin.
- ~~`Entity.current_location` as the location source~~ → `Projection.current_location`.
- Carried forward unchanged: `attune` (was `spoof_location`), `project_domain`,
  zones kept, `default_ego` on `Trait`/`TraitSet`.

## Scope

### In scope (this change)

1. **Data model** — `Projection` gains `origin_universe`, `name`, `background_image`,
   `current_location`; `Entity` gains `current_projection` (occupant) and drops
   `transversal`/`home_universes`/`current_location`; `TraitSetting` gains
   `from_type="projection"`; `transversal` edges gain `transversal_type`.
2. **Logic** — `effective_universes` rewrite; origin-based trait gating; in-place
   inapposite travel; consciousness travel (spawn/cleanup); projection-driven
   occupancy.
3. **Effects** — `attune` (exists), `travel` (update), `project_domain` (exists).
4. **Migration** — existing data into the new shape (see Migration).
5. **Frontend** — projection management in GM panels; entity gallery shows all
   projection images; character sheet renders active projection name/image +
   its morph traits; GM-drag = inapposite.

### Deferred / out of scope

- Inner locations for occupants (characters/GMCs/assets as `super`-parents).
- `Entity.owned_by` removal → relationship trait (separate cleanup).
- Reconciling `Projection.background_image` with the `EntityImage` table
  (plain path + fallback for now).

## Backend change list

### `domain/__init__.py`

- `Projection`: add `origin_universe: str = ""`, `name: str = ""`,
  `background_image: Optional[str] = None`, `current_location: Optional[str] = None`.
  Keep `universe` (now "current") and `transversal_type`.
- `TraitSetting.from_type`: document `"projection"` (plain `str`, no enum change).
- `Entity`: add `current_projection: Optional[str] = None` (occupant); remove
  `transversal`, `home_universes`, `current_location`; keep `current_universe`
  for non-occupants (make it optional/empty for occupants).

### `db/repository.py`

- `effective_universes(entity)`: `{current_projection.universe}` ∪ unexpired
  attunements. Remove location-chain and `transversal` branches.
- `get_effective_traitsettings(entity_id, universes)`: ego (`from_type="entity"`)
  always; morph (`from_type="projection"`) iff its projection's `origin_universe`
  is in `universes` (plus defensive `trait.universes ∩ traitset.universes`).
- Projection CRUD: no key churn — `update_projection` mutates `universe`/
  `current_location` in place; `id`/`origin_universe` immutable.
- `navigate_from`: occupants = projections at this location joined to entities.
- `_domain_attunement_universes`: derive the location chain from the active
  projection's `current_location` (and its ancestors).
- `create_relationship`: accept + store `transversal_type` on `transversal` edges.
- Remove `physical_universe`.

### `services/entity_manager.py`

- `create_projection` / `add_projection`: set `origin_universe` and wire
  `Entity.current_projection`.
- `move_to`: in-place relocate the active projection (`universe` + `current_location`),
  set `Entity.current_projection`; keep SSE `location_changed`.

### `services/effects_applier.py`

- `attune` enable/disable — unchanged.
- `travel` — read the edge's `transversal_type`:
  - `inapposite` → in-place relocate the active projection (`universe` +
    `current_location`, `transversal_type=INAPPOSITE`); key unchanged.
  - `consciousness` → leave the NATIVE projection (body) in place; create a
    `CONSCIOUSNESS` projection at the destination; set `current_projection`.
  - spend Razmerit (unchanged).
- `project_domain` — attune `scope="domain"` (exists).

### `services/effects_engine.py`

- Attunement expiry unchanged (`until` timing). Add consciousness-projection
  cleanup when its governing attunement ends.

### `api/rest/locations.py`

- `EdgeRequest` gains optional `transversal_type` (for `transversal` edges).
- `create_edge`/`delete_edge` store/remove it (both directions).
- `move_entity` → inapposite move (relocate projection in place).

### `api/graphql/*`

- Expose `Projection.origin_universe/name/background_image/current_location/transversal_type`.
- Expose `current_projection` and `effective_universes`; projection-anchored
  `effective_trait_settings`.
- Remove `Entity.transversal`/`home_universes`; add attunement mutation support
  if not already present.

### `db/seed.py`

- Remove `transversal`/`home_universes` seeding; express multiversal entities as
  permanent attunements + one NATIVE projection per universe.

## Trait gating (precise rule)

A morph trait setting (`from_type="projection"`, `_from → projections/{id}`,
id = `{entity_id}:{origin_universe}`) is active iff:

1. `origin_universe ∈ effective_universes`, **and**
2. `origin_universe ∈ trait.universes ∩ traitset.universes` (defensive —
   the "trait-set gate", checked against the projection's origin universe).

(2) is primarily enforced at write/editor time; the query-time check is a
safety net against bad data, same as today.

## Migration

Ordered, idempotent, guarded by existence checks (existing convention):

1. For every entity, ensure a NATIVE projection exists for `current_universe`;
   set `origin_universe = current_universe`; copy `Entity.current_location` onto
   that projection; set `Entity.current_projection` to it.
2. For every entity with `transversal=true`, create NATIVE projections for each
   `home_universes` entry (if missing, `origin_universe` = that universe) and
   append permanent self-attunements (`scope="self"`, `until=None`).
3. For every `ego=false` entity-anchored trait setting: anchor it to the
   projection whose `origin_universe` is in `trait.universes ∩ traitset.universes`
   (prefer `current_universe` on ambiguity; flag truly ambiguous rows for GM review).
   `ego=true` settings stay entity-anchored.
4. Drop `Entity.transversal`, `home_universes`, `current_location`.

## Frontend change list

- **CharacterSheet** — render the active projection's name/image; ego traits
  always, morph traits from the active projection; keep the GM-only 🌍 show-all
  toggle (now shows all projections' traits).
- **GM entity editor** — "Projections" section: list, add-by-universe, remove,
  edit per-projection name/image/location (image fallback indicator).
- **Entity gallery** — entity image + every projection image.
- **GM-drag** — inapposite travel (in-place relocate + set `current_projection`).
- **GmTraitEditPanel** — ego/morph toggle maps to the `from_type` anchor;
  universe chips become "which projection" where a morph trait is being added.

## Progress checklist

### Data model
- [x] `Projection` gains `origin_universe`, `name`, `background_image`, `current_location`.
- [x] `Entity.current_projection` added; `transversal`/`home_universes` removed.
- [ ] `Entity.current_location` removed (kept as a denormalised active-self cache for now — ~24 read sites still use it).
- [x] `TraitSetting.from_type` supports `"projection"` (+ `_from` → `projections/{id}`, `projection_id` field).
- [x] `transversal` edges gain `transversal_type`.

### Logic
- [x] `effective_universes` = `{current_projection.universe}` ∪ unexpired attunements.
- [x] Origin-based trait gating (morph iff `origin_universe` ∈ effective; legacy entity path preserved).
- [x] In-place inapposite travel (no copy/delete; key stays origin).
- [x] Consciousness travel (spawn/reuse `CONSCIOUSNESS` projection).
- [ ] Consciousness-projection cleanup on return/attunement-end (effects_engine).
- [x] Projection-driven occupancy in `navigate_from` + `list_entities_by_location`.
- [ ] Domain attunement over the projection's location subtree (still reads entity cache).

### Effects
- [x] `attune` (carried forward) — confirmed unchanged.
- [x] `travel` — in-place inapposite / consciousness per `transversal_type`.
- [x] `project_domain` (carried forward) — confirmed unchanged.

### Migration
- [x] `migrate_projections` script (NATIVE projection backfill + `origin_universe`/`current_location` copy + `current_projection`).
- [x] `ego=false` → projection anchor (with ambiguity flag).
- [n/a] `transversal`/`home_universes` → permanent attunements (no seed data used them).
- [ ] Run migration against ArangoDB (needs a live DB).

### Frontend
- [x] Character sheet active-projection name/image rendering.
- [x] GM projections management (list/add/remove) in `GmEntityEditPanel`.
- [x] Entity gallery shows per-universe images (existing `EntityImage` gallery).
- [x] GM-drag = inapposite travel (`move_to` now relocates the active projection).
- [ ] GmTraitEditPanel ego/morph ↔ `from_type` anchor mapping.

### Not started / deferred
- [ ] Inner locations for occupants.
- [ ] `owned_by` removal.
- [ ] `EntityImage` ↔ projection image reconciliation.
- [x] Remove leftover `[diag]` `console.log` lines in `CharacterSheet.vue`.
- [ ] Consolidate drag-and-drop into a shared `useDragDrop` composable (currently duplicated across `GmLocationTree`, `GmTraitsetsPanel`, `LocationViewer`, `App`, `BlueBook`, `DiceRoller`, `EffectEditor`, and the new projection image drop).

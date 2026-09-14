"""Phase 1 migration: old Entities → new entities (and the old→new key map).

Reads old-app JSON dumps from /app/data and migrates the `Entities` collection
into the new `entities` collection. Produces a persistent old→new key map so
later phases (relationships, traitsettings, traitsetsettings) can remap their
``Entities/{numeric}`` references.

Conventions (see [[Data Migration Plan]]):
- ``npc`` / ``gm`` → ``gmc``; other types unchanged.
- old universe locations (direct children of Multiverse ``Entities/2``) → new
  ``universe`` entities; all other locations → ``location``.
- ID: ``{type}-{old_numeric_key}`` for non-universes (matches the existing
  ``loc-{numeric}`` convention); ``universe-{slug}`` for universes.
- archetype templates (``is_archetype``) are dropped (D1) — unless
  ``--include-archetypes`` (Phase 2b), which migrates the spawnable ones as
  GMCs (``gmc-{numeric}``) and leaves the character-creation base templates out.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_entities [--apply]
    docker compose exec api python -m transversal.migrate_entities --apply --include-archetypes
"""

from __future__ import annotations

import json
import sys

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, RatingType, TraitSetting
from transversal.migrate_common import (
    DATA_DIR,
    MULTIVERSE,
    TYPE_PREFIX,
    build_parent_map,
    build_universe_map,
    is_migratable_archetype,
    load_json,
    resolve_direct_location,
    resolve_universe_key,
)

# The registry trait that carries an entity's freeform description as `notes`.
DESCRIPTION_TRAIT = "trait-description"
DESCRIPTION_TRAITSET = "ts-secrets-1b55"


def migrate(apply: bool = False, include_archetypes: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")

    parent_map = build_parent_map(relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())
    entity_type_map = {e["_key"]: e.get("type") for e in entities}
    entity_loc = {e["_key"]: e.get("location") for e in entities}

    repo = EntityRepository()

    # Existing new-entity keys — for idempotency + reuse of already-migrated data.
    existing = {e.id for e in repo.list_all_entities()}

    old_to_new: dict[str, str] = {}
    report = {
        "total_old": len(entities),
        "dropped_archetype": 0,
        "skipped_system": 0,
        "skipped_existing": 0,
        "created_entity": 0,
        "created_archetype": 0,
        "created_universe": 0,
        "type_map": {},
        "dropped_fields": ["active", "favorite",
                           "imagened", "imagening", "archetype_id",
                           "subtitle", "entity_type", "is_archetype"],
        "mapped_fields": ["pp -> razmerit", "description -> traitsetting.notes (trait-description)"],
        "universe_slugs": universe_map,
    }

    for e in entities:
        key = e["_key"]
        name = e.get("name", "")
        old_type = e.get("type")
        is_arch = e.get("is_archetype") is True

        # System entities with no new-model equivalent
        if key == MULTIVERSE or (key == "1" and old_type == "gm"):
            report["skipped_system"] += 1
            continue

        # Universe classification takes precedence — a universe flagged
        # is_archetype (e.g. "The Floating Vagabond") still migrates as a universe.
        is_universe = old_type == "location" and key in universe_keys

        # D1 — drop archetype templates (but never a universe). Phase 2b
        # (``--include-archetypes``) resurrects the spawnable ones as GMCs.
        is_arch_gmc = False
        if is_arch and not is_universe:
            if include_archetypes and is_migratable_archetype(e):
                is_arch_gmc = True
            else:
                report["dropped_archetype"] += 1
                continue

        # Type remap
        if old_type == "npc" or old_type == "gm" or is_arch_gmc:
            new_type = EntityType.GMC
        elif is_universe:
            new_type = EntityType.UNIVERSE
        elif old_type in ("character", "faction", "asset", "location"):
            new_type = EntityType(old_type)
        else:
            report["skipped_system"] += 1
            continue

        report["type_map"][old_type] = report["type_map"].get(old_type, 0) + 1

        # Resolve current_location + current_universe (mirrors the old app's
        # retrieve_location): non-location entities use their `location` field;
        # locations use their `super` parent.
        current_location = None
        current_universe = ""
        if new_type == EntityType.UNIVERSE:
            current_universe = universe_map[key]
        else:
            loc_key = resolve_direct_location(key, entity_type_map, entity_loc, parent_map)
            if loc_key:
                if loc_key in universe_keys:
                    current_location = f"universe-{universe_map[loc_key]}"
                    current_universe = universe_map[loc_key]
                else:
                    current_location = f"loc-{loc_key}"
                    uni_key = resolve_universe_key(loc_key, parent_map, universe_keys)
                    current_universe = universe_map.get(uni_key, "") if uni_key else ""

        # ID
        if new_type == EntityType.UNIVERSE:
            new_id = f"universe-{universe_map[key]}"
        elif is_arch_gmc:
            new_id = f"gmc-{key}"
        else:
            prefix = TYPE_PREFIX[old_type]
            new_id = f"{prefix}-{key}"

        old_to_new[f"Entities/{key}"] = new_id

        if new_id in existing:
            report["skipped_existing"] += 1
        else:
            doc = Entity(
                id=new_id,
                type=new_type,
                name=name,
                razmerit=e.get("pp") or 0,
                current_universe=current_universe,
                current_location=current_location,
            )
            if new_type == EntityType.UNIVERSE:
                report["created_universe"] += 1
            elif is_arch_gmc:
                report["created_archetype"] += 1
            else:
                report["created_entity"] += 1
            if apply:
                repo.create_entity(doc)

        # Description → traitsetting.notes on the registry trait `trait-description`.
        # Runs for every migrated entity (new or pre-existing), so descriptions
        # land even on the 136 already-migrated locations.
        desc = (e.get("description") or "").strip()
        if desc:
            ts_id = f"{new_id}:{DESCRIPTION_TRAIT}"
            if repo.get_traitsetting(ts_id) is None:
                report["description_notes"] = report.get("description_notes", 0) + 1
                if apply:
                    repo.create_traitsetting(TraitSetting(
                        id=ts_id,
                        entity_id=new_id,
                        trait_id=DESCRIPTION_TRAIT,
                        from_type="entity",
                        traitset_id=DESCRIPTION_TRAITSET,
                        rating_type=RatingType.EMPTY,
                        dice=[],
                        notes=desc,
                    ))

    # Persist the key map (always, even dry-run, so later phases can inspect it)
    if apply:
        with open(f"{DATA_DIR}/old_to_new_keys.json", "w") as f:
            json.dump(old_to_new, f, indent=2)

    print("=== ENTITY MIGRATION (Phase 1) ===")
    print(f"apply={apply}")
    for k, v in report.items():
        if k == "universe_slugs":
            print(f"  universe_slugs:")
            for uk, us in sorted(v.items()):
                print(f"    {uk}: {us}")
        elif k == "dropped_fields":
            print(f"  dropped_fields: {', '.join(v)}")
        else:
            print(f"  {k}: {v}")
    print(f"  old_to_new keys mapped: {len(old_to_new)}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    include_archetypes = "--include-archetypes" in sys.argv
    sys.exit(migrate(apply=apply, include_archetypes=include_archetypes))

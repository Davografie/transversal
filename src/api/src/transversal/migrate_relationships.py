"""Phase 1b migration: old Relations → new relationships (entity↔entity).

Remaps old ``Relations`` edges onto the new entity keys and types:

- ``super`` (420) → ``super``, but only location→location. Edges to the
  Multiverse root (15) and to universe entities (48) are skipped — the new
  model links locations to universes via ``current_universe``, not a super edge.
- ``transversable`` (338) → ``transversal`` (rename).
- ``relation`` (682) → ``relation`` (kept, D2).
- ``archetype`` (543) → dropped (D1).
- ``agency`` (43) → DEFERRED: these are ``Players/* → Entities/*`` and need a
  player key map (separate concern); reported but not migrated here.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_relationships [--apply]
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.migrate_common import (
    MULTIVERSE,
    build_entity_key_map,
    build_parent_map,
    build_universe_map,
    load_json,
)

# Old relation type → (new type, migrate?)   None = dropped/deferred.
REL_TYPE_MAP = {
    "super": ("super", True),
    "transversable": ("transversal", True),
    "relation": ("relation", True),
    "archetype": (None, False),   # D1 dropped
    "agency": (None, False),      # deferred — needs player map
}


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")

    old_to_new = build_entity_key_map(entities, relations)
    parent_map = build_parent_map(relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())

    repo = EntityRepository()

    report = {
        "total_old": len(relations),
        "dropped_archetype": 0,
        "deferred_agency": 0,
        "skipped_super_to_universe": 0,
        "skipped_super_to_multiverse": 0,
        "skipped_dangling": 0,
        "skipped_existing": 0,
        "created": 0,
        "by_new_type": {},
    }

    for r in relations:
        old_type = r["type"]
        new_type, do_migrate = REL_TYPE_MAP.get(old_type, (None, False))

        if old_type == "archetype":
            report["dropped_archetype"] += 1
            continue

        if old_type == "agency":
            report["deferred_agency"] += 1
            continue

        if not do_migrate:
            continue

        from_ref = r["_from"]      # e.g. "Entities/123"
        to_ref = r["_to"]
        from_key = from_ref.split("/")[1]
        to_key = to_ref.split("/")[1]

        # super edges: skip the ones that the new model captures differently.
        if old_type == "super":
            if to_ref == f"Entities/{MULTIVERSE}":
                report["skipped_super_to_multiverse"] += 1
                continue
            if to_key in universe_keys:
                report["skipped_super_to_universe"] += 1
                continue

        # Map endpoints through the key map; skip if either end is unmapped
        # (archetype template, system entity, or otherwise dropped).
        new_from = old_to_new.get(from_ref)
        new_to = old_to_new.get(to_ref)
        if new_from is None or new_to is None:
            report["skipped_dangling"] += 1
            continue

        # Idempotency
        if repo.get_relationship(new_from, new_to, new_type) is not None:
            report["skipped_existing"] += 1
            continue

        report["created"] += 1
        report["by_new_type"][new_type] = report["by_new_type"].get(new_type, 0) + 1

        if apply:
            repo.create_relationship(new_from, new_to, new_type)

    print("=== RELATIONSHIPS MIGRATION (Phase 1b) ===")
    print(f"apply={apply}")
    for k, v in report.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

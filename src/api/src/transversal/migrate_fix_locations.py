"""Fix-up: backfill ``current_location`` + ``current_universe`` on migrated entities.

Phase 2 originally derived location only from the ``super`` hierarchy, which
characters/GMCs/factions/assets don't have — their location lives in the old
``location`` field. This re-derives both fields the correct way (mirroring the
old app's ``retrieve_location``) and updates the already-migrated entities.

Any entity that still ends up with no location is scattered to a starter
location (falling back to Earth's Eindhoven) so nothing is left "nowhere".

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_fix_locations [--apply]
"""

from __future__ import annotations

import sys
from collections import Counter

from transversal.db.arango import ENTITIES, get_db
from transversal.migrate_common import (
    build_entity_key_map,
    build_parent_map,
    build_universe_map,
    load_json,
    resolve_direct_location,
    resolve_universe_key,
)

FALLBACK_LOCATION = "loc-469287"  # Eindhoven (Earth)


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")

    parent_map = build_parent_map(relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())
    entity_type = {e["_key"]: e.get("type") for e in entities}
    entity_loc = {e["_key"]: e.get("location") for e in entities}
    key_map = build_entity_key_map(entities, relations)

    db = get_db()
    col = db.collection(ENTITIES)

    # Starter locations (for scatter), keyed by universe.
    starters: list[dict] = [e for e in col.all() if e.get("starter_location")]
    starter_by_universe: dict[str, str] = {
        s.get("current_universe"): s["_key"] for s in starters if s.get("current_universe")
    }

    report: Counter = Counter()

    for old_ref, new_id in key_map.items():
        key = old_ref.split("/")[1]
        doc = col.get(new_id)
        if doc is None:
            report["skip_not_found"] += 1
            continue

        current_location = None
        current_universe = ""
        if new_id.startswith("universe-"):
            current_universe = doc.get("current_universe") or universe_map.get(key, "")
        else:
            loc_key = resolve_direct_location(key, entity_type, entity_loc, parent_map)
            if loc_key:
                if loc_key in universe_keys:
                    current_location = f"universe-{universe_map[loc_key]}"
                    current_universe = universe_map[loc_key]
                else:
                    current_location = f"loc-{loc_key}"
                    uni_key = resolve_universe_key(loc_key, parent_map, universe_keys)
                    current_universe = universe_map.get(uni_key, "") if uni_key else ""

        if current_location is None:
            report["scatter"] += 1
            current_location = starter_by_universe.get(current_universe)
            if current_location is None:
                current_location = FALLBACK_LOCATION
                current_universe = "earth"

        if doc.get("current_location") == current_location and doc.get("current_universe") == current_universe:
            report["unchanged"] += 1
            continue

        report["updated"] += 1
        if apply:
            doc["current_location"] = current_location
            doc["current_universe"] = current_universe
            col.update(doc)

    print("=== LOCATION FIX-UP ===")
    print(f"apply={apply}")
    print(f"mapped entities: {len(key_map)}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

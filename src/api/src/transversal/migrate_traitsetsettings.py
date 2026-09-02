"""Phase 5 migration: old ``TraitsetSettings`` → new ``traitsetsettings``.

Per decision D3, only the ``dicepool_limit`` → ``limit`` override is preserved.
An override is written only when the per-entity ``dicepool_limit`` deviates from
the traitset's registry default; everything else (``name``, ``entity_types``,
``order``, ``duplicates``, ``explainer``, ``sfx_ids``) is dropped. SFX pointers
are dropped entirely per D5.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_traitsetsettings [--apply]
"""

from __future__ import annotations

import sys
from collections import Counter

from transversal.db.arango import ENTITIES, TRAITSETS, TRAITSETSETTINGS, get_db
from transversal.migrate_common import (
    build_entity_key_map,
    build_registry_key_maps,
    load_json,
)


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    old_tsets = load_json("traitsets.json")
    tss = load_json("traitsetsettings.json")

    tset_map, _, _ = build_registry_key_maps(old_tsets, load_json("traits.json"))
    entity_key_map = build_entity_key_map(entities, relations)
    tset_default_limit = {t["_key"]: t.get("dicepool_limit") for t in old_tsets}

    db = get_db()
    col = db.collection(TRAITSETSETTINGS)

    report: Counter = Counter()

    for s in tss:
        from_ref = s["_from"]            # Entities/{key}
        to_ref = s["_to"]                # Traitsets/{key}
        entity_id = entity_key_map.get(from_ref)
        traitset_id = tset_map.get(to_ref.split("/")[1])
        if entity_id is None:
            report["skip_entity_dangling"] += 1
            continue
        if traitset_id is None:
            report["skip_traitset_dropped"] += 1
            continue

        own = s.get("dicepool_limit")
        default = tset_default_limit.get(to_ref.split("/")[1])
        if own is None or own == default:
            report["skip_matches_default"] += 1
            continue

        report["override"] += 1
        key = f"{entity_id}:{traitset_id}"
        doc = {
            "_key": key,
            "_from": f"{ENTITIES}/{entity_id}",
            "_to": f"{TRAITSETS}/{traitset_id}",
            "entity_id": entity_id,
            "traitset_id": traitset_id,
            "from_type": "entity",
            "sfx_ids": [],
            "limit": own,
        }
        if apply:
            if col.get(key) is None:
                col.insert(doc)
            else:
                report["skip_existing"] += 1

    print("=== TRAITSETSETTINGS MIGRATION (Phase 5) ===")
    print(f"apply={apply}")
    print(f"source total: {len(tss)}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

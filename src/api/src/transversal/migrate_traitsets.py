"""Migrate traitsets from old Transversal DB dump to new Transversal 2.

Reads dumped JSON files from /tmp, derives universe scoping from Multiverse
hierarchy, and creates TraitSet documents in the new DB.

Usage:
    docker compose exec api python -m transversal.migrate_traitsets
"""

from __future__ import annotations

import hashlib
import json
import sys

from transversal.db.arango import get_db, TRAITSETS
from transversal.domain import DieType, EntityType

# ── Rating encoding ────────────────────────────────────
RATING_TO_DIE: dict[int, DieType] = {
    1: DieType.D4, 2: DieType.D6, 3: DieType.D8, 4: DieType.D10, 5: DieType.D12,
    -1: DieType.D4, -2: DieType.D6, -3: DieType.D8, -4: DieType.D10, -5: DieType.D12,
}

# ── Entity type mapping ─────────────────────────────────
TYPE_MAP: dict[str, str] = {
    "character": "character", "location": "location", "faction": "faction",
    "asset": "asset", "npc": "gmc", "gm": "gmc",
    "subtrait": "subtrait", "relation": "relation",
}

SKIP_NAMES = {"custom", "tutorial"}

DATA_DIR = "/app/data"


def resolve_universes(
    en_ids: list[str], dis_ids: list[str], universe_map: dict[str, str]
) -> set[str]:
    all_unis = set(universe_map.values())

    if en_ids and "2" not in en_ids:
        result = set()
        for uid in en_ids:
            if uid in universe_map:
                result.add(universe_map[uid])
        return result

    if "2" in dis_ids:
        return set()

    result = set(all_unis)
    for uid in dis_ids:
        if uid in universe_map:
            result.discard(universe_map[uid])
    return result


def migrate() -> int:
    # ── Load dumped data ────────────────────────────────
    with open(f"{DATA_DIR}/old_tsets.json") as f:
        old_tsets = json.load(f)["result"]
    with open(f"{DATA_DIR}/universes.json") as f:
        children = json.load(f)["result"]

    universe_map = {c["key"]: c["name"] for c in children if c.get("key") and c.get("name")}
    print(f"Universe children: {len(universe_map)}")
    print(f"Old traitsets: {len(old_tsets)}")

    # ── Clear existing traitsets ────────────────────────
    new_db = get_db()
    ts_col = new_db.collection(TRAITSETS)
    existing = list(ts_col.all())
    for doc in existing:
        ts_col.delete(doc["_key"])
    print(f"Cleared {len(existing)} existing traitsets")

    # ── Migrate ─────────────────────────────────────────
    migrated = skipped = 0
    rt_stats = {"empty": 0, "static": 0, "resource": 0, "challenge": 0, "fallback": 0}

    for ts in old_tsets:
        name = ts.get("name") or ""
        if not name:
            skipped += 1
            continue
        if name in SKIP_NAMES:
            print(f"  SKIP: {name}")
            skipped += 1
            continue

        # Entity types
        if name == "secrets":
            new_types = [e.value for e in EntityType]
        else:
            old_types = ts.get("entity_types") or []
            mapped = [TYPE_MAP[t] for t in old_types if t in TYPE_MAP]
            new_types = list(dict.fromkeys(mapped))

        # Universes
        en_ids = [e.split("/")[1] for e in (ts.get("en") or []) if e]
        dis_ids = [e.split("/")[1] for e in (ts.get("dis") or []) if e]
        universes = resolve_universes(en_ids, dis_ids, universe_map)

        # Rating
        rt = ts.get("default_rt")
        rating = ts.get("default_rating") or []
        rt_map = {"resource": "resource", "challenge": "challenge", "static": "static", "empty": "empty"}
        default_rt = rt_map.get(rt, "static")
        rt_stats[default_rt if rt in rt_map else "fallback"] += 1

        default_die = DieType.D4
        if rating:
            r = abs(rating[0])
            default_die = RATING_TO_DIE.get(r, RATING_TO_DIE.get(rating[0], DieType.D4))

        # Key
        slug = name.lower().replace(" ", "-")
        joined = ",".join(sorted(universes))
        hash4 = hashlib.md5(f"{slug}:{joined}".encode()).hexdigest()[:4]
        new_key = f"ts-{slug}-{hash4}"

        limit = ts.get("dicepool_limit") or 1
        if limit == 0:
            limit = 1

        doc = {
            "_key": new_key, "name": name,
            "universes": sorted(universes),
            "explanation": (ts.get("explainer") or "").strip(),
            "entity_types": new_types,
            "order": ts.get("order") or 0,
            "limit": limit,
            "allow_duplicates": ts.get("duplicates") or False,
            "location_restricted": ts.get("location_restricted") or False,
            "default_rating_type": default_rt,
            "default_die_type": default_die.value,
        }
        ts_col.insert(doc)
        migrated += 1

        uni_str = ", ".join(sorted(universes)[:3])
        if len(universes) > 3:
            uni_str += f" +{len(universes)-3}"
        hidden_str = " [HIDDEN]" if ts.get("hidden") else ""
        print(f"  {name:<26} → {new_key}  [{default_rt}/{default_die.value}]  {uni_str}{hidden_str}")

    print(f"\n=== DONE ===")
    print(f"Migrated: {migrated}, Skipped: {skipped}, Total: {ts_col.count()}")
    print(f"Rating types: {rt_stats}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())

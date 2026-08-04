"""Migrate traits from old Transversal DB dump to new Transversal 2.

Reads dumped JSON files, derives universe scoping from trait defaults with
hierarchy walking, and creates Trait documents in the new DB.

Usage:
    docker compose exec api python -m transversal.migrate_traits
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

from transversal.db.arango import get_db, TRAITS
from transversal.domain import DieType

DATA_DIR = "/app/data"

# ── Rating encoding ────────────────────────────────────
RATING_TO_DIE: dict[int, DieType] = {
    1: DieType.D4, 2: DieType.D6, 3: DieType.D8, 4: DieType.D10, 5: DieType.D12,
    -1: DieType.D4, -2: DieType.D6, -3: DieType.D8, -4: DieType.D10, -5: DieType.D12,
}

def load_json(name: str) -> list[dict]:
    with open(f"{DATA_DIR}/{name}") as f:
        return json.load(f)["result"]


def build_parent_map(super_edges: list[dict]) -> dict[str, str]:
    """child → parent map from super edges."""
    return {e["child"]: e["parent"] for e in super_edges}


def resolve_universe(
    location_key: str, universe_set: set[str], parent_map: dict[str, str]
) -> str | None:
    """Walk super chain from location up to find which universe it belongs to."""
    current = location_key
    visited = set()
    while current and current not in visited:
        if current in universe_set:
            return current
        visited.add(current)
        current = parent_map.get(current, "")
    return None


def resolve_universes_from_default(
    en: list[str], dis: list[str],
    universe_set: set[str], universe_lookup: dict[str, str],
    parent_map: dict[str, str],
) -> set[str]:
    """Resolve universe names from enabled/disabled location lists with hierarchy walking."""
    en_ids = [e.split("/")[1] for e in en if e]
    dis_ids = [e.split("/")[1] for e in dis if e]

    # Walk hierarchy for each enabled location
    resolved_en: set[str] = set()
    for lid in en_ids:
        uni = resolve_universe(lid, universe_set, parent_map)
        if uni:
            resolved_en.add(uni)

    resolved_dis: set[str] = set()
    for lid in dis_ids:
        uni = resolve_universe(lid, universe_set, parent_map)
        if uni:
            resolved_dis.add(uni)

    if resolved_en and "2" not in resolved_en:
        return {universe_lookup[u] for u in resolved_en if u in universe_lookup}

    if "2" in resolved_dis:
        return set()

    result = set(universe_lookup.values())
    for u in resolved_dis:
        result.discard(universe_lookup.get(u, ""))
    return result


def migrate() -> int:
    # ── Load data ────────────────────────────────────────
    old_traits = load_json("old_traits.json")
    universes_raw = load_json("universes.json")
    old_tsets = load_json("old_tsets.json")
    super_edges = load_json("super_relations.json")

    universe_lookup = {u["key"]: u["name"] for u in universes_raw if u.get("key")}
    universe_set = set(universe_lookup.keys())
    parent_map = build_parent_map(super_edges)

    # ── Build old→new traitset key map ───────────────────
    old_tset_map: dict[str, str] = {}
    for ts in old_tsets:
        name = ts.get("name") or ""
        if name in ("custom", "tutorial") or not name:
            continue
        en = ts.get("en") or []
        dis = ts.get("dis") or []
        universes = resolve_universes_from_default(en, dis, universe_set, universe_lookup, parent_map)
        slug = name.lower().replace(" ", "-")
        joined = ",".join(sorted(universes))
        hash4 = hashlib.md5(f"{slug}:{joined}".encode()).hexdigest()[:4]
        old_tset_map[ts["key"]] = f"ts-{slug}-{hash4}"

    # ── Pre-compute old→new trait key map ────────────────
    old_trait_map: dict[str, str] = {}
    for t in old_traits:
        name = t.get("name") or ""
        key = t.get("key") or ""
        if not name or not key:
            continue
        en = t.get("en") or []
        dis = t.get("dis") or []
        universes = resolve_universes_from_default(en, dis, universe_set, universe_lookup, parent_map)
        # If no default universes, inherit from traitset
        if not universes:
            ts_ref = t.get("traitset") or ""
            ts_key = ts_ref.split("/")[1] if "/" in ts_ref else ""
            if ts_key in old_tset_map:
                # Will be resolved later
                pass
        slug = name.lower().replace(" ", "-").replace("_", "-")
        joined = ",".join(sorted(universes)) if universes else "none"
        hash4 = hashlib.md5(f"{slug}:{joined}".encode()).hexdigest()[:4]
        old_trait_map[f"Traits/{key}"] = f"trait-{slug}-{hash4}"

    print(f"Super edges: {len(super_edges)}")
    print(f"Universe children: {len(universe_set)}")
    print(f"Old traitsets mapped: {len(old_tset_map)}")
    print(f"Old traits: {len(old_traits)}")

    # ── Clear existing traits ────────────────────────────
    new_db = get_db()
    trait_col = new_db.collection(TRAITS)
    existing = list(trait_col.all())
    for doc in existing:
        trait_col.delete(doc["_key"])
    print(f"Cleared {len(existing)} existing traits")

    # ── Phase 1: Create trait documents ──────────────────
    migrated = skipped = 0
    rt_stats = {None: 0, "static": 0, "resource": 0, "challenge": 0, "empty": 0}

    # Store created traits for Phase 2 resolution
    created_traits: dict[str, dict] = {}  # old_id → doc

    for t in old_traits:
        name = t.get("name") or ""
        key = t.get("key") or ""
        if not name or not key:
            skipped += 1
            continue

        # ── Resolve traitset ──────────────────────────────
        ts_ref = t.get("traitset") or ""
        ts_key = ts_ref.split("/")[1] if "/" in ts_ref else ""
        new_ts_id = old_tset_map.get(ts_key, "")
        if not new_ts_id:
            print(f"  SKIP (no traitset): {name} (ts_key={ts_key})")
            skipped += 1
            continue

        # ── Resolve universes ─────────────────────────────
        en = t.get("en") or []
        dis = t.get("dis") or []
        has_default = en or dis or t.get("default_rt") or t.get("default_rating")
        if has_default:
            universes = resolve_universes_from_default(en, dis, universe_set, universe_lookup, parent_map)
        else:
            universes = set()

        # If no universes from default, don't fill in — let traitSet provide
        uni_list = sorted(universes)

        # ── Default rating (only if present in old data) ──
        rt = t.get("default_rt")
        rating = t.get("default_rating") or []
        default_rt = rt if rt else None
        default_die = None
        if rating:
            r = abs(rating[0])
            default_die = RATING_TO_DIE.get(r, DieType.D4)
        if default_rt is None and default_die is None:
            rt_stats[None] += 1
        elif default_rt:
            rt_stats[default_rt] = rt_stats.get(default_rt, 0) + 1

        # ── Generate key ──────────────────────────────────
        slug = name.lower().replace(" ", "-").replace("_", "-")
        # Sanitize: only [a-z0-9-]
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        if not slug:
            slug = f"trait-{key}"
        joined = ",".join(uni_list) if uni_list else "none"
        hash4 = hashlib.md5(f"{slug}:{joined}:{key}".encode()).hexdigest()[:4]
        new_key = f"trait-{slug}-{hash4}"

        # ── Create document ───────────────────────────────
        doc: dict = {
            "_key": new_key,
            "name": name,
            "traitset_id": new_ts_id,
            "universes": uni_list,
            "possible_subtrait_ids": [],  # Phase 2
            "possible_sfx_ids": [],
            "required_trait_ids": [],     # Phase 2
            "location_restricted": False,
            "explanation": t.get("explanation") or "",
            "random_weight": t.get("random_weight") or 0,
        }
        if default_die:
            doc["default_die_type"] = default_die.value
        if default_rt:
            doc["default_rating_type"] = default_rt

        trait_col.insert(doc)
        created_traits[f"Traits/{key}"] = doc
        migrated += 1

    print(f"\nPhase 1: Created {migrated} traits, skipped {skipped}")

    # ── Phase 2: Resolve references ──────────────────────
    updated = 0
    for old_id, doc in created_traits.items():
        t = next((x for x in old_traits if f"Traits/{x.get('key')}" == old_id), None)
        if not t:
            continue

        needs_update = False

        # possible_sub_traits
        subs = t.get("possible_sub_traits") or []
        if subs:
            mapped = []
            for s in subs:
                if s in old_trait_map:
                    mapped.append(old_trait_map[s])
            if mapped:
                doc["possible_subtrait_ids"] = mapped
                needs_update = True

        # required_traits
        reqs = t.get("required_traits") or []
        if reqs:
            mapped = []
            for r in reqs:
                if r in old_trait_map:
                    mapped.append(old_trait_map[r])
            if mapped:
                doc["required_trait_ids"] = mapped
                needs_update = True

        if needs_update:
            trait_col.update(doc)
            updated += 1

    print(f"Phase 2: Updated {updated} traits with sub-trait/required refs")
    print(f"\n=== DONE ===")
    print(f"Total in new DB: {trait_col.count()}")
    print(f"Rating types: {{k: v for k, v in rt_stats.items() if v > 0}}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())

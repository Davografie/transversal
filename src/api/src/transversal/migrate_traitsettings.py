"""Phase 4 migration: old ``TraitSettings`` → new ``traitsettings``.

Remaps the old app's 6,106 TraitSettings edges onto the new model's
``traitsettings`` edge collection:

- 505 trait defaults + 34 traitset defaults (``_to: "Traits/1"``) are registry
  metadata already folded into ``traits``/``traitsets`` by migrate_registry —
  NOT migrated as edges here.
- 4,446 entity-traits → ``from_type: entity`` (ego) or ``projection`` (morph),
  per the D4 rule: morph when ``Entities/2`` is in ``locations_disabled`` at any
  of three levels (edge → trait default → traitset default). Morph applies only
  to occupant types (character/npc/gm); locations/factions/assets/universes are
  always ego (they have no bodies).
- 306 relation-traits → ``from_type: relationship`` (new relationship key
  resolved at apply time via ``_from``/``_to``/``type`` endpoint lookup).
- 815 sub-traits → ``from_type: traitsetting`` (two-pass; parents first).

Decisions folded in:
- D6: multi-universe morph splits into one setting per projection; key
  ``{projection_id}:{trait_id}`` (projection_id = ``{entity_id}:{universe}``).
- D7: sub-traits whose parent is a trait-default are skipped (no edge anchor).
- D8: old ``hidden`` dropped. D9: morph projections created on the fly.
- D10: ``locations_*`` left empty (location restrictions ignored).
- D11: mixed-sign rating defaults to positive polarity.
- ``rating`` int → ``dice`` (abs); negative → ``polarity: negative``.
- challenge: negative → ``dice``=doom pool; positive → ``capacity``=target, empty.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_traitsettings [--apply]
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from transversal.db.arango import (
    ENTITIES,
    PROJECTIONS,
    RELATIONSHIPS,
    TRAITSETTINGS,
    get_db,
)
from transversal.migrate_common import (
    MULTIVERSE,
    RATING_TO_DIE,
    RATING_TYPE_MAP,
    build_archetype_depths,
    build_entity_key_map,
    build_registry_key_maps,
    build_universe_map,
    load_json,
)

OCCUPANT_TYPES = {"character", "npc", "gm"}

# Old relation type → new type (None = dropped/deferred). Mirrors Phase 3.
REL_TYPE_MAP = {
    "super": "super",
    "transversable": "transversal",
    "relation": "relation",
    "archetype": None,
    "agency": None,
}


def _rating(rating: list[int] | None, rating_type: str) -> tuple[list[str], list[str] | None, str]:
    """Map old int ``rating`` → (dice, capacity, polarity)."""
    vals = [x for x in (rating or []) if x != 0]
    if not vals:
        return [], None, "positive"
    dice = [RATING_TO_DIE.get(abs(x), "d4") for x in vals]
    # D11: mixed-sign ratings resolve positive; only all-negative is negative.
    polarity = "negative" if all(x < 0 for x in vals) else "positive"
    capacity: list[str] | None = None
    if rating_type == "challenge" and polarity == "positive":
        # Positive progress challenge: old rating is the completion target.
        capacity = dice
        dice = []
    return dice, capacity, polarity


def _universe_slugs(refs: list[str] | None, universe_map: dict[str, str]) -> list[str]:
    out: list[str] = []
    for r in refs or []:
        if not r or "/" not in r:
            continue
        k = r.split("/")[1]
        if k in universe_map:
            out.append(universe_map[k])
    return out


def _find_relationship_key(db, from_id: str, to_id: str, rel_type: str) -> str | None:
    query = f"""
        FOR r IN {RELATIONSHIPS}
        FILTER r._from == @f AND r._to == @t AND r.type == @ty
        LIMIT 1
        RETURN r._key
    """
    cur = list(db.aql.execute(query, bind_vars={
        "f": f"{ENTITIES}/{from_id}", "t": f"{ENTITIES}/{to_id}", "ty": rel_type,
    }))
    return cur[0] if cur else None


def materialize_inheritance(
    entities: list[dict],
    relations: list[dict],
    traits: list[dict],
    traitsets: list[dict],
    tsettings: list[dict],
) -> tuple[list[dict], Counter]:
    """Materialize the old app's read-time trait inheritance.

    Two mechanisms (verified against ``flask/app.py``):

    - **archetype** — OUTBOUND ``archetype`` relations (transitive). An entity
      inherits every TraitSetting on its archetype ancestors.
    - **super-hierarchy** — OUTBOUND ``super`` relations (locations only). A
      location inherits ancestor traits where ``inheritable == true``.

    Replicates the old app's dedup exactly:

    - priority: direct ``10000`` > super-inherited ``5000`` > archetype
      ``max_depth - depth`` (shallower archetype wins).
    - ``inherited_as``: a setting with ``inherited_as: TraitSettings/X``
      shadows X (removed before dedup).
    - dedup key per traitset: ``name`` when ``traitset.duplicates == false``,
      else ``name + statement``; highest priority survives.

    Returns synthetic entity-trait settings (``_from`` rewritten to the
    inheriting entity, locations reset — D10) for each surviving inherited
    trait, plus a stats counter.
    """
    tset_duplicates = {ts["_key"]: ts.get("duplicates", False) for ts in traitsets}
    trait_meta: dict[str, tuple[str, str]] = {}
    for t in traits:
        ref = t.get("traitset") or ""
        trait_meta[t["_key"]] = (t.get("name") or "", ref.split("/")[1] if "/" in ref else "")

    settings_by_entity: dict[str, list[dict]] = defaultdict(list)
    for s in tsettings:
        if s["_from"].startswith("Entities/"):
            settings_by_entity[s["_from"]].append(s)

    arch_depths = build_archetype_depths(relations)
    super_parent: dict[str, str] = {
        r["_from"]: r["_to"] for r in relations if r.get("type") == "super"
    }

    stats: Counter = Counter()
    synthetic: list[dict] = []

    for entity_ref in settings_by_entity:
        direct = settings_by_entity[entity_ref]

        # Transitive archetype ancestors with (shortest) depth.
        arch_ancestors = list(arch_depths.get(entity_ref, {}).items())

        # Transitive super ancestors (locations).
        super_ancestors: list[str] = []
        cur, seen = entity_ref, set()
        while cur in super_parent and cur not in seen:
            seen.add(cur)
            cur = super_parent[cur]
            super_ancestors.append(cur)

        if not arch_ancestors and not super_ancestors:
            continue

        max_depth = max((d for _, d in arch_ancestors), default=0)

        candidates: list[tuple[int, dict, bool]] = []  # (priority, setting, is_direct)
        for s in direct:
            candidates.append((10000, s, True))
        for a_ref, d in arch_ancestors:
            for s in settings_by_entity.get(a_ref, []):
                candidates.append((max_depth - d, s, False))
        for a_ref in super_ancestors:
            for s in settings_by_entity.get(a_ref, []):
                if s.get("inheritable") is True:
                    candidates.append((5000, s, False))

        # inherited_as shadows (remove the shadowed setting _id).
        shadowed = {s.get("inherited_as") for _, s, _ in candidates if s.get("inherited_as")}
        kept = [(p, s, isd) for p, s, isd in candidates if s["_id"] not in shadowed]
        stats["shadowed"] += len(candidates) - len(kept)

        # Dedup per (traitset, key), highest priority wins.
        best: dict[tuple[str, str], tuple[int, dict, bool]] = {}
        for p, s, isd in kept:
            tkey = s["_to"].split("/")[1]
            name, tset_key = trait_meta.get(tkey, ("", ""))
            dup = tset_duplicates.get(tset_key, False)
            key = (tset_key, name if not dup else name + (s.get("statement") or ""))
            if key not in best or p > best[key][0]:
                best[key] = (p, s, isd)

        inherited_kept = sum(1 for _, _, isd in kept if not isd)
        materialized = 0
        for key, (p, s, isd) in best.items():
            if isd:
                continue  # direct trait — already migrated normally
            materialized += 1
            stats["materialized"] += 1
            synthetic.append({
                "_from": entity_ref,
                "_to": s["_to"],
                "_orig_key": s["_key"],  # ancestor setting key → sub-trait re-anchor
                "rating_type": s.get("rating_type"),
                "rating": s.get("rating"),
                "statement": s.get("statement") or "",
                "notes": s.get("notes") or "",
                "locations_enabled": [],   # D10: ancestor scoping doesn't carry over
                "locations_disabled": [],  # D10
                "_materialized": True,
            })
        stats["dedup_dropped"] += inherited_kept - materialized

    return synthetic, stats


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    old_traits = load_json("traits.json")
    old_tsets = load_json("traitsets.json")
    tsettings = load_json("traitsettings.json")

    tset_map, trait_map, trait_tset_map = build_registry_key_maps(old_tsets, old_traits)
    entity_key_map = build_entity_key_map(entities, relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())

    entity_type = {e["_key"]: e.get("type") for e in entities}
    relation_by_key = {r["_key"]: r for r in relations}
    trait_old_tset: dict[str, str] = {}
    for t in old_traits:
        ref = t.get("traitset") or ""
        trait_old_tset[t["_key"]] = ref.split("/")[1] if "/" in ref else ""

    # Default settings (_to "Traits/1"), keyed by their source key.
    trait_defaults: dict[str, dict] = {}
    tset_defaults: dict[str, dict] = {}
    for s in tsettings:
        if s["_to"] != "Traits/1":
            continue
        src = s["_from"]
        if src.startswith("Traits/"):
            trait_defaults[src.split("/")[1]] = s
        elif src.startswith("Traitsets/"):
            tset_defaults[src.split("/")[1]] = s

    db = get_db()
    ts_col = db.collection(TRAITSETTINGS)
    proj_col = db.collection(PROJECTIONS)
    existing_proj: set[str] = set(p["_key"] for p in proj_col.all())

    report: Counter = Counter()

    # Registry-metadata edges (folded into traits/traitsets by Phase 1) are
    # counted for completeness but not migrated as edges.
    report["skip_trait_default"] = sum(
        1 for s in tsettings if s["_from"].startswith("Traits/")
    )
    report["skip_tset_default"] = sum(
        1 for s in tsettings if s["_from"].startswith("Traitsets/")
    )

    def is_morph(s: dict, trait_ok: str, tset_ok: str) -> bool:
        sentinel = f"Entities/{MULTIVERSE}"
        for lvl in (
            s.get("locations_disabled"),
            trait_defaults.get(trait_ok, {}).get("locations_disabled"),
            tset_defaults.get(tset_ok, {}).get("locations_disabled"),
        ):
            if lvl and sentinel in lvl:
                return True
        return False

    def morph_slugs(s: dict, trait_ok: str, tset_ok: str) -> list[str]:
        for lvl in (
            s.get("locations_enabled"),
            trait_defaults.get(trait_ok, {}).get("locations_enabled"),
            tset_defaults.get(tset_ok, {}).get("locations_enabled"),
        ):
            slugs = _universe_slugs(lvl, universe_map)
            if slugs:
                return slugs
        return []

    def ensure_projection(entity_id: str, slug: str) -> str:
        pid = f"{entity_id}:{slug}"
        if pid in existing_proj:
            report["projection_reused"] += 1
            return pid
        if apply:
            proj_col.insert({
                "_key": pid,
                "entity_id": entity_id,
                "origin_universe": slug,
                "universe": slug,
                "name": "",
                "current_location": None,
                "transversal_type": "consciousness",
                "sfx_ids": [],
            })
        existing_proj.add(pid)
        report["projection_created"] += 1
        return pid

    def insert(key: str, from_handle: str, entity_id: str, trait_id: str,
               tset_id: str, from_type: str, rating_type: str, dice: list[str],
               capacity: list[str] | None, polarity: str, statement: str,
               notes: str, projection_id: str | None = None,
               parent_key: str | None = None) -> None:
        doc: dict = {
            "_key": key,
            "_from": from_handle,
            "_to": f"traits/{trait_id}",
            "entity_id": entity_id,
            "trait_id": trait_id,
            "from_type": from_type,
            "traitset_id": tset_id,
            "rating_type": rating_type,
            "dice": dice,
            "spent_dice": [],
            "polarity": polarity,
            "statement": statement,
            "notes": notes,
            "sfx_ids": [],
            "locations_enabled": [],   # D10: ignore location restrictions
            "locations_disabled": [],  # D10
            "enabled": True,
            "known_to": [],
        }
        if capacity is not None:
            doc["capacity"] = capacity
        if projection_id is not None:
            doc["projection_id"] = projection_id
        if parent_key is not None:
            doc["parent_traitsetting_id"] = parent_key
        if apply and ts_col.get(key) is not None:
            report["skipped_existing"] += 1
            return
        if apply:
            ts_col.insert(doc)
        report["created"] += 1

    # old TraitSettings key → [(new traitsetting key, owning entity_id)]
    parent_new: dict[str, list[tuple[str, str]]] = {}

    # ── Pass 1a: entity-traits (direct + materialized inheritance) ──
    synthetic, mat_stats = materialize_inheritance(
        entities, relations, old_traits, old_tsets, tsettings
    )
    report.update(mat_stats)
    entity_settings = [s for s in tsettings if s["_from"].startswith("Entities/")]
    entity_settings.extend(synthetic)

    for s in entity_settings:
        ent_old = s["_from"].split("/")[1]
        trait_old = s["_to"].split("/")[1]

        entity_id = entity_key_map.get(f"Entities/{ent_old}")
        trait_id = trait_map.get(f"Traits/{trait_old}")
        tset_id = trait_tset_map.get(trait_old)
        if entity_id is None:
            report["skip_entity_dangling"] += 1
            continue
        if trait_id is None or tset_id is None:
            report["skip_entity_trait_dropped"] += 1
            continue

        tset_old = trait_old_tset.get(trait_old, "")
        rt = RATING_TYPE_MAP.get(s.get("rating_type"), "static")
        dice, capacity, polarity = _rating(s.get("rating"), rt)
        statement = s.get("statement") or ""
        notes = s.get("notes") or ""

        old_type = entity_type.get(ent_old)
        morph = old_type in OCCUPANT_TYPES and is_morph(s, trait_old, tset_old)

        if not morph:
            key = f"{entity_id}:{trait_id}"
            insert(key, f"{ENTITIES}/{entity_id}", entity_id, trait_id, tset_id,
                   "entity", rt, dice, capacity, polarity, statement, notes)
            pk = s.get("_orig_key", s.get("_key"))
            if pk is not None:
                parent_new.setdefault(pk, []).append((key, entity_id))
            report["ego"] += 1
            continue

        slugs = morph_slugs(s, trait_old, tset_old)
        if not slugs:
            report["skip_morph_no_universe"] += 1
            continue
        entries: list[tuple[str, str]] = []
        for slug in slugs:
            pid = ensure_projection(entity_id, slug)
            key = f"{pid}:{trait_id}"
            insert(key, f"{PROJECTIONS}/{pid}", entity_id, trait_id, tset_id,
                   "projection", rt, dice, capacity, polarity, statement, notes,
                   projection_id=pid)
            entries.append((key, entity_id))
            report["morph"] += 1
            if len(slugs) > 1:
                report["morph_multi_universe"] += 1
        pk = s.get("_orig_key", s.get("_key"))
        if pk is not None:
            parent_new.setdefault(pk, []).extend(entries)

    # ── Pass 1b: relation-traits ─────────────────────────
    for s in tsettings:
        if not s["_from"].startswith("Relations/"):
            continue
        rel_old = s["_from"].split("/")[1]
        trait_old = s["_to"].split("/")[1]

        rel = relation_by_key.get(rel_old)
        if rel is None:
            report["skip_relation_dangling"] += 1
            continue
        old_type = rel.get("type")
        new_type = REL_TYPE_MAP.get(old_type)
        if new_type is None:
            report["skip_relation_dropped_type"] += 1
            continue
        from_ref, to_ref = rel["_from"], rel["_to"]
        to_key = to_ref.split("/")[1]
        if old_type == "super" and (
            to_ref == f"Entities/{MULTIVERSE}" or to_key in universe_keys
        ):
            report["skip_relation_super"] += 1
            continue
        new_from = entity_key_map.get(from_ref)
        new_to = entity_key_map.get(to_ref)
        if new_from is None or new_to is None:
            report["skip_relation_endpoint"] += 1
            continue

        trait_id = trait_map.get(f"Traits/{trait_old}")
        tset_id = trait_tset_map.get(trait_old)
        if trait_id is None or tset_id is None:
            report["skip_relation_trait_dropped"] += 1
            continue

        rt = RATING_TYPE_MAP.get(s.get("rating_type"), "static")
        dice, capacity, polarity = _rating(s.get("rating"), rt)
        statement = s.get("statement") or ""
        notes = s.get("notes") or ""

        if apply:
            rel_key = _find_relationship_key(db, new_from, new_to, new_type)
            if rel_key is None:
                report["skip_relation_not_found"] += 1
                continue
            key = f"{rel_key}:{trait_id}"
            insert(key, f"{RELATIONSHIPS}/{rel_key}", rel_key, trait_id, tset_id,
                   "relationship", rt, dice, capacity, polarity, statement, notes)
        report["relationship"] += 1

    # ── Pass 2: sub-traits ───────────────────────────────
    for s in tsettings:
        if not s["_from"].startswith("TraitSettings/"):
            continue
        parent_old = s["_from"].split("/")[1]
        trait_old = s["_to"].split("/")[1]

        parents = parent_new.get(parent_old)
        if parents is None:
            # Either the parent is dangling (skipped) or a trait-default edge.
            report["skip_subtrait_parent"] += 1
            continue

        trait_id = trait_map.get(f"Traits/{trait_old}")
        tset_id = trait_tset_map.get(trait_old)
        if trait_id is None or tset_id is None:
            report["skip_subtrait_trait_dropped"] += 1
            continue

        rt = RATING_TYPE_MAP.get(s.get("rating_type"), "static")
        dice, capacity, polarity = _rating(s.get("rating"), rt)
        statement = s.get("statement") or ""
        notes = s.get("notes") or ""

        for parent_key, entity_id in parents:
            key = f"{parent_key}:{trait_id}"
            insert(key, f"{TRAITSETTINGS}/{parent_key}", entity_id, trait_id,
                   tset_id, "traitsetting", rt, dice, capacity, polarity,
                   statement, notes, parent_key=parent_key)
            report["subtrait"] += 1

    print("=== TRAITSETTINGS MIGRATION (Phase 4) ===")
    print(f"apply={apply}")
    print(f"source total: {len(tsettings)}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

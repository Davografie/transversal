"""Deterministic trait/traitset registry migration (replaces the two prior scripts).

Reads the old-app JSON dumps and (re)creates the ``traits`` and ``traitsets``
collections from scratch, using ONE universe-resolution function and ONE key
formula so the old→new trait key map is trivially reproducible — which the
traitsettings migration depends on.

Conventions:
- traitset key: ``ts-{old_numeric_key}`` (e.g. ``ts-3133856``)
- trait key:   ``trait-{old_numeric_key}`` (e.g. ``trait-2081363``)
- skips ``custom`` and ``tutorial`` traitsets (and their traits).
- preserves ``ts-emberline`` + its traits (new-app-only content, no old source).

Dry-run by default. ``--apply`` wipes old-app-sourced traits/traitsets and writes.

Usage:
    docker compose exec api python -m transversal.migrate_registry [--apply]
"""

from __future__ import annotations

import sys

from transversal.db.arango import TRAITS, TRAITSETS, get_db
from transversal.migrate_common import (
    RATING_TO_DIE,
    RATING_TYPE_MAP,
    build_parent_map,
    build_universe_lookup,
    load_json,
    resolve_universes_from_default,
)

SKIP_TRAITSETS = {"custom", "tutorial"}
EMBERLINE_TS = "ts-emberline"

# New-app-only traitsets that have no old-app source but hold hand-authored
# traits we must preserve (Option A). Old-app traits of the SAME name are
# merged into these preserved traitsets rather than creating a fresh key.
#   old traitset name → preserved new traitset key
PRESERVED_TRAITSETS = {
    "relations": "ts-relations-b114",
    "secrets": "ts-secrets-1b55",
    "location": "ts-location-afd2",
}

# New-app-only trait keys (inside the preserved traitsets) that the wipe must
# leave untouched. Old-app traits of the same name/area don't exist, so there
# are no key collisions.
PRESERVED_TRAITS = {
    "trait-description",
    "trait-rel-rank",
    "trait-rel-tenure",
    "trait-regime-alert",
}


def _traitset_key(old_key: str) -> str:
    return f"ts-{old_key}"


def _trait_key(old_key: str) -> str:
    return f"trait-{old_key}"


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    old_tsets = load_json("traitsets.json")
    old_traits = load_json("traits.json")
    tsettings = load_json("traitsettings.json")

    universe_lookup = build_universe_lookup(entities, relations)
    parent_map = build_parent_map(relations)

    # ── Index the defaults ────────────────────────────────
    # traitset defaults: _from Traitsets/{key} -> _to Traits/1
    # trait defaults:    _from Traits/{key}     -> _to Traits/1
    tset_defaults: dict[str, dict] = {}
    trait_defaults: dict[str, dict] = {}
    for s in tsettings:
        if s["_to"] != "Traits/1":
            continue
        src = s["_from"]
        if src.startswith("Traitsets/"):
            tset_defaults[src.split("/")[1]] = s
        elif src.startswith("Traits/"):
            trait_defaults[src.split("/")[1]] = s

    # ── Build traitset key map ────────────────────────────
    old_tset_map: dict[str, str] = {}   # old numeric key -> new key
    old_tset_unis: dict[str, set[str]] = {}  # old numeric key -> universe slugs
    for ts in old_tsets:
        name = ts.get("name") or ""
        key = ts["_key"]
        if not name or name in SKIP_TRAITSETS:
            continue
        d = tset_defaults.get(key, {})
        unis = resolve_universes_from_default(
            d.get("locations_enabled") or [], d.get("locations_disabled") or [],
            universe_lookup,
        )
        # Preserved traitsets keep their existing new key; the old-app traits
        # are merged into them instead of a fresh ts-{numeric} key.
        old_tset_map[key] = PRESERVED_TRAITSETS.get(name, _traitset_key(key))
        old_tset_unis[key] = unis

    # ── Build trait key map (for sub/required reference resolution) ──
    old_trait_map: dict[str, str] = {}
    for t in old_traits:
        key = t["_key"]
        old_trait_map[f"Traits/{key}"] = _trait_key(key)

    # ── Resolve universe for a trait (trait default → traitset default) ──
    def trait_universes(t: dict) -> set[str]:
        key = t["_key"]
        d = trait_defaults.get(key)
        if d:
            unis = resolve_universes_from_default(
                d.get("locations_enabled") or [], d.get("locations_disabled") or [],
                universe_lookup,
            )
            if unis:
                return unis
        # fall back to traitset scoping
        ts_ref = t.get("traitset") or ""
        ts_key = ts_ref.split("/")[1] if "/" in ts_ref else ""
        return old_tset_unis.get(ts_key, set())

    # ── Dry-run report state ──────────────────────────────
    report = {
        "existing_traitsets": 0,
        "existing_traits": 0,
        "preserved_emberline_traitsets": 0,
        "preserved_emberline_traits": 0,
        "preserved_newonly_traitsets": 0,
        "preserved_newonly_traits": 0,
        "wiped_traitsets": 0,
        "wiped_traits": 0,
        "created_traitsets": 0,
        "created_traits": 0,
        "skipped_traitsets": 0,
        "skipped_traits": 0,
    }

    db = get_db()
    tset_col = db.collection(TRAITSETS)
    trait_col = db.collection(TRAITS)

    # ── Determine current state ──────────────────────────
    existing_tsets = {d["_key"]: d for d in tset_col.all()}
    existing_traits = {d["_key"]: d for d in trait_col.all()}
    report["existing_traitsets"] = len(existing_tsets)
    report["existing_traits"] = len(existing_traits)

    # ── Apply: wipe old-app-sourced traits/traitsets, preserve new-only ──
    preserved_tset_keys = set(PRESERVED_TRAITSETS.values()) | {EMBERLINE_TS}
    to_wipe_tsets = [
        k for k in existing_tsets
        if k.startswith("ts-") and k not in preserved_tset_keys
    ]
    to_wipe_traits = [
        k for k in existing_traits
        if k.startswith("trait-")
        and not k.startswith("trait-emberline-")
        and k not in PRESERVED_TRAITS
    ]
    report["preserved_emberline_traitsets"] = sum(
        1 for k in existing_tsets if k == EMBERLINE_TS
    )
    report["preserved_emberline_traits"] = sum(
        1 for k in existing_traits if k.startswith("trait-emberline-")
    )
    report["preserved_newonly_traitsets"] = sum(
        1 for k in existing_tsets if k in preserved_tset_keys and k != EMBERLINE_TS
    )
    report["preserved_newonly_traits"] = sum(
        1 for k in existing_traits if k in PRESERVED_TRAITS
    )
    report["wiped_traitsets"] = len(to_wipe_tsets)
    report["wiped_traits"] = len(to_wipe_traits)
    if apply:
        for k in to_wipe_tsets:
            tset_col.delete(k)
        for k in to_wipe_traits:
            trait_col.delete(k)

    # ── Migrate traitsets ────────────────────────────────
    for ts in old_tsets:
        name = ts.get("name") or ""
        key = ts["_key"]
        if not name or name in SKIP_TRAITSETS:
            report["skipped_traitsets"] += 1
            continue

        d = tset_defaults.get(key, {})
        unis = old_tset_unis[key]
        rt = d.get("rating_type")
        rating = d.get("rating") or []

        # Preserved traitsets already exist (with their hand-authored traits).
        # We merge old-app traits into them; do not recreate the traitset doc.
        if name in PRESERVED_TRAITSETS:
            report["merged_into_preserved_traitsets"] = report.get("merged_into_preserved_traitsets", 0) + 1
            continue

        # defaults: fall back to static/d4 when absent (per plan)
        new_rt = RATING_TYPE_MAP.get(rt, "static")
        new_die = RATING_TO_DIE.get(abs(rating[0]), "d4") if rating else "d4"

        doc = {
            "_key": _traitset_key(key),
            "name": name,
            "universes": sorted(unis),
            "description": (ts.get("explainer") or "").strip(),
            "entity_types": _map_entity_types(ts.get("entity_types")),
            "order": ts.get("order") or 0,
            "limit": ts.get("dicepool_limit") or 1,
            "location_restricted": bool(ts.get("location_restricted")),
            "default_rating_type": new_rt,
            "default_die_type": new_die,
        }
        report["created_traitsets"] += 1
        if apply:
            tset_col.insert(doc)

    # ── Migrate traits ───────────────────────────────────
    for t in old_traits:
        name = t.get("name") or ""
        key = t["_key"]
        ts_ref = t.get("traitset") or ""
        ts_key = ts_ref.split("/")[1] if "/" in ts_ref else ""

        if ts_key not in old_tset_map:
            report["skipped_traits"] += 1
            continue

        d = trait_defaults.get(key, {})
        unis = trait_universes(t)

        # defaults: only set when the trait has its own default (else traitset
        # fallback applies at runtime). Per plan: do not fill empty trait defaults.
        rt = d.get("rating_type")
        rating = d.get("rating") or []
        new_rt = RATING_TYPE_MAP.get(rt) if rt else None
        new_die = RATING_TO_DIE.get(abs(rating[0])) if rating else None

        doc = {
            "_key": _trait_key(key),
            "name": name,
            "universes": sorted(unis),
            "traitset_id": old_tset_map[ts_key],
            "default_rating_type": new_rt or "static",
            "default_die_type": new_die or "d6",
            "required_trait_ids": [
                old_trait_map[r] for r in (t.get("required_traits") or [])
                if r in old_trait_map
            ],
            "possible_subtrait_ids": [
                old_trait_map[r] for r in (t.get("possible_sub_traits") or [])
                if r in old_trait_map
            ],
            "possible_subtraitset_ids": [
                old_tset_map.get(r.split("/")[1], "") for r in (t.get("possible_sub_traitsets") or [])
                if r.split("/")[1] in old_tset_map
            ],
            "possible_sfx_ids": [],      # SFX dropped (D5)
            "default_sfx_ids": [],       # SFX dropped (D5)
            "location_restricted": bool(t.get("location_restricted")),
            "explanation": t.get("explanation") or "",
            "random_weight": t.get("random_weight") or 0,
        }
        report["created_traits"] += 1
        if apply:
            trait_col.insert(doc)

    print("=== REGISTRY MIGRATION ===")
    print(f"apply={apply}")
    for k, v in report.items():
        print(f"  {k}: {v}")
    return 0


def _map_entity_types(old_types: list[str]) -> list[str]:
    mapping = {
        "character": "character", "location": "location", "faction": "faction",
        "asset": "asset", "npc": "gmc", "gm": "gmc",
        "subtrait": "subtrait", "relation": "relation",
    }
    out = []
    for t in old_types or []:
        m = mapping.get(t)
        if m and m not in out:
            out.append(m)
    return out


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

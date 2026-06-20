"""Fixup traitset_id references after trait/traitset migration.

The two migration scripts (migrate_traits.py and migrate_traitsets.py) use
different universe-resolution logic, causing them to compute different
traitset keys for the same traitset.  This script matches traits back to
their correct traitsets by name (from the old data) and updates the
traitset_id field.

Usage:
    docker compose exec api python -m transversal.fixup_traitset_ids --dry-run
    docker compose exec api python -m transversal.fixup_traitset_ids
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from transversal.db.arango import get_db, TRAITS, TRAITSETS

DATA_DIR = "/app/data"


def load_json(name: str) -> list[dict]:
    with open(f"{DATA_DIR}/{name}") as f:
        data = json.load(f)
    return data.get("result", data)


def fixup(dry_run: bool = True) -> int:
    db = get_db()
    traits_col = db.collection(TRAITS)
    traitsets_col = db.collection(TRAITSETS)

    # ── Load current DB state ──────────────────────────
    existing_traitsets: dict[str, dict] = {}
    for doc in traitsets_col.all():
        existing_traitsets[doc["_key"]] = doc

    existing_traits: list[dict] = list(traits_col.all())

    print(f"Traitsets in DB: {len(existing_traitsets)}")
    print(f"Traits in DB:     {len(existing_traits)}")

    # ── Build traitset name → _key map from actual DB ──
    # (names are unique enough for matching)
    name_to_ts: dict[str, str] = {}  # normalized_name → _key
    name_collisions: dict[str, list[str]] = defaultdict(list)

    for key, doc in existing_traitsets.items():
        name = (doc.get("name") or "").strip()
        norm = name.lower()
        name_to_ts[norm] = key
        name_collisions[norm].append(key)

    collisions = {n: ks for n, ks in name_collisions.items() if len(ks) > 1}
    if collisions:
        print(f"\n⚠  Name collisions detected ({len(collisions)}):")
        for name, keys in sorted(collisions.items()):
            print(f"   '{name}': {keys}")
        print("   These will use the LAST key inserted (non-deterministic).")
        print("   Manual fix may be required.\n")

    # ── Load old data to map traits → traitset names ────
    try:
        old_traits = load_json("old_traits.json")
        old_tsets = load_json("old_tsets.json")
    except FileNotFoundError as e:
        print(f"ERROR: Old data file not found: {e}")
        print("Make sure /app/data/ contains old_traits.json and old_tsets.json")
        return 1

    # old traitset key → name
    old_tset_names: dict[str, str] = {}
    for ts in old_tsets:
        key = ts.get("key") or ts.get("_key") or ""
        name = (ts.get("name") or "").strip()
        if key and name:
            old_tset_names[key] = name

    # old trait key → old traitset key
    old_trait_to_tset: dict[str, str] = {}
    for t in old_traits:
        key = t.get("key") or t.get("_key") or ""
        ts_ref = t.get("traitset") or ""
        if "/" in ts_ref:
            ts_key = ts_ref.split("/")[1]
        else:
            ts_key = ts_ref
        if key and ts_key:
            old_trait_to_tset[key] = ts_key

    print(f"Old traits loaded:       {len(old_traits)}")
    print(f"Old traitsets loaded:     {len(old_tsets)}")
    print(f"Old trait→tset mappings:  {len(old_trait_to_tset)}")
    print(f"Old traitset names:       {len(old_tset_names)}")

    # ── Match traits to correct traitsets ───────────────
    fixed = 0
    already_ok = 0
    no_match = 0
    no_old_data = 0
    collision_ambiguous = 0
    not_found_in_db = 0
    dry_run_prefix = "[DRY RUN] " if dry_run else ""

    for trait_doc in existing_traits:
        trait_key = trait_doc["_key"]
        current_ts_id = trait_doc.get("traitset_id") or ""

        # Check if current traitset_id is valid
        if current_ts_id in existing_traitsets:
            already_ok += 1
            continue

        # Try to find the correct traitset from old data
        # The trait's key format: trait-{slug}-{hash4}
        # We need the old trait key to look up its old traitset reference
        # Strategy: extract the slug from the trait key and match against
        # old traits by name/slug

        # Try matching by old trait key if we have it
        old_tset_key = None
        trait_name = trait_doc.get("name") or ""

        # Find the old trait by name (most reliable cross-reference)
        for old_t in old_traits:
            if (old_t.get("name") or "").strip() == trait_name:
                old_key = old_t.get("key") or old_t.get("_key") or ""
                if old_key in old_trait_to_tset:
                    old_tset_key = old_trait_to_tset[old_key]
                    break

        if old_tset_key is None:
            # Fallback: try matching by the trait's name slug
            no_old_data += 1
            continue

        # Get the old traitset name
        old_tset_name = old_tset_names.get(old_tset_key)
        if not old_tset_name:
            not_found_in_db += 1
            continue

        # Find matching traitset in new DB by name
        norm_name = old_tset_name.strip().lower()
        new_ts_key = name_to_ts.get(norm_name)

        if new_ts_key is None:
            not_found_in_db += 1
            if not dry_run or not_found_in_db <= 5:
                print(f"  NOT FOUND: trait '{trait_name}' ({trait_key})")
                print(f"              expects traitset '{old_tset_name}' — not in DB")
            continue

        # Check for collisions
        if norm_name in collisions:
            collision_ambiguous += 1
            if not dry_run or collision_ambiguous <= 5:
                print(f"  COLLISION: trait '{trait_name}' ({trait_key})")
                print(f"             traitset '{old_tset_name}' has multiple keys: {collisions[norm_name]}")
                print(f"             using: {new_ts_key}")
            # Still fix it — better than a broken reference

        if dry_run:
            fixed += 1
            if fixed <= 10:
                print(f"  {dry_run_prefix}FIX: trait '{trait_name}' ({trait_key})")
                print(f"       traitset_id: '{current_ts_id}' → '{new_ts_key}'")
        else:
            trait_doc["traitset_id"] = new_ts_key
            traits_col.update(trait_doc)
            fixed += 1
            if fixed <= 10:
                print(f"  FIXED: trait '{trait_name}' ({trait_key})")
                print(f"         traitset_id → '{new_ts_key}'")

    # ── Phase 2: Fill empty universes from traitset ──────
    # Traits with universes=[] inherit their traitset's universes.
    print(f"\n{'='*50}")
    print(f"Phase 2: Fill empty universes from traitsets")

    uni_fixed = 0
    uni_already = 0
    uni_no_ts = 0
    uni_dry = dry_run  # re-use dry-run mode

    # Re-fetch traits (some may have been updated in Phase 1)
    existing_traits = list(traits_col.all())

    for trait_doc in existing_traits:
        if trait_doc.get("universes"):
            uni_already += 1
            continue

        ts_id = trait_doc.get("traitset_id") or ""
        ts_doc = existing_traitsets.get(ts_id)
        if not ts_doc:
            uni_no_ts += 1
            continue

        ts_universes = ts_doc.get("universes") or []
        if not ts_universes:
            uni_no_ts += 1
            continue

        if uni_dry:
            uni_fixed += 1
            if uni_fixed <= 10:
                print(f"  {dry_run_prefix}FILL: trait '{trait_doc.get('name','')}' ({trait_doc['_key']})")
                print(f"         universes: [] → {ts_universes}")
        else:
            trait_doc["universes"] = ts_universes
            traits_col.update(trait_doc)
            uni_fixed += 1
            if uni_fixed <= 10:
                print(f"  FILLED: trait '{trait_doc.get('name','')}' ({trait_doc['_key']})")
                print(f"          universes → {ts_universes}")

    # ── Phase 3: Normalize universe names to canonical keys ──
    # The migration stored display names ("Earth", "Three Realms") but the
    # API and seed use lowercase keys ("earth", "three_realms").  AQL IN
    # is case-sensitive so they never match.
    print(f"\n{'='*50}")
    print(f"Phase 3: Normalize universe names to canonical keys")

    # Build canonical mapping from universe entities in the DB
    ents_col = db.collection("entities")
    canonical: dict[str, str] = {}  # display_name → canonical_key
    for doc in ents_col.find({"type": "universe"}):
        name = (doc.get("name") or "").strip()
        key = doc.get("current_universe") or ""
        if name and key:
            canonical[name.lower()] = key

    def normalize(name: str) -> str:
        """Convert a display name to its canonical key."""
        # Check explicit mapping first
        low = name.strip().lower()
        if low in canonical:
            return canonical[low]
        # Derive: lowercase, underscores, strip non-ASCII/special chars
        import re
        key = low
        key = key.replace(": ", "_").replace(":","_").replace(" - ","_")
        key = key.replace(" ", "_").replace("-", "_")
        key = re.sub(r"[^a-z0-9_]", "", key)
        key = re.sub(r"_+", "_", key).strip("_")
        return key

    norm_ts = 0
    norm_tr = 0
    norm_skip = 0
    norm_dry = dry_run

    # Normalize traitset universes
    existing_traitsets = {doc["_key"]: doc for doc in traitsets_col.all()}
    for key, doc in existing_traitsets.items():
        old = doc.get("universes") or []
        new = [normalize(u) for u in old]
        if old == new:
            continue
        if norm_dry:
            norm_ts += 1
            if norm_ts <= 5:
                print(f"  {dry_run_prefix}NORM TS: {doc.get('name','')} ({key})")
                print(f"           {old[:3]}{'…' if len(old)>3 else ''} → {new[:3]}{'…' if len(new)>3 else ''}")
        else:
            doc["universes"] = new
            traitsets_col.update(doc)
            norm_ts += 1

    # Normalize trait universes
    existing_traits = list(traits_col.all())
    for doc in existing_traits:
        old = doc.get("universes") or []
        new = [normalize(u) for u in old]
        if old == new:
            continue
        if norm_dry:
            norm_tr += 1
        else:
            doc["universes"] = new
            traits_col.update(doc)
            norm_tr += 1

    if norm_dry and norm_tr <= 10:
        # Show a few trait examples
        shown = 0
        for doc in existing_traits:
            old = doc.get("universes") or []
            new = [normalize(u) for u in old]
            if old != new and shown < 5:
                print(f"  {dry_run_prefix}NORM TR: {doc.get('name','')} ({doc['_key']})")
                print(f"           {old[:3]}{'…' if len(old)>3 else ''} → {new[:3]}{'…' if len(new)>3 else ''}")
                shown += 1

    norm_skip = len(existing_traits) - norm_tr

    # ── Summary ────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"Summary ({dry_run_prefix.strip()}):")
    print(f"  Phase 1 — traitset_id fix:    {already_ok} ok, {fixed} fixed")
    print(f"  Phase 2 — universes fill:     {uni_already} ok, {uni_fixed} filled, {uni_no_ts} no-ts")
    print(f"  Phase 3 — normalize keys:     {norm_ts} tsets, {norm_tr} traits, {norm_skip} skip")
    print(f"  Total traits:                 {len(existing_traits)}")

    if dry_run and (fixed > 0 or uni_fixed > 0 or norm_ts > 0 or norm_tr > 0):
        print(f"\n  Run without --dry-run to apply fixes.")

    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(fixup(dry_run=dry))

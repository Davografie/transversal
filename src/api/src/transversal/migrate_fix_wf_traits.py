"""Fix-up: drop Whispering Forest memory traits wrongly materialized onto entities.

The old app gated the WF "memory replay" settings (11 on the ``default
character`` archetype ``Entities/3`` + 1 on Phaos) by the character's *current
location* (flask ``filter_trait_settings_by_location``). TV2 has no location
gating (D10), so archetype inheritance materialized them onto every descendant
of ``Entities/3`` — unrestricted, which dirtied dozens of character sheets.

This fix-up removes exactly those instances:

- **pure WF pairs** (the only old source is WF-gated) → every instance dropped;
- **mixed pairs** (e.g. ``container`` also comes from two universe-scoped sect
  archetypes plus direct character settings) → an instance is kept when its
  entity reaches a non-WF source (direct setting or archetype ancestor), and
  dropped only when the WF source is its sole origin;
- instances whose entity reaches no WF source at all (e.g. user-added in-app)
  are kept.

Idempotent: re-running after an apply reports ``to_delete: 0``. Dry-run by
default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_fix_wf_traits [--apply]
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from transversal.db.repository import EntityRepository
from transversal.migrate_common import (
    build_archetype_depths,
    build_entity_key_map,
    load_json,
)
from transversal.migrate_traitsettings import (
    WF_ROOT,
    build_location_subtree,
    is_wf_gated,
)


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    tsettings = load_json("traitsettings.json")

    wf_keys = build_location_subtree(WF_ROOT, relations)

    # ── Old-side sources per (trait ref, statement) ──────
    # Only pairs with at least one WF-gated source are targets.
    wf_pairs = {
        (s["_to"], s.get("statement") or "")
        for s in tsettings
        if is_wf_gated(s, wf_keys)
    }
    wf_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    other_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in tsettings:
        pair = (s["_to"], s.get("statement") or "")
        if pair not in wf_pairs:
            continue
        (wf_sources if is_wf_gated(s, wf_keys) else other_sources)[pair].add(s["_from"])

    print(f"WF-gated source settings → {len(wf_pairs)} distinct (trait, statement) pairs")
    for pair in sorted(wf_pairs):
        print(
            f"  {pair[0]:22s} stmt={pair[1]!r:30s}"
            f"  wf_sources={len(wf_sources[pair])} other_sources={len(other_sources[pair])}"
        )

    # ── Old→new key maps ────────────────────────────────
    new_to_old = {v: k for k, v in build_entity_key_map(entities, relations).items()}
    arch_depths = build_archetype_depths(relations)

    def reaches(old_ref: str, sources: set[str]) -> bool:
        """True when ``old_ref`` is, or inherits from, one of ``sources``."""
        if not sources:
            return False
        if old_ref in sources:
            return True
        return bool(set(arch_depths.get(old_ref, {})) & sources)

    # ── Scan live instances ─────────────────────────────
    repo = EntityRepository()
    all_ts = repo.list_all_traitsettings()

    report: Counter = Counter()
    per_pair: dict[tuple[str, str], Counter] = defaultdict(Counter)
    to_delete: list[str] = []
    for ts in all_ts:
        pair = (f"Traits/{ts.trait_id.removeprefix('trait-')}", ts.statement or "")
        if pair not in wf_pairs:
            continue
        old_ref = new_to_old.get(ts.entity_id)
        if old_ref is None:
            report["unresolved_entity"] += 1
            per_pair[pair]["unresolved"] += 1
            continue
        if not reaches(old_ref, wf_sources[pair]):
            report["kept_unrelated"] += 1       # user-added in-app, or another origin
            per_pair[pair]["kept_unrelated"] += 1
        elif reaches(old_ref, other_sources[pair]):
            report["kept_has_other_source"] += 1  # legit source (sect archetype etc.)
            per_pair[pair]["kept_other"] += 1
        else:
            to_delete.append(ts.id)
            report["wf_derived"] += 1
            per_pair[pair]["delete"] += 1

    delete_set = set(to_delete)
    cascaded = sum(
        1 for ts in all_ts
        if ts.parent_traitsetting_id and ts.parent_traitsetting_id in delete_set
    )

    print()
    print("=== WF TRAIT FIX-UP ===")
    print(f"apply={apply}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    if cascaded:
        print(f"  subtraits_cascaded: {cascaded}")
    print(f"  to_delete: {len(to_delete)}")
    print("  per pair (delete / keep-other / keep-unrelated):")
    for pair in sorted(wf_pairs):
        c = per_pair[pair]
        print(
            f"    {pair[0]:20s} stmt={pair[1]!r:30s}"
            f"  {c['delete']:3d} / {c['kept_other']:2d} / {c['kept_unrelated']:2d}"
        )
    for key in to_delete[:12]:
        print(f"    - {key}")
    if len(to_delete) > 12:
        print(f"    … and {len(to_delete) - 12} more")

    if apply and to_delete:
        removed = repo._delete_traitsettings_subtree(to_delete)
        print(f"  removed: {removed}")

    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

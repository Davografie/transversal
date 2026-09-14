"""Fix-up: re-anchor inherited traits whose universe gating was flattened away.

`materialize_inheritance` copies archetype settings onto descendants, and D10
strips the ancestor's location scoping from the copy. For settings whose *own*
`locations_disabled` names the Multiverse — e.g. the `default character`
archetype's Earth-scoped `tool`/"Smartphone" and `legal document`/"Passport",
or the Azure Dawn Sect Disciple's Three-Realm-scoped `container` — that left
the ego/morph decision with no signal, so they materialized as unrestricted ego
traits instead of morph traits of the gated projection.

The corrected migration (`carries_morph_gating`) classifies them as morph. This
fix-up removes the stale instances; then re-run the migration to recreate them
on the right projections:

    docker compose exec api python -m transversal.migrate_traitsettings --apply --include-archetypes

Only instances whose entity inherits one of the affected sources are touched
(the Whispering Forest sources are excluded — Phase 4 skips them, and
[[migrate_fix_wf_traits]] already handled their fallout). Dry-run by default.
Pass ``--apply`` to delete.

Usage:
    docker compose exec api python -m transversal.migrate_fix_inherited_gating [--apply]
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
    build_default_gating,
    build_location_subtree,
    carries_morph_gating,
    is_wf_gated,
)


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    traits = load_json("traits.json")
    tsettings = load_json("traitsettings.json")

    depths = build_archetype_depths(relations)
    ancestors: set[str] = set()
    for d in depths.values():
        ancestors |= set(d)

    tdef_dis, sdef_dis = build_default_gating(tsettings)
    trait_tset_of = {
        t["_key"]: (t.get("traitset") or "").split("/")[-1] for t in traits
    }
    wf_keys = build_location_subtree(WF_ROOT, relations)

    # Affected (trait, statement) pairs → source entity refs whose gating only
    # lived on the setting itself. WF-gated sources are excluded — Phase 4
    # skips them entirely ([[migrate_fix_wf_traits]] owns their fallout).
    sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in tsettings:
        src = s.get("_from") or ""
        if src not in ancestors or is_wf_gated(s, wf_keys):
            continue
        if not carries_morph_gating(s, tdef_dis, sdef_dis, trait_tset_of):
            continue
        pair = (f"trait-{s['_to'].split('/')[1]}", s.get("statement") or "")
        sources[pair].add(src)

    print(f"affected (trait, statement) pairs: {len(sources)}")
    for pair in sorted(sources):
        print(f"  {pair[0]:28s} stmt={pair[1]!r:32s} sources={len(sources[pair])}")

    new_to_old = {
        v: k
        for k, v in build_entity_key_map(
            entities, relations, include_archetypes=True
        ).items()
    }

    repo = EntityRepository()
    all_ts = repo.list_all_traitsettings()

    report: Counter = Counter()
    per_pair: dict[tuple[str, str], Counter] = defaultdict(Counter)
    to_delete: list[str] = []
    to_delete_set: set[str] = set()
    for ts in all_ts:
        pair = (ts.trait_id, ts.statement or "")
        if pair not in sources:
            continue
        if ts.parent_traitsetting_id:
            continue  # sub-traits cascade with their parent
        old_ref = new_to_old.get(ts.entity_id)
        if old_ref is None:
            report["unresolved_entity"] += 1
            per_pair[pair]["unresolved"] += 1
            continue
        if not (set(depths.get(old_ref, {})) & sources[pair]):
            report["kept_unrelated"] += 1
            per_pair[pair]["kept"] += 1
            continue
        to_delete.append(ts.id)
        to_delete_set.add(ts.id)
        report["stale"] += 1
        per_pair[pair]["delete"] += 1
        if ts.spent_dice or ts.sfx_ids:
            report["has_play_state"] += 1

    cascaded = sum(
        1 for ts in all_ts
        if ts.parent_traitsetting_id and ts.parent_traitsetting_id in to_delete_set
    )

    print()
    print("=== INHERITED-GATING FIX-UP ===")
    print(f"apply={apply}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    if cascaded:
        print(f"  subtraits_cascaded: {cascaded}")
    print(f"  to_delete: {len(to_delete)}")
    print("  per pair (delete / keep-unrelated):")
    for pair in sorted(sources):
        c = per_pair[pair]
        print(
            f"    {pair[0]:26s} stmt={pair[1]!r:30s}"
            f"  {c['delete']:4d} / {c['kept']:3d}"
        )
    for key in to_delete[:10]:
        print(f"    - {key}")
    if len(to_delete) > 10:
        print(f"    … and {len(to_delete) - 10} more")

    if apply and to_delete:
        removed = repo._delete_traitsettings_subtree(to_delete)
        print(f"  removed: {removed}")
        print("  next: python -m transversal.migrate_traitsettings --apply --include-archetypes")

    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

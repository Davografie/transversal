"""One-off backfill: ensure every entity with images has a navdot role image.

The media migration mapped ``portrait*``→``sheet`` and ``original/large/small/
mini``→``background`` but left ``navdot`` untagged, so entities with images
rendered initials in their map dots. This pass fixes the current data:

- Base role: any image with no roles gets ``sheet`` (character/GMC) or
  ``background`` (everything else), so the handful of untagged images resolve.
- Navdot: for each entity with >=1 image but no ``navdot``-role image, tag the
  best candidate — a ``sheet`` image first, else a ``background`` image, else
  the newest image.

Idempotent (only adds roles, never removes) and scoped to entities that still
exist; orphaned ``entity_images`` (whose ``entity_id`` no longer matches an
entity key) are reported but left untouched — those need the data-migration
session's key remap, not a role tag.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.backfill_navdot_roles
    docker compose exec api python -m transversal.backfill_navdot_roles --apply
"""

from __future__ import annotations

import sys
from collections import defaultdict

from transversal.db.arango import get_db, ENTITIES, IMAGES

SHEET_TYPES = {"character", "gmc"}


def migrate(apply: bool = False) -> int:
    db = get_db()
    entities = db.collection(ENTITIES)
    images_col = db.collection(IMAGES)

    entity_types = {e["_key"]: e.get("type", "") for e in entities.all()}

    by_entity: dict[str, list[dict]] = defaultdict(list)
    for img in images_col.all():
        by_entity[img["entity_id"]].append(img)

    base_assigned = 0
    navdot_assigned = 0
    skipped_has_navdot = 0
    orphaned: list[str] = []

    for eid in sorted(by_entity):
        etype = entity_types.get(eid)
        if etype is None:
            orphaned.append(eid)
            continue

        imgs = sorted(by_entity[eid], key=lambda d: d.get("created_at") or "", reverse=True)

        # 1. Base role for images with no roles.
        for img in imgs:
            if img.get("roles"):
                continue
            base = "sheet" if etype in SHEET_TYPES else "background"
            live = images_col.get(img["_key"])
            if live is None or (live.get("roles") or []):
                continue
            marker = "APPLY " if apply else "DRY-RUN"
            print(f"{marker} base  {eid} ({etype}) {img['_key']} -> ['{base}']")
            if apply:
                images_col.update({**live, "roles": [base]})
            base_assigned += 1

        # Re-read after base assignment.
        current = sorted(
            images_col.find({"entity_id": eid}),
            key=lambda d: d.get("created_at") or "",
            reverse=True,
        )

        # 2. Navdot if missing.
        if any("navdot" in (i.get("roles") or []) for i in current):
            skipped_has_navdot += 1
            continue

        target = (
            next((i for i in current if "sheet" in (i.get("roles") or [])), None)
            or next((i for i in current if "background" in (i.get("roles") or [])), None)
            or (current[0] if current else None)
        )
        if target is None:
            continue
        live = images_col.get(target["_key"])
        if live is None:
            continue
        roles = list(live.get("roles") or [])
        if "navdot" in roles:
            skipped_has_navdot += 1
            continue
        roles.append("navdot")
        marker = "APPLY " if apply else "DRY-RUN"
        print(f"{marker} navdot {eid} ({etype}) {target['_key']} -> {roles}")
        if apply:
            images_col.update({**live, "roles": roles})
        navdot_assigned += 1

    print()
    print("=== NAVDOT BACKFILL ===")
    print(f"apply={apply}")
    print(f"  base roles assigned:   {base_assigned}")
    print(f"  navdot roles assigned: {navdot_assigned}")
    print(f"  skipped (has navdot):  {skipped_has_navdot}")
    print(f"  orphaned entities:     {len(orphaned)}")
    if orphaned:
        print("  orphaned entity_ids (need key remap, not a role tag):")
        for eid in orphaned:
            print(f"    - {eid}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

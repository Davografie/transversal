"""Assign role-tagged images to their owning projection (body).

Entity images now carry an optional ``projection_id``. Empty means entity-level
(the "soul default", used as fallback for any body); a concrete id means the
image belongs to that body. Role uniqueness is now keyed on the owner
(projection id or entity id) plus role, so two entity-level images carrying the
same role across different universes would collapse. This script prevents that
by moving universe-specific images onto the projection that lives in that
universe.

Mapping for each image with at least one role tag:
  * Find the entity's projections whose ``origin_universe`` (falling back to
    ``universe``) equals the image's ``universe``.
  * Exactly one match → assign ``projection_id``.
  * Several matches → use ``current_projection`` when it is among them, else
    leave entity-level (ambiguous).
  * No match → leave entity-level.

Images with no roles are left untouched (ownership is decided by the user via
the gallery drag, not inferred here).

Usage:
    docker compose exec api python -m transversal.backfill_projection_images --dry-run
    docker compose exec api python -m transversal.backfill_projection_images
"""

from __future__ import annotations

import sys

from transversal.db.arango import get_db, ENTITIES, IMAGES, PROJECTIONS


def migrate(dry_run: bool = True) -> int:
    db = get_db()
    entities = db.collection(ENTITIES)
    projections = db.collection(PROJECTIONS)
    images_col = db.collection(IMAGES)

    assigned = 0
    left_entity = 0
    skipped_no_roles = 0

    for entity in entities.all():
        entity_id = entity["_key"]
        current_projection = entity.get("current_projection")

        # Index projections by their home universe for this entity.
        projs = list(projections.find({"entity_id": entity_id}))
        by_universe: dict[str, list[dict]] = {}
        for p in projs:
            home = p.get("origin_universe") or p.get("universe") or ""
            by_universe.setdefault(home, []).append(p)

        for img in images_col.find({"entity_id": entity_id}):
            roles = img.get("roles") or []
            if not roles:
                skipped_no_roles += 1
                continue

            universe = img.get("universe") or ""
            candidates = by_universe.get(universe, [])
            target = None

            if len(candidates) == 1:
                target = candidates[0]
            elif len(candidates) > 1 and current_projection:
                target = next(
                    (p for p in candidates if p["_key"] == current_projection),
                    None,
                )

            if target is None:
                left_entity += 1
                continue

            live = images_col.get(img["_key"])
            if live is None:
                continue
            if live.get("projection_id") == target["_key"]:
                left_entity += 1  # already assigned, nothing to do
                continue

            marker = "DRY-RUN" if dry_run else "APPLY  "
            print(
                f"{marker} {entity_id} ({entity.get('name','')}) image {img['_key']} "
                f"(universe={universe}, roles={roles}) → projection {target['_key']}"
            )
            if not dry_run:
                images_col.update({**live, "projection_id": target["_key"]})
            assigned += 1

    print(f"\n{'='*60}")
    print(f"Summary ({'dry-run' if dry_run else 'applied'}):")
    print(f"  images assigned to projections:  {assigned}")
    print(f"  images left entity-level:        {left_entity}")
    print(f"  images skipped (no roles):       {skipped_no_roles}")
    if dry_run and assigned:
        print("\n  Run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(migrate(dry_run=dry))

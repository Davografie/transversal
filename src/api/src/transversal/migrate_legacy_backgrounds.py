"""Transition legacy entity ``background_image`` fields to role-tagged images.

Before this migration, entities could carry a denormalized ``background_image``
string (e.g. ``/media/loc-xxx.webp``) with no matching image holding the
``background`` role tag.  The role-based ``Entity.image(role)`` resolver ignores
that legacy field, so those entities would resolve to ``null``.

This script assigns the ``background`` role to the appropriate ``entity_images``
document so the role-based resolver takes over:

  1. If the legacy path references an image whose filename appears in the path
     (e.g. ``.../Phaos_Tyish_..._anim_dd0b42ed.webm`` → image ``dd0b42ed``),
     that image gets the role.  This preserves animated backgrounds.
  2. Otherwise, the entity's earliest-created image ("first available") gets
     the role.

The legacy ``background_image`` field is left intact — the existing
``background_image`` resolver already prefers role tags, so after this run the
old and new resolvers agree.

Usage:
    docker compose exec api python -m transversal.migrate_legacy_backgrounds --dry-run
    docker compose exec api python -m transversal.migrate_legacy_backgrounds
"""

from __future__ import annotations

import sys

from transversal.db.arango import get_db, ENTITIES, ENTITY_IMAGES


def migrate(dry_run: bool = True) -> int:
    db = get_db()
    entities = db.collection(ENTITIES)
    images_col = db.collection(ENTITY_IMAGES)

    assigned = 0
    skipped_already = 0
    skipped_no_images = 0
    matched_by_path = 0
    matched_by_first = 0

    for entity in entities.all():
        legacy = entity.get("background_image")
        if not legacy:
            continue
        entity_id = entity["_key"]

        imgs = list(images_col.find({"entity_id": entity_id}))
        imgs.sort(key=lambda d: d.get("created_at") or "")

        if any("background" in (img.get("roles") or []) for img in imgs):
            skipped_already += 1
            continue
        if not imgs:
            skipped_no_images += 1
            continue

        # 1) Prefer the image whose filename (with/without extension) appears
        #    in the legacy path — preserves e.g. animated backgrounds.
        chosen = None
        for img in imgs:
            filename = img.get("filename") or ""
            ext = img.get("extension") or ""
            if filename and filename in legacy:
                chosen = img
                break
            if filename and ext and f"{filename}.{ext}" in legacy:
                chosen = img
                break

        by_path = chosen is not None
        if chosen is None:
            # 2) Fall back to the earliest-created ("first available") image.
            chosen = imgs[0]
            matched_by_first += 1
        else:
            matched_by_path += 1

        roles = list(chosen.get("roles") or [])
        if "background" in roles:
            skipped_already += 1
            continue
        roles.append("background")

        marker = "DRY-RUN" if dry_run else "APPLY  "
        print(
            f"{marker} {entity_id} ({entity.get('name','')}) "
            f"→ image {chosen['_key']} ({chosen.get('image_type','')}, "
            f"{'path-match' if by_path else 'first-available'})"
        )

        if not dry_run:
            images_col.update({**chosen, "roles": roles})
        assigned += 1

    print(f"\n{'='*60}")
    print(f"Summary ({'dry-run' if dry_run else 'applied'}):")
    print(f"  assigned 'background' role:  {assigned}")
    print(f"    matched by legacy path:    {matched_by_path}")
    print(f"    matched by first-available:{matched_by_first}")
    print(f"  skipped (already had role):  {skipped_already}")
    print(f"  skipped (no images):         {skipped_no_images}")
    if dry_run and assigned:
        print("\n  Run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(migrate(dry_run=dry))

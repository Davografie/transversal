"""Backfill canonical image role tags (background / navdot / sheet).

Entities historically carried a denormalized ``background_image`` string (e.g.
``/media/loc-xxx.webp``) with no matching ``entity_images`` document holding the
role tag.  The role-based ``Entity.image(role)`` resolver ignores that legacy
field, so such entities resolve to ``null`` for the missing roles.

This script targets entities that still carry the legacy ``background_image``
field, and ensures their images carry all three canonical role tags, assigning
each *missing* role to the appropriate image:

  * ``background`` — the image referenced by the legacy path (preserves animated
    backgrounds, e.g. ``..._anim_xxx.webm`` → that animated image), else the
    earliest-created image.
  * ``navdot`` / ``sheet`` — the earliest static (non-animated) image, else the
    earliest image.  Dots and portraits are small; the static upload is the
    natural source.  (In practice the earliest image is always static.)

Only *missing* roles are assigned — existing role tags are never moved or
removed, so uniqueness (universe + role) is preserved.  The legacy
``background_image`` field is left intact; the ``background_image`` resolver
already prefers role tags, so old and new resolvers agree after this run.

Usage:
    docker compose exec api python -m transversal.backfill_image_roles --dry-run
    docker compose exec api python -m transversal.backfill_image_roles
"""

from __future__ import annotations

import sys

from transversal.db.arango import get_db, ENTITIES, ENTITY_IMAGES

ROLES = ("background", "navdot", "sheet")


def migrate(dry_run: bool = True) -> int:
    db = get_db()
    entities = db.collection(ENTITIES)
    images_col = db.collection(ENTITY_IMAGES)

    assigned = 0
    skipped_complete = 0
    skipped_no_images = 0
    background_by_path = 0
    background_first = 0

    for entity in entities.all():
        legacy = entity.get("background_image")
        if not legacy:
            continue  # only migrate entities still on the legacy field

        entity_id = entity["_key"]
        imgs = list(images_col.find({"entity_id": entity_id}))
        imgs.sort(key=lambda d: d.get("created_at") or "")

        if not imgs:
            skipped_no_images += 1
            continue

        present = set()
        for img in imgs:
            present.update(img.get("roles") or [])
        missing = [r for r in ROLES if r not in present]
        if not missing:
            skipped_complete += 1
            continue

        # background target: legacy-path match, else earliest.
        bg_target = None
        bg_by_path = False
        for img in imgs:
            filename = img.get("filename") or ""
            ext = img.get("extension") or ""
            if (filename and filename in legacy) or (filename and ext and f"{filename}.{ext}" in legacy):
                bg_target = img
                bg_by_path = True
                break
        if bg_target is None:
            bg_target = imgs[0]

        # navdot/sheet target: earliest static image, else earliest.
        static = next((img for img in imgs if img.get("image_type") != "animated"), None) or imgs[0]

        for role in missing:
            target = bg_target if role == "background" else static
            # Re-read the live document — the same image often receives multiple
            # roles, and reusing a stale snapshot would fail with a _rev conflict.
            live = images_col.get(target["_key"])
            if live is None:
                continue
            roles = list(live.get("roles") or [])
            if role in roles:
                continue
            roles.append(role)

            if role == "background":
                label = "path-match" if bg_by_path else "first-available"
                if bg_by_path:
                    background_by_path += 1
                else:
                    background_first += 1
            else:
                label = "static"

            marker = "DRY-RUN" if dry_run else "APPLY  "
            print(
                f"{marker} {entity_id} ({entity.get('name','')}) "
                f"role={role} → image {target['_key']} "
                f"({target.get('image_type','')}, {label})"
            )

            if not dry_run:
                images_col.update({**live, "roles": roles})
            assigned += 1

    print(f"\n{'='*60}")
    print(f"Summary ({'dry-run' if dry_run else 'applied'}):")
    print(f"  roles assigned:               {assigned}")
    print(f"    background by legacy path:  {background_by_path}")
    print(f"    background by first-avail:  {background_first}")
    print(f"  skipped (complete):           {skipped_complete}")
    print(f"  skipped (no images):          {skipped_no_images}")
    if dry_run and assigned:
        print("\n  Run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(migrate(dry_run=dry))

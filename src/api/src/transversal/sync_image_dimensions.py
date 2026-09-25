"""Make every image record's width/height match the master file on disk.

`MediaImage.width`/`height` are written once, at ingestion, and nothing has ever
maintained them. Two ways that went wrong:

- **Upscaling changes the master** ([[B207]]) without touching the record, so the
  GM gallery kept reporting the pre-upscale size — the image looked un-upscaled.
- **708 of 1125 records say ``0×0``**, because the paths that created them
  (migration, and some upload routes) never measured the image at all.

The dimensions shown in the UI are the only size a user ever sees, so they are
worth being true. The **master** is the authority: `Original` is the archival copy
and every tier is derived from it, so the record describes `Original`.

Idempotent, dry-run by default.

Usage::

    docker compose exec api python -m transversal.sync_image_dimensions
    docker compose exec api python -m transversal.sync_image_dimensions --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from transversal.db.arango import IMAGES, get_db

IMAGEN_DIR = Path("/app/media/imagen")


def migrate(apply: bool = False) -> int:
    db = get_db()
    images = db.collection(IMAGES)

    checked = fixed = missing = 0
    for doc in sorted(images.all(), key=lambda d: d.get("_key") or ""):
        if (doc.get("image_type") or "") == "animated":
            continue  # a loop's "master" is the video; width/height are its frame
        path = (
            IMAGEN_DIR
            / (doc.get("owner_id") or "")
            / (doc.get("universe") or "")
            / f"{doc.get('filename')}_Original.{doc.get('extension') or 'webp'}"
        )
        if not path.exists():
            missing += 1
            continue
        checked += 1
        with Image.open(path) as im:
            actual = im.size
        if (doc.get("width"), doc.get("height")) == actual:
            continue
        if apply:
            images.update({"_key": doc["_key"], "width": actual[0], "height": actual[1]})
        elif fixed < 10:
            print(f"  {doc.get('filename')} ({doc.get('owner_id')}): "
                  f"{doc.get('width')}x{doc.get('height')} -> {actual[0]}x{actual[1]}")
        fixed += 1

    print()
    print("=== IMAGE DIMENSION SYNC ===")
    print(f"apply={apply}")
    print(f"  static images with a master: {checked}")
    print(f"  corrected:                   {fixed}")
    print(f"  master missing:              {missing}")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))

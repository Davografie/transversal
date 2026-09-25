"""One-off backfill: mark EntityImages whose files have transparent backgrounds.

Detects transparency from each image's ``_Original.webp`` (an alpha channel
with any non-opaque pixel) and sets ``MediaImage.transparent`` accordingly.
Animated images are skipped (videos have no alpha). Idempotent — only writes
rows whose flag differs — and dry-run by default.

Usage:
    docker compose exec api python -m transversal.backfill_transparency
    docker compose exec api python -m transversal.backfill_transparency --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

from transversal.db.arango import get_db, ENTITY_IMAGES
from transversal.services.media_utils import has_transparency

MEDIA_DIR = Path("/app/media")
IMAGEN_DIR = MEDIA_DIR / "imagen"


def migrate(apply: bool = False) -> int:
    db = get_db()
    images_col = db.collection(ENTITY_IMAGES)

    flagged = 0
    already_ok = 0
    missing_file = 0
    animated = 0

    docs = sorted(images_col.all(), key=lambda d: d.get("entity_id") or "")
    for doc in docs:
        key = doc.get("_key") or doc.get("id")
        if (doc.get("image_type") or "") == "animated":
            animated += 1
            continue

        filename = doc.get("filename") or ""
        entity_id = doc.get("entity_id") or ""
        universe = doc.get("universe") or ""
        extension = doc.get("extension") or "webp"
        if not filename or not entity_id or not universe:
            missing_file += 1
            continue

        path = IMAGEN_DIR / entity_id / universe / f"{filename}_Original.{extension}"
        if not path.exists():
            missing_file += 1
            continue

        actual = has_transparency(path.read_bytes())
        recorded = bool(doc.get("transparent"))
        if actual == recorded:
            already_ok += 1
            continue

        marker = "APPLY " if apply else "DRY-RUN"
        print(f"{marker} {key} ({entity_id}) transparent={actual} (was {recorded})")
        if apply:
            live = images_col.get(key)
            if live is not None:
                images_col.update({**live, "transparent": actual})
        flagged += 1

    print()
    print("=== TRANSPARENCY BACKFILL ===")
    print(f"apply={apply}")
    print(f"  flagged (updated):   {flagged}")
    print(f"  already correct:     {already_ok}")
    print(f"  animated (skipped):  {animated}")
    print(f"  missing/unparseable: {missing_file}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

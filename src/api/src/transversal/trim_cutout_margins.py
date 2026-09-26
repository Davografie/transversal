"""One-off: trim the transparent margins off every existing cutout ([[B213]]).

A cutout keeps the **source's canvas**, so its subject is served at whatever
fraction of the frame it happened to occupy. Measured on the live library, 53 of
225 mattes use less than 95% of a side and 17 use less than 85% — the worst
(`Lin`) covers 42%, so every surface drawing it was rendering it at 2.4× smaller
than the tier allowed, floating in empty space.

Trimming discards only transparent pixels, so it cannot lose any of the artwork:
the subject is cropped to its own bounding box (with the small pad
`trim_transparent_margins` documents), and the matte's ladder is re-rendered from
the trimmed master. The **source picture is not touched** — its framing is its
own, and `width`/`height` on the record describe that master, not the matte.

Idempotent by construction: an already-tight matte is returned unchanged by the
helper and skipped, so a second run reports 0. New cutouts are trimmed by the
pipeline itself (`run_remove_background`), so this is only for the ones made
before that.

Dry-run by default. Usage::

    docker compose exec api python -m transversal.trim_cutout_margins
    docker compose exec api python -m transversal.trim_cutout_margins --apply
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

from transversal.db.arango import IMAGES, get_db
from transversal.services.media_utils import save_image_variants, trim_transparent_margins

IMAGEN_DIR = Path("/app/media/imagen")


def migrate(apply: bool = False) -> int:
    db = get_db()
    if not db.has_collection(IMAGES):
        print(f"nothing to do: no {IMAGES} collection")
        return 0

    docs = list(db.aql.execute(
        f"FOR d IN {IMAGES} FILTER 'cutout' IN d.renders RETURN d"
    ))

    total = trimmed = tight = missing = 0
    for doc in docs:
        total += 1
        owner, universe, filename = doc["owner_id"], doc["universe"], doc["filename"]
        directory = IMAGEN_DIR / owner / universe
        master = directory / f"{filename}_Cutout_Original.webp"
        if not master.exists():
            missing += 1
            print(f"  SKIP {filename}: no matte master at {master}")
            continue

        data = master.read_bytes()
        trimmed_bytes, changed = trim_transparent_margins(data)
        if not changed:
            tight += 1
            continue

        with Image.open(io.BytesIO(data)) as before:
            old = before.size
        with Image.open(io.BytesIO(trimmed_bytes)) as after:
            new = after.size
        # A tier is fitted to the long side, so a smaller canvas means the subject
        # is scaled *up* to fill it: the subject's rendered size grows by
        # old/new. (For the first pass this read backwards.)
        gain = max(old) / max(new)
        print(f"  TRIM {filename} ({owner}): {old[0]}x{old[1]} -> {new[0]}x{new[1]} "
              f"(subject renders {gain:.2f}x larger)")

        if apply:
            # Rewrites the whole Cutout ladder from the trimmed master, so every
            # tier a surface asks for is derived from the crop.
            save_image_variants(trimmed_bytes, directory, f"{filename}_Cutout")
        trimmed += 1

    print()
    print("=== CUTOUT MARGIN TRIM (B213) ===")
    print(f"apply={apply}")
    print(f"  cutouts:      {total}")
    print(f"  trimmed:      {trimmed}")
    print(f"  already tight: {tight}")
    if missing:
        print(f"  ! missing master: {missing}")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))

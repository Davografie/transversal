"""Re-render every image's variants from its stored ``_Original``.

Two things are wrong with the variants already on disk, and both are fixed by
rebuilding them from the master that sits beside them:

1. **Portraits were squeezed.** Two copies of the variant logic existed and
   disagreed; the one the generation pipelines used scaled portraits on the width
   axis, turning an 832×1216 master into 478×700. The survivor scales to fit the
   long side, aspect preserved.
2. **There was no tier big enough for a full-bleed backdrop.** ``Large`` caps at
   1024, but a location backdrop is drawn at viewport size — a 1080p screen wants
   ~1920 device pixels and a phone held portrait ~1170×2532. ``XLarge`` (2048,
   never upscaled) is what the ``background`` role now renders from.

Nothing is generated or interpolated beyond the tiers' own scaling, so this is a
CPU job: it recovers detail that is already in the masters and adds no invented
pixels. Animated images are skipped — they have no variant set.

Idempotent: re-running rebuilds the same bytes. Dry-run by default.

Usage::

    docker compose exec api python -m transversal.rerender_image_variants
    docker compose exec api python -m transversal.rerender_image_variants --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from transversal.db.arango import IMAGES, get_db
from transversal.services.media_utils import VARIANT_LONG_SIDES, save_image_variants

IMAGEN_DIR = Path("/app/media/imagen")
ANIMATED_DIR = Path("/app/media/animated")


def _expected(long_side: int, tier: str) -> int:
    """The long side this tier should end up with, given the master's."""
    cap = VARIANT_LONG_SIDES[tier]
    return min(long_side, cap)


def migrate(apply: bool = False) -> int:
    db = get_db()
    images = db.collection(IMAGES)

    processed = 0
    stale = 0
    missing = 0
    skipped_animated = 0
    gained_pixels = 0
    added_bytes = 0

    for doc in sorted(images.all(), key=lambda d: d.get("_key") or ""):
        if (doc.get("image_type") or "") == "animated":
            skipped_animated += 1
            continue

        owner = doc.get("owner_id") or ""
        universe = doc.get("universe") or ""
        filename = doc.get("filename") or ""
        ext = doc.get("extension") or "webp"
        if not (owner and universe and filename):
            missing += 1
            continue

        out_dir = IMAGEN_DIR / owner / universe
        original = out_dir / f"{filename}_Original.{ext}"
        if not original.exists():
            missing += 1
            continue
        processed += 1

        data = original.read_bytes()
        with Image.open(original) as im:
            master_long = max(im.size)

        # Is any tier currently wrong? Compare the dimensions on disk with what
        # the ladder says they should be.
        wrong = False
        before_bytes = 0
        before_pixels = 0
        for tier, cap in VARIANT_LONG_SIDES.items():
            path = out_dir / f"{filename}_{tier}.webp"
            want = _expected(master_long, tier)
            if not path.exists():
                wrong = True
                continue
            with Image.open(path) as im:
                have_long = max(im.size)
            before_bytes += path.stat().st_size
            before_pixels += im.size[0] * im.size[1] if False else 0
            if have_long != want:
                wrong = True

        if not wrong:
            continue

        stale += 1
        if not apply:
            # Say what the biggest tier would become, which is the point of the run.
            with Image.open(original) as im:
                w, h = im.size
            print(f"STALE {filename} ({owner}) master {w}x{h} -> XLarge "
                  f"{_expected(master_long, 'XLarge')} long side")
            continue

        save_image_variants(data, out_dir, filename)
        after_bytes = sum(
            (out_dir / f"{filename}_{tier}.webp").stat().st_size
            for tier in VARIANT_LONG_SIDES
            if (out_dir / f"{filename}_{tier}.webp").exists()
        )
        added_bytes += after_bytes - before_bytes

    print()
    print("=== VARIANT RE-RENDER ===")
    print(f"apply={apply}")
    print(f"  static images examined: {processed}")
    print(f"  already current:        {processed - stale}")
    print(f"  rebuilt (stale):        {stale}")
    print(f"  skipped (animated):     {skipped_animated}")
    print(f"  missing original:       {missing}")
    if apply:
        print(f"  net bytes added:        {added_bytes / 1e6:.1f} MB")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))

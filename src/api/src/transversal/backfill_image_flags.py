"""One-off backfill: stamp provenance flags on images that predate them.

`MediaImage.flags` carries provenance labels — ``ai`` (set by a human who knows
AI was in the workflow), ``ai_generated`` (the imagen pipeline), ``ai_animated``
(the animate pipeline). Images created before the field existed have none, but
``image_type`` already records how most of them were made, so the pipeline-set
labels can be derived:

======================  ==================
``image_type``          derived flag
======================  ==================
``imagen``              ``ai_generated``
``animated``            ``ai_animated``
``cutout``              ``ai``
``uploaded``            *(nothing — the provenance of an upload is unknown,
                        which is exactly what the manual ``ai`` label is for)*
======================  ==================

**Additive and idempotent**: a row keeps whatever flags it already has and only
gains the derived one, so a re-run is a no-op and it never erases a label a human
set. A cutout gets ``ai`` because BiRefNet is itself a model — that matches what
a *new* cutout records.

Dry-run by default::

    docker compose exec api python -m transversal.backfill_image_flags
    docker compose exec api python -m transversal.backfill_image_flags --apply
"""

from __future__ import annotations

import sys

from transversal.db.arango import IMAGES, get_db

#: How an image was made decides what it can be labelled without guessing.
DERIVED_FLAGS = {
    "imagen": "ai_generated",
    "animated": "ai_animated",
    "cutout": "ai",
}


def migrate(apply: bool = False) -> int:
    db = get_db()
    images = db.collection(IMAGES)

    stamped = 0
    already_ok = 0
    unknown = 0
    counts: dict[str, int] = {}

    for doc in sorted(images.all(), key=lambda d: d.get("_key") or ""):
        key = doc.get("_key")
        image_type = (doc.get("image_type") or "").lower()
        flags = list(doc.get("flags") or [])

        derived = DERIVED_FLAGS.get(image_type)
        if not derived:
            unknown += 1
            continue

        if derived in flags:
            already_ok += 1
            continue

        merged = sorted(set(flags) | {derived})
        counts[derived] = counts.get(derived, 0) + 1
        if apply:
            images.update({**doc, "flags": merged})
        stamped += 1

    print()
    print("=== IMAGE FLAG BACKFILL ===")
    print(f"apply={apply}")
    print(f"  stamped (updated):   {stamped}")
    print(f"  already carried it:  {already_ok}")
    print(f"  no derivable flag:   {unknown}  (uploads — provenance unknown)")
    for flag, n in sorted(counts.items()):
        print(f"    {flag:<14} {n}")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))

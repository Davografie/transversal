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
``cutout``              *(nothing — the cutter asserts nothing of its own)*
``uploaded``            *(nothing — the provenance of an upload is unknown,
                        which is exactly what the manual ``ai`` label is for)*
======================  ==================

A **cutout derives no flag.** It is tempting to call BiRefNet an AI step and
label every cutout ``ai`` — this script did exactly that in its first cut, and
the human's call is that it should not: only imagen and animate declare AI, and
a cutout is the same picture with its background removed. Cutouts made by the
pipeline still *inherit* their source's labels, so a cutout of a Flux image
remains ``ai_generated``; they simply never gain one of their own.

**Additive and idempotent**: a row keeps whatever flags it already has and only
gains the derived one, so a re-run is a no-op and it never erases a label a human
set.

Dry-run by default::

    docker compose exec api python -m transversal.backfill_image_flags
    docker compose exec api python -m transversal.backfill_image_flags --apply
"""

from __future__ import annotations

import sys

from transversal.db.arango import IMAGES, get_db

#: How an image was made decides what it can be labelled without guessing.
#: No `cutout` entry on purpose — see the module docstring.
DERIVED_FLAGS = {
    "imagen": "ai_generated",
    "animated": "ai_animated",
}


def clear_cutout_ai(apply: bool = False) -> int:
    """Remove the ``ai`` flag the first cut of this script stamped on cutouts.

    A one-off correction, deliberately narrow: it touches only rows whose
    ``image_type`` is ``cutout`` and which carry ``ai``. A human who ticks `[AI]`
    on a cutout afterwards keeps it — this is run once, now, not on every
    backfill.
    """
    db = get_db()
    images = db.collection(IMAGES)

    cleared = 0
    for doc in sorted(images.all(), key=lambda d: d.get("_key") or ""):
        if (doc.get("image_type") or "").lower() != "cutout":
            continue
        flags = list(doc.get("flags") or [])
        if "ai" not in flags:
            continue
        remaining = [f for f in flags if f != "ai"]
        print(f"CLEAR {doc.get('_key')} ({doc.get('owner_id')}) {flags} -> {remaining}")
        if apply:
            images.update({**doc, "flags": remaining})
        cleared += 1

    print()
    print("=== CUTOUT 'ai' CORRECTION ===")
    print(f"apply={apply}")
    print(f"  cutouts cleared of 'ai': {cleared}")
    if not apply:
        print("  (dry run — re-run with --remove-cutout-ai --apply)")
    return 0


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
    if "--remove-cutout-ai" in sys.argv:
        sys.exit(clear_cutout_ai(apply="--apply" in sys.argv))
    sys.exit(migrate(apply="--apply" in sys.argv))

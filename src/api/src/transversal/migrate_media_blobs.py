"""One-shot: move the legacy media tree into the content-addressed store ([[B88]]).

Run inside the API container::

    docker compose exec api python -m transversal.migrate_media_blobs --dry-run
    docker compose exec api python -m transversal.migrate_media_blobs

Before the store existed, a picture's files lived at paths that named **the owner**, not
the content: ``/app/media/imagen/<owner>/<universe>/<filename>_Large.webp``. Because a
fork is a verbatim clone, two campaigns' records point at the *same* file, which is how
a delete in one campaign could destroy another's images. The store removed that by
addressing bytes; this script moves the files that predate it.

For every campaign database it works out where each record's variants live, hashes each
file **once**, copies it into the store, records ``suffix -> digest`` on the record and
retains it in the registry's refcount. Only once every reference is recorded does it
remove the originals — moving first and recording second would leave a record pointing
at a file that is already gone if anything failed in between.

Idempotent, and safe to re-run: a record that already carries blobs is skipped, and a
blob that is already in the store is not written again. ``--keep-legacy`` copies
instead of moving, for a first pass that changes nothing on disk.

**It moves bytes, it does not free them.** The saving is the *dedup* — the same picture
at two owners' paths collapses to one blob — so a run that reports "590 MB moved" has
not reclaimed 590 MB of disk; it has reclaimed whatever was duplicated. Files no record
claims (orphans, or a variant this script does not model) are **left alone and
reported**, because guessing about a file nothing references is how pictures get lost.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from transversal.db.arango import get_db
from transversal.db.arango import use_database
from transversal.db.registry_repository import RegistryRepository
from transversal.services import blobs
from transversal.services.media_store import MEDIA_ROOT
from transversal.services.media_utils import PICTURE_TIERS
from transversal.services.provisioner import campaign_databases

#: The images collection under both names it has had ([[B200]]'s split).
IMAGE_COLLECTIONS = ("images", "entity_images")


def variants_of(doc: dict) -> list[tuple[str, str, str]]:
    """``(kind, suffix, ext)`` for each file one image record's variants live in.

    Mirrors ``RepositoryImages.image_url`` — the one place that knows a picture's
    shape — because a migration that disagreed with the reader would move files to
    addresses the app never asks for, and leave the files it did not think of on the
    owner-named path where two campaigns share them.

    The ladder comes from ``media_utils.PICTURE_TIERS`` rather than a list written
    here, and the **matte keeps the whole ladder**, not one tier: this function used
    to name `_Cutout_Large` alone, so `sheet` — `ROLE_RENDER`'s `cutout/Small` —
    was never migrated and stayed shared between campaigns ([[B88]], 2026-10-16).
    """
    ext = doc.get("extension") or "webp"
    found = [("imagen", f"_{tier}", ext) for tier in PICTURE_TIERS]
    # The pre-upscale master is a backup, not part of the served ladder, but it is
    # still a file in the tree this migration is retiring.
    found.append(("imagen", "_PreUpscale", ext))
    found += [("imagen", f"_Cutout_{tier}", "webp") for tier in PICTURE_TIERS]
    if "animated" in (doc.get("renders") or []):
        found.append(("animated", "", doc.get("animated_extension") or ext))
    return found


def missing_variants(doc: dict) -> list[tuple[str, str, str]]:
    """What this record still needs moved: everything it can have, minus what it
    already records.

    A record is **not skipped for carrying blobs** — it is topped up. Skipping any
    row with blobs is what made the missing matte tiers unhealable: with it, adding
    the tier to the model and re-running would have reported "already migrated" and
    changed nothing at all.
    """
    known = doc.get("blobs") or {}
    return [variant for variant in variants_of(doc) if variant[1] not in known]


def legacy_path(doc: dict, kind: str, suffix: str, ext: str) -> Path:
    """Where a file lived before the store: named for the owner, sharded by universe."""
    owner = doc.get("owner_id") or doc.get("entity_id") or ""
    universe = doc.get("universe") or ""
    filename = doc.get("filename") or ""
    return MEDIA_ROOT / kind / owner / universe / f"{filename}{suffix}.{ext}"


def _images(db, collection: str):
    if not db.has_collection(collection):
        return []
    return list(db.aql.execute(f"FOR d IN {collection} RETURN d"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m transversal.migrate_media_blobs")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would move, write nothing"
    )
    parser.add_argument(
        "--keep-legacy",
        action="store_true",
        help="copy into the store and leave the originals (a no-risk first pass)",
    )
    parser.add_argument(
        "--database", action="append", help="only this campaign (repeatable)"
    )
    args = parser.parse_args(argv)

    registry = RegistryRepository()
    databases = args.database or campaign_databases(registry)

    #: path -> (digest, suffix, ext): hashed and copied once, however many records or
    #: campaigns point at it. This is the whole reason the migration is cheap — the
    #: duplication being removed is exactly the sharing.
    moved: dict[Path, tuple[str, str, str]] = {}
    claimed: set[Path] = set()
    records = 0
    skipped = 0

    for name in databases:
        with use_database(name):
            db = get_db()
            for collection in IMAGE_COLLECTIONS:
                for doc in _images(db, collection):
                    updates: dict[str, str] = {}
                    for kind, suffix, ext in missing_variants(doc):
                        path = legacy_path(doc, kind, suffix, ext)
                        if not path.exists():
                            continue
                        if path not in moved:
                            data = path.read_bytes()
                            if not args.dry_run:
                                blobs.put(data, suffix=suffix, ext=ext)
                            moved[path] = (blobs.digest(data), suffix, ext)
                        digest, suffix, ext = moved[path]
                        updates[suffix] = digest
                        claimed.add(path)
                    if not updates:
                        # Nothing left on disk for this record: it is either complete
                        # or never had the files its shape allows. Counted as skipped
                        # so a re-run converges on "already migrated: <all records>"
                        # rather than re-reporting every record as pending forever.
                        skipped += 1
                        continue
                    records += 1
                    if args.dry_run:
                        continue
                    db.collection(collection).update(
                        {
                            "_key": doc["_key"],
                            # Merged by hand rather than left to the server: a top-up
                            # adds to the digests already recorded, and a shallow
                            # update would replace the object with only the new ones.
                            "blobs": {**(doc.get("blobs") or {}), **updates},
                        }
                    )
                    for digest in updates.values():
                        blobs.retain(digest, ext="webp")

    bytes_moved = sum(p.stat().st_size for p in claimed if p.exists())
    distinct_blobs = len({(d, s, e) for d, s, e in moved.values()})
    print(
        f"files {'to move' if args.dry_run else 'moved'}: {len(moved)}  "
        f"records {'to update' if args.dry_run else 'updated'}: {records}  "
        f"already migrated: {skipped}  "
        f"duplicate files the store collapses: {len(claimed) - distinct_blobs}  "
        f"bytes {'to move' if args.dry_run else 'moved'}: {bytes_moved / 1e6:.1f} MB"
    )

    if args.dry_run or args.keep_legacy:
        if args.dry_run:
            print("dry run: nothing was written", file=sys.stderr)
        return 0

    # Originals go last, and only now: every reference to them is recorded, so nothing
    # can be left pointing at a file that has been deleted.
    for path in claimed:
        try:
            path.unlink()
        except OSError:
            print(f"warning: could not remove {path}", file=sys.stderr)
    print(f"removed {len(claimed)} legacy file(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin wrapper
    sys.exit(main())

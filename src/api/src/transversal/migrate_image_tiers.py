"""One-off: a cutout and a loop become **renders of the picture** they came from.

`B210`. A cutout used to be a picture of its own — its own record, its own base
name — and a loop too. Every cutout defect fixed in September 2026 came from that
one modelling error: credits lost, AI mislabelled, roles redistributed, loops with
no roles. This folds them in. See [[Image Tiers Design Log]].

Two shapes, because the live library has two:

**Cutouts (224) are mechanical.** Every one names its source in ``prompt`` as
``"background removed from {filename}"`` and every source still exists on the same
owner, so the fold is a rename plus a merge:

* files  ``{cut}_{Tier}.webp``  →  ``{source}_Cutout_{Tier}.webp``
* record the source gains ``renders += ["cutout"]``, ``transparent``, and the
  union of the cutout's roles; the cutout's row goes.

The BiRefNet output is **not re-rendered** — the files are moved byte-for-byte.
Only a tier that is missing is rebuilt from the cutout's own ``_Original`` (two
live cutouts have no ``_XLarge``).

**Loops (43) are not mechanical, because a loop record is self-contained**: its
still ladder and its video sit under one base name on one record, so there is
usually no second record to fold into. The source has to be *recovered*, by
matching the loop's still against its owner's other pictures — the animate
pipeline copied those bytes, and re-encoded them, so byte equality misses most of
them while a 64-bit average hash finds them (measured: 28 of 43 within 2 bits;
the other 15 match nothing, so ``run_animate`` generated their still and they
become standalone ``imagen`` pictures). Those 15, minus the one that already
carries ``ai_generated``, are the "fresh loops" the human asked to stamp — a still
that matches nothing on its owner's rung is the evidence the rule would have had.

Two collisions are handled explicitly, both decided by the human (2026-09-25):

* **Two loops on one source** — only one can hold the single ``Animated`` render.
  The newest keeps it and the older record is retired; its video file is left on
  disk rather than deleted.
* **A source that already has a matte** (the new writer ran during the window)
  — the source's own render wins and the legacy cutout record is retired.

**Idempotent, and meant to be re-run.** The containers at `:3000` keep running the
older code until this branch merges, so a cutout or loop created in the meantime
lands in the old shape; re-running picks it up. A row that already carries the
render is skipped.

Dry-run by default. Usage::

    docker compose exec api python -m transversal.migrate_image_tiers
    docker compose exec api python -m transversal.migrate_image_tiers --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from transversal.db.arango import get_db
from transversal.domain import ImageType, MediaImage
from transversal.imagen.orchestrator import ANIMATED_DIR, IMAGEN_DIR
from transversal.services.media_utils import save_image_variants

#: The tiers a ladder is built from, in ladder order.
_TIERS = ("Original", "XLarge", "Large", "Small", "Mini")

#: Bits of difference allowed between two 64-bit average hashes before a loop's
#: still is called a copy of another picture. 2 is what the live library needs:
#: 28 of 43 loops match a sibling at 0-2 bits and the next-closest is 16.
_HASH_TOLERANCE = 2

CUTOUT_PREFIX = "background removed from "


# ── hashing ──────────────────────────────────────────


def average_hash(path: Path) -> int | None:
    """64-bit average hash of an image, or None when it cannot be read.

    Chosen over a byte comparison because the animate pipeline reads the source's
    ``_Large`` and re-encodes what it writes, so a sourced loop's still is the same
    picture but not the same bytes.
    """
    try:
        with Image.open(path) as im:
            grey = im.convert("L").resize((8, 8), Image.LANCZOS)
            # `tobytes` rather than the deprecated `getdata`: 64 greyscale values.
            pixels = list(grey.tobytes())
    except (OSError, ValueError):
        return None
    mean = sum(pixels) / len(pixels)
    return sum(1 << index for index, value in enumerate(pixels) if value >= mean)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ── files ────────────────────────────────────────────


def _still_dir(img: MediaImage) -> Path:
    return IMAGEN_DIR / img.owner_id / img.universe


def _loop_path(img: MediaImage) -> Path:
    return ANIMATED_DIR / img.owner_id / img.universe / f"{img.filename}.{img.extension}"


def _move(src: Path, dest: Path) -> bool:
    """Move one file, creating the directory. False when the source is missing."""
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    return True


def _synthesise_missing_tiers(source: MediaImage, report: dict) -> None:
    """Rebuild a matte's ladder from its own ``_Original`` when a tier is absent.

    Two live cutouts have no ``_XLarge`` (they predate the tier). The whole ladder
    is rewritten from the original rather than the missing tier being resampled
    from a sibling, so nothing is derived from an already-downscaled copy.
    """
    base = _still_dir(source) / f"{source.filename}_Cutout"
    missing = [t for t in _TIERS if not base.with_name(f"{base.name}_{t}.webp").exists()]
    original = base.with_name(f"{base.name}_Original.webp")
    if not missing or not original.exists():
        return
    report["tiers_rebuilt"] += 1
    save_image_variants(original.read_bytes(), _still_dir(source), f"{source.filename}_Cutout")


def _delete_still_ladder(img: MediaImage, report: dict) -> None:
    """Remove a retired record's own still ladder — the picture it was is kept
    elsewhere (or is a duplicate), so these files are unreferenced."""
    directory = _still_dir(img)
    for tier in _TIERS:
        path = directory / f"{img.filename}_{tier}.webp"
        if path.exists():
            path.unlink()
            report["files_deleted"] += 1


# ── the two passes ───────────────────────────────────


def _migrate_cutouts(images: list[MediaImage], by_name: dict, apply: bool, report: dict) -> None:
    for cut in [i for i in images if i.image_type == ImageType.CUTOUT]:
        report["cutouts"] += 1
        source_name = cut.prompt[len(CUTOUT_PREFIX):].strip() if cut.prompt.startswith(CUTOUT_PREFIX) else ""
        source = by_name.get((cut.owner_id, cut.universe, source_name)) if source_name else None
        if source is None:
            report["cutouts_unmatched"] += 1
            print(f"  SKIP cutout {cut.id}: source {source_name or 'UNNAMED'!r} not found on {cut.owner_id}")
            continue
        if source.image_type == ImageType.CUTOUT:
            report["cutouts_unmatched"] += 1
            print(f"  SKIP cutout {cut.id}: its source {source.id} is itself a cutout")
            continue

        if "cutout" in source.available_renders:
            # The new writer made this matte during the transition; the picture's
            # own render is the one to keep.
            report["cutouts_duplicate"] += 1
            print(f"  MERGE cutout {cut.id} -> {source.id}: source already has a matte, retiring the record")
            if apply:
                _delete_still_ladder(cut, report)
                _db_delete(cut.id)
            continue

        report["cutouts_merged"] += 1
        print(f"  MERGE cutout {cut.id} -> {source.id} "
              f"({source_name}: +renders cutout, roles {sorted(set(source.roles) | set(cut.roles))})")
        if not apply:
            continue

        for tier in _TIERS:
            if _move(_still_dir(cut) / f"{cut.filename}_{tier}.webp",
                     _still_dir(source) / f"{source.filename}_Cutout_{tier}.webp"):
                report["files_renamed"] += 1
        _synthesise_missing_tiers(source, report)

        source.renders = sorted(set(source.available_renders) | {"cutout"})
        source.transparent = source.transparent or cut.transparent
        source.roles = sorted(set(source.roles) | set(cut.roles))
        _db_update(source)
        _db_delete(cut.id)


def _migrate_loops(images: list[MediaImage], apply: bool, report: dict) -> None:
    loops = [i for i in images if i.image_type == ImageType.ANIMATED]
    statics = [i for i in images if i.image_type not in (ImageType.CUTOUT, ImageType.ANIMATED)]

    # Match every loop's still against its owner's static pictures.
    matches: dict[str, MediaImage] = {}
    for loop in loops:
        report["loops"] += 1
        digest = average_hash(_still_dir(loop) / f"{loop.filename}_Original.webp")
        if digest is None:
            report["loops_no_still"] += 1
            print(f"  SKIP loop {loop.id}: no readable still to match on")
            continue
        best: tuple[int, MediaImage] | None = None
        for candidate in statics:
            if candidate.owner_id != loop.owner_id:
                continue
            other = average_hash(_still_dir(candidate) / f"{candidate.filename}_Original.webp")
            if other is None:
                continue
            distance = hamming(digest, other)
            if best is None or distance < best[0]:
                best = (distance, candidate)
        if best is not None and best[0] <= _HASH_TOLERANCE:
            matches[loop.id] = best[1]
        else:
            report["loops_fresh"] += 1

    # Only one loop can hold a picture's single Animated render. The human's call
    # is that the **newest** keeps it — it is the later attempt at the same motion,
    # and in the one live case it is also the one carrying a role.
    superseded: dict[str, str] = {}
    winners: dict[str, str] = {}
    for loop in sorted(loops, key=lambda i: i.created_at or "", reverse=True):
        source = matches.get(loop.id)
        if source is None:
            continue
        if source.id in winners:
            superseded[loop.id] = winners[source.id]
        else:
            winners[source.id] = loop.id

    for loop in loops:
        if loop.id in matches and loop.id not in superseded:
            source = matches[loop.id]
            report["loops_sourced"] += 1
            print(f"  MERGE loop {loop.id} -> {source.id} ({source.filename}: +render animated)")
            if apply:
                destination = ANIMATED_DIR / source.owner_id / source.universe / f"{source.filename}.{loop.extension}"
                if destination.exists() and destination != _loop_path(loop):
                    report["loop_video_collisions"] += 1
                    print(f"    ! {destination.name} already exists — leaving both")
                elif _move(_loop_path(loop), destination):
                    report["files_moved"] += 1
                _delete_still_ladder(loop, report)
                source.renders = sorted(set(source.available_renders) | {"animated"})
                source.animated_extension = loop.extension
                source.flags = sorted(set(source.flags) | set(loop.flags))
                # The loop's own roles move onto the picture too: a loop that was
                # tagged `background` is *why* the backdrop animates, and dropping
                # the tag here would silently stop the animation.
                source.roles = sorted(set(source.roles) | set(loop.roles))
                _db_update(source)
                _db_delete(loop.id)
        elif loop.id in superseded:
            report["loops_superseded"] += 1
            print(f"  RETIRE loop {loop.id}: {superseded[loop.id]} already holds the Animated render "
                  f"(its video is left on disk)")
            if apply:
                _delete_still_ladder(loop, report)
                _db_delete(loop.id)
        else:
            # Fresh: the still was generated by run_animate, so the picture is
            # `imagen` and the motion is a render of it. `extension` now names the
            # still, which is why the video's container moves to its own field.
            report["loops_fresh_migrated"] += 1
            add_generated = "ai_generated" not in loop.flags
            if add_generated:
                report["loops_stamped"] += 1
            print(f"  STANDALONE loop {loop.id} -> imagen + animated render"
                  + (" (+ai_generated)" if add_generated else ""))
            if apply:
                loop.image_type = ImageType.IMAGEN
                loop.renders = ["animated"]
                loop.animated_extension = loop.extension
                loop.extension = "webp"
                if add_generated:
                    loop.flags = sorted(set(loop.flags) | {"ai_generated"})
                _db_update(loop)
                _ensure_still_has_xlarge(loop, report)


def _ensure_still_has_xlarge(img: MediaImage, report: dict) -> None:
    """A loop's still ladder predates the XLarge tier (all 43 lack it)."""
    base = _still_dir(img)
    if not (base / f"{img.filename}_XLarge.webp").exists():
        original = base / f"{img.filename}_Original.webp"
        if original.exists():
            report["tiers_rebuilt"] += 1
            save_image_variants(original.read_bytes(), base, img.filename)


# ── db helpers ───────────────────────────────────────


def _collection():
    return get_db().collection("images")


def _db_update(img: MediaImage) -> None:
    _collection().update({**img.model_dump(), "_key": img.id})


def _db_delete(image_id: str) -> None:
    _collection().delete(image_id)


# ── entry point ──────────────────────────────────────


def migrate(apply: bool = False) -> int:
    db = get_db()
    if not db.has_collection("images"):
        print("nothing to do: no `images` collection")
        return 0

    docs = list(db.aql.execute("FOR d IN images RETURN d"))
    images = [MediaImage.model_validate({**d, "id": d["_key"]}) for d in docs]

    # A cutout names its source by filename, so index the pictures that can be one.
    by_name: dict[tuple[str, str, str], MediaImage] = {}
    for img in images:
        if img.image_type == ImageType.CUTOUT:
            continue
        key = (img.owner_id, img.universe, img.filename)
        if key in by_name:
            print(f"  ! two records named {img.filename} on {img.owner_id}/{img.universe}")
        by_name.setdefault(key, img)

    report = {
        "cutouts": 0, "cutouts_merged": 0, "cutouts_unmatched": 0, "cutouts_duplicate": 0,
        "loops": 0, "loops_sourced": 0, "loops_superseded": 0,
        "loops_fresh": 0, "loops_fresh_migrated": 0, "loops_stamped": 0, "loops_no_still": 0,
        "files_renamed": 0, "files_moved": 0, "files_deleted": 0, "tiers_rebuilt": 0,
        "loop_video_collisions": 0,
    }

    print("=== CUTOUTS: fold each matte into its picture ===")
    _migrate_cutouts(images, by_name, apply, report)
    print()
    print("=== LOOPS: a loop is a render, not a picture ===")
    _migrate_loops(images, apply, report)

    print()
    print("=== IMAGE TIER MIGRATION (B210) ===")
    print(f"apply={apply}")
    print(f"  cutouts:  {report['cutouts']} found, {report['cutouts_merged']} merged, "
          f"{report['cutouts_duplicate']} already had a matte, {report['cutouts_unmatched']} unmatched")
    print(f"  loops:    {report['loops']} found, {report['loops_sourced']} sourced, "
          f"{report['loops_superseded']} superseded, {report['loops_fresh']} fresh "
          f"({report['loops_stamped']} stamped ai_generated), {report['loops_no_still']} unreadable")
    print(f"  files:    {report['files_renamed']} matte tiers renamed, {report['files_moved']} videos moved, "
          f"{report['files_deleted']} still tiers removed, {report['tiers_rebuilt']} ladders rebuilt")
    if report["loop_video_collisions"]:
        print(f"  ! {report['loop_video_collisions']} loop videos could not be moved onto the picture")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))

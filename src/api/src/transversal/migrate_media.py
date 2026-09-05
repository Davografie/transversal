"""Media migration: old ``media/uploads`` → new ``EntityImage`` + ``media/imagen``.

Per [[Media Migration Proposal]] and media's response:

- Old files are keyed by old numeric entity key: ``{key}/{variant}.{ext}`` (dirs)
  and ``{key}.{ext}`` (flat files). ``{key}/{location_key}/…`` subdirs are
  per-location (per-universe) appearance.
- Role mapping: ``portrait``/``portrait_small`` → ``sheet``; ``original``/
  ``large``/``small``/``mini`` → ``background`` (one EntityImage per image, not
  per variant). Flat files: ``sheet`` for character/GMC, ``background`` for
  location/asset/faction.
- Ownership: entity-level (``projection_id`` empty).
- Universe: entity's ``current_universe`` for its own dir/flat file; for a
  per-location subdir, the universe of that location (via the super chain).
- Format: re-encode to WebP via ``_save_image_variants`` (Original/Large/Small/
  Mini), one EntityImage with ``extension="webp"``, ``image_type=uploaded``.

Dry-run by default. Pass ``--apply`` to write files + records.

Usage:
    docker compose exec api python -m transversal.migrate_media [--apply]
"""

from __future__ import annotations

import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from transversal.db.arango import get_db
from transversal.db.repository import EntityRepository
from transversal.domain import EntityImage, ImageType
from transversal.imagen.orchestrator import _safe_filename, _save_image_variants
from transversal.migrate_common import (
    build_entity_key_map,
    build_parent_map,
    build_universe_map,
    load_json,
    resolve_universe_key,
)

OLD_MEDIA = Path("/app/data/old_media_uploads")
IMAGEN_DIR = Path("/app/media/imagen")

IMG_EXTS = {".png", ".webp", ".jpg", ".jpeg"}
BACKGROUND_ORDER = ["original", "large", "small", "mini"]
SHEET_ORDER = ["portrait", "portrait_small"]
SHEET_TYPES = {"character", "gmc"}


def _pick(variants: dict[str, Path], order: list[str]) -> Path | None:
    """Return the best source file for a variant-name order list."""
    for v in order:
        if v in variants:
            return variants[v]
    return None


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    key_map = build_entity_key_map(entities, relations)  # "Entities/{k}" → new id
    parent_map = build_parent_map(relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())

    db = get_db()
    repo = EntityRepository()
    new_entities = {e["_key"]: e for e in db.collection("entities").all()}

    def universe_of_loc(loc_key: str) -> str | None:
        if loc_key in universe_keys:
            return universe_map[loc_key]
        uni = resolve_universe_key(loc_key, parent_map, universe_keys)
        return universe_map.get(uni) if uni else None

    report: Counter = Counter()

    for entry in sorted(OLD_MEDIA.iterdir()):
        # ── Flat file: {key}.{ext} ────────────────────────
        if entry.is_file():
            if entry.suffix.lower() not in IMG_EXTS:
                report["skip_non_image"] += 1
                continue
            new_id = key_map.get(f"Entities/{entry.stem}")
            if new_id is None:
                report["skip_unmapped_flat"] += 1
                continue
            e = new_entities.get(new_id)
            if e is None:
                report["skip_not_found"] += 1
                continue
            role = "sheet" if e.get("type") in SHEET_TYPES else "background"
            report[f"flat_{role}"] += 1
            if apply:
                _write_image(repo, e, entry, [role], e.get("current_universe") or "earth")
            continue

        # ── Entity dir: {key}/ ────────────────────────────
        new_id = key_map.get(f"Entities/{entry.name}")
        if new_id is None:
            report["skip_unmapped_dir"] += 1
            continue
        e = new_entities.get(new_id)
        if e is None:
            report["skip_not_found"] += 1
            continue

        # Direct variant files → entity-level images (entity's current_universe).
        direct: dict[str, Path] = {}
        for p in entry.iterdir():
            if p.is_file() and p.suffix.lower() in IMG_EXTS:
                direct[p.stem] = p

        bg = _pick(direct, BACKGROUND_ORDER)
        if bg:
            report["dir_background"] += 1
            if apply:
                _write_image(repo, e, bg, ["background"], e.get("current_universe") or "earth")
        sh = _pick(direct, SHEET_ORDER)
        if sh:
            report["dir_sheet"] += 1
            if apply:
                _write_image(repo, e, sh, ["sheet"], e.get("current_universe") or "earth")

        # Per-location subdirs → per-universe images.
        for sub in sorted(entry.iterdir()):
            if not sub.is_dir():
                continue
            universe = universe_of_loc(sub.name)
            if universe is None:
                report["skip_loc_no_universe"] += 1
                continue
            variants: dict[str, Path] = {
                p.stem: p for p in sub.iterdir()
                if p.is_file() and p.suffix.lower() in IMG_EXTS
            }
            bg2 = _pick(variants, BACKGROUND_ORDER)
            if bg2:
                report["loc_background"] += 1
                if apply:
                    _write_image(repo, e, bg2, ["background"], universe)
            sh2 = _pick(variants, SHEET_ORDER)
            if sh2:
                report["loc_sheet"] += 1
                if apply:
                    _write_image(repo, e, sh2, ["sheet"], universe)

    print("=== MEDIA MIGRATION ===")
    print(f"apply={apply}")
    print(f"old media root: {OLD_MEDIA}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


def _write_image(repo: EntityRepository, entity: dict, source: Path, roles: list[str], universe: str) -> None:
    entity_id = entity["_key"]
    safe_name = _safe_filename(entity.get("name") or entity_id)
    safe_universe = _safe_filename(universe)
    short_hash = uuid.uuid4().hex[:8]
    base_name = f"{safe_name}_{safe_universe}_{short_hash}"
    output_dir = IMAGEN_DIR / entity_id / universe
    image_data = source.read_bytes()
    _save_image_variants(image_data, output_dir, base_name)
    # Use the source file's mtime so migrated images sort OLDER than the
    # survived new-app images (resolver picks newest-first).
    created_at = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat()
    repo.create_entity_image(EntityImage(
        id=short_hash,
        entity_id=entity_id,
        projection_id=None,
        universe=universe,
        image_type=ImageType.UPLOADED,
        roles=roles,
        filename=base_name,
        extension="webp",
        created_at=created_at,
    ))


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

"""Media migration: old ``media/uploads`` → new ``EntityImage`` + ``media/imagen``.

Per [[Media Migration Proposal]] and media's response:

- Old files are keyed by old numeric entity key: ``{key}/{variant}.{ext}`` (dirs)
  and ``{key}.{ext}`` (flat files).
- Role mapping: ``portrait``/``portrait_small`` → ``sheet``; ``original``/
  ``large``/``small``/``mini`` → ``background`` (one EntityImage per image, not
  per variant). Flat files: ``sheet`` for character/GMC, ``background`` for
  location/asset/faction.
- Ownership: entity-level (``projection_id`` empty).
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
from transversal.migrate_common import build_entity_key_map, load_json

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

    db = get_db()
    repo = EntityRepository()
    new_entities = {e["_key"]: e for e in db.collection("entities").all()}

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
                _write_image(repo, e, entry.read_bytes(), [role])
            continue

        # ── Entity dir: {key}/{variant}.{ext} ─────────────
        new_id = key_map.get(f"Entities/{entry.name}")
        if new_id is None:
            report["skip_unmapped_dir"] += 1
            continue
        e = new_entities.get(new_id)
        if e is None:
            report["skip_not_found"] += 1
            continue

        variants: dict[str, Path] = {}
        subdirs = 0
        for p in entry.iterdir():
            if p.is_file() and p.suffix.lower() in IMG_EXTS:
                variants[p.stem] = p
            elif p.is_dir():
                subdirs += 1

        bg_src = _pick(variants, BACKGROUND_ORDER)
        if bg_src:
            report["dir_background"] += 1
            if apply:
                _write_image(repo, e, bg_src.read_bytes(), ["background"])

        sheet_src = _pick(variants, SHEET_ORDER)
        if sheet_src:
            report["dir_sheet"] += 1
            if apply:
                _write_image(repo, e, sheet_src.read_bytes(), ["sheet"])

        if subdirs:
            report["skip_per_location_subdirs"] += subdirs

    print("=== MEDIA MIGRATION ===")
    print(f"apply={apply}")
    print(f"old media root: {OLD_MEDIA}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


def _write_image(repo: EntityRepository, entity: dict, image_data: bytes, roles: list[str]) -> None:
    universe = entity.get("current_universe") or "earth"
    entity_id = entity["_key"]
    safe_name = _safe_filename(entity.get("name") or entity_id)
    safe_universe = _safe_filename(universe)
    short_hash = uuid.uuid4().hex[:8]
    base_name = f"{safe_name}_{safe_universe}_{short_hash}"
    output_dir = IMAGEN_DIR / entity_id / universe
    _save_image_variants(image_data, output_dir, base_name)
    repo.create_entity_image(EntityImage(
        id=short_hash,
        entity_id=entity_id,
        projection_id=None,
        universe=universe,
        image_type=ImageType.UPLOADED,
        roles=roles,
        filename=base_name,
        extension="webp",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

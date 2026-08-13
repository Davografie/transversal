"""Migrate legacy life path documents to the new roll-table model.

Legacy life paths carried the Cortex-v1 sub-models (``qualification`` /
``curriculum`` / ``survival`` / ``events`` / ``advancement`` /
``muster_out``). Those are now represented as linked ``RollTable`` documents,
so a ``LifePath`` doc only holds an entry table id.

For the current data the legacy docs are empty authoring stubs, so this is a
normalize pass: drop the legacy keys, keep ``id`` / ``name`` / ``description``
/ ``discovery``, fix the universe value, and leave ``entry_table_id`` empty.
Non-empty legacy term content is flagged rather than silently dropped.

Usage:
    docker compose exec api python -m transversal.migrate_life_paths
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import LifePath

LEGACY_KEYS = (
    "qualification",
    "curriculum",
    "survival",
    "events",
    "advancement",
    "muster_out",
)


def _normalize_universe(value: str) -> str:
    """Some editor-era docs stored ``universe-three_realms`` instead of ``three_realms``."""
    if value.startswith("universe-"):
        return value[len("universe-"):]
    return value


def _has_term_content(doc: dict) -> bool:
    if doc.get("qualification"):
        return True
    if doc.get("curriculum"):
        return True

    survival = doc.get("survival") or {}
    if survival.get("trait_ids") or survival.get("mishaps"):
        return True

    if doc.get("events"):
        return True

    advancement = doc.get("advancement") or {}
    if advancement.get("trait_ids") or advancement.get("ranks"):
        return True

    muster = doc.get("muster_out") or {}
    if muster.get("per_term_benefits") or muster.get("at_ranks"):
        return True

    return False


def migrate() -> int:
    repo = EntityRepository()
    migrated = 0
    flagged = 0

    for doc in list(repo._life_paths.all()):
        if not any(k in doc for k in LEGACY_KEYS):
            continue

        lp = LifePath(
            id=doc["_key"],
            name=doc.get("name") or doc["_key"],
            universe=_normalize_universe(doc.get("universe") or ""),
            description=doc.get("description") or "",
            entry_table_id=doc.get("entry_table_id") or "",
            discovery=doc.get("discovery"),
        )
        repo.update_lifepath(lp)
        migrated += 1

        if _has_term_content(doc):
            flagged += 1
            print(f"  FLAG: {lp.id} has legacy term content — needs manual re-authoring")

        print(f"  {lp.id}: '{doc.get('universe')}' -> '{lp.universe}'")

    print(f"\nMigrated {migrated} legacy life path(s); {flagged} flagged with unconverted term content")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())

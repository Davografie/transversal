"""One-off migration: retrofit projections into the origin/current model.

Fixes transversal2's own data (not the old-app migration):

1. Backfill ``origin_universe`` on every projection from its immutable key
   (``"{entity_id}:{origin_universe}"``).
2. Ensure every occupant has exactly one NATIVE home projection (keyed on
   ``current_universe``) and a valid ``current_projection`` pointer; every
   other projection is demoted to CONSCIOUSNESS.

Idempotent: re-running is safe (existence checks + empty-field backfills).

Usage:
    docker compose exec api python -m transversal.migrate_projections
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import EntityType, Projection, TransversalType
from transversal.services.entity_manager import _origin_universe_from_key

OCCUPANT_TYPES = {EntityType.CHARACTER, EntityType.GMC, EntityType.ASSET}


def migrate(apply: bool = False) -> int:
    repo = EntityRepository()

    origin_backfills = 0
    projections_created = 0
    promoted = 0
    demoted = 0
    current_projections_set = 0

    # 1. Backfill origin_universe on every projection from its stable key.
    for proj in repo.list_all_projections():
        if not proj.origin_universe:
            proj.origin_universe = _origin_universe_from_key(proj.id)
            if apply:
                repo.update_projection(proj)
            origin_backfills += 1

    # 2. Occupants: exactly one NATIVE home projection (keyed on
    #    current_universe); every other projection is CONSCIOUSNESS.
    for entity in repo.list_all_entities():
        if entity.type not in OCCUPANT_TYPES:
            continue

        projections = repo.get_projections_for_entity(entity.id)

        home_id = (
            f"{entity.id}:{entity.current_universe}" if entity.current_universe else None
        )
        home = next((p for p in projections if p.id == home_id), None) if home_id else None

        if home is None:
            if not entity.current_universe:
                continue
            home = Projection(
                id=home_id,
                entity_id=entity.id,
                origin_universe=entity.current_universe,
                universe=entity.current_universe,
                current_location=entity.current_location,
                transversal_type=TransversalType.NATIVE,
            )
            if apply:
                repo.create_projection(home)
            projections.append(home)
            projections_created += 1

        # Promote the home projection to NATIVE (idempotent).
        if home.transversal_type != TransversalType.NATIVE:
            home.transversal_type = TransversalType.NATIVE
            if apply:
                repo.update_projection(home)
            promoted += 1

        # Demote every other projection to CONSCIOUSNESS (idempotent).
        for p in projections:
            if p.id != home.id and p.transversal_type == TransversalType.NATIVE:
                p.transversal_type = TransversalType.CONSCIOUSNESS
                if apply:
                    repo.update_projection(p)
                demoted += 1

        if entity.current_projection != home.id:
            entity.current_projection = home.id
            if apply:
                repo.update_entity(entity)
            current_projections_set += 1

    print("=== PROJECTIONS MIGRATION ===")
    print(f"apply={apply}")
    print(f"origin_backfills: {origin_backfills}")
    print(f"projections_created: {projections_created}")
    print(f"promoted: {promoted}")
    print(f"demoted: {demoted}")
    print(f"current_projections_set: {current_projections_set}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

"""One-off migration: retrofit projections into the origin/current model.

Fixes transversal2's own data (not the old-app migration):

1. Backfill ``origin_universe`` on every projection from its immutable key
   (``"{entity_id}:{origin_universe}"``).
2. Ensure every occupant entity has a NATIVE projection and a valid
   ``current_projection`` pointer (only set when missing or dangling — an
   existing pointer is never re-pointed).

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
    current_projections_set = 0

    # 1. Backfill origin_universe on every projection from its stable key.
    for proj in repo.list_all_projections():
        if not proj.origin_universe:
            proj.origin_universe = _origin_universe_from_key(proj.id)
            if apply:
                repo.update_projection(proj)
            origin_backfills += 1

    # 2. Ensure occupants have a NATIVE projection + valid current_projection.
    for entity in repo.list_all_entities():
        if entity.type not in OCCUPANT_TYPES:
            continue

        projections = repo.get_projections_for_entity(entity.id)
        native = [p for p in projections if p.transversal_type == TransversalType.NATIVE]

        if not native:
            if not entity.current_universe:
                continue
            proj = Projection(
                id=f"{entity.id}:{entity.current_universe}",
                entity_id=entity.id,
                origin_universe=entity.current_universe,
                universe=entity.current_universe,
                current_location=entity.current_location,
                transversal_type=TransversalType.NATIVE,
            )
            if apply:
                repo.create_projection(proj)
            projections.append(proj)
            projections_created += 1

        if not entity.current_projection or not any(
            p.id == entity.current_projection for p in projections
        ):
            target = next(
                (p for p in projections
                 if p.transversal_type == TransversalType.NATIVE
                 and p.origin_universe == entity.current_universe),
                None,
            )
            if target is None:
                target = next(
                    (p for p in projections if p.transversal_type == TransversalType.NATIVE),
                    None,
                )
            if target is not None:
                entity.current_projection = target.id
                if apply:
                    repo.update_entity(entity)
                current_projections_set += 1

    print("=== PROJECTIONS MIGRATION ===")
    print(f"apply={apply}")
    print(f"origin_backfills: {origin_backfills}")
    print(f"projections_created: {projections_created}")
    print(f"current_projections_set: {current_projections_set}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))

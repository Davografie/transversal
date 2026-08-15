"""One-off migration: retrofit projections into the origin/current model.

1. For each occupant entity (character / gmc / asset), ensure a NATIVE
   projection exists for its ``current_universe``, backfill ``origin_universe``
   and ``current_location`` from the entity, and set ``current_projection``.
2. Re-anchor ``ego=False`` entity trait settings onto their matching projection
   (``from_type="projection"``).

Idempotent: re-running is safe (existence checks + empty-field backfills).

Usage:
    docker compose exec api python -m transversal.migrate_projections
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import EntityType, Projection, TransversalType

OCCUPANT_TYPES = {EntityType.CHARACTER, EntityType.GMC, EntityType.ASSET}


def _origin_universe(repo: EntityRepository, ts) -> str | None:
    """Pick the origin universe a morph trait setting belongs to."""
    trait = repo.get_trait(ts.trait_id)
    if trait is None:
        return None
    allowed = set(trait.universes)
    if ts.traitset_id:
        traitset = repo.get_traitset_by_id(ts.traitset_id)
        if traitset is not None and traitset.universes:
            allowed &= set(traitset.universes)
    if not allowed:
        return None
    if len(allowed) == 1:
        return next(iter(allowed))
    # Ambiguous — defer to the entity's current universe when allowed.
    entity = repo.get_entity(ts.entity_id)
    if entity and entity.current_universe in allowed:
        return entity.current_universe
    return None  # flag for manual review


def migrate() -> int:
    repo = EntityRepository()

    projection_backfills = 0
    setting_anchors = 0
    ambiguous = 0

    for entity in repo.list_all_entities():
        if entity.type not in OCCUPANT_TYPES:
            continue
        if not entity.current_universe:
            continue

        # 1. Ensure a NATIVE projection + current_projection.
        proj_id = f"{entity.id}:{entity.current_universe}"
        proj = repo.get_projection(proj_id)
        if proj is None:
            repo.create_projection(Projection(
                id=proj_id,
                entity_id=entity.id,
                origin_universe=entity.current_universe,
                universe=entity.current_universe,
                current_location=entity.current_location,
                transversal_type=TransversalType.NATIVE,
            ))
        else:
            if not proj.origin_universe:
                proj.origin_universe = proj.id.rsplit(":", 1)[-1]
            if not proj.current_location and entity.current_location:
                proj.current_location = entity.current_location
            repo.update_projection(proj)

        if entity.current_projection != proj_id:
            entity.current_projection = proj_id
            repo.update_entity(entity)
            projection_backfills += 1

        # 2. Re-anchor ego=False entity settings onto their projection.
        for ts in repo.get_traitsettings_for_entity(entity.id):
            if ts.from_type != "entity" or ts.ego:
                continue
            universe = _origin_universe(repo, ts)
            if universe is None:
                ambiguous += 1
                print(f"  AMBIGUOUS  {entity.name}: trait={ts.trait_id}")
                continue
            ts.from_type = "projection"
            ts.projection_id = f"{entity.id}:{universe}"
            repo.update_traitsetting(ts)
            setting_anchors += 1

    print("=== DONE ===")
    print(f"Projection backfills: {projection_backfills}")
    print(f"Morph settings re-anchored: {setting_anchors}")
    print(f"Ambiguous (left entity-anchored): {ambiguous}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())

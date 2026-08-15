"""One-off migration: retrofit projections into the origin/current model.

Fixes transversal2's own data (not the old-app migration):

1. Backfill ``origin_universe`` on every projection from its immutable key
   (``"{entity_id}:{origin_universe}"``).
2. Ensure every occupant entity has a NATIVE projection and a valid
   ``current_projection`` pointer (only set when missing or dangling — an
   existing pointer is never re-pointed).
3. Re-anchor ``ego=False`` entity trait settings onto their matching
   projection (``from_type="projection"``), creating the projection if the
   entity doesn't already have one for that universe.

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

    origin_backfills = 0
    projections_created = 0
    current_projections_set = 0
    setting_anchors = 0
    ambiguous = 0

    # 1. Backfill origin_universe on every projection from its stable key.
    for proj in repo.list_all_projections():
        if not proj.origin_universe:
            proj.origin_universe = proj.id.rsplit(":", 1)[-1]
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
            proj = repo.create_projection(Projection(
                id=f"{entity.id}:{entity.current_universe}",
                entity_id=entity.id,
                origin_universe=entity.current_universe,
                universe=entity.current_universe,
                current_location=entity.current_location,
                transversal_type=TransversalType.NATIVE,
            ))
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
                repo.update_entity(entity)
                current_projections_set += 1

        # 3. Re-anchor ego=False entity settings onto their projection.
        for ts in repo.get_traitsettings_for_entity(entity.id):
            if ts.from_type != "entity" or ts.ego:
                continue
            universe = _origin_universe(repo, ts)
            if universe is None:
                ambiguous += 1
                print(f"  AMBIGUOUS  {entity.name}: trait={ts.trait_id}")
                continue
            proj_id = f"{entity.id}:{universe}"
            if repo.get_projection(proj_id) is None:
                repo.create_projection(Projection(
                    id=proj_id,
                    entity_id=entity.id,
                    origin_universe=universe,
                    universe=universe,
                    current_location=None,
                    transversal_type=TransversalType.NATIVE,
                ))
                projections_created += 1
            ts.from_type = "projection"
            ts.projection_id = proj_id
            repo.update_traitsetting(ts)
            setting_anchors += 1

    print("=== DONE ===")
    print(f"Origin backfills: {origin_backfills}")
    print(f"Projections created: {projections_created}")
    print(f"Current projections set: {current_projections_set}")
    print(f"Morph settings re-anchored: {setting_anchors}")
    print(f"Ambiguous (left entity-anchored): {ambiguous}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())

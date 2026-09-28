"""Life path discovery — checks whether a character meets DiscoveryBlock conditions."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from transversal.db.repository import EntityRepository

from transversal.domain import DiscoveryBlock, DieType


def check_discovery(
    entity_id: str, discovery: DiscoveryBlock | None, repo: "EntityRepository"
) -> bool:
    """Check whether an entity has discovered a hidden life path.

    Returns True if any single condition in the DiscoveryBlock is met,
    or if the discovery block is None / entirely empty.
    """
    # No discovery block → always visible
    if discovery is None:
        return True

    # All conditions empty → always visible
    if not any(
        [
            discovery.at_location,
            discovery.knows_entity,
            discovery.possesses_trait,
            discovery.has_trait_rating,
            discovery.has_relationship,
        ]
    ):
        return True

    # ── at_location ──────────────────────────────────────
    if discovery.at_location:
        entity = repo.get_entity(entity_id)
        if entity and entity.current_location:
            loc_ids = {entity.current_location}
            loc_ids.update(repo.get_location_ancestors(entity.current_location))
            if loc_ids & set(discovery.at_location):
                return True

    # ── knows_entity ─────────────────────────────────────
    if discovery.knows_entity:
        # `known_to` is an **audience**: X's list names who knows X, not what X
        # knows (the author, 2026-09-27). So "this character knows that one" is
        # that one's list containing *this character* — the reverse lookup, and
        # the direction the index on `known_to[*]` exists for.
        for known_id in discovery.knows_entity:
            known = repo.get_entity(known_id)
            if known and entity_id in (getattr(known, "known_to", None) or []):
                return True

    # ── possesses_trait ──────────────────────────────────
    if discovery.possesses_trait:
        traitsettings = repo.get_traitsettings_for_entity(entity_id)
        ts_trait_ids = {ts.trait_id for ts in traitsettings}
        if ts_trait_ids & set(discovery.possesses_trait):
            return True

    # ── has_trait_rating ─────────────────────────────────
    if discovery.has_trait_rating:
        # Reuse traitsettings if already fetched; otherwise fetch now
        if not (discovery.possesses_trait):
            traitsettings = repo.get_traitsettings_for_entity(entity_id)
        # Build a lookup: trait_id → highest die value this entity has
        trait_max: dict[str, int] = {}
        for ts in traitsettings:
            if ts.dice:
                best = max(d.max_value for d in ts.dice)
                prev = trait_max.get(ts.trait_id, 0)
                if best > prev:
                    trait_max[ts.trait_id] = best

        for trait_id, min_die in discovery.has_trait_rating.items():
            if trait_id in trait_max and trait_max[trait_id] >= min_die.max_value:
                return True

    # ── has_relationship ─────────────────────────────────
    if discovery.has_relationship:
        eref = f"entities/{entity_id}"
        targets = [f"entities/{tid}" for tid in discovery.has_relationship]

        if repo.db is not None:
            # Real ArangoDB backend — use AQL
            cursor = repo.db.aql.execute(
                "FOR r IN relationships FILTER r._from == @eref AND r._to IN @targets LIMIT 1 RETURN true",
                bind_vars={"eref": eref, "targets": targets},
            )
            if any(cursor):
                return True
        else:
            # In-memory mode — scan _relationships list
            for rel in repo._relationships:
                if rel.get("_from") == eref and rel.get("_to") in targets:
                    return True

    # No conditions passed
    return False

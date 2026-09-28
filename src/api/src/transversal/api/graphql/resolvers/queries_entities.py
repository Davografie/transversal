"""Queries entities — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import CharacterView
from transversal.api.graphql.types import Entity
from transversal.api.graphql.types import EntityType
from transversal.api.graphql.types import EntityFactionRef
from transversal.api.graphql.types import FactionDistance
from transversal.api.graphql.types import FactionMember
from transversal.api.graphql.types import Projection
from transversal.api.graphql.types import RelatedEntity
from transversal.api.graphql.types import Relationship
from transversal.domain import EntityType as DomainEntityType
from transversal.domain import is_structural_relationship_type
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _entity_to_gql,
    _resolve_relationship_endpoint,
    _ts_to_gql,
)


@strawberry.type
class QueriesEntities:
    """Mixin contributing 5 field(s) to the root type."""

    @strawberry.field
    def entity(self, info: strawberry.Info, id: strawberry.ID) -> Optional[Entity]:
        e = _em(info).repo.get_entity(str(id))
        return _entity_to_gql(e) if e else None

    @strawberry.field
    def character(self, info: strawberry.Info, id: strawberry.ID) -> Optional[CharacterView]:
        cv = _em(info).get_character(str(id))
        if cv is None:
            return None
        return CharacterView(
            entity=_entity_to_gql(cv.entity),
            projections=[
                Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe,
                           universe=p.universe, name=p.name, background_image=p.background_image,
                           current_location=p.current_location, transversal_type=p.transversal_type,
                           sfx_ids=p.sfx_ids)
                for p in cv.projections
            ],
            trait_settings=[_ts_to_gql(s) for s in cv.trait_settings],
        )

    @strawberry.field
    def entities(
        self, info: strawberry.Info,
        type: Optional[EntityType] = None,
        universe: Optional[str] = None,
        ids: Optional[list[strawberry.ID]] = None,
    ) -> list[Entity]:
        repo = _em(info).repo
        if ids is not None:
            results = repo.get_entities_by_ids([str(i) for i in ids])
        elif type is not None:
            domain_type = DomainEntityType(type.value)
            results = repo.list_entities_by_type(domain_type, universe)
        else:
            results = repo.list_all_entities(universe)
        return [_entity_to_gql(e) for e in results]

    @strawberry.field
    def relationship(
        self, info: strawberry.Info,
        from_entity_id: strawberry.ID,
        to_entity_id: strawberry.ID,
        type: str = "relation",
        elevated: bool = False,
    ) -> Optional[Relationship]:
        """Get a directional relationship edge between two entities, or null."""
        repo = _em(info).repo
        from_id = str(from_entity_id)
        to_id = str(to_entity_id)
        if not is_structural_relationship_type(type):
            frm, from_proj = _resolve_relationship_endpoint(repo, from_id, elevated)
            to, to_proj = _resolve_relationship_endpoint(repo, to_id, elevated)
        else:
            frm, from_proj = from_id, False
            to, to_proj = to_id, False
        edge = repo.get_relationship(frm, to, type, from_projection=from_proj, to_projection=to_proj)
        if edge is None and (from_proj or to_proj):
            # Fall back to the entity-level edge. The migration stored personal
            # relationships at the entity level, but the projection resolution
            # above can only reach body-level edges — and since every occupant
            # now carries a single NATIVE projection, `is_transversal` is False
            # for all of them, so `elevated` can no longer select the entity
            # path either. Without this fallback, 663 of the 664 `relation`
            # edges in the live DB are invisible to this query.
            # Additive by construction: it only runs when the lookup above found
            # nothing, so no edge that resolves today changes shape.
            edge = repo.get_relationship(from_id, to_id, type)
        if edge is None:
            return None
        return Relationship(
            id=edge["_key"],
            from_entity_id=from_id,
            to_entity_id=to_id,
            type=edge.get("type", type),
            description=edge.get("description", ""),
        )

    @strawberry.field
    def related_entities(
        self, info: strawberry.Info,
        entity_id: strawberry.ID,
        query: str = "",
    ) -> list[RelatedEntity]:
        """Get entities connected via relationship edges, filtered by name."""
        repo = _em(info).repo
        results = repo.get_related_entities(str(entity_id), query)
        return [
            RelatedEntity(
                id=r["id"], name=r["name"],
                type=r.get("type", ""),
                sheet_portrait=r.get("sheet_portrait", ""),
            )
            for r in results
        ]

    @strawberry.field
    def faction_members(
        self, info: strawberry.Info, faction_id: strawberry.ID
    ) -> list[FactionMember]:
        """A faction's roster — its members with their role and rank."""
        repo = _em(info).repo
        return [
            FactionMember(
                id=m["id"], name=m["name"], type=m["type"],
                role=m.get("role"), rank=m.get("rank"),
            )
            for m in repo.get_faction_roster(str(faction_id))
        ]

    @strawberry.field
    def relationship_types(self, info: strawberry.Info) -> list[str]:
        """The relationship-type vocabulary, for a picker rather than a text box.

        One answer for both places that ask: a `Create Relationship` effect's
        *Relationship Type* field and a path's `relationship.type` filter. It is a
        vocabulary, not an enum — the types are content (`membership`, `agency`, a
        GM's own `relation`), which is why it has to be asked rather than typed.
        """
        return _em(info).repo.list_relationship_types()

    @strawberry.field
    def entity_factions(
        self, info: strawberry.Info, entity_ids: list[strawberry.ID]
    ) -> list[EntityFactionRef]:
        """Which factions these entities are tied to — **any** tie, either direction.

        One row per ``(entity, faction)`` association for the whole list, in one
        query. The GM focus filter needs this shape: it asks "factions associated
        with these characters/GMCs/assets/locations", and a *type* chip ("every
        character") cannot be answered by a per-entity read without unbounded
        fan-out.

        A posture the faction holds toward the entity counts as much as a
        membership, so ``outTieType``/``inTieType`` are reported separately — the
        former is the edge a role write belongs on. See
        :class:`~transversal.api.graphql.type_defs.relationships.EntityFactionRef`.
        """
        repo = _em(info).repo
        return [
            EntityFactionRef(
                entity_id=r["entity_id"], faction_id=r["faction_id"], name=r["name"],
                out_tie_type=r["out_tie_type"], in_tie_type=r["in_tie_type"],
            )
            for r in repo.get_factions_for_entities([str(e) for e in entity_ids])
        ]

    @strawberry.field
    def faction_distances(
        self, info: strawberry.Info, location_id: strawberry.ID
    ) -> list[FactionDistance]:
        """Every faction ranked by its distance to this location, nearest first.

        The read behind a distance-sorted faction list ([[Tickets#B134]]): the
        near ones float to the top, a faction present at this very place is 0, and
        each entry says *why* it is present — an authored tie (``holds_ground``) or
        members standing there (``has_people``) — and *where*. A faction present
        nowhere reachable carries a null distance and sorts last; 52 of 81 today.
        See :class:`~transversal.api.graphql.type_defs.relationships.FactionDistance`.
        """
        repo = _em(info).repo
        return [
            FactionDistance(
                faction_id=r["faction_id"], name=r["name"],
                distance=r["distance"], nearest_location_id=r["nearest_location_id"],
                nearest_location_name=r["nearest_location_name"],
                presence=r["presence"],
            )
            for r in repo.get_faction_distances_for_location(str(location_id))
        ]

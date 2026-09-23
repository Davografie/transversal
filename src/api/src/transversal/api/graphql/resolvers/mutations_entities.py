"""Mutations entities — split out of src/api/src/transversal/api/graphql/schema.py."""

import json
import strawberry

from transversal.api.graphql.types import CreateEntityInput
from transversal.api.graphql.types import Entity
from transversal.api.graphql.types import EntityType
from transversal.api.graphql.types import Projection
from transversal.api.graphql.types import TransversalTypeEnum
from transversal.api.graphql.types import UpdateEntityInput
from transversal.domain import EntityType as DomainEntityType
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _entity_to_gql,
)


@strawberry.type
class MutationsEntities:
    """Mixin contributing 8 field(s) to the root type."""

    @strawberry.mutation
    def create_entity(self, info: strawberry.Info, input: CreateEntityInput) -> Entity:
        e = _em(info).create(
            name=input.name,
            entity_type=DomainEntityType(input.type.value),
            universe=input.universe,
            location=input.location,
            razmerit=input.razmerit,
            starter_location=input.starter_location,
        )
        if input.type == EntityType.CHARACTER:
            from transversal.services.state_events import fire_state_sfx
            fire_state_sfx(e.id, input.universe, "character_created", {"entity_created": e.id})
        if input.type in (EntityType.CHARACTER, EntityType.GMC, EntityType.ASSET):
            from transversal.services.state_events import fire_projection_created
            fire_projection_created(e.id, input.universe, e.current_projection)
        return _entity_to_gql(e)

    @strawberry.mutation
    def update_entity(self, info: strawberry.Info, input: UpdateEntityInput) -> Entity:
        e = _em(info).get(str(input.id))
        if input.name is not None:
            e.name = input.name
        if input.razmerit is not None:
            e.razmerit = input.razmerit
        if input.current_universe is not None:
            e.current_universe = input.current_universe
        if input.current_location is not None:
            e.current_location = input.current_location
        if input.hidden is not None:
            e.hidden = input.hidden
        if input.unpublished is not None:
            e.unpublished = input.unpublished
        if input.support_eligible is not None:
            e.support_eligible = input.support_eligible
        if input.known_to is not None:
            e.known_to = input.known_to
        if input.background_image is not None:
            e.background_image = input.background_image
        if input.owned_by is not None:
            e.owned_by = input.owned_by
        if input.suitable_life_path_ids is not None:
            e.suitable_life_path_ids = input.suitable_life_path_ids
        if input.overlay is not None:
            e.overlay = input.overlay if input.overlay != "" else None
        if input.starter_location is not None:
            e.starter_location = input.starter_location
        if input.nav_positions is not None:
            e.nav_positions = json.loads(input.nav_positions)
        if input.lora_config is not None:
            e.lora_config = json.loads(input.lora_config) if input.lora_config else None
        if input.prompt_steering is not None:
            e.prompt_steering = input.prompt_steering.strip()
        if input.prompt_include_ancestors is not None:
            e.prompt_include_ancestors = input.prompt_include_ancestors
        updated = _em(info).update(e)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def delete_entity(self, info: strawberry.Info, id: strawberry.ID, rmtree: bool = False) -> bool:
        return _em(info).delete(str(id), rmtree=rmtree)

    @strawberry.mutation
    def add_projection(self, info: strawberry.Info, entity_id: strawberry.ID, universe: str, type: TransversalTypeEnum = TransversalTypeEnum.CONSCIOUSNESS, location: Optional[strawberry.ID] = None) -> Entity:
        e = _em(info).get(str(entity_id))
        updated = _em(info).add_projection(e, universe, type, location=str(location) if location else None)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def update_projection(self, info: strawberry.Info, projection_id: strawberry.ID, name: Optional[str] = None, background_image: Optional[str] = None, current_location: Optional[strawberry.ID] = None, transversal_type: Optional[TransversalTypeEnum] = None) -> Projection:
        p = _em(info).update_projection(str(projection_id), name=name, background_image=background_image, current_location=str(current_location) if current_location else None, transversal_type=transversal_type)
        return Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe, universe=p.universe, name=p.name, background_image=p.background_image, current_location=p.current_location, transversal_type=p.transversal_type, sfx_ids=p.sfx_ids)

    @strawberry.mutation
    def remove_projection(self, info: strawberry.Info, projection_id: strawberry.ID) -> Entity:
        updated = _em(info).remove_projection(str(projection_id))
        return _entity_to_gql(updated) if updated else None

    @strawberry.mutation
    def activate_projection(self, info: strawberry.Info, entity_id: strawberry.ID, projection_id: strawberry.ID, location: Optional[strawberry.ID] = None) -> Entity:
        updated = _em(info).activate_projection(str(entity_id), str(projection_id), location=str(location) if location else None)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def inapposite_travel(self, info: strawberry.Info, entity_id: strawberry.ID, location: strawberry.ID,
                          arrival_kind: Optional[str] = None) -> Entity:
        """Move an entity to a location.

        ``arrival_kind`` labels how they got there; it defaults to ``move``
        because this mutation's callers are the GM panels (a placement), not a
        walk through a portal. Pass ``transversal`` for a real crossing.
        """
        from transversal.domain import ArrivalKind

        updated = _em(info).travel(str(entity_id), str(location), transversal_type="inapposite",
                                   arrival_kind=ArrivalKind.parse(arrival_kind, ArrivalKind.MOVE))
        return _entity_to_gql(updated)

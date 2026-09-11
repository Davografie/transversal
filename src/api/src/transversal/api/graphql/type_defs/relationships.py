"""Relationships — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from transversal.api.graphql.type_defs.traits import (
    TraitSetting,
    _gql_trait_setting,
)


@strawberry.type
class Relationship:
    """A directional relationship edge between two entities."""
    id: str
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str
    description: str = ""

    @strawberry.field
    def relation_traits(self, info: strawberry.Info) -> list[TraitSetting]:
        """Trait settings anchored to this edge (``from_type == 'relationship'``).

        These are the traits the ``_from`` side holds *about* the ``_to`` side —
        the contact is deliberately left off, because on the surface that renders
        them the other end of the edge is the subject.
        """
        repo = info.context["entity_manager"].repo
        return [_gql_trait_setting(ts) for ts in repo.get_relationship_traitsettings(self.id)]

@strawberry.input
class CreateRelationshipInput:
    """Input for creating or updating a relationship edge."""
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str = "relation"
    description: str = ""
    elevated: bool = False  # True → entity→entity (both multiversal); False → projection→projection

@strawberry.input
class DeleteRelationshipInput:
    """Input for deleting a relationship edge."""
    from_entity_id: strawberry.ID
    to_entity_id: strawberry.ID
    type: str = "relation"
    elevated: bool = False

@strawberry.type
class RelatedEntity:
    """An entity connected via a relationship edge, with portrait."""
    id: strawberry.ID
    name: str
    sheet_portrait: str = ""

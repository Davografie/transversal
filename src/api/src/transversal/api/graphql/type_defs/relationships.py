"""Relationships — split out of src/api/src/transversal/api/graphql/types.py."""

from typing import Optional

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
    type: str = ""
    sheet_portrait: str = ""


@strawberry.type
class FactionMember:
    """A roster entry — who is in a faction, and what their place in it is.

    ``role`` is the tie's statement ("sect elder"), ``rank`` its rating, i.e. the
    two authored roster traits; both are None when the tie carries neither.
    """
    id: strawberry.ID
    name: str
    type: str = ""
    role: Optional[str] = None
    rank: Optional[str] = None


@strawberry.type
class EntityFactionRef:
    """One entity's association with one faction, and the edges behind it.

    An association exists when *either* tie type is non-empty — the entity holds
    a tie to the faction (``out_tie_type``, ``entity → faction``), or the faction
    holds one toward the entity (``in_tie_type``, a posture).

    The direction is not decoration: ``out_tie_type`` names the edge a role write
    belongs on, and it is the only direction the roster read counts. Writing
    ``membership`` blindly beside an authored ``relation`` roster tie is how a
    member ends up with two parallel edges — so a caller that means to edit a role
    must use ``out_tie_type`` when it is set, and only create a ``membership``
    when it is empty.

    ``tieType`` is deliberately two fields rather than one: a live pair (Azure
    Dawn) is tied in *both* directions, so a single "the tie's type" would have to
    silently pick one.
    """
    entity_id: strawberry.ID
    faction_id: strawberry.ID
    name: str
    out_tie_type: str = ""
    in_tie_type: str = ""


@strawberry.type
class FactionDistance:
    """How far a faction's nearest **presence** is from a location.

    Presence is two things (the author's widening, 2026-09-26): an authored
    ``faction → location`` tie (``presence = "holds_ground"``), or a member of the
    faction standing at the location (``presence = "has_people"``). The kind is
    reported rather than flattened because the list exists to *remind* the GM why
    a faction is on it — "has people in Murkwell Caves" is the useful half of the
    answer, and an informant anywhere is what makes their faction visible at all.

    ``distance`` is a weighted step count along the location graph (``super`` and
    ``transversal`` edges, walked undirected); a portal that crosses a universe
    boundary costs more than a step inside one. It is None when the faction is
    present nowhere reachable — still true for most factions, since 52 of 81 have
    neither members nor ties.

    ``nearest_location_id``/``nearest_location_name`` are the place the
    measurement was taken to, so a surface can name it as well as count to it.
    """
    faction_id: strawberry.ID
    name: str
    distance: Optional[int] = None
    nearest_location_id: Optional[strawberry.ID] = None
    nearest_location_name: Optional[str] = None
    presence: Optional[str] = None

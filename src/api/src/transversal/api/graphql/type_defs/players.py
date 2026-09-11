"""Players — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.entities import (
    Entity,
)


@strawberry.type
class AgencyEdge:
    """A player→entity ownership edge, with its ``main`` flag."""
    entity_id: strawberry.ID
    main: bool = False

@strawberry.type
class Player:
    """A human player's identity + spotlight recency."""
    id: strawberry.ID
    name: str
    role: str = "player"
    last_spotlight_at: Optional[str] = None
    last_main_entity_id: Optional[strawberry.ID] = None
    agency: list[AgencyEdge] = strawberry.field(default_factory=list)

    @strawberry.field
    def main_entity(self, info: strawberry.Info) -> Optional["Entity"]:
        """The player's main entity for the overview (B63).

        Resolves ``last_main_entity_id`` (recency — the main last taken control
        of) when set; otherwise falls back to the player's *designated* main
        (first agency edge flagged ``main``). Null when the player has neither
        — including when a remembered main's entity has since been deleted
        (the stale stamp must not fail the whole ``spotlightRecency`` query).
        """
        em = info.context["entity_manager"]
        # ``repo.get_entity`` returns Optional; ``em.get`` would raise on a
        # deleted entity (see B55/spotlightRecency stale-reference bug).
        main_id = str(self.last_main_entity_id) if self.last_main_entity_id else None
        entity = em.repo.get_entity(main_id) if main_id else None
        if entity is None:
            designated = em.repo.get_designated_main(str(self.id))
            entity = em.repo.get_entity(designated) if designated else None
        if entity is None:
            return None
        from transversal.api.graphql.schema import _entity_to_gql

        return _entity_to_gql(entity)

@strawberry.input
class SetAgencyMainInput:
    """Flag (or un-flag) an owned entity as a player main."""
    player_id: strawberry.ID
    entity_id: strawberry.ID
    main: bool = True

@strawberry.type
class SupportCharacter:
    """A support character and the main it supports (B57)."""
    entity: Entity
    main: Entity
    main_owner_id: Optional[strawberry.ID] = None
    owner_id: Optional[strawberry.ID] = None
    main_active: bool = False

@strawberry.type
class ActiveMain:
    """A main currently being controlled by its player (B66)."""
    player_id: strawberry.ID
    player_name: str = ""
    main: Entity

@strawberry.type
class PlayerBody:
    """The entity a player is currently controlling (main or SC)."""
    player_id: strawberry.ID
    player_name: str = ""
    entity: Entity

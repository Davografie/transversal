"""Mutations players — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import Entity
from transversal.api.graphql.types import Player as GqlPlayer
from transversal.api.graphql.types import SetAgencyMainInput
from transversal.api.graphql.resolvers.converters import (
    _em,
    _entity_to_gql,
    _player_to_gql,
)


@strawberry.type
class MutationsPlayers:
    """Mixin contributing 2 field(s) to the root type."""

    @strawberry.mutation
    def set_agency_main(self, info: strawberry.Info, input: SetAgencyMainInput) -> GqlPlayer:
        """Flag (or un-flag) an owned entity as one of the player's mains."""
        repo = _em(info).repo
        player_id = str(input.player_id)
        entity_id = str(input.entity_id)
        if not repo.set_agency_main(player_id, entity_id, input.main):
            raise ValueError(f"Player '{player_id}' has no agency over entity '{entity_id}'")
        p = repo.get_player(player_id)
        assert p is not None
        return _player_to_gql(p, repo)

    @strawberry.mutation
    def create_support_character(
        self, info: strawberry.Info,
        player_id: strawberry.ID,
        main_entity_id: strawberry.ID,
        table_id: strawberry.ID,
        index: int,
    ) -> Entity:
        """Create a support character from a roll-table entry (B59).

        The main pays the entry's cost; a new GMC is created, owned by the player
        (``agency``, ``main: false``) and linked to the main via ``support``; the
        entry's benefit effects land on the new SC.
        """
        from transversal.services.roll_table_menu import create_support_character

        sc = create_support_character(
            _em(info), str(player_id), str(main_entity_id), str(table_id), index
        )
        return _entity_to_gql(sc)

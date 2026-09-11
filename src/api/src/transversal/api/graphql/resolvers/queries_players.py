"""Queries players — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import ActiveMain
from transversal.api.graphql.types import Player as GqlPlayer
from transversal.api.graphql.types import PlayerBody
from transversal.api.graphql.types import SupportCharacter
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _entity_to_gql,
    _player_to_gql,
)


@strawberry.type
class QueriesPlayers:
    """Mixin contributing 7 field(s) to the root type."""

    @strawberry.field
    def player(self, info: strawberry.Info, id: strawberry.ID) -> Optional[GqlPlayer]:
        """A player by id, with their agency edges (and ``main`` flags)."""
        repo = _em(info).repo
        p = repo.get_player(str(id))
        return _player_to_gql(p, repo) if p else None

    @strawberry.field
    def players(self, info: strawberry.Info) -> list[GqlPlayer]:
        """All players (identity + spotlight recency + agency)."""
        repo = _em(info).repo
        return [_player_to_gql(p, repo) for p in repo.list_players()]

    @strawberry.field
    def spotlight_recency(self, info: strawberry.Info) -> list[GqlPlayer]:
        """Players ordered oldest-first by spotlight recency (B55).

        Never-spotlit players (``last_spotlight_at`` null) sort first — they are
        most due for a spotlight scene. Each row resolves its most-recent main
        via ``main_entity``.
        """
        repo = _em(info).repo
        return [_player_to_gql(p, repo) for p in repo.list_players_by_spotlight()]

    @strawberry.field
    def support_characters(self, info: strawberry.Info) -> list[SupportCharacter]:
        """Support characters (SC → main ``support`` edges) with availability.

        ``main_active`` is true when the main's owning player is currently
        controlling it — the same signal the ``main_active`` SSE event tracks.
        """
        from transversal.services.player_manager import is_main_active

        repo = _em(info).repo
        out: list[SupportCharacter] = []
        for edge in repo.list_support_edges():
            sc_id = edge["_from"].rsplit("/", 1)[-1]
            main_id = edge["_to"].rsplit("/", 1)[-1]
            sc = repo.get_entity(sc_id)
            main = repo.get_entity(main_id)
            if sc is None or main is None:
                continue
            owner_id = None
            for pid in repo.get_entity_players(main_id):
                if repo.get_agency_main(pid, main_id):
                    owner_id = pid
                    break
            sc_owner_ids = repo.get_entity_players(sc_id)
            sc_owner_id = sc_owner_ids[0] if sc_owner_ids else None
            out.append(SupportCharacter(
                entity=_entity_to_gql(sc),
                main=_entity_to_gql(main),
                main_owner_id=owner_id,
                owner_id=sc_owner_id,
                main_active=owner_id is not None and is_main_active(owner_id, main_id),
            ))
        return out

    @strawberry.field
    def online_players(self, info: strawberry.Info) -> list[strawberry.ID]:
        """Player ids with an active SSE connection (presence)."""
        from transversal.services.presence import list_online_players

        return list_online_players()

    @strawberry.field
    def active_mains(self, info: strawberry.Info) -> list[ActiveMain]:
        """The mains currently being controlled by their players (B66).

        One entry per active main (player → main), resolved to its entity. The
        frontend filters out the acting player to show other players' active mains.
        """
        from transversal.services.player_manager import list_active_mains

        repo = _em(info).repo
        out: list[ActiveMain] = []
        for player_id, main_id in list_active_mains().items():
            main = repo.get_entity(main_id)
            if main is None:
                continue
            player = repo.get_player(player_id)
            out.append(ActiveMain(
                player_id=player_id,
                player_name=player.name if player else player_id,
                main=_entity_to_gql(main),
            ))
        return out

    @strawberry.field
    def player_bodies(self, info: strawberry.Info) -> list[PlayerBody]:
        """The entity each player is currently controlling (main or SC)."""
        from transversal.services.player_manager import list_current_bodies

        repo = _em(info).repo
        out: list[PlayerBody] = []
        for player_id, entity_id in list_current_bodies().items():
            entity = repo.get_entity(entity_id)
            if entity is None:
                continue
            player = repo.get_player(player_id)
            out.append(PlayerBody(
                player_id=player_id,
                player_name=player.name if player else player_id,
                entity=_entity_to_gql(entity),
            ))
        return out

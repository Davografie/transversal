"""Queries lifepath — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import LifePath as GqlLifePath
from transversal.api.graphql.types import RollTable
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _life_path_to_gql,
    _roll_table_to_gql,
)


@strawberry.type
class QueriesLifepath:
    """Mixin contributing 4 field(s) to the root type."""

    @strawberry.field
    def life_paths(
        self,
        info: strawberry.Info,
        universe: Optional[str] = None,
        entity_id: Optional[strawberry.ID] = None,
    ) -> list[GqlLifePath]:
        """List life paths, optionally filtered by universe.

        Pass ``entity_id`` to also get **walkability** for that character
        ([[B194]]): each path carries ``walkable`` and, when it is not, the
        ``unwalkableReasons`` that stop it. Without an entity both stay absent
        (``walkable`` is null), because a gate nobody asked about has no answer —
        this field used to take no entity at all, which is why it could only ever
        offer every path to everyone.

        The gate is the effects **conditions** model, not ``discovery``: discovery
        is a one-time reveal of the path's existence, walkability is whether this
        character may take it *now*. See ``services/lifepath_walkability``.
        """
        repo = _em(info).repo
        if universe:
            lps = repo.list_lifepaths_by_universe(universe)
        else:
            lps = repo.list_all_lifepaths()
        if entity_id is None:
            return [_life_path_to_gql(lp) for lp in lps]

        from transversal.services.lifepath_walkability import unwalkable_reasons

        entity = repo.get_entity(str(entity_id))
        if entity is None:
            # No such entity: nothing was evaluated, so report nothing rather than
            # "every path is walkable" — the latter would be a silent yes.
            return [_life_path_to_gql(lp) for lp in lps]
        reasons = unwalkable_reasons(repo, entity, lps)
        return [
            _life_path_to_gql(
                lp,
                walkable=str(lp.id) not in reasons,
                reasons=reasons.get(str(lp.id), ()),
            )
            for lp in lps
        ]

    @strawberry.field
    def roll_tables(self, info: strawberry.Info, life_path_id: Optional[str] = None) -> list[RollTable]:
        """List roll tables, optionally scoped to a life path."""
        repo = _em(info).repo
        tables = repo.list_roll_tables(life_path_id)
        return [_roll_table_to_gql(t) for t in tables]

    @strawberry.field
    def roll_table(self, info: strawberry.Info, id: strawberry.ID) -> Optional[RollTable]:
        """Fetch one roll table by id."""
        t = _em(info).repo.get_roll_table(str(id))
        return _roll_table_to_gql(t) if t else None

    @strawberry.field
    def support_cast_table_id(self, info: strawberry.Info, entity_id: strawberry.ID) -> Optional[strawberry.ID]:
        """The universe-scoped support-cast roll table id for an entity (B65).

        Resolves ``rt-<universe>-support-cast`` from the entity's current
        universe, falling back to the generic ``rt-support-cast``.
        """
        from transversal.services.roll_table_menu import resolve_support_cast_table_id

        entity = _em(info).repo.get_entity(str(entity_id))
        if entity is None:
            return None
        tid = resolve_support_cast_table_id(_em(info).repo, entity.current_universe or "")
        return strawberry.ID(tid) if tid else None

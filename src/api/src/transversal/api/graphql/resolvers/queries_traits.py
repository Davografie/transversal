"""Queries traits — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import TraitRef
from transversal.api.graphql.types import TraitSetRef
from transversal.api.graphql.resolvers.converters import (
    _em,
    _trait_to_gql,
)


@strawberry.type
class QueriesTraits:
    """Mixin contributing 4 field(s) to the root type."""

    @strawberry.field
    def traitsets(self, info: strawberry.Info) -> list[TraitSetRef]:
        tss = _em(info).repo.get_all_traitsets()
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit,
                        allow_duplicates=ts.allow_duplicates, polarity=ts.polarity,
                        sheet_tab=ts.sheet_tab)
            for ts in tss
        ]

    @strawberry.field
    def traits_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitRef]:
        traits = _em(info).repo.get_traits_by_universe(universe)
        return [_trait_to_gql(t) for t in traits]

    @strawberry.field
    def trait_tags(self, info: strawberry.Info, universe: str) -> list[str]:
        """Distinct tags across every trait in a universe, deduped and sorted.

        The tag *pool* an editor offers as suggestions: a character need not
        carry a tagged trait of its own to see the vocabulary its universe uses.
        Aggregated in the repository, so the caller gets the handful of strings
        rather than every trait in the universe.
        """
        return _em(info).repo.get_trait_tags_by_universe(universe)

    @strawberry.field
    def traits_by_traitsets(self, info: strawberry.Info, traitset_ids: list[strawberry.ID]) -> list[TraitRef]:
        """Traits belonging to the given trait sets (across universes)."""
        repo = _em(info).repo
        seen: set[str] = set()
        result: list[TraitRef] = []
        for tsid in traitset_ids:
            for t in repo.get_traits_by_traitset(str(tsid)):
                if t.id not in seen:
                    seen.add(t.id)
                    result.append(_trait_to_gql(t))
        return result

    @strawberry.field
    def traitsets_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitSetRef]:
        tss = _em(info).repo.get_traitsets_by_universe(universe)
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit,
                        allow_duplicates=ts.allow_duplicates, polarity=ts.polarity,
                        sheet_tab=ts.sheet_tab)
            for ts in tss
        ]

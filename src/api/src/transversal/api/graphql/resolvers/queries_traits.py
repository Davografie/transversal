"""Queries traits — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import TraitRef
from transversal.api.graphql.types import TraitSetRef
from transversal.api.graphql.type_defs.traits import TraitSetting as GqlTraitSetting
from transversal.api.graphql.type_defs.traits import _gql_trait_setting
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
                        entity_types=ts.entity_types, explanation=ts.explanation,
                        order=ts.order, limit=ts.limit,
                        allow_duplicates=ts.allow_duplicates, polarity=ts.polarity,
                        sheet_tab=ts.sheet_tab)
            for ts in tss
        ]

    @strawberry.field
    def traits_declaring_sfx(self, info: strawberry.Info, sfx_id: strawberry.ID) -> list[TraitRef]:
        """The registry traits that nominate a rule ([[B131]]).

        Written from the *rule's* side, because that is the side the editor is
        looking at: a rule's ability to reach every instance of a trait is decided
        by traits it does not name, so without this read the declaration is
        invisible exactly where it matters. Both nominations are included —
        ``defaultSfxIds`` (provisioned onto the instance) and ``possibleSfxIds``
        (offered, and *granted* on an implicit rule).
        """
        return [_trait_to_gql(t) for t in
                _em(info).repo.list_traits_declaring_sfx(str(sfx_id))]

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
                        entity_types=ts.entity_types, explanation=ts.explanation,
                        order=ts.order, limit=ts.limit,
                        allow_duplicates=ts.allow_duplicates, polarity=ts.polarity,
                        sheet_tab=ts.sheet_tab)
            for ts in tss
        ]

    @strawberry.field
    def trait_instances(
        self, info: strawberry.Info, trait_id: strawberry.ID,
    ) -> list[GqlTraitSetting]:
        """Every instance of a trait **definition**, whatever it hangs off.

        The inverse of every other trait-setting read: those walk from a host
        (``entity.traitSettings``, ``relationship.relationTraits``,
        ``subTraitSettings``), which cannot answer "who holds this trait?".

        This is the registry's side of a cleanup question — one definition, all of
        its instances, each with its ``host`` — because a definition is what an
        author edits and the instances are what a migration leaves behind. It
        includes instances anchored as a **sub-trait** of another trait (they
        reference this definition too, so they are instances of it) and instances
        on **relationship edges**, and it is deliberately *not* scoped to a
        universe or an entity: seeing the whole spread is the point.
        """
        repo = _em(info).repo
        return [
            _gql_trait_setting(s)
            for s in repo.get_traitsettings_by_trait(str(trait_id))
        ]

"""Mutations traitcatalog — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import EntityType
from transversal.api.graphql.types import Polarity
from transversal.api.graphql.types import SheetTab
from transversal.api.graphql.types import TraitDisplayName as GqlTraitDisplayName
from transversal.api.graphql.types import TraitInput
from transversal.api.graphql.types import TraitRef
from transversal.api.graphql.types import TraitSetRef
from transversal.api.graphql.types import TraitUpdateInput
from transversal.domain import TraitDisplayName as DomainTraitDisplayName
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
)


@strawberry.type
class MutationsTraitCatalog:
    """Mixin contributing 7 field(s) to the root type."""

    @strawberry.mutation
    def create_traitset(self, info: strawberry.Info, id: str, name: str, universes: list[str],
                        entity_types: Optional[list[EntityType]] = None, explanation: str = "",
                        description: Optional[str] = None,
                        order: int = 0, limit: int = 1,
                        allow_duplicates: bool = False,
                        polarity: Optional[Polarity] = None,
                        sheet_tab: SheetTab = SheetTab.TRAITS) -> TraitSetRef:
        from transversal.domain import TraitSet as DomainTraitSet
        # `description` is the name this field carried before it was renamed to
        # `explanation`. It stays a write alias so the MCP tool's mutation document
        # — which declares `$description` and always sends it — keeps working until
        # [[mcp-architect]] flips its tool property. `explanation` wins if both.
        if not explanation and description:
            explanation = description
        ts = DomainTraitSet(id=id, name=name, universes=universes,
                            entity_types=entity_types or [], explanation=explanation,
                            order=order, limit=limit, allow_duplicates=allow_duplicates, polarity=polarity,
                            sheet_tab=sheet_tab)
        created = _em(info).repo.create_traitset(ts)
        return TraitSetRef(id=created.id, name=created.name, universes=created.universes,
                           entity_types=created.entity_types, explanation=created.explanation,
                           order=created.order, limit=created.limit,
                           allow_duplicates=created.allow_duplicates, polarity=created.polarity,
                           sheet_tab=created.sheet_tab)

    @strawberry.mutation
    def update_traitset(self, info: strawberry.Info, id: strawberry.ID, name: Optional[str] = None,
                        universes: Optional[list[str]] = None, entity_types: Optional[list[EntityType]] = None,
                        explanation: Optional[str] = None, description: Optional[str] = None,
                        order: Optional[int] = None,
                        limit: Optional[int] = None, allow_duplicates: Optional[bool] = None,
                        polarity: Optional[Polarity] = None,
                        sheet_tab: Optional[SheetTab] = None,
                        clear_polarity: bool = False) -> TraitSetRef:
        existing = _em(info).repo.get_traitset_by_id(str(id))
        if not existing: raise ValueError(f"TraitSet '{id}' not found")
        old_polarity = existing.polarity
        if name is not None: existing.name = name
        if universes is not None: existing.universes = universes
        if entity_types is not None: existing.entity_types = entity_types
        if explanation is None: explanation = description  # deprecated alias, see create_traitset
        if explanation is not None: existing.explanation = explanation
        if order is not None: existing.order = order
        if limit is not None: existing.limit = limit
        if allow_duplicates is not None: existing.allow_duplicates = allow_duplicates
        if sheet_tab is not None: existing.sheet_tab = sheet_tab
        if clear_polarity:
            existing.polarity = None
        elif polarity is not None:
            existing.polarity = polarity
        updated = _em(info).repo.update_traitset(existing)
        from transversal.services.polarity import propagate_traitset_polarity
        propagate_traitset_polarity(_em(info).repo, str(id), old_polarity, existing.polarity)
        return TraitSetRef(id=updated.id, name=updated.name, universes=updated.universes,
                           entity_types=updated.entity_types, explanation=updated.explanation,
                           order=updated.order, limit=updated.limit,
                           allow_duplicates=updated.allow_duplicates, polarity=updated.polarity,
                           sheet_tab=updated.sheet_tab)

    @strawberry.mutation
    def delete_traitset(self, info: strawberry.Info, id: strawberry.ID) -> str:
        result = _em(info).repo.delete_traitset(str(id))
        return f"Deleted traitset and {result['traits_removed']} traits, {result['settings_removed']} settings"

    @strawberry.mutation
    def reorder_traitsets(self, info: strawberry.Info, ids: list[strawberry.ID]) -> bool:
        _em(info).repo.reorder_traitsets([str(i) for i in ids])
        return True

    @strawberry.mutation
    def create_trait(self, info: strawberry.Info, input: TraitInput) -> TraitRef:
        from transversal.domain import Trait as DomainTrait
        t = DomainTrait(
            id=input.id, name=input.name, universes=input.universes,
            traitset_id=str(input.traitset_id),
            default_die_type=input.default_die_type,
            default_rating_type=input.default_rating_type,
            possible_sfx_ids=[str(s) for s in input.possible_sfx_ids],
            possible_subtrait_ids=[str(s) for s in input.possible_subtrait_ids],
            possible_subtraitset_ids=[str(s) for s in input.possible_subtraitset_ids],
            default_sfx_ids=[str(s) for s in input.default_sfx_ids],
            default_ego=input.default_ego,
            tags=[str(s) for s in (input.tags or [])],
            polarity=input.polarity,
            explanation=input.explanation,
            display_names=[
                DomainTraitDisplayName(name=dn.name, universe=dn.universe,
                                       ratings=dn.ratings)
                for dn in input.display_names
            ],
        )
        created = _em(info).repo.create_trait(t)
        return TraitRef(
            id=created.id, name=created.name, universes=created.universes,
            traitset_id=created.traitset_id,
            default_die_type=created.default_die_type,
            default_rating_type=created.default_rating_type,
            possible_sfx_ids=created.possible_sfx_ids,
            default_sfx_ids=created.default_sfx_ids,
            possible_subtrait_ids=created.possible_subtrait_ids,
            possible_subtraitset_ids=created.possible_subtraitset_ids,
            default_ego=created.default_ego,
            tags=list(created.tags or []),
            polarity=created.polarity,
            explanation=created.explanation,
            display_names=[
                GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                    ratings=dn.ratings)
                for dn in created.display_names
            ],
        )

    @strawberry.mutation
    def update_trait(self, info: strawberry.Info, id: strawberry.ID, input: TraitUpdateInput) -> TraitRef:
        existing = _em(info).repo.get_trait(str(id))
        if not existing:
            raise ValueError(f"Trait '{id}' not found")
        old_polarity = existing.polarity
        if input.name is not None:
            existing.name = input.name
        if input.universes is not None:
            existing.universes = input.universes
        if input.traitset_id is not None:
            existing.traitset_id = str(input.traitset_id)
        if input.default_die_type is not None:
            existing.default_die_type = input.default_die_type
        if input.default_rating_type is not None:
            existing.default_rating_type = input.default_rating_type
        if input.possible_sfx_ids is not None:
            existing.possible_sfx_ids = [str(s) for s in input.possible_sfx_ids]
        if input.possible_subtrait_ids is not None:
            existing.possible_subtrait_ids = [str(s) for s in input.possible_subtrait_ids]
        if input.possible_subtraitset_ids is not None:
            existing.possible_subtraitset_ids = [str(s) for s in input.possible_subtraitset_ids]
        default_sfx_changed = input.default_sfx_ids is not None
        if default_sfx_changed:
            existing.default_sfx_ids = [str(s) for s in input.default_sfx_ids]
        if input.default_ego is not None:
            existing.default_ego = input.default_ego
        if input.tags is not None:
            existing.tags = [str(s) for s in input.tags]
        if input.explanation is not None:
            existing.explanation = input.explanation
        if input.clear_polarity:
            existing.polarity = None
        elif input.polarity is not None:
            existing.polarity = input.polarity
        if input.display_names is not None:
            existing.display_names = [
                DomainTraitDisplayName(name=dn.name, universe=dn.universe,
                                       ratings=dn.ratings)
                for dn in input.display_names
            ]
        updated = _em(info).repo.update_trait(existing)
        from transversal.services.polarity import propagate_trait_polarity
        traitset = _em(info).repo.get_traitset_by_id(updated.traitset_id)
        propagate_trait_polarity(
            _em(info).repo, str(id), old_polarity, updated.polarity,
            traitset.polarity if traitset else None,
        )
        if default_sfx_changed:
            # Re-provision existing instances with the new defaults (#49).
            from transversal.services.sfx_owner import propagate_trait_default_sfx
            propagate_trait_default_sfx(_em(info).repo, str(id))
        # A trait's declared rules changed: `possible_sfx_ids` decides which
        # implicit rules its instances carry ([[B131]]), so the availability cache
        # must not keep serving the pre-edit declaration.
        from transversal.services.sfx_owner import invalidate_sfx_cache
        invalidate_sfx_cache()
        return TraitRef(
            id=updated.id, name=updated.name, universes=updated.universes,
            traitset_id=updated.traitset_id,
            default_die_type=updated.default_die_type,
            default_rating_type=updated.default_rating_type,
            possible_sfx_ids=updated.possible_sfx_ids,
            default_sfx_ids=updated.default_sfx_ids,
            possible_subtrait_ids=updated.possible_subtrait_ids,
            possible_subtraitset_ids=updated.possible_subtraitset_ids,
            default_ego=updated.default_ego,
            tags=list(updated.tags or []),
            polarity=updated.polarity,
            explanation=updated.explanation,
            display_names=[
                GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                    ratings=dn.ratings)
                for dn in updated.display_names
            ],
        )

    @strawberry.mutation
    def delete_trait(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_trait(str(id))

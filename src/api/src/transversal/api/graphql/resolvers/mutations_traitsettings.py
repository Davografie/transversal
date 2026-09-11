"""Mutations traitsettings — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import DieType as GqlDieType
from transversal.api.graphql.types import RazmeritResult
from transversal.api.graphql.types import TraitSetting
from transversal.api.graphql.types import TraitSettingInput
from transversal.api.graphql.types import TraitSettingUpdateInput
from transversal.domain import TraitSetting as DomainTraitSetting
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _raz,
    _ts_to_gql,
)


@strawberry.type
class MutationsTraitSettings:
    """Mixin contributing 10 field(s) to the root type."""

    @strawberry.mutation
    def add_trait_setting(self, info: strawberry.Info, entity_id: strawberry.ID, input: TraitSettingInput) -> TraitSetting:
        repo = _em(info).repo
        traitset = repo.get_traitset_by_id(str(input.traitset_id))
        allow_duplicates = traitset.allow_duplicates if traitset is not None else False
        collision = repo.find_traitsetting_collision(
            str(entity_id), str(input.trait_id),
            statement=input.statement or "", allow_duplicates=allow_duplicates,
        )
        if collision is not None:
            raise ValueError(
                f"Trait '{input.trait_id}' already present"
                + (f" with statement '{input.statement}'" if allow_duplicates and input.statement else "")
            )
        ts_id = repo.resolve_traitsetting_id(
            str(entity_id), str(input.trait_id),
            statement=input.statement or "", allow_duplicates=allow_duplicates,
        )
        trait = repo.get_trait(str(input.trait_id))
        from transversal.services.polarity import default_polarity
        polarity = input.polarity if input.polarity is not None else default_polarity(trait, traitset)
        from_type = input.from_type
        projection_id = str(input.projection_id) if input.projection_id else None
        if from_type is None:
            # Default anchor from the trait's registry hint.
            if trait is not None and not getattr(trait, "default_ego", False):
                entity = repo.get_entity(str(entity_id))
                if entity is not None and entity.current_projection:
                    from_type = "projection"
                    projection_id = entity.current_projection
                else:
                    from_type = "entity"
            else:
                from_type = "entity"
        ts = DomainTraitSetting(
            id=ts_id,
            entity_id=str(entity_id),
            trait_id=str(input.trait_id),
            traitset_id=str(input.traitset_id),
            dice=input.dice,
            rating_type=input.rating_type,
            capacity=input.capacity,
            polarity=polarity,
            statement=input.statement,
            notes=input.notes,
            from_type=from_type,
            projection_id=projection_id,
            sfx_ids=[str(s) for s in input.sfx_ids],
        )
        created = _em(info).add_traitsetting(ts)
        return _ts_to_gql(created)

    @strawberry.mutation
    def step_up_trait(self, info: strawberry.Info, trait_setting_id: strawberry.ID) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(trait_setting_id))
        if ts is None:
            raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
        updated = _em(info).step_up_trait(ts)
        return _ts_to_gql(updated)

    @strawberry.mutation
    def step_down_trait(self, info: strawberry.Info, trait_setting_id: strawberry.ID) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(trait_setting_id))
        if ts is None:
            raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
        updated = _em(info).step_down_trait(ts)
        return _ts_to_gql(updated)

    @strawberry.mutation
    def remove_trait_setting(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_traitsetting(str(id))

    @strawberry.mutation
    def update_trait_setting(self, info: strawberry.Info, id: strawberry.ID, input: TraitSettingUpdateInput) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(id))
        if ts is None:
            raise ValueError(f"TraitSetting '{id}' not found")
        if input.dice is not None:
            ts.dice = input.dice
        if input.rating_type is not None:
            ts.rating_type = input.rating_type
        if input.capacity is not None:
            ts.capacity = input.capacity
        if input.polarity is not None:
            ts.polarity = input.polarity
        if input.statement is not None:
            ts.statement = input.statement
        if input.notes is not None:
            ts.notes = input.notes
        if input.from_type is not None and ts.from_type not in ("relationship", "traitsetting"):
            if input.from_type == "projection":
                if input.projection_id is None:
                    raise ValueError("projectionId is required when fromType is 'projection'")
                proj = _em(info).repo.get_projection(str(input.projection_id))
                if proj is None or proj.entity_id != ts.entity_id:
                    raise ValueError(f"Projection '{input.projection_id}' does not belong to this entity")
                ts.from_type = "projection"
                ts.projection_id = str(input.projection_id)
            elif input.from_type == "entity":
                ts.from_type = "entity"
                ts.projection_id = None
            else:
                raise ValueError(f"Unknown fromType '{input.from_type}'")
        if input.sfx_ids is not None:
            ts.sfx_ids = [str(s) for s in input.sfx_ids]
        if input.known_to is not None:
            ts.known_to = [str(k) for k in input.known_to]
        if input.enabled is not None:
            ts.enabled = input.enabled
        updated = _em(info).update_traitsetting(ts)
        return _ts_to_gql(updated)

    @strawberry.mutation
    def add_sub_trait(self, info: strawberry.Info, parent_traitsetting_id: strawberry.ID,
                      trait_id: strawberry.ID, die: Optional[GqlDieType] = None,
                      statement: str = "") -> TraitSetting:
        """Nest a sub-trait under a parent trait setting.

        Sub-traits reuse the ``traitsettings`` edge collection, anchored to the
        parent setting (``from_type='traitsetting'``, ``_from → TRAITSETTINGS/{parent}``).
        The trait set is derived from the sub-trait's registry entry; ``entity_id``
        is inherited from the parent so cascade cleanup and ownership stay intact.
        """
        repo = _em(info).repo
        parent = repo.get_traitsetting(str(parent_traitsetting_id))
        if parent is None:
            raise ValueError(f"Parent TraitSetting '{parent_traitsetting_id}' not found")
        trait = repo.get_trait(str(trait_id))
        if trait is None:
            raise ValueError(f"Trait '{trait_id}' not found")
        traitset_id = trait.traitset_id
        if die is None:
            die = trait.default_die_type

        from transversal.services.polarity import default_polarity
        traitset = repo.get_traitset_by_id(traitset_id)
        polarity = default_polarity(trait, traitset)

        ts = DomainTraitSetting(
            id=f"{parent.id}:{trait_id}",
            entity_id=parent.entity_id,
            trait_id=str(trait_id),
            traitset_id=traitset_id,
            from_type="traitsetting",
            parent_traitsetting_id=parent.id,
            dice=[die],
            rating_type=trait.default_rating_type,
            polarity=polarity,
            statement=statement,
        )
        created = repo.create_traitsetting(ts)
        return _ts_to_gql(created)

    @strawberry.mutation
    def remove_sub_trait(self, info: strawberry.Info, sub_trait_setting_id: strawberry.ID) -> bool:
        """Remove a sub-trait setting (and its nested sub-traits) from its parent."""
        return _em(info).repo.delete_traitsetting(str(sub_trait_setting_id))

    @strawberry.mutation
    def spend_razmerit(self, info: strawberry.Info, entity_id: strawberry.ID, amount: int, reason: str = "sfx_cost") -> RazmeritResult:
        r = _raz(info).spend(str(entity_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

    @strawberry.mutation
    def earn_razmerit(self, info: strawberry.Info, entity_id: strawberry.ID, amount: int, reason: str = "complication") -> RazmeritResult:
        r = _raz(info).earn(str(entity_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

    @strawberry.mutation
    def transfer_razmerit(self, info: strawberry.Info, from_id: strawberry.ID, to_id: strawberry.ID, amount: int, reason: str = "transfer") -> RazmeritResult:
        r = _raz(info).transfer(str(from_id), str(to_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

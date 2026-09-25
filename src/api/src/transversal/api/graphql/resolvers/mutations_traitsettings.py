"""Mutations traitsettings — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import DieType as GqlDieType
from transversal.api.graphql.types import RazmeritResult
from transversal.api.graphql.types import TraitSetting
from transversal.api.graphql.types import TraitSettingInput
from transversal.api.graphql.types import TraitSettingUpdateInput
from transversal.domain import TraitSetting as DomainTraitSetting
from transversal.services.trait_change import repoint_trait_setting
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
        if input.parent_traitsetting_id is not None and input.from_type != "traitsetting":
            raise ValueError("parentTraitsettingId requires fromType 'traitsetting'")
        # The set is the **trait's**, never the caller's: a setting does not record
        # one ([[B200]]). `input.traitset_id` is still accepted and deliberately
        # ignored, so an older client that sends it keeps working — and it always
        # sent the trait's own set anyway, because the setting's copy could not be
        # anything else without drifting.
        trait = repo.get_trait(str(input.trait_id))
        traitset = repo.get_traitset_by_id(
            getattr(trait, "traitset_id", "") or "")
        allow_duplicates = traitset.allow_duplicates if traitset is not None else False
        parent = None
        if input.from_type == "traitsetting":
            # A nested setting is keyed to its parent, not the entity, and one
            # registry trait legitimately appears many times under one container —
            # every portent in an agenda is a setting of the same generic trait. The
            # entity-wide collision rule would refuse the second portent, and the
            # dedicated `addSubTrait` mutation has never applied it, so the two
            # create paths agree by skipping it here.
            if input.parent_traitsetting_id is None:
                raise ValueError(
                    "parentTraitsettingId is required when fromType is 'traitsetting'")
            parent = repo.get_traitsetting(str(input.parent_traitsetting_id))
            if parent is None:
                raise ValueError(
                    f"Parent TraitSetting '{input.parent_traitsetting_id}' not found")
            if str(parent.entity_id) != str(entity_id):
                raise ValueError("A sub-trait's parent must belong to the same entity")
            ts_id = repo.resolve_subtrait_id(
                str(parent.id), str(input.trait_id), input.statement or "")
        else:
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
        # Nesting on create — the twin of `fromType: "traitsetting"` in
        # `update_trait_setting`. The parent used to be accepted and dropped here,
        # which wrote ``_from = TRAITSETTINGS/None``: a dangling edge that put the
        # child in no container at all.
        parent_traitsetting_id = str(parent.id) if parent is not None else None
        if parent_traitsetting_id is not None:
            projection_id = None
        ts = DomainTraitSetting(
            id=ts_id,
            entity_id=str(entity_id),
            trait_id=str(input.trait_id),
            dice=input.dice,
            rating_type=input.rating_type,
            capacity=input.capacity,
            polarity=polarity,
            statement=input.statement,
            notes=input.notes,
            order=input.order,
            tags=[str(t) for t in (input.tags or [])],
            from_type=from_type,
            projection_id=projection_id,
            parent_traitsetting_id=parent_traitsetting_id,
            sfx_ids=[str(s) for s in input.sfx_ids],
            enabled=input.enabled,
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
        if input.order is not None:
            ts.order = input.order
        if input.tags is not None:
            ts.tags = [str(t) for t in input.tags]
        # Changing the instance's definition. Shares one implementation with the
        # `change_trait` effect action (`services/trait_change`), so the sheet and
        # an effect can never disagree about what the move means — in particular
        # that the instance keeps everything it owns and only its registry pointer
        # (and, with it, its set) moves.
        if input.trait_id is not None:
            change = repoint_trait_setting(ts, str(input.trait_id), _em(info).repo)
            if not change.changed and change.reason == "missing":
                raise ValueError(f"Trait definition '{input.trait_id}' not found")
        # Re-anchoring. A **relationship** setting is anchored by its edge key and
        # must not be moved; everything else may be (a top-level trait, or a
        # sub-trait moving between containers or back out to the entity).
        if input.from_type is not None and ts.from_type != "relationship":
            if input.from_type == "projection":
                if input.projection_id is None:
                    raise ValueError("projectionId is required when fromType is 'projection'")
                proj = _em(info).repo.get_projection(str(input.projection_id))
                if proj is None or proj.entity_id != ts.entity_id:
                    raise ValueError(f"Projection '{input.projection_id}' does not belong to this entity")
                ts.from_type = "projection"
                ts.projection_id = str(input.projection_id)
                ts.parent_traitsetting_id = None
            elif input.from_type == "entity":
                ts.from_type = "entity"
                ts.projection_id = None
                ts.parent_traitsetting_id = None
            elif input.from_type == "traitsetting":
                # Nest under another setting — the drag-into-a-container move.
                # The parent is deliberately *not* checked against the trait
                # registry's ``possible_subtrait_ids``: containment is direct
                # manipulation, and nothing else on the write path enforces that
                # nomination either. Cycles are refused by the repository
                # (``_would_cycle``), which walks the ancestor chain.
                if input.parent_traitsetting_id is None:
                    raise ValueError(
                        "parentTraitsettingId is required when fromType is 'traitsetting'")
                parent = _em(info).repo.get_traitsetting(str(input.parent_traitsetting_id))
                if parent is None:
                    raise ValueError(
                        f"Parent TraitSetting '{input.parent_traitsetting_id}' not found")
                if str(parent.id) == str(ts.id):
                    # Checked here, not only in the repository: the guard lives in
                    # the Arango write path, so an implementation without it (the
                    # in-memory test repo, for one) would happily nest a setting
                    # under itself. Descendant cycles are still the repository's.
                    raise ValueError("A trait setting cannot be nested under itself")
                if str(parent.entity_id) != str(ts.entity_id):
                    raise ValueError("A sub-trait's parent must belong to the same entity")
                ts.from_type = "traitsetting"
                ts.parent_traitsetting_id = str(parent.id)
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
                      statement: str = "", order: Optional[int] = None) -> TraitSetting:
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
            id=repo.resolve_subtrait_id(str(parent.id), str(trait_id), statement),
            entity_id=parent.entity_id,
            trait_id=str(trait_id),
            from_type="traitsetting",
            parent_traitsetting_id=parent.id,
            dice=[die],
            rating_type=trait.default_rating_type,
            polarity=polarity,
            statement=statement,
            order=order,
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

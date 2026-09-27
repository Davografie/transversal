"""Mutations sfx — split out of src/api/src/transversal/api/graphql/schema.py."""

from transversal.services.sfx_owner import invalidate_sfx_cache
import strawberry

from transversal.api.graphql.types import OwnerRefInput
from transversal.api.graphql.types import SfxInput
from transversal.api.graphql.types import SfxRef
from transversal.api.graphql.types import SfxUpdateInput
from transversal.domain import Condition as DomainCondition
from transversal.domain import ConditionType as DomainConditionType
from transversal.services.sfx_text import repo_name_resolver
from transversal.api.graphql.resolvers.converters import (
    _bound_variables_from_input,
    _condition_input_to_domain,
    _duration_input_to_domain,
    _effect_input_to_domain,
    _em,
    _maybe_rearm_passives,
    _sfx_ref,
    _target_spec_from_input,
)


@strawberry.type
class MutationsSfx:
    """Mixin contributing 5 field(s) to the root type."""

    @strawberry.mutation
    def create_sfx(self, info: strawberry.Info, input: SfxInput) -> SfxRef:
        import logging
        from transversal.domain import SFX as DomainSFX
        logging.info(
            "[SFX-CREATE] id=%s name=%s trigger=%s effects=%s",
            input.id, input.name, input.trigger,
            [(e.type, e.action, e.target, e.result, e.timing) for e in input.effects],
        )
        conditions = [_condition_input_to_domain(c) for c in (input.conditions or [])]
        if input.limit and not any(
            c.type == DomainConditionType.NARRATIVE and c.narrative for c in conditions
        ):
            conditions.append(DomainCondition(type=DomainConditionType.NARRATIVE, narrative=input.limit))

        s = DomainSFX(
            id=input.id, name=input.name, description=input.description,
            trigger=input.trigger, conditions=conditions,
            source_kind=input.source_kind, placement=input.placement,
            arming_scope=input.arming_scope,
            listener_spec=_target_spec_from_input(input.listener_spec),
            acquire_spec=_target_spec_from_input(input.acquire_spec),
            implicit=bool(getattr(input, "implicit", False)),
            bound_variables=_bound_variables_from_input(input.bound_variables),
            effects=[_effect_input_to_domain(e) for e in input.effects],
            duration=_duration_input_to_domain(input.duration),
        )
        created = _em(info).repo.create_sfx(s)
        # The availability caches — SFX records and trait declarations — are
        # dropped on **every** rule write, not only when an effects engine happens
        # to be attached: a cache that a write does not invalidate is a cache that
        # keeps answering with the state before it.
        invalidate_sfx_cache()
        # Also register with the in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(created)
        _maybe_rearm_passives(created.trigger)
        return _sfx_ref(created, repo_name_resolver(_em(info).repo))

    @strawberry.mutation
    def update_sfx(self, info: strawberry.Info, input: SfxUpdateInput) -> SfxRef:
        import logging
        logging.info(
            "[SFX-UPDATE] id=%s effects=%s",
            input.id,
            [(e.type, e.action, e.target, e.result, e.timing) for e in (input.effects or [])],
        )
        existing = _em(info).repo.get_sfx(str(input.id))
        if not existing:
            raise ValueError(f"SFX '{input.id}' not found")
        old_trigger = existing.trigger
        if input.name is not None:
            existing.name = input.name
        if input.description is not None:
            existing.description = input.description
        if input.conditions is not None:
            existing.conditions = [_condition_input_to_domain(c) for c in input.conditions]
        elif input.limit is not None:
            existing.conditions = [
                c for c in (existing.conditions or [])
                if c.type != DomainConditionType.NARRATIVE
            ]
            if input.limit:
                existing.conditions.append(
                    DomainCondition(type=DomainConditionType.NARRATIVE, narrative=input.limit)
                )
        if input.trigger is not None:
            existing.trigger = input.trigger
        if input.source_kind is not None:
            existing.source_kind = input.source_kind
        if input.placement is not None:
            existing.placement = input.placement
        if input.arming_scope is not None:
            existing.arming_scope = input.arming_scope
        if input.listener_spec is not None:
            existing.listener_spec = _target_spec_from_input(input.listener_spec)
        if input.acquire_spec is not None:
            existing.acquire_spec = _target_spec_from_input(input.acquire_spec)
        if input.implicit is not None:
            existing.implicit = bool(input.implicit)
        if input.bound_variables is not None:
            existing.bound_variables = _bound_variables_from_input(input.bound_variables)
        if input.effects is not None:
            existing.effects = [_effect_input_to_domain(e) for e in input.effects]
        if input.duration is not None:
            existing.duration = _duration_input_to_domain(input.duration)
        updated = _em(info).repo.update_sfx(existing)
        # Unconditional, for the same reason as `create_sfx` above: a rule edit
        # must reach the availability reads whether or not an engine is attached
        # to this context.
        invalidate_sfx_cache()
        # Also update in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(updated)
        _maybe_rearm_passives(old_trigger, updated.trigger)
        return _sfx_ref(updated, repo_name_resolver(_em(info).repo))

    @strawberry.mutation
    def delete_sfx(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        repo = _em(info).repo
        existing = repo.get_sfx(str(id))
        ok = repo.delete_sfx(str(id))
        if ok:
            invalidate_sfx_cache()
        if ok and existing is not None:
            _maybe_rearm_passives(existing.trigger)
        return ok

    @strawberry.mutation
    def add_owner_sfx(
        self,
        info: strawberry.Info,
        owner_refs: list[OwnerRefInput],
        sfx_id: strawberry.ID,
    ) -> bool:
        """Add one SFX id to every referenced owner (batch, idempotent)."""
        from transversal.services.sfx_owner import add_sfx_to_owner, attach_refusal

        repo = _em(info).repo
        sfx = repo.get_sfx(str(sfx_id)) if hasattr(repo, "get_sfx") else None
        # Validate *all* of them before touching any: a batch either applies or it
        # doesn't, and a refusal says why instead of returning a bare False.
        for ref in owner_refs:
            reason = (attach_refusal(sfx, ref.owner_type.value, str(ref.owner_id), repo)
                      if sfx is not None else None)
            if reason:
                raise ValueError(f"'{sfx.name or sfx.id}' {reason}, not {ref.owner_type.value}")
        for ref in owner_refs:
            if not add_sfx_to_owner(repo, ref.owner_type.value, str(ref.owner_id), str(sfx_id)):
                return False
        return True

    @strawberry.mutation
    def remove_owner_sfx(
        self,
        info: strawberry.Info,
        owner_refs: list[OwnerRefInput],
        sfx_id: strawberry.ID,
    ) -> bool:
        """Remove one SFX id from every referenced owner (batch, idempotent)."""
        from transversal.services.sfx_owner import remove_sfx_from_owner

        repo = _em(info).repo
        for ref in owner_refs:
            if not remove_sfx_from_owner(repo, ref.owner_type.value, str(ref.owner_id), str(sfx_id)):
                return False
        return True

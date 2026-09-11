"""Queries sfx — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import ScheduledEvent as GqlScheduledEvent
from transversal.api.graphql.types import SfxInput
from transversal.api.graphql.types import SfxOwnerKindGql
from transversal.api.graphql.types import SfxOwnerRef
from transversal.api.graphql.types import SfxRef
from transversal.services.sfx_text import repo_name_resolver
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _condition_input_to_domain,
    _duration_input_to_domain,
    _effect_input_to_domain,
    _em,
    _scheduled_event_to_gql,
    _sfx_ref,
    _target_spec_from_input,
)


@strawberry.type
class QueriesSfx:
    """Mixin contributing 7 field(s) to the root type."""

    @strawberry.field
    def sfx_text(self, info: strawberry.Info, sfx: SfxInput) -> str:
        """Derived rules text for an SFX payload.

        Stateless on purpose: the SFX editor renders an *unsaved* draft, so the
        text must come from the payload, not from the stored SFX.
        """
        from transversal.domain import SFX as DomainSFX
        from transversal.services.sfx_text import sfx_text as render

        domain = DomainSFX(
            id=sfx.id, name=sfx.name, description=sfx.description,
            trigger=sfx.trigger, limit=sfx.limit,
            source_kind=sfx.source_kind, placement=sfx.placement,
            arming_scope=sfx.arming_scope,
            conditions=[_condition_input_to_domain(c) for c in (sfx.conditions or [])],
            effects=[_effect_input_to_domain(e) for e in (sfx.effects or [])],
            duration=_duration_input_to_domain(sfx.duration),
        )
        return render(domain, resolve=repo_name_resolver(_em(info).repo))

    @strawberry.field
    def sfxs(self, info: strawberry.Info) -> list[SfxRef]:
        # Prefer DB-persisted SFXs; fall back to in-memory engine
        repo = _em(info).repo
        db_sfxs = repo.get_all_sfxs()
        if db_sfxs:
            resolve = repo_name_resolver(repo)
            return [_sfx_ref(s, resolve) for s in db_sfxs]
        from transversal.services.effects_engine import EffectsEngine
        engine = info.context.get("effects_engine")
        if engine:
            resolve = repo_name_resolver(repo)
            return [_sfx_ref(s, resolve) for s in engine.get_all()]
        return []

    @strawberry.field
    def sfx_owners(self, info: strawberry.Info, owner_type: SfxOwnerKindGql) -> list[SfxOwnerRef]:
        """Flattened owner instances of one type for the SFX ownership manager."""
        from transversal.services.sfx_owner import list_owner_refs

        refs = list_owner_refs(_em(info).repo, owner_type.value)
        return [
            SfxOwnerRef(
                owner_type=r["owner_type"],
                owner_id=r["owner_id"],
                label=r["label"],
                entity_type=r.get("entity_type", ""),
                sfx_ids=r["sfx_ids"],
            )
            for r in refs
        ]

    @strawberry.field
    def scheduled_events(
        self, info: strawberry.Info,
        target_type: Optional[str] = None,
        target_id: Optional[strawberry.ID] = None,
        target_ids: Optional[list[strawberry.ID]] = None,
    ) -> list[GqlScheduledEvent]:
        """Running centrally-scheduled timers, optionally scoped to owners.

        ``target_type`` is ``"entity"`` or ``"trait_setting"``. ``target_id``
        scopes to one owner; ``target_ids`` scopes to a set of owners (e.g. a
        sheet's trait-setting ids). Omit all for the full store.
        """
        events = _em(info).repo.list_scheduled_events(
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            target_ids=[str(i) for i in target_ids] if target_ids is not None else None,
        )
        return [_scheduled_event_to_gql(e) for e in events]

    @strawberry.field
    def armed_sfx_ids(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[strawberry.ID]:
        """SFX ids currently armed (roll-deferred, in effect) for an entity."""
        from transversal.services.roll_deferral import list_armed_sfx_ids

        return [strawberry.ID(i) for i in list_armed_sfx_ids(str(entity_id))]

    @strawberry.field
    def available_sfx_ids(self, info: strawberry.Info, entity_id: strawberry.ID, universe: str = "") -> list[strawberry.ID]:
        """SFX ids currently available to an entity (ownership + static conditions).

        ``universe`` gates trait-level grants via effective trait settings; when
        blank it falls back to the entity's current universe.
        """
        from transversal.services.sfx_owner import get_available_sfx_ids

        repo = _em(info).repo
        if not universe:
            entity = repo.get_entity(str(entity_id))
            universe = entity.current_universe if entity else ""
        return [strawberry.ID(i) for i in get_available_sfx_ids(str(entity_id), universe, repo)]

    @strawberry.field
    def validate_sfx(self, info: strawberry.Info, input: SfxInput) -> list[str]:
        """Return authoring warnings for an SFX draft (unknown variables, etc.)."""
        from transversal.domain import SFX as DomainSFX
        from transversal.services.sfx_validation import validate_sfx

        draft = DomainSFX(
            id=input.id, name=input.name, trigger=input.trigger,
            source_kind=input.source_kind, placement=input.placement,
            arming_scope=input.arming_scope,
            listener_spec=_target_spec_from_input(input.listener_spec),
            conditions=[_condition_input_to_domain(c) for c in (input.conditions or [])],
            effects=[_effect_input_to_domain(e) for e in (input.effects or [])],
            duration=_duration_input_to_domain(input.duration),
        )
        return validate_sfx(draft, repo=_em(info).repo)

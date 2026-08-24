"""Strawberry GraphQL schema — queries and mutations."""

import json
import strawberry
from typing import Optional

from transversal.api.graphql.types import (
    CharacterView,
    Condition,
    ConditionInput,
    ConditionTypeOption,
    CreateEntityInput,
    CreateRelationshipInput,
    ConsequenceOption,
    ConsequenceOptionInput,
    DeleteRelationshipInput,
    DieType as GqlDieType,
    EffectActionMeta as GqlEffectActionMeta,
    EffectFieldDef as GqlEffectFieldDef,
    EffectApplicationResult,
    EffectInput,
    EffectTargetResolutionInput,
    FilterFieldOption,
    Entity,
    EntityType,
    HistoricalRecord,
    JournalEntryInput,
    LifePath as GqlLifePath,
    LifePathStepResult,
    Message,
    MessageKind,
    OutcomeTier as GqlOutcomeTier,
    PendingTerm as GqlPendingTerm,
    Polarity,
    Projection,
    RelatedEntity,
    Relationship,
    RollTable,
    RollTableCheck,
    RollTableCheckInput,
    RollTableEntry,
    RollTableEntryInput,
    RollTableInput,
    RazmeritResult,
    ScopeVariable,
    SendMessageInput,
    Effect as GqlEffect,
    EffectDuration as GqlEffectDuration,
    EffectDurationInput,
    Timer as GqlTimer,
    TimerInput,
    SfxInput,
    SfxRef,
    SfxOwnerKindGql,
    SfxOwnerRef,
    OwnerRefInput,
    TeachResult,
    GiftResult,
    TakeResult,
    TargetCandidate,
    PendingChoiceRef,
    TraitDisplayName as GqlTraitDisplayName,
    SfxUpdateInput,
    TraitInput,
    TraitRef,
    TraitSetRef,
    TraitSetting,
    TraitSettingInput,
    TraitSettingUpdateInput,
    TraitUpdateInput,
    Attunement,
    TransversalTypeEnum,
    TriggerOption,
    UpdateEntityInput,
    UpdateMessageInput,
    Zone,
)
from transversal.domain import Entity as DomainEntity
from transversal.domain import EntityType as DomainEntityType
from transversal.domain import TraitSetting as DomainTraitSetting
from transversal.domain import TraitDisplayName as DomainTraitDisplayName
from transversal.domain import Condition as DomainCondition
from transversal.domain import ConditionType as DomainConditionType
from transversal.domain import Effect as DomainEffect
from transversal.domain import EffectDuration as DomainEffectDuration
from transversal.domain import Timer as DomainTimer
from transversal.domain import ConsequenceOption as DomainConsequenceOption
from transversal.domain import RollTable as DomainRollTable
from transversal.domain import RollTableEntry as DomainRollTableEntry
from transversal.domain import RollTableCheck as DomainRollTableCheck
from transversal.domain import HistoricalRecord as DomainHistoricalRecord
from transversal.domain import dice_list_to_rating
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService


def _em(info: strawberry.Info) -> EntityManager:
    return info.context["entity_manager"]


def _raz(info: strawberry.Info) -> RazmeritService:
    return info.context["razmerit_service"]


def _entity_to_gql(e: DomainEntity) -> Entity:
    return Entity(
        id=e.id, type=e.type, name=e.name, razmerit=e.razmerit,
        current_universe=e.current_universe, current_location=e.current_location,
        current_projection=e.current_projection,
        hidden=e.hidden, unpublished=e.unpublished, known_to=e.known_to,
        _background_image=e.background_image, overlay=e.overlay,
        starter_location=e.starter_location,
        zones=[Zone(name=z.name, background_image=z.background_image, location_id=z.location_id, x=z.x, y=z.y) for z in e.zones],
        map_x=e.map_x, map_y=e.map_y,
        nav_positions=json.dumps(e.nav_positions) if e.nav_positions else "{}",
        node_ids=e.node_ids, owned_by=e.owned_by,
        attunements=[
            Attunement(universe=a.universe, scope=a.scope.value,
                       until=a.until, source_sfx_id=a.source_sfx_id)
            for a in e.attunements
        ],
        lora_config=json.dumps(e.lora_config) if e.lora_config else None,
    )


def _ts_to_gql(s: DomainTraitSetting) -> TraitSetting:
    return TraitSetting(
        id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
        traitset_id=s.traitset_id,
        rating_type=s.rating_type, dice=s.dice,
        spent_dice=s.spent_dice,
        polarity=s.polarity,
        statement=s.statement,
        notes=s.notes,
        from_type=s.from_type, projection_id=s.projection_id,
        sfx_ids=s.sfx_ids,
        known_to=s.known_to,
    )


def _message_to_gql(m: "Message", repo) -> Message:
    """Convert a domain Message to GraphQL Message, resolving the
    ``associate`` relationship description between sender and recipient."""
    from transversal.domain import MessageKind as DomainMessageKind
    rel = repo.get_relationship(m.sender_entity_id, m.recipient_entity_id, "associate")
    if rel is None:
        rel = repo.get_relationship(m.recipient_entity_id, m.sender_entity_id, "associate")
    return Message(
        id=m.id,
        sender_entity_id=m.sender_entity_id,
        recipient_entity_id=m.recipient_entity_id,
        kind=MessageKind(m.kind.value),
        title=m.title,
        body=m.body,
        images=m.images,
        after_ids=m.after_ids,
        threads=m.threads,
        created_at=m.created_at,
        relationship_description=(rel or {}).get("description", ""),
    )


def _duration_to_gql(d) -> Optional[GqlEffectDuration]:
    if d is None:
        return None
    return GqlEffectDuration(
        timers=[GqlTimer(event=t.event, remaining=t.remaining) for t in d.timers],
        combine=d.combine,
    )


def _duration_input_to_domain(d) -> Optional[DomainEffectDuration]:
    if d is None:
        return None
    return DomainEffectDuration(
        timers=[DomainTimer(event=t.event, remaining=t.remaining) for t in d.timers],
        combine=d.combine,
    )


def _effect_to_gql(e: DomainEffect) -> GqlEffect:
    return GqlEffect(
        timing=e.timing, type=e.type, action=e.action,
        target=e.target, entity=e.entity, result=e.result,
        target_scope=e.target_scope, entity_scope=e.entity_scope,
        target_filter=e.target_filter or None,
        negative=e.negative,
        context=e.context,
        duration=_duration_to_gql(e.duration),
    )


def _condition_to_gql(c: DomainCondition) -> Condition:
    return Condition(type=c.type, subject=c.subject, target=c.target, value=c.value, narrative=c.narrative)


def _entry_to_gql(e: DomainRollTableEntry) -> RollTableEntry:
    return RollTableEntry(
        label=e.label, description=e.description,
        min_value=e.min_value, max_value=e.max_value, weight=e.weight, tier=e.tier,
        conditions=[_condition_to_gql(c) for c in e.conditions],
        effects=[_effect_to_gql(x) for x in e.effects],
    )


def _roll_table_to_gql(t: DomainRollTable) -> RollTable:
    return RollTable(
        id=t.id, name=t.name, universe=t.universe, life_path=t.life_path,
        scheme=t.scheme, roll_source=t.roll_source, trait_dice_count=t.trait_dice_count,
        die=t.die,
        check=(
            RollTableCheck(
                trait_ids=t.check.trait_ids,
                difficulty=t.check.difficulty,
                free_choice=t.check.free_choice,
            )
            if t.check is not None
            else None
        ),
        entries=[_entry_to_gql(e) for e in t.entries],
        canvas_x=t.canvas_x,
        canvas_y=t.canvas_y,
    )


def _effect_input_to_domain(e: EffectInput) -> DomainEffect:
    return DomainEffect(
        timing=e.timing, type=e.type, action=e.action,
        target=e.target, entity=e.entity, result=e.result,
        target_scope=e.target_scope, entity_scope=e.entity_scope,
        target_filter=e.target_filter or {},
        negative=e.negative,
        context=e.context or {},
        duration=_duration_input_to_domain(e.duration),
    )


def _consequence_option_to_gql(o: DomainConsequenceOption) -> ConsequenceOption:
    return ConsequenceOption(
        id=o.id, label=o.label, side=o.side,
        effects=[_effect_to_gql(e) for e in o.effects],
        source=o.source,
    )


def _consequence_option_input_to_domain(o: ConsequenceOptionInput) -> DomainConsequenceOption:
    return DomainConsequenceOption(
        id=o.id, label=o.label, side=o.side,
        effects=[_effect_input_to_domain(e) for e in o.effects],
        source="entity",
    )


def _effects_result_to_gql(result) -> EffectApplicationResult:
    return EffectApplicationResult(
        applied=[a.summary for a in result.applied],
        pending_choices=[
            PendingChoiceRef(index=i, kind=c.kind, scope=c.scope, field=c.field, filter=c.effect.target_filter or None, effect=_effect_to_gql(c.effect))
            for i, c in enumerate(result.pending_choices)
        ],
    )


def _condition_input_to_domain(c: ConditionInput) -> DomainCondition:
    return DomainCondition(type=c.type, subject=c.subject, target=c.target, value=c.value, narrative=c.narrative)


def _check_input_to_domain(c: RollTableCheckInput) -> DomainRollTableCheck:
    return DomainRollTableCheck(trait_ids=c.trait_ids, difficulty=c.difficulty, free_choice=c.free_choice)


def _entry_input_to_domain(e: RollTableEntryInput) -> DomainRollTableEntry:
    return DomainRollTableEntry(
        label=e.label, description=e.description,
        min_value=e.min_value, max_value=e.max_value, weight=e.weight, tier=e.tier,
        conditions=[_condition_input_to_domain(c) for c in e.conditions],
        effects=[_effect_input_to_domain(x) for x in e.effects],
    )


def _roll_table_input_to_domain(t: RollTableInput) -> DomainRollTable:
    return DomainRollTable(
        id=t.id, name=t.name, universe=t.universe, life_path=t.life_path,
        scheme=t.scheme, roll_source=t.roll_source, trait_dice_count=t.trait_dice_count,
        die=t.die,
        check=(_check_input_to_domain(t.check) if t.check is not None else None),
        entries=[_entry_input_to_domain(e) for e in t.entries],
    )


def _historical_record_to_gql(r: DomainHistoricalRecord) -> HistoricalRecord:
    rtype = r.record_type.value if hasattr(r.record_type, "value") else r.record_type
    return HistoricalRecord(
        id=r.id,
        entity_id=r.entity_id,
        record_type=rtype,
        universe=r.universe,
        session_id=r.session_id,
        data=r.data,
        created_at=r.created_at,
    )


# ── Queries ──────────────────────────────────────────

@strawberry.type
class Query:
    @strawberry.field
    def entity(self, info: strawberry.Info, id: strawberry.ID) -> Optional[Entity]:
        e = _em(info).repo.get_entity(str(id))
        return _entity_to_gql(e) if e else None

    @strawberry.field
    def character(self, info: strawberry.Info, id: strawberry.ID) -> Optional[CharacterView]:
        cv = _em(info).get_character(str(id))
        if cv is None:
            return None
        return CharacterView(
            entity=_entity_to_gql(cv.entity),
            projections=[
                Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe,
                           universe=p.universe, name=p.name, background_image=p.background_image,
                           current_location=p.current_location, transversal_type=p.transversal_type)
                for p in cv.projections
            ],
            trait_settings=[_ts_to_gql(s) for s in cv.trait_settings],
        )

    @strawberry.field
    def entities(
        self, info: strawberry.Info,
        type: Optional[EntityType] = None,
        universe: Optional[str] = None,
        ids: Optional[list[strawberry.ID]] = None,
    ) -> list[Entity]:
        repo = _em(info).repo
        if ids is not None:
            results = repo.get_entities_by_ids([str(i) for i in ids])
        elif type is not None:
            domain_type = DomainEntityType(type.value)
            results = repo.list_entities_by_type(domain_type, universe)
        else:
            results = repo.list_all_entities(universe)
        return [_entity_to_gql(e) for e in results]

    @strawberry.field
    def traitsets(self, info: strawberry.Info) -> list[TraitSetRef]:
        tss = _em(info).repo.get_all_traitsets()
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit,
                        polarity=ts.polarity)
            for ts in tss
        ]

    @strawberry.field
    def sfxs(self, info: strawberry.Info) -> list[SfxRef]:
        # Prefer DB-persisted SFXs; fall back to in-memory engine
        repo = _em(info).repo
        db_sfxs = repo.get_all_sfxs()
        if db_sfxs:
            return [
                SfxRef(
                    id=s.id, name=s.name, description=s.description,
                    trigger=s.trigger, limit=s.limit,
                    effects=[_effect_to_gql(e) for e in s.effects],
                )
                for s in db_sfxs
            ]
        from transversal.services.effects_engine import EffectsEngine
        engine = info.context.get("effects_engine")
        if engine:
            return [
                SfxRef(
                    id=s.id, name=s.name, description=s.description,
                    trigger=s.trigger, limit=s.limit,
                    effects=[_effect_to_gql(e) for e in s.effects],
                ) for s in engine.get_all()
            ]
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
                sfx_ids=r["sfx_ids"],
            )
            for r in refs
        ]

    @strawberry.field
    def traits_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitRef]:
        traits = _em(info).repo.get_traits_by_universe(universe)
        return [
            TraitRef(
                id=t.id, name=t.name, universes=t.universes,
                traitset_id=t.traitset_id, default_die_type=t.default_die_type,
                default_rating_type=t.default_rating_type,
                possible_sfx_ids=t.possible_sfx_ids,
                default_sfx_ids=t.default_sfx_ids,
                location_restricted=t.location_restricted,
                default_ego=t.default_ego,
                polarity=t.polarity,
                display_names=[
                    GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                        ratings=dn.ratings)
                    for dn in t.display_names
                ],
            )
            for t in traits
        ]

    @strawberry.field
    def traitsets_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitSetRef]:
        tss = _em(info).repo.get_traitsets_by_universe(universe)
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit,
                        polarity=ts.polarity)
            for ts in tss
        ]

    @strawberry.field
    def effect_actions(self, info: strawberry.Info) -> list[GqlEffectActionMeta]:
        from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
        return [
            GqlEffectActionMeta(
                action_id=m.action_id, label=m.label, description=m.description,
                category=m.category, effect_type=m.effect_type, effect_action=m.effect_action,
                valid_timings=m.valid_timings,
                fields=[GqlEffectFieldDef(name=f.name, label=f.label, field_type=f.field_type, required=f.required, default=f.default, options=f.options or []) for f in m.fields],
                context_fields=[GqlEffectFieldDef(name=f.name, label=f.label, field_type=f.field_type, required=f.required, default=f.default, options=f.options or []) for f in m.context_fields],
                implicit_target=m.implicit_target, implicit_result=m.implicit_result, implicit_timing=m.implicit_timing,
                requires_choice=m.requires_choice, target_kind=m.target_kind, supports_duration=m.supports_duration,
                supports_polarity=m.supports_polarity, supports_return_exit=m.supports_return_exit,
            ) for m in EFFECT_ACTION_REGISTRY
        ]

    @strawberry.field
    def scope_variables(
        self, info: strawberry.Info,
        trigger: str = "",
    ) -> list[ScopeVariable]:
        """Typed ``{variable}`` tokens available to authored effects for a trigger
        (auto-fire, manual, or menu)."""
        from transversal.services.menu_contexts import trigger_variables

        return [ScopeVariable(name=v.name, type=v.type) for v in trigger_variables(trigger)]

    @strawberry.field
    def triggers(self, info: strawberry.Info) -> list[TriggerOption]:
        """The activation-trigger vocabulary for the SFX editor, sourced from the backend."""
        from transversal.services.menu_contexts import TRIGGERS
        return [TriggerOption(value=t.value, label=t.label, group=t.group) for t in TRIGGERS]

    @strawberry.field
    def condition_types(self, info: strawberry.Info) -> list[ConditionTypeOption]:
        """The condition-type vocabulary for the SFX editor, sourced from the backend."""
        from transversal.services.conditions import CONDITION_TYPES
        return [
            ConditionTypeOption(
                value=c.value, label=c.label,
                needs_target=c.needs_target, target_placeholder=c.target_placeholder,
                target_kind=c.target_kind,
            )
            for c in CONDITION_TYPES
        ]

    @strawberry.field
    def validate_sfx(self, info: strawberry.Info, input: SfxInput) -> list[str]:
        """Return authoring warnings for an SFX draft (unknown variables, etc.)."""
        from transversal.domain import SFX as DomainSFX
        from transversal.services.sfx_validation import validate_sfx

        draft = DomainSFX(
            id=input.id, name=input.name, trigger=input.trigger,
            conditions=[_condition_input_to_domain(c) for c in (input.conditions or [])],
            effects=[_effect_input_to_domain(e) for e in (input.effects or [])],
        )
        return validate_sfx(draft)

    @strawberry.field
    def target_candidates(
        self, info: strawberry.Info,
        kind: str,
        entity_id: Optional[strawberry.ID] = None,
        scope: Optional[str] = None,
        action: Optional[str] = None,
        filter: Optional[strawberry.scalars.JSON] = None,
    ) -> list[TargetCandidate]:
        """Resolve the selectable targets for a ``choose``/``random`` effect target.

        ``kind`` is one of the target kinds (``location``, ``occupant``, ``trait``,
        ``rating_die``, ``entity``, ``life_path``, ``roll_table``); ``scope`` is the
        ``target_scope`` narrowing string (``faction:X``, ``subtree:X``, etc.).
        ``action`` narrows trait picks to the entity's own instances for
        mutate-only actions (``step_down``/``step_up``/``set``/``remove``).
        ``filter`` is a map of candidate entity fields to required values
        (e.g. ``{"starter_location": true}``).

        ``entity_id`` may be omitted for authoring previews; the resolver then
        uses a synthetic context whose universe comes from ``scope``.
        """
        from transversal.services.effect_targets import resolve_candidates, parse_scope

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id)) if entity_id else None
        if entity is None:
            universe = ""
            prefix, value = parse_scope(scope)
            if prefix == "universe":
                universe = value
            entity = DomainEntity(
                id="__preview__", type=DomainEntityType.UNIVERSE,
                name="", current_universe=universe,
            )
        return [
            TargetCandidate(id=c.id, name=c.name, universe=c.universe)
            for c in resolve_candidates(kind, scope, entity, repo, action, filter or {})
        ]

    @strawberry.field
    def target_filter_fields(self, info: strawberry.Info) -> list[FilterFieldOption]:
        """Candidate filter fields the SFX editor can build, sourced from the backend."""
        from transversal.services.effect_targets import FILTER_FIELDS
        return [
            FilterFieldOption(field=f.field, label=f.label, value_type=f.value_type, kinds=list(f.kinds))
            for f in FILTER_FIELDS
        ]

    @strawberry.field
    def consequence_options(
        self, info: strawberry.Info,
        entity_id: strawberry.ID,
        side: str = "player",
        menu_context: str = "test_success",
    ) -> list[ConsequenceOption]:
        """Assemble the post-roll consequence menu for a side in a menu context.

        ``side`` is ``"player"`` or ``"gm"``. ``menu_context`` is one of the
        menu triggers (``test_success``, ``simplified_roll``, ``contest_win``,
        ``contest_give_in``). Options come from base moves, the acting entity's
        location chain, and SFX whose ``trigger`` matches.
        """
        from transversal.services.consequence_menu import assemble_consequence_menu

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            return []
        return [
            _consequence_option_to_gql(o)
            for o in assemble_consequence_menu(entity, repo, side, menu_context)
        ]

    @strawberry.field
    def hitch_menu(
        self, info: strawberry.Info,
        roller_id: Optional[strawberry.ID] = None,
        buyer_id: Optional[strawberry.ID] = None,
    ) -> list[ConsequenceOption]:
        """Return the GM hitch menu — SFX from the gm/table/players owners whose
        trigger is ``hitch``. ``roller_id``/``buyer_id`` populate ``{hitch_entity}``
        and ``{buying_entity}`` so conditions can reference them."""
        from transversal.services.consequence_menu import assemble_hitch_menu

        repo = _em(info).repo
        return [
            _consequence_option_to_gql(o)
            for o in assemble_hitch_menu(
                repo,
                str(roller_id) if roller_id else "",
                str(buyer_id) if buyer_id else "",
            )
        ]

    @strawberry.field
    def incoming_messages(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[Message]:
        """Get messages addressed to this entity (player: only incoming; GM: all)."""
        repo = _em(info).repo
        messages = repo.get_incoming_messages(str(entity_id))
        return [
            _message_to_gql(m, repo) for m in messages
        ]

    @strawberry.field
    def conversation(
        self, info: strawberry.Info, entity_a: strawberry.ID, entity_b: strawberry.ID
    ) -> list[Message]:
        """Get all messages between two entities (GM view)."""
        repo = _em(info).repo
        messages = repo.get_conversation(str(entity_a), str(entity_b))
        return [
            _message_to_gql(m, repo) for m in messages
        ]

    @strawberry.field
    def recent_messages(
        self, info: strawberry.Info,
        since: str = "",
        kind: Optional[MessageKind] = None,
    ) -> list[Message]:
        """Get all messages across all entities (GM activity feed), newest first.

        Optionally filter by kind and/or minimum created_at ISO timestamp."""
        repo = _em(info).repo
        messages = repo.get_recent_messages(since=since, kind=kind.value if kind else "")
        return [_message_to_gql(m, repo) for m in messages]

    @strawberry.field
    def journal(
        self, info: strawberry.Info, entity_id: strawberry.ID
    ) -> list[Message]:
        """Get an entity's personal journal (self-referential entries, GM-visible)."""
        repo = _em(info).repo
        entries = repo.get_journal(str(entity_id))
        return [_message_to_gql(m, repo) for m in entries]

    @strawberry.field
    def historical_records(
        self, info: strawberry.Info,
        entity_id: strawberry.ID,
        record_type: Optional[str] = None,
    ) -> list[HistoricalRecord]:
        """Get an entity's historical records (append-only event log)."""
        repo = _em(info).repo
        records = repo.list_historical_records(str(entity_id), record_type or "")
        return [_historical_record_to_gql(r) for r in records]

    @strawberry.field
    def relationship(
        self, info: strawberry.Info,
        from_entity_id: strawberry.ID,
        to_entity_id: strawberry.ID,
        type: str = "associate",
    ) -> Optional[Relationship]:
        """Get a directional relationship edge between two entities, or null."""
        repo = _em(info).repo
        edge = repo.get_relationship(str(from_entity_id), str(to_entity_id), type)
        if edge is None:
            return None
        return Relationship(
            id=edge["_key"],
            from_entity_id=str(from_entity_id),
            to_entity_id=str(to_entity_id),
            type=edge.get("type", type),
            description=edge.get("description", ""),
        )

    @strawberry.field
    def message_threads(self, info: strawberry.Info) -> list[str]:
        """Return all distinct tags across all messages (for autocomplete)."""
        return _em(info).repo.get_all_threads()

    @strawberry.field
    def timeline(
        self, info: strawberry.Info,
        entity_id: strawberry.ID = "",
        tags: Optional[list[str]] = None,
    ) -> list[Message]:
        """Return messages in causal (topological) order.

        Filter by entity (sender or recipient) and/or threads.
        Messages ordered by after_ids DAG; floaters by created_at.
        """
        repo = _em(info).repo
        messages = repo.get_timeline(
            entity_id=str(entity_id) if entity_id else "",
            threads=tags,
        )
        return [_message_to_gql(m, repo) for m in messages]

    @strawberry.field
    def related_entities(
        self, info: strawberry.Info,
        entity_id: strawberry.ID,
        query: str = "",
    ) -> list[RelatedEntity]:
        """Get entities connected via relationship edges, filtered by name."""
        repo = _em(info).repo
        results = repo.get_related_entities(str(entity_id), query)
        return [
            RelatedEntity(id=r["id"], name=r["name"], sheet_portrait=r.get("sheet_portrait", ""))
            for r in results
        ]

    @strawberry.field
    def life_paths(self, info: strawberry.Info, universe: Optional[str] = None) -> list[GqlLifePath]:
        """List life paths, optionally filtered by universe."""
        repo = _em(info).repo
        if universe:
            lps = repo.list_lifepaths_by_universe(universe)
        else:
            lps = repo.list_all_lifepaths()
        return [_life_path_to_gql(lp) for lp in lps]

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


# ── Life path helpers ─────────────────────────────────

def _life_path_to_gql(lp) -> GqlLifePath:
    """Convert a domain LifePath to the GraphQL type."""
    return GqlLifePath(
        id=lp.id,
        name=lp.name,
        universe=lp.universe,
        description=lp.description if hasattr(lp, 'description') else "",
        entry_table_id=lp.entry_table_id,
        discovery=lp.discovery,
    )


# ── Mutations ────────────────────────────────────────

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_entity(self, info: strawberry.Info, input: CreateEntityInput) -> Entity:
        e = _em(info).create(
            name=input.name,
            entity_type=DomainEntityType(input.type.value),
            universe=input.universe,
            location=input.location,
            razmerit=input.razmerit,
            starter_location=input.starter_location,
        )
        if input.type == EntityType.CHARACTER:
            from transversal.services.state_events import fire_state_sfx
            fire_state_sfx(e.id, input.universe, "character_created", {"entity_created": e.id})
        return _entity_to_gql(e)

    @strawberry.mutation
    def add_trait_setting(self, info: strawberry.Info, entity_id: strawberry.ID, input: TraitSettingInput) -> TraitSetting:
        ts_id = f"{entity_id}:{input.trait_id}"
        repo = _em(info).repo
        existing = repo.get_traitsetting(ts_id)
        if existing:
            raise ValueError(f"TraitSetting '{ts_id}' already exists")
        trait = repo.get_trait(str(input.trait_id))
        traitset = repo.get_traitset_by_id(str(input.traitset_id))
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

    @strawberry.mutation
    def add_projection(self, info: strawberry.Info, entity_id: strawberry.ID, universe: str, type: TransversalTypeEnum = TransversalTypeEnum.CONSCIOUSNESS, location: Optional[strawberry.ID] = None) -> Entity:
        e = _em(info).get(str(entity_id))
        updated = _em(info).add_projection(e, universe, type, location=str(location) if location else None)
        from transversal.services.state_events import fire_state_sfx
        fire_state_sfx(
            updated.id, universe, "projection_created",
            {
                "entity_created": updated.id,
                "projection_created": updated.current_projection,
                "universe": universe,
            },
        )
        return _entity_to_gql(updated)

    @strawberry.mutation
    def update_projection(self, info: strawberry.Info, projection_id: strawberry.ID, name: Optional[str] = None, background_image: Optional[str] = None, current_location: Optional[strawberry.ID] = None) -> Projection:
        p = _em(info).update_projection(str(projection_id), name=name, background_image=background_image, current_location=str(current_location) if current_location else None)
        return Projection(id=p.id, entity_id=p.entity_id, origin_universe=p.origin_universe, universe=p.universe, name=p.name, background_image=p.background_image, current_location=p.current_location, transversal_type=p.transversal_type)

    @strawberry.mutation
    def remove_projection(self, info: strawberry.Info, projection_id: strawberry.ID) -> Entity:
        updated = _em(info).remove_projection(str(projection_id))
        return _entity_to_gql(updated) if updated else None

    @strawberry.mutation
    def activate_projection(self, info: strawberry.Info, entity_id: strawberry.ID, projection_id: strawberry.ID, location: Optional[strawberry.ID] = None) -> Entity:
        updated = _em(info).activate_projection(str(entity_id), str(projection_id), location=str(location) if location else None)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def inapposite_travel(self, info: strawberry.Info, entity_id: strawberry.ID, location: strawberry.ID) -> Entity:
        updated = _em(info).travel(str(entity_id), str(location), transversal_type="inapposite")
        return _entity_to_gql(updated)

    @strawberry.mutation
    def update_entity(self, info: strawberry.Info, input: UpdateEntityInput) -> Entity:
        e = _em(info).get(str(input.id))
        if input.name is not None:
            e.name = input.name
        if input.razmerit is not None:
            e.razmerit = input.razmerit
        if input.current_universe is not None:
            e.current_universe = input.current_universe
        if input.current_location is not None:
            e.current_location = input.current_location
        if input.hidden is not None:
            e.hidden = input.hidden
        if input.unpublished is not None:
            e.unpublished = input.unpublished
        if input.known_to is not None:
            e.known_to = input.known_to
        if input.background_image is not None:
            e.background_image = input.background_image
        if input.owned_by is not None:
            e.owned_by = input.owned_by
        if input.suitable_life_path_ids is not None:
            e.suitable_life_path_ids = input.suitable_life_path_ids
        if input.overlay is not None:
            e.overlay = input.overlay if input.overlay != "" else None
        if input.starter_location is not None:
            e.starter_location = input.starter_location
        if input.nav_positions is not None:
            e.nav_positions = json.loads(input.nav_positions)
        if input.lora_config is not None:
            e.lora_config = json.loads(input.lora_config) if input.lora_config else None
        updated = _em(info).update(e)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def delete_entity(self, info: strawberry.Info, id: strawberry.ID, rmtree: bool = False) -> bool:
        return _em(info).delete(str(id), rmtree=rmtree)

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
        if input.polarity is not None:
            ts.polarity = input.polarity
        if input.statement is not None:
            ts.statement = input.statement
        if input.notes is not None:
            ts.notes = input.notes
        if input.from_type is not None:
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
        updated = _em(info).update_traitsetting(ts)
        return _ts_to_gql(updated)

    # ── Traitset CRUD ────────────────────────────────────

    @strawberry.mutation
    def create_traitset(self, info: strawberry.Info, id: str, name: str, universes: list[str],
                        entity_types: Optional[list[EntityType]] = None, description: str = "",
                        order: int = 0, limit: int = 1,
                        polarity: Optional[Polarity] = None) -> TraitSetRef:
        from transversal.domain import TraitSet as DomainTraitSet
        ts = DomainTraitSet(id=id, name=name, universes=universes,
                            entity_types=entity_types or [], description=description,
                            order=order, limit=limit, polarity=polarity)
        created = _em(info).repo.create_traitset(ts)
        return TraitSetRef(id=created.id, name=created.name, universes=created.universes,
                           entity_types=created.entity_types, order=created.order, limit=created.limit,
                           polarity=created.polarity)

    @strawberry.mutation
    def update_traitset(self, info: strawberry.Info, id: strawberry.ID, name: Optional[str] = None,
                        universes: Optional[list[str]] = None, entity_types: Optional[list[EntityType]] = None,
                        description: Optional[str] = None, order: Optional[int] = None,
                        limit: Optional[int] = None, polarity: Optional[Polarity] = None,
                        clear_polarity: bool = False) -> TraitSetRef:
        existing = _em(info).repo.get_traitset_by_id(str(id))
        if not existing: raise ValueError(f"TraitSet '{id}' not found")
        old_polarity = existing.polarity
        if name is not None: existing.name = name
        if universes is not None: existing.universes = universes
        if entity_types is not None: existing.entity_types = entity_types
        if description is not None: existing.description = description
        if order is not None: existing.order = order
        if limit is not None: existing.limit = limit
        if clear_polarity:
            existing.polarity = None
        elif polarity is not None:
            existing.polarity = polarity
        updated = _em(info).repo.update_traitset(existing)
        from transversal.services.polarity import propagate_traitset_polarity
        propagate_traitset_polarity(_em(info).repo, str(id), old_polarity, existing.polarity)
        return TraitSetRef(id=updated.id, name=updated.name, universes=updated.universes,
                           entity_types=updated.entity_types, order=updated.order, limit=updated.limit,
                           polarity=updated.polarity)

    @strawberry.mutation
    def delete_traitset(self, info: strawberry.Info, id: strawberry.ID) -> str:
        result = _em(info).repo.delete_traitset(str(id))
        return f"Deleted traitset and {result['traits_removed']} traits, {result['settings_removed']} settings"

    @strawberry.mutation
    def reorder_traitsets(self, info: strawberry.Info, ids: list[strawberry.ID]) -> bool:
        _em(info).repo.reorder_traitsets([str(i) for i in ids])
        return True

    # ── Trait CRUD ────────────────────────────────────────

    @strawberry.mutation
    def create_trait(self, info: strawberry.Info, input: TraitInput) -> TraitRef:
        from transversal.domain import Trait as DomainTrait
        t = DomainTrait(
            id=input.id, name=input.name, universes=input.universes,
            traitset_id=str(input.traitset_id),
            default_die_type=input.default_die_type,
            default_rating_type=input.default_rating_type,
            possible_sfx_ids=[str(s) for s in input.possible_sfx_ids],
            default_sfx_ids=[str(s) for s in input.default_sfx_ids],
            location_restricted=input.location_restricted,
            default_ego=input.default_ego,
            polarity=input.polarity,
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
            location_restricted=created.location_restricted,
            default_ego=created.default_ego,
            polarity=created.polarity,
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
        if input.default_sfx_ids is not None:
            existing.default_sfx_ids = [str(s) for s in input.default_sfx_ids]
        if input.location_restricted is not None:
            existing.location_restricted = input.location_restricted
        if input.default_ego is not None:
            existing.default_ego = input.default_ego
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
        return TraitRef(
            id=updated.id, name=updated.name, universes=updated.universes,
            traitset_id=updated.traitset_id,
            default_die_type=updated.default_die_type,
            default_rating_type=updated.default_rating_type,
            possible_sfx_ids=updated.possible_sfx_ids,
            default_sfx_ids=updated.default_sfx_ids,
            location_restricted=updated.location_restricted,
            default_ego=updated.default_ego,
            polarity=updated.polarity,
            display_names=[
                GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                    ratings=dn.ratings)
                for dn in updated.display_names
            ],
        )

    @strawberry.mutation
    def delete_trait(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_trait(str(id))

    # ── SFX CRUD ──────────────────────────────────────────

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
            effects=[_effect_input_to_domain(e) for e in input.effects],
        )
        created = _em(info).repo.create_sfx(s)
        # Also register with the in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(created)
        return SfxRef(
            id=created.id, name=created.name, description=created.description,
            trigger=created.trigger, limit=created.limit,
            conditions=[_condition_to_gql(c) for c in created.conditions],
            effects=[_effect_to_gql(e) for e in created.effects],
        )

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
        if input.effects is not None:
            existing.effects = [_effect_input_to_domain(e) for e in input.effects]
        updated = _em(info).repo.update_sfx(existing)
        # Also update in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(updated)
        return SfxRef(
            id=updated.id, name=updated.name, description=updated.description,
            trigger=updated.trigger, limit=updated.limit,
            conditions=[_condition_to_gql(c) for c in updated.conditions],
            effects=[_effect_to_gql(e) for e in updated.effects],
        )

    @strawberry.mutation
    def delete_sfx(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_sfx(str(id))

    @strawberry.mutation
    def add_owner_sfx(
        self,
        info: strawberry.Info,
        owner_refs: list[OwnerRefInput],
        sfx_id: strawberry.ID,
    ) -> bool:
        """Add one SFX id to every referenced owner (batch, idempotent)."""
        from transversal.services.sfx_owner import add_sfx_to_owner

        repo = _em(info).repo
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

    @strawberry.mutation
    def send_message(self, info: strawberry.Info, input: SendMessageInput) -> Message:
        """Send a persistent message from one entity to another.

        Publishes a ``message_received`` SSE event to all active sessions.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.sender_entity_id),
            str(input.recipient_entity_id),
            body=input.body,
            kind=input.kind.value if input.kind else "letter",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": msg.kind.value if hasattr(msg.kind, 'value') else msg.kind,
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": gql_msg.relationship_description,
                },
            ))

        return gql_msg

    @strawberry.mutation
    def add_journal_entry(self, info: strawberry.Info, input: JournalEntryInput) -> Message:
        """Add a personal journal entry for an entity.

        Journal entries are self-referential (character writes to themself)
        and visible to the GM. No recipient parameter needed.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.entity_id),
            str(input.entity_id),
            body=input.body,
            kind="journal",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": "journal",
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": "",
                },
            ))

        return gql_msg

    @strawberry.mutation
    def create_relationship(self, info: strawberry.Info, input: CreateRelationshipInput) -> Relationship:
        """Create (or update) a directional relationship edge between two entities.

        Returns the real ArangoDB edge key as ``id`` so callers can attach
        relationship-scoped trait settings (e.g. conspyramid rank/role) to it.
        """
        repo = _em(info).repo
        # Upsert: delete first if exists, then create fresh
        repo.delete_relationship(str(input.from_entity_id), str(input.to_entity_id), input.type)
        edge = repo.create_relationship(
            str(input.from_entity_id), str(input.to_entity_id),
            input.type, description=input.description,
        )
        return Relationship(
            id=edge["_key"],
            from_entity_id=str(input.from_entity_id),
            to_entity_id=str(input.to_entity_id),
            type=input.type,
            description=input.description,
        )

    @strawberry.mutation
    def delete_relationship(self, info: strawberry.Info, input: DeleteRelationshipInput) -> bool:
        """Delete a directional relationship edge between two entities."""
        repo = _em(info).repo
        return repo.delete_relationship(
            str(input.from_entity_id), str(input.to_entity_id), input.type,
        )

    @strawberry.mutation
    def add_relationship_trait(self, info: strawberry.Info, from_entity_id: strawberry.ID,
                               to_entity_id: strawberry.ID, rel_type: str = "relation",
                               trait_id: strawberry.ID = "", die: GqlDieType = GqlDieType.D6,
                               traitset_id: str = "ts-relations-b114",
                               statement: str = "") -> TraitSetting:
        """Create a rated trait on a relationship edge.

        Attaches to the *real* ArangoDB edge key (not a synthetic key), so the
        faction canvas can read rank/role traits back.
        """
        repo = _em(info).repo
        rel = repo.get_relationship(str(from_entity_id), str(to_entity_id), rel_type)
        if not rel:
            rel = repo.create_relationship(str(from_entity_id), str(to_entity_id), rel_type)
        edge_key = rel["_key"]

        ts = DomainTraitSetting(
            id=f"{edge_key}:{trait_id}",
            entity_id=edge_key,
            trait_id=str(trait_id),
            traitset_id=traitset_id,
            from_type="relationship",
            dice=[die],
            statement=statement,
        )
        created = repo.create_traitsetting(ts)
        return _ts_to_gql(created)

    @strawberry.mutation
    def update_message(self, info: strawberry.Info, input: UpdateMessageInput) -> bool:
        """Update after_ids and/or threads on an existing message."""
        repo = _em(info).repo
        return repo.update_message(
            str(input.id),
            after_ids=[str(a) for a in input.after_ids] if input.after_ids is not None else None,
            threads=input.threads,
        )

    @strawberry.mutation
    def start_term(self, info: strawberry.Info, entity_id: strawberry.ID,
                   faction_id: strawberry.ID, path_id: strawberry.ID) -> GqlPendingTerm:
        """Begin (or restart) a term in a faction's life path.

        Sets the entity's pending-term checkpoint to the path's entry table and
        persists it so the term can be resumed later.
        """
        from transversal.services.lifepath_executor import start_term as start_lp_term

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        pt = start_lp_term(entity, str(faction_id), str(path_id), repo)
        repo.update_entity(entity)

        return GqlPendingTerm(
            faction_id=pt.faction_id,
            path_id=pt.path_id,
            current_table_id=pt.current_table_id,
            continuation=pt.continuation,
        )

    @strawberry.mutation
    def resolve_step(self, info: strawberry.Info, entity_id: strawberry.ID,
                     roll: Optional[int] = None,
                     tier: Optional[GqlOutcomeTier] = None,
                     index: Optional[int] = None) -> LifePathStepResult:
        """Resolve the current pending roll-table step in a life path term.

        ``index`` is a manual/click selection (1-based); ``roll`` is a rolled
        number for range/index/weight tables; ``tier`` is an outcome tier for
        check tables. Immediate effects apply now; deferred-timing effects are
        queued into the shared scheduler.
        """
        from transversal.domain import OutcomeTier as DomainOutcomeTier
        from transversal.services.lifepath_executor import resolve_step as resolve_lp_step

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        domain_tier = DomainOutcomeTier(tier.value) if tier is not None else None
        summary = resolve_lp_step(
            entity, repo, roll=roll, tier=domain_tier, index=index,
            engine=info.context["effects_engine"],
        )

        pt = summary.get("pending_term")
        pending_term = (
            GqlPendingTerm(
                faction_id=pt.faction_id,
                path_id=pt.path_id,
                current_table_id=pt.current_table_id,
                continuation=pt.continuation,
            )
            if pt is not None
            else None
        )

        return LifePathStepResult(
            done=summary.get("done", False),
            applied=summary.get("applied", []),
            pending_choices=summary.get("pending_choices", []),
            mustered=summary.get("mustered", False),
            mishap_muster=summary.get("mishap_muster", False),
            pending_term=pending_term,
            scheduled=summary.get("scheduled", 0),
            error=summary.get("error"),
            table_id=summary.get("table_id"),
            entry_label=summary.get("entry_label"),
        )

    @strawberry.mutation
    def teach_trait(self, info: strawberry.Info, teacher_id: strawberry.ID, student_id: strawberry.ID,
                    trait_setting_id: strawberry.ID) -> TeachResult:
        from transversal.services.trait_transfer import teach_trait

        repo = _em(info).repo
        result = teach_trait(str(teacher_id), str(student_id), str(trait_setting_id), repo)
        # Spend razmerit from teacher
        _raz(info).spend(str(teacher_id), 1, "teach_trait")
        return TeachResult(
            student_trait_setting_id=result["student_trait_setting"].id,
            razmerit_cost=1,
        )

    @strawberry.mutation
    def gift_trait(self, info: strawberry.Info, giver_id: strawberry.ID, recipient_id: strawberry.ID,
                   trait_setting_id: strawberry.ID) -> GiftResult:
        from transversal.services.trait_transfer import gift_trait

        repo = _em(info).repo
        result = gift_trait(str(giver_id), str(recipient_id), str(trait_setting_id), repo)
        return GiftResult(
            transferred_trait_id=result["transferred_trait"].id,
            relationship_created=result.get("relationship_created") is not None,
        )

    @strawberry.mutation
    def take_trait(self, info: strawberry.Info, taker_id: strawberry.ID, victim_id: strawberry.ID,
                   trait_setting_id: strawberry.ID, method: str = "stealth") -> TakeResult:
        from transversal.services.trait_transfer import take_trait

        repo = _em(info).repo
        result = take_trait(str(taker_id), str(victim_id), str(trait_setting_id), method, repo)
        contest = result.get("contest_result")
        summary = ""
        if contest:
            if hasattr(contest, 'player_result') and hasattr(contest.player_result, 'highest'):
                summary = f"taker {contest.player_result.highest} vs victim {contest.opponent_result.highest} — {'success' if result['success'] else 'failure'}"
            else:
                summary = f"{'success' if result['success'] else 'failure'}"
        return TakeResult(
            success=result["success"],
            contest_summary=summary,
            transferred_trait_id=result["transferred_trait"].id if result.get("transferred_trait") else None,
            stolen=result.get("stolen", False),
        )

    @strawberry.mutation
    def save_life_path(self, info: strawberry.Info, id: str, name: str, universe: str,
                       description: str,
                       entry_table_id: str = "",
                       discovery: Optional[strawberry.scalars.JSON] = None) -> strawberry.scalars.JSON:
        """Create or update a life path definition. For GM content authoring."""
        from transversal.domain import DiscoveryBlock, LifePath

        d = None
        if discovery:
            d = DiscoveryBlock(
                at_location=discovery.get("atLocation", []) or [],
                knows_entity=discovery.get("knowsEntity", []) or [],
                possesses_trait=discovery.get("possessesTrait", []) or [],
                has_trait_rating=discovery.get("hasTraitRating"),
                has_relationship=discovery.get("hasRelationship", []) or [],
            )

        import uuid
        if not id:
            id = f"lp-{uuid.uuid4().hex[:8]}"
        lp = LifePath(
            id=id, name=name, universe=universe, description=description,
            entry_table_id=entry_table_id, discovery=d,
        )

        repo = info.context["entity_manager"].repo
        existing = repo.get_lifepath(id)
        if existing:
            repo.update_lifepath(lp)
        else:
            repo.create_lifepath(lp)
        return {"ok": True, "id": id}

    @strawberry.mutation
    def delete_life_path(self, info: strawberry.Info, id: strawberry.ID) -> strawberry.scalars.JSON:
        repo = info.context["entity_manager"].repo
        repo.delete_lifepath(str(id))
        return {"ok": True}

    @strawberry.mutation
    def save_roll_table(self, info: strawberry.Info, input: RollTableInput) -> RollTable:
        """Create or update a roll table. Empty ``id`` generates a new key."""
        import uuid

        repo = _em(info).repo
        table = _roll_table_input_to_domain(input)
        if not table.id:
            table.id = f"rt-{uuid.uuid4().hex[:8]}"

        existing = repo.get_roll_table(table.id)
        if existing is None:
            saved = repo.create_roll_table(table)
        else:
            # Preserve canvas layout positions — they are managed by
            # set_roll_table_position, not by full-table saves.
            table.canvas_x = existing.canvas_x
            table.canvas_y = existing.canvas_y
            saved = repo.update_roll_table(table)
        return _roll_table_to_gql(saved)

    @strawberry.mutation
    def delete_roll_table(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_roll_table(str(id))

    @strawberry.mutation
    def set_roll_table_position(self, info: strawberry.Info, id: strawberry.ID, x: Optional[float] = None, y: Optional[float] = None) -> Optional[RollTable]:
        """Persist a roll table's canvas position (x/y null clears it)."""
        t = _em(info).repo.set_roll_table_position(str(id), x, y)
        return _roll_table_to_gql(t) if t else None

    @strawberry.mutation
    def clear_roll_table_positions(self, info: strawberry.Info, life_path_id: strawberry.ID) -> int:
        """Clear all saved canvas positions for a life path's roll tables."""
        return _em(info).repo.clear_roll_table_positions(str(life_path_id))

    @strawberry.mutation
    def apply_effects(self, info: strawberry.Info, entity_id: strawberry.ID,
                      effects: list[EffectInput]) -> EffectApplicationResult:
        """Apply a set of effects to an entity in-memory and persist them.

        Returns the applied summaries plus any unresolved ``{choose_*}`` targets
        the caller must resolve (via :meth:`resolve_effect_targets`).
        """
        from transversal.services.effects_commit import commit_effects

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        domain_effects = [_effect_input_to_domain(e) for e in effects]
        result = commit_effects(entity, domain_effects, repo)
        return _effects_result_to_gql(result)

    @strawberry.mutation
    def resolve_effect_targets(self, info: strawberry.Info, entity_id: strawberry.ID,
                               resolutions: list[EffectTargetResolutionInput]) -> EffectApplicationResult:
        """Re-apply previously-pending effects with their resolved targets."""
        from transversal.services.effects_commit import commit_effects

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        resolved = []
        for r in resolutions:
            eff = _effect_input_to_domain(r.effect)
            field = r.field or "target"
            if field in ("target_scope", "entity_scope"):
                from transversal.services.effects_applier import _resolve_scope_choose
                eff = eff.model_copy(update={field: _resolve_scope_choose(getattr(eff, field), r.target)})
            elif "." in field:
                top, _, sub = field.partition(".")
                ctx = dict(eff.context or {})
                ctx[sub] = r.target
                eff = eff.model_copy(update={top: ctx})
            else:
                eff = eff.model_copy(update={field: r.target})
            resolved.append(eff)
        result = commit_effects(entity, resolved, repo)
        return _effects_result_to_gql(result)

    @strawberry.mutation
    def set_consequence_options(self, info: strawberry.Info, entity_id: strawberry.ID,
                                options: list[ConsequenceOptionInput]) -> Entity:
        """Replace an entity's authored consequence options (location moves)."""
        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        entity.consequence_options = [_consequence_option_input_to_domain(o) for o in options]
        repo.update_entity(entity)
        return _entity_to_gql(entity)


schema = strawberry.Schema(query=Query, mutation=Mutation)
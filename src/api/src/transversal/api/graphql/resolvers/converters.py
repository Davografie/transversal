"""Converters — split out of src/api/src/transversal/api/graphql/schema.py."""

import json
import strawberry

from transversal.api.graphql.types import AgencyEdge
from transversal.api.graphql.types import Attunement
from transversal.api.graphql.types import BoundVariable
from transversal.api.graphql.types import Condition
from transversal.api.graphql.types import ConditionInput
from transversal.api.graphql.types import ConsequenceOption
from transversal.api.graphql.types import ConsequenceOptionInput
from transversal.api.graphql.types import Effect as GqlEffect
from transversal.api.graphql.types import EffectApplicationResult
from transversal.api.graphql.types import EffectDuration as GqlEffectDuration
from transversal.api.graphql.types import EffectFieldDef as GqlEffectFieldDef
from transversal.api.graphql.types import EffectInput
from transversal.api.graphql.types import Entity
from transversal.api.graphql.types import HistoricalRecord
from transversal.api.graphql.types import LifePath as GqlLifePath
from transversal.api.graphql.types import Message
from transversal.api.graphql.types import MessageKind
from transversal.api.graphql.types import PendingChoiceRef
from transversal.api.graphql.types import Player as GqlPlayer
from transversal.api.graphql.types import RollTable
from transversal.api.graphql.types import RollTableCheck
from transversal.api.graphql.types import RollTableCheckInput
from transversal.api.graphql.types import RollTableEntry
from transversal.api.graphql.types import RollTableEntryInput
from transversal.api.graphql.types import RollTableInput
from transversal.api.graphql.types import ScheduledEvent as GqlScheduledEvent
from transversal.api.graphql.types import SfxRef
from transversal.api.graphql.types import TargetSpecInput
from transversal.api.graphql.types import Timer as GqlTimer
from transversal.api.graphql.types import TraitDisplayName as GqlTraitDisplayName
from transversal.api.graphql.types import TraitRef
from transversal.api.graphql.types import TraitSetting
from transversal.api.graphql.types import Zone
from transversal.domain import Condition as DomainCondition
from transversal.domain import ConsequenceOption as DomainConsequenceOption
from transversal.domain import Effect as DomainEffect
from transversal.domain import EffectDuration as DomainEffectDuration
from transversal.domain import Entity as DomainEntity
from transversal.domain import HistoricalRecord as DomainHistoricalRecord
from transversal.domain import Player as DomainPlayer
from transversal.domain import RollTable as DomainRollTable
from transversal.domain import RollTableCheck as DomainRollTableCheck
from transversal.domain import RollTableEntry as DomainRollTableEntry
from transversal.domain import ScheduledEvent as DomainScheduledEvent
from transversal.domain import Timer as DomainTimer
from transversal.domain import TraitSetting as DomainTraitSetting
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService
from transversal.services.target_spec import TargetSpec
from typing import Optional


def _em(info: strawberry.Info) -> EntityManager:
    return info.context["entity_manager"]

def _raz(info: strawberry.Info) -> RazmeritService:
    return info.context["razmerit_service"]

def _maybe_rearm_passives(*triggers: str) -> None:
    """Re-arm the global passive rule set when an ``on_session_start`` SFX changes.

    Passive rules are armed once at [Session] Start into an in-memory snapshot
    (``roll_deferral.arm_passive``). Creating/editing/deleting such an SFX leaves
    that snapshot stale until the next [Session] Start, so a timing or
    targeting-path edit silently does nothing. Re-arm here so the change takes
    effect immediately.
    """
    if "on_session_start" not in triggers:
        return
    from transversal.services.state_events import fire_session_start
    fire_session_start()

def _resolve_relationship_endpoint(repo, entity_id, elevated: bool = False):
    """Resolve a personal-relationship endpoint to ``(id, is_projection)``.

    Elevated + multiversal → the entity itself (soul-level, universal).
    Otherwise the entity's active projection (body-level, universe-local),
    falling back to the entity when it has no projection.
    """
    entity = repo.get_entity(str(entity_id))
    if entity is None:
        return str(entity_id), False
    if elevated and repo.is_transversal(entity):
        return str(entity_id), False
    if entity.current_projection:
        return str(entity.current_projection), True
    return str(entity_id), False

def _entity_to_gql(e: DomainEntity) -> Entity:
    return Entity(
        id=e.id, type=e.type, name=e.name, razmerit=e.razmerit,
        total_dice_bonus=e.total_dice_bonus, effect_dice_bonus=e.effect_dice_bonus,
        current_universe=e.current_universe, current_location=e.current_location,
        current_projection=e.current_projection,
        hidden=e.hidden, unpublished=e.unpublished, known_to=e.known_to,
        support_eligible=e.support_eligible,
        sfx_ids=e.sfx_ids,
        _background_image=e.background_image, overlay=e.overlay,
        starter_location=e.starter_location,
        zones=[Zone(background_image=z.background_image, location_id=z.location_id, x=z.x, y=z.y) for z in e.zones],
        map_x=e.map_x, map_y=e.map_y,
        nav_positions=json.dumps(e.nav_positions) if e.nav_positions else "{}",
        node_ids=e.node_ids, owned_by=e.owned_by,
        attunements=[
            Attunement(op=a.op.value, universe=a.universe, projection_id=a.projection_id,
                       scope=a.scope.value, until=a.until, source_sfx_id=a.source_sfx_id)
            for a in e.attunements
        ],
        lora_config=json.dumps(e.lora_config) if e.lora_config else None,
        prompt_steering=e.prompt_steering or None,
        prompt_include_ancestors=e.prompt_include_ancestors,
    )

def _player_to_gql(p: DomainPlayer, repo) -> GqlPlayer:
    agency = [
        AgencyEdge(entity_id=edge["entity_id"], main=edge["main"])
        for edge in repo.get_agency_edges(p.id)
    ]
    return GqlPlayer(
        id=p.id,
        name=p.name,
        role=p.role,
        last_spotlight_at=p.last_spotlight_at,
        last_main_entity_id=p.last_main_entity_id,
        agency=agency,
    )

def _ts_to_gql(s: DomainTraitSetting) -> TraitSetting:
    # Same rule as the read path, from the same helper: an EMPTY trait rates with
    # no dice. Shared so the two converters cannot drift apart again.
    from transversal.api.graphql.type_defs.traits import rating_dice
    return TraitSetting(
        id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
        rating_type=s.rating_type, dice=rating_dice(s),
        spent_dice=s.spent_dice,
        capacity=s.capacity,
        polarity=s.polarity,
        statement=s.statement,
        notes=s.notes,
        order=s.order,
        tags=s.tags,
        from_type=s.from_type, projection_id=s.projection_id,
        parent_traitsetting_id=s.parent_traitsetting_id,
        sfx_ids=s.sfx_ids,
        known_to=s.known_to,
        enabled=s.enabled,
    )

def _trait_to_gql(t) -> TraitRef:
    """Convert a domain Trait to a GraphQL TraitRef."""
    return TraitRef(
        id=t.id, name=t.name, universes=t.universes,
        traitset_id=t.traitset_id, default_die_type=t.default_die_type,
        default_rating_type=t.default_rating_type,
        possible_sfx_ids=t.possible_sfx_ids,
        default_sfx_ids=t.default_sfx_ids,
        possible_subtrait_ids=t.possible_subtrait_ids,
        possible_subtraitset_ids=t.possible_subtraitset_ids,
        default_ego=t.default_ego,
        tags=list(t.tags or []),
        polarity=t.polarity,
        display_names=[
            GqlTraitDisplayName(name=dn.name, universe=dn.universe, ratings=dn.ratings)
            for dn in t.display_names
        ],
    )

def _message_to_gql(m: "Message", repo) -> Message:
    """Convert a domain Message to GraphQL Message, resolving the
    ``relation`` relationship description between sender and recipient."""
    from transversal.domain import MessageKind as DomainMessageKind
    rel = repo.get_relationship(m.sender_entity_id, m.recipient_entity_id, "relation")
    if rel is None:
        rel = repo.get_relationship(m.recipient_entity_id, m.sender_entity_id, "relation")
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

        die_filter=e.die_filter or None,
        negative=e.negative,
        context=e.context,
        duration=_duration_to_gql(e.duration),
        target_spec=e.target_spec.model_dump() if e.target_spec else None,
        entity_spec=e.entity_spec.model_dump() if e.entity_spec else None,
        owner_spec=e.owner_spec.model_dump() if e.owner_spec else None,
        result_spec=e.result_spec.model_dump() if e.result_spec else None,
        refs=_refs_to_gql(e.refs),
        output=e.output,
        conditions=[_condition_to_gql(c) for c in e.conditions],
    )

def _condition_to_gql(c: DomainCondition) -> Condition:
    return Condition(
        type=c.type, subject=c.subject, target=c.target,
        targets=list(getattr(c, "targets", []) or []), value=c.value,
        operator=c.operator, narrative=c.narrative,
        spec=c.spec.model_dump() if c.spec else None,
    )

def _scheduled_event_to_gql(e: DomainScheduledEvent, repo=None) -> GqlScheduledEvent:
    # The rule that booked the timer, by name — a running countdown is only
    # meaningful with its origin (the sheet's "1 beat" needs to say *One Trick*).
    source_name = None
    if repo is not None and e.source_sfx_id:
        sfx = repo.get_sfx(e.source_sfx_id)
        source_name = getattr(sfx, "name", None) if sfx is not None else None
    return GqlScheduledEvent(
        id=e.id,
        target_type=e.target_type,
        target_id=e.target_id,
        effect=_effect_to_gql(e.effect),
        timers=[GqlTimer(event=t.event, remaining=t.remaining) for t in e.timers],
        combine=e.combine,
        source_sfx_id=e.source_sfx_id,
        source_sfx_name=source_name,
    )

def _entry_to_gql(e: DomainRollTableEntry) -> RollTableEntry:
    return RollTableEntry(
        label=e.label, description=e.description,
        min_value=e.min_value, max_value=e.max_value, weight=e.weight, tier=e.tier,
        conditions=[_condition_to_gql(c) for c in e.conditions],
        cost_effects=[_effect_to_gql(x) for x in e.cost_effects],
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
        bound_variables=[
            BoundVariable(
                name=bv.name,
                spec=(bv.spec.model_dump(mode="json", exclude_none=True) if bv.spec else None),
            )
            for bv in (t.bound_variables or [])
        ],
        canvas_x=t.canvas_x,
        canvas_y=t.canvas_y,
    )

def _effect_timing_to_domain(timing):
    """The domain's snake-case ``EffectTiming`` from the GraphQL enum's value.

    The GraphQL enum is spelled upper-case (``IMMEDIATE``) while the domain
    values are lower-case (``immediate``), and this seam passed the former to the
    latter — so `createSfx` rejected **every** effect-bearing SFX with a
    pydantic error that graphql-core then failed to format (it surfaced as
    ``'str' object has no attribute 'get_location'``). The editor only ever misses
    this because it saves through `updateSfx`.
    """
    from transversal.domain import EffectTiming
    value = getattr(timing, "value", timing)
    if isinstance(value, EffectTiming):
        return value
    return EffectTiming(str(value).strip().lower())


def _effect_input_to_domain(e: EffectInput) -> DomainEffect:
    return DomainEffect(
        timing=_effect_timing_to_domain(e.timing), type=e.type, action=e.action,
        target=e.target, entity=e.entity, result=e.result,

        die_filter=e.die_filter or {},
        negative=e.negative,
        context=e.context or {},
        duration=_duration_input_to_domain(e.duration),
        target_spec=_target_spec_from_input(e.target_spec),
        entity_spec=_target_spec_from_input(e.entity_spec),
        owner_spec=_target_spec_from_input(e.owner_spec),
        result_spec=_target_spec_from_input(e.result_spec),
        refs=_refs_from_input(e.refs),
        output=e.output,
        conditions=[_condition_input_to_domain(c) for c in (e.conditions or [])],
    )

def _refs_to_gql(refs: dict) -> dict | None:
    """Serialize ``Effect.refs`` to a JSON-friendly ``{name: {value, spec}}``."""
    if not refs:
        return None
    return {
        name: {
            "value": r.value,
            "spec": r.spec.model_dump() if r.spec else None,
        }
        for name, r in refs.items()
    }

def _refs_from_input(raw) -> dict:
    """Validate GraphQL JSON refs into the domain ``TargetRef`` map."""
    if not raw:
        return {}
    from transversal.domain import TargetRef

    out: dict[str, TargetRef] = {}
    for name, data in (raw or {}).items():
        if isinstance(data, dict):
            out[name] = TargetRef(
                value=data.get("value") or "",
                spec=_target_spec_from_input(data.get("spec")),
            )
    return out

def _target_spec_from_input(raw) -> Optional[TargetSpec]:
    """Validate a GraphQL JSON target spec into the domain model (None-safe)."""
    if not raw:
        return None
    from transversal.services.target_spec import TargetSpec

    return TargetSpec.model_validate(raw)


def _bound_variables_from_input(raw) -> list:
    """Validate an SFX's declared bound variables into domain models.

    A nameless or pathless entry is dropped rather than persisted: the editor can
    hold a half-typed row, and a stored variable that resolves to nothing would
    look like a live name that never binds.
    """
    from transversal.domain import BoundVariable as DomainBoundVariable

    out = []
    for item in raw or []:
        name = (getattr(item, "name", "") or "").strip()
        spec = _target_spec_from_input(getattr(item, "spec", None))
        if not name or spec is None:
            continue
        out.append(DomainBoundVariable(name=name, spec=spec))
    return out

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

def _structured_choice_to_dict(c) -> dict:
    """Serialize a ``StructuredChoice`` to the wire shape the picker consumes."""
    from transversal.services.effects_engine import effect_to_wire_dict

    return {
        "structured": True,
        "element": c.element,
        "candidates": c.candidates,
        "count": c.count,
        "field": c.field,
        "step_index": c.step_index,
        "source_kind": c.source_kind,
        "source_id": c.source_id,
        "source_sfx_id": c.source_sfx_id,
        "answers_so_far": c.answers_so_far,
        "sfx_name": c.sfx_name,
        "sfx_description": c.sfx_description,
        "effect": effect_to_wire_dict(c.effect),
        **({"continuation": [effect_to_wire_dict(e) for e in c.continuation]} if c.continuation else {}),
    }

def _effects_result_to_gql(result, structured=None) -> EffectApplicationResult:
    return EffectApplicationResult(
        applied=[a.summary for a in result.applied],
        pending_choices=[
            PendingChoiceRef(index=i, kind=c.kind, scope=c.scope, field=c.field, effect=_effect_to_gql(c.effect))
            for i, c in enumerate(result.pending_choices)
        ],
        structured=[_structured_choice_to_dict(c) for c in (structured or [])],
    )

def _resolve_continuation_effects(continuation, entity, repo, resolved, structured):
    """Resolve + apply a list of domain ``Effect``s in order.

    Defer the rest when one blocks on a ``choose`` (nested sequential
    continuation): the remaining effects are attached to the new pending choice.
    """
    from transversal.services.effects_engine import resolve_effect_spec_choices

    for i, eff in enumerate(continuation):
        if eff.refs:
            applied, pending = resolve_effect_spec_choices(eff, "refs." + next(iter(eff.refs)), {}, entity, repo)
            resolved.extend(applied)
            if pending:
                pending[-1].continuation = continuation[i + 1:]
                structured.extend(pending)
                return
        elif eff.target_spec is not None:
            applied, pending = resolve_effect_spec_choices(eff, "target", {}, entity, repo)
            resolved.extend(applied)
            if pending:
                pending[-1].continuation = continuation[i + 1:]
                structured.extend(pending)
                return
        else:
            resolved.append(eff)

def _condition_input_to_domain(c: ConditionInput) -> DomainCondition:
    return DomainCondition(
        type=c.type, subject=c.subject, target=c.target,
        targets=[str(t) for t in (c.targets or [])], value=c.value,
        operator=c.operator, narrative=c.narrative,
        spec=_target_spec_from_input(c.spec),
    )

def _target_spec_input_to_domain(inp: TargetSpecInput):
    """Convert a GraphQL target-spec draft into the domain ``TargetSpec``.

    Steps carry a flat shape over GraphQL (a discriminated union of inputs is
    awkward); ``kind`` selects the right step model. Unknown kinds become an
    empty ``select`` so the type-checker surfaces them as an error.
    """
    from transversal.services import target_spec as ts

    steps = []
    for s in (inp.steps or []):
        kind = s.kind
        if kind == "select":
            steps.append(ts.SelectStep(collection=s.collection or "", variable=s.variable or "", output=s.output))
        elif kind == "filter":
            steps.append(ts.FilterStep(field=s.field or "", operator=s.operator or "==", value=s.value, output=s.output))
        elif kind == "navigate":
            steps.append(ts.NavigateStep(edge=s.edge or "", dedup=bool(s.dedup), output=s.output))
        elif kind == "aggregate":
            steps.append(ts.AggregateStep(fn=s.fn or "", field=s.field,
                                          count=int(s.count or 1), output=s.output))
        elif kind == "random":
            # Retired as a step of its own: random sampling is an aggregation. A
            # client still sending the old spelling keeps working.
            steps.append(ts.AggregateStep(fn="random", count=int(s.count or 1), output=s.output))
        elif kind == "choose":
            steps.append(ts.ChooseStep(count=int(s.count or 1), output=s.output))
        elif kind == "top":
            # Retired as a step of its own: `top` is the aggregate function that
            # keeps the element carrying the extreme value (argmax/argmin).
            steps.append(ts.AggregateStep(
                fn="bottom" if s.direction == "asc" else "top", field=s.field,
                output=s.output))
        elif kind == "evaluate":
            steps.append(ts.EvaluateStep(operator=s.operator or "exists", field=s.field or "", value=s.value))
        else:
            steps.append(ts.SelectStep(collection=""))
    return ts.TargetSpec(steps=steps)

def _bindings_from_json(value) -> dict:
    """Turn a JSON activation scope into ``name → Binding`` for the resolver.

    Two shapes are accepted per name, because a caller inspecting a path may know
    only the variable's *type* (an element name) or may have a concrete value to
    seed it with:

    * ``"traitsetting"`` — the element type, no value;
    * ``{"element": "traitsetting", "cardinality": "many",
       "value": "id", "values": ["id", …]}``

    A name whose element cannot be determined is dropped: the resolver's
    ``select variable`` step reports it as unbound, which is the honest answer.
    """
    from transversal.services.target_resolver import Binding

    out: dict = {}
    if not isinstance(value, dict):
        return out
    for name, spec in value.items():
        if isinstance(spec, str):
            if spec:
                out[str(name)] = Binding(element=spec)
            continue
        if not isinstance(spec, dict):
            continue
        element = str(spec.get("element") or "")
        if not element:
            continue
        values = [str(v) for v in (spec.get("values") or [])]
        single = str(spec.get("value") or "")
        cardinality = str(spec.get("cardinality") or ("many" if values else "one"))
        if values and not single:
            single = values[0]
        if single and not values:
            values = [single]
        out[str(name)] = Binding(
            value=single, values=values, element=element, cardinality=cardinality,
        )
    return out

def _check_input_to_domain(c: RollTableCheckInput) -> DomainRollTableCheck:
    return DomainRollTableCheck(trait_ids=c.trait_ids, difficulty=c.difficulty, free_choice=c.free_choice)

def _entry_input_to_domain(e: RollTableEntryInput) -> DomainRollTableEntry:
    return DomainRollTableEntry(
        label=e.label, description=e.description,
        min_value=e.min_value, max_value=e.max_value, weight=e.weight, tier=e.tier,
        conditions=[_condition_input_to_domain(c) for c in e.conditions],
        cost_effects=[_effect_input_to_domain(x) for x in e.cost_effects],
        effects=[_effect_input_to_domain(x) for x in e.effects],
    )

def _roll_table_input_to_domain(t: RollTableInput) -> DomainRollTable:
    from transversal.domain import BoundVariable as DomainBoundVariable

    return DomainRollTable(
        id=t.id, name=t.name, universe=t.universe, life_path=t.life_path,
        scheme=t.scheme, roll_source=t.roll_source, trait_dice_count=t.trait_dice_count,
        die=t.die,
        check=(_check_input_to_domain(t.check) if t.check is not None else None),
        entries=[_entry_input_to_domain(e) for e in t.entries],
        bound_variables=[
            DomainBoundVariable(
                name=bv.name,
                spec=_target_spec_from_input(bv.spec) if bv.spec else None,
            )
            for bv in (t.bound_variables or [])
        ],
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
        after_ids=r.after_ids,
        created_at=r.created_at,
    )

def _sfx_ref(sfx, resolve=None) -> SfxRef:
    """Build the GraphQL SFX ref, including its derived card text
    ([[SFX Natural Language Plan]])."""
    from transversal.services.sfx_owner import owner_surfaces_for
    from transversal.services.sfx_text import sfx_text

    return SfxRef(
        id=sfx.id, name=sfx.name, description=sfx.description,
        trigger=sfx.trigger, limit=sfx.limit, source_kind=sfx.source_kind,
        owner_surfaces=sorted(owner_surfaces_for(sfx)),
        placement=sfx.placement, arming_scope=sfx.arming_scope,
        listener_spec=sfx.listener_spec.model_dump() if sfx.listener_spec else None,
        acquire_spec=sfx.acquire_spec.model_dump() if sfx.acquire_spec else None,
        implicit=bool(getattr(sfx, "implicit", False)),
        bound_variables=[
            BoundVariable(
                name=bv.name,
                spec=bv.spec.model_dump() if getattr(bv, "spec", None) else None,
            )
            for bv in (getattr(sfx, "bound_variables", None) or [])
        ],
        conditions=[_condition_to_gql(c) for c in sfx.conditions],
        effects=[_effect_to_gql(e) for e in sfx.effects],
        duration=_duration_to_gql(sfx.duration),
        card_text=sfx_text(sfx, resolve=resolve),
    )

def _action_meta_for(effect_type: str, effect_action: str):
    """The registry entry for an effect (type, action), or None."""
    from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY

    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect_type and meta.effect_action == effect_action:
            return meta
    return None

def _universe_options(repo) -> tuple[list[str], list[str]]:
    """``(values, labels)`` for the universes in the database.

    Content keys a universe by its ``current_universe`` handle (``three_realms``),
    falling back to the entity id — that handle is what an ``attune`` effect
    stores, so it must be the option *value*; the entity's name is the label.
    """
    pairs = []
    for entity in repo.list_all_entities():
        if getattr(entity, "type", "") != "universe":
            continue
        key = getattr(entity, "current_universe", "") or entity.id
        pairs.append((key, entity.name or key))
    pairs.sort(key=lambda p: p[1].lower())
    return [p[0] for p in pairs], [p[1] for p in pairs]

def _field_options(fdef, repo) -> tuple[list[str], list[str]]:
    """A field's options: dynamic when it declares a source, else its own list."""
    source = _OPTION_SOURCES.get(fdef.options_from)
    if source is not None:
        values, labels = source(repo)
        if values:
            return values, labels
    return list(fdef.options or []), []

def _relationship_type_options(repo) -> tuple[list[str], list[str]]:
    """The relationship-type vocabulary for an action field's picker.

    No separate labels: a type *is* its own name (`membership`, `relation`), unlike
    a universe key whose label is the world's name.
    """
    values = repo.list_relationship_types()
    return values, []


_OPTION_SOURCES = {
    "universes": _universe_options,
    "relationship_types": _relationship_type_options,
}

def _gql_field_def(fdef, repo) -> GqlEffectFieldDef:
    """One effect-action field, with its options resolved."""
    options, labels = _field_options(fdef, repo)
    return GqlEffectFieldDef(name=fdef.name, label=fdef.label, field_type=fdef.field_type,
                             required=fdef.required, default=fdef.default,
                             options=options, option_labels=labels,
                             hidden_when_ref=fdef.hidden_when_ref,
                             description=getattr(fdef, "description", "") or "")

def _life_path_to_gql(lp, *, walkable=None, reasons=()) -> GqlLifePath:
    """Convert a domain LifePath to the GraphQL type.

    ``walkable``/``reasons`` come from the entity-scoped read ([[B194]]); both are
    omitted by callers that did not ask about an entity, which is why ``walkable``
    stays ``None`` ("not evaluated") rather than defaulting to true.
    """
    return GqlLifePath(
        id=lp.id,
        name=lp.name,
        universe=lp.universe,
        description=lp.description if hasattr(lp, 'description') else "",
        entry_table_id=lp.entry_table_id,
        discovery=lp.discovery,
        conditions=[_condition_to_gql(c) for c in (getattr(lp, "conditions", None) or [])],
        walkable=walkable,
        unwalkable_reasons=list(reasons),
    )

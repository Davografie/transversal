"""Queries targeting — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import ConditionInput
from transversal.api.graphql.types import ConditionTypeOption
from transversal.api.graphql.types import ConsequenceOption
from transversal.api.graphql.types import EffectActionMeta as GqlEffectActionMeta
from transversal.api.graphql.types import EffectInput
from transversal.api.graphql.types import EffectVariable
from transversal.api.graphql.types import FilterFieldOption
from transversal.api.graphql.types import RefDef as GqlRefDef
from transversal.api.graphql.types import ScopeVariable
from transversal.api.graphql.types import SourceKindOption
from transversal.api.graphql.types import TargetCandidate
from transversal.api.graphql.types import TargetCatalog
from transversal.api.graphql.types import TargetCatalogAggregation
from transversal.api.graphql.types import TargetCatalogCollection
from transversal.api.graphql.types import TargetCatalogEdge
from transversal.api.graphql.types import TargetCatalogElement
from transversal.api.graphql.types import TargetCatalogField
from transversal.api.graphql.types import TargetLabel
from transversal.api.graphql.types import TargetSpecInput
from transversal.api.graphql.types import TargetTraceError
from transversal.api.graphql.types import TargetTraceResult
from transversal.api.graphql.types import TargetTraceType
from transversal.api.graphql.types import TriggerOption
from transversal.domain import Entity as DomainEntity
from transversal.domain import EntityType as DomainEntityType
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _action_meta_for,
    _condition_input_to_domain,
    _consequence_option_to_gql,
    _effect_input_to_domain,
    _em,
    _gql_field_def,
    _target_spec_input_to_domain,
)


@strawberry.type
class QueriesTargeting:
    """Mixin contributing 12 field(s) to the root type."""

    @strawberry.field
    def effect_actions(self, info: strawberry.Info) -> list[GqlEffectActionMeta]:
        from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
        repo = _em(info).repo
        return [
            GqlEffectActionMeta(
                action_id=m.action_id, label=m.label, description=m.description,
                category=m.category, group=m.group, effect_type=m.effect_type, effect_action=m.effect_action,
                valid_timings=m.valid_timings,
                fields=[_gql_field_def(f, repo) for f in m.fields],
                context_fields=[_gql_field_def(f, repo) for f in m.context_fields],
                implicit_target=m.implicit_target, implicit_result=m.implicit_result, implicit_timing=m.implicit_timing,
                output_element=m.output_element,
                requires_choice=m.requires_choice, target_kind=m.target_kind, path_elements=list(m.path_element), supports_duration=m.supports_duration,
                duration_elements=list(m.duration_elements),
                supports_polarity=m.supports_polarity, supports_return_exit=m.supports_return_exit,
                refs=[GqlRefDef(name=r.name, label=r.label, element=r.element) for r in m.refs],
                refs_first=m.refs_first,
            ) for m in EFFECT_ACTION_REGISTRY
        ]

    @strawberry.field
    def scope_variables(
        self, info: strawberry.Info,
        trigger: str = "",
        source_kind: Optional[str] = None,
    ) -> list[ScopeVariable]:
        """Typed ``{variable}`` tokens available to authored effects for a trigger
        (auto-fire, manual, or menu), plus the declared source variable when
        ``source_kind`` is set."""
        from transversal.services.menu_contexts import trigger_variables
        from transversal.services.target_catalog import source_kind as sk

        out = [ScopeVariable(name=v.name, type=v.type) for v in trigger_variables(trigger)]
        if source_kind:
            declared = sk(source_kind)
            if declared and not any(v.name == declared.variable for v in out):
                out.append(ScopeVariable(name=declared.variable, type=declared.element))
        return out

    @strawberry.field
    def triggers(self, info: strawberry.Info) -> list[TriggerOption]:
        """The activation-trigger vocabulary for the SFX editor, sourced from the backend."""
        from transversal.services.menu_contexts import TRIGGERS
        return [
            TriggerOption(value=t.value, label=t.label, group=t.group,
                          requires_source_elements=list(t.requires_source_elements))
            for t in TRIGGERS
        ]

    @strawberry.field
    def condition_types(self, info: strawberry.Info) -> list[ConditionTypeOption]:
        """The condition-type vocabulary for the SFX editor, sourced from the backend.

        Returned in the picker's order — grouped into bands, declaration order
        within a band (`ordered_condition_types`) — so the editor can render the
        grouping by grouping consecutive runs, with no taxonomy of its own.
        """
        from transversal.services.conditions import ordered_condition_types

        return [
            ConditionTypeOption(
                value=c.value, label=c.label,
                needs_target=c.needs_target, target_placeholder=c.target_placeholder,
                target_kind=c.target_kind, value_kind=c.value_kind,
                operators=list(c.operators), target_options=list(c.target_options),
                uses_spec=c.uses_spec,
                requires_context_any_of=list(c.requires_context_any_of),
                requires_source_elements=list(c.requires_source_elements),
                group=c.group,
            )
            for c in ordered_condition_types()
        ]

    @strawberry.field
    def condition_context_keys(
        self, info: strawberry.Info,
        trigger: Optional[str] = None,
        placement: Optional[str] = None,
        timing: Optional[str] = None,
    ) -> Optional[list[str]]:
        """The context keys available at an evaluation point (null = unrestricted).

        Answers "what can a condition read here?" for one point — an SFX-level
        condition (pass the trigger/placement) or an effect's own fire (pass its
        timing too). ``null`` means the site is not modelled, so nothing is
        forbidden: the map only ever forbids. The editor keeps an option out of a
        site that supplies none of the keys it reads; ``validate_sfx`` reports the
        exact per-condition gap.
        """
        from transversal.services.conditions import context_keys_for
        keys = context_keys_for(trigger, timing, placement or None)
        return None if keys is None else sorted(keys)

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

        ``kind`` is one of the target kinds (``location``, ``occupant``, ``entity``,
        ``trait``, ``traitset``, ``life_path``, ``roll_table``, ``rating_die``,
        ``universe``, ``projection``); ``scope`` is the
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
            TargetCandidate(id=c.id, name=c.name, universe=c.universe, subtitle=c.subtitle)
            for c in resolve_candidates(kind, scope, entity, repo, action, filter or {})
        ]

    @strawberry.field
    def target_filter_fields(self, info: strawberry.Info) -> list[FilterFieldOption]:
        """Candidate filter fields the SFX editor can build, sourced from the backend."""
        from transversal.services.effect_targets import FILTER_FIELDS
        return [
            FilterFieldOption(field=f.field, label=f.label, value_type=f.value_type, kinds=list(f.kinds), options=list(f.options))
            for f in FILTER_FIELDS
        ]

    @strawberry.field
    def target_labels(self, info: strawberry.Info, ids: list[strawberry.ID]) -> list[TargetLabel]:
        """Display names for ids — so authoring surfaces never show a raw id.

        Resolved through the same repository name resolver the card text renders
        with (entities, registry traits, trait sets, life paths, roll tables,
        universe keys), so what the editor shows and what the card says cannot
        drift.
        """
        from transversal.services.sfx_text import repo_name_resolver

        resolve = repo_name_resolver(_em(info).repo)
        return [TargetLabel(id=str(i), name=resolve(str(i)) or str(i)) for i in ids]

    @strawberry.field
    def target_catalog(self, info: strawberry.Info) -> TargetCatalog:
        """The declarative targeting catalog (element types, edges, fields,
        aggregations, collections) the targeting wizard composes specs from."""
        from transversal.services import target_catalog as tc
        return TargetCatalog(
            elements=[TargetCatalogElement(name=e.name, label=e.label) for e in tc.ELEMENT_TYPES.values()],
            edges=[
                TargetCatalogEdge(name=e.name, source=e.source, targets=list(e.target), cardinality=e.cardinality, label=e.label)
                for e in tc.EDGES
            ],
            fields=[
                TargetCatalogField(element=element_name, name=f.name, type=f.type, label=tc.field_label(f), options=list(f.options), operators=list(tc.operators_for(f)), references=f.references, suggest=f.suggest)
                for element_name, fields in tc.SCALAR_FIELDS.items()
                for f in fields.values()
            ],
            aggregations=[
                TargetCatalogAggregation(name=a.name, label=a.label, output=a.output,
                                         needs_field=a.needs_field, needs_count=a.needs_count,
                                         accepts=list(a.accepts))
                for a in tc.AGGREGATIONS
            ],
            collections=[
                TargetCatalogCollection(name=c.name, element=c.element, label=c.label, singular=c.singular)
                for c in tc.COLLECTIONS
            ],
            source_kinds=[
                SourceKindOption(value=s.value, label=s.label, element=s.element, variable=s.variable, owner_surface=s.owner_surface)
                for s in tc.SOURCE_KINDS
            ],
        )

    @strawberry.field
    def trace_target_spec(
        self, info: strawberry.Info,
        input: TargetSpecInput,
        destination_elements: Optional[list[str]] = None,
        destination_cardinality: Optional[str] = None,
        source_element: Optional[str] = None,
        variables: Optional[strawberry.scalars.JSON] = None,
    ) -> TargetTraceResult:
        """Type-check a targeting spec draft: the type after each step, step
        errors, and whether it reaches the requested destination type.

        ``destination_elements`` is the set of element types the effect field
        accepts — a list because a field may accept more than one (a die in a
        pool *or* a rating die); the spec is valid when it reaches any of them.
        ``source_element`` is the catalog element type of the SFX's declared
        ``source_kind``, so ``select source`` type-checks against it.
        ``variables`` maps a bound output-variable name to its catalog element
        type so ``select variable`` type-checks."""
        from transversal.services import target_spec as ts

        spec = _target_spec_input_to_domain(input)
        variables_map = variables if isinstance(variables, dict) else None
        types, errors = ts.trace(spec, source_element, variables_map)

        valid = False
        if destination_elements and destination_cardinality:
            wanted = [ts.ValueType(e, destination_cardinality) for e in destination_elements]
            valid, _ = ts.check(spec, wanted, source_element, variables_map)

        return TargetTraceResult(
            types=[
                TargetTraceType(element=(t.element if t else ""), cardinality=(t.cardinality if t else ""))
                for t in types
            ],
            errors=[TargetTraceError(step_index=e.step_index, message=e.message) for e in errors],
            valid=valid,
        )

    @strawberry.field
    def effect_variables(
        self, info: strawberry.Info,
        effects: list[EffectInput],
        source_element: Optional[str] = None,
        conditions: Optional[list[ConditionInput]] = None,
        trigger: Optional[str] = None,
        source_kind: Optional[str] = None,
    ) -> list[EffectVariable]:
        """The typed output variables exposed to a list of effects (in order).

        Traces the SFX's ``conditions`` first — they are evaluated before any
        effect, so the names their targeting paths output (e.g. ``d4_traits``) are
        in scope for every effect — then each effect's ``target_spec``/
        ``entity_spec``/``refs.*.spec`` in sequence, accumulating step ``outputs``
        typed by their resolved element. The targeting wizard offers the result as
        ``select variable`` candidates.

        ``trigger`` / ``source_kind`` seed the scope with the activation's **own**
        names (``{contest_entity_opponent}``, ``{trait_setting}``, …) — declared
        on the trigger and the source, and bound by the engine when the rule
        fires, so a path can *start* from them and not only join to an output.
        """
        from transversal.services import target_spec as ts
        from transversal.services.target_catalog import scope_seed_names

        scope = {
            name: ts.ValueType(element, "one")
            for name, element in scope_seed_names(trigger, source_kind).items()
        }
        for c in (conditions or []):
            cd = _condition_input_to_domain(c)
            if cd.spec is not None:
                scope = ts.spec_variables(cd.spec, source_element, scope)
        for e in (effects or []):
            d = _effect_input_to_domain(e)
            specs = [d.target_spec, d.entity_spec]
            specs += [r.spec for r in (d.refs or {}).values() if r and r.spec]
            for spec in specs:
                if spec is not None:
                    scope = ts.spec_variables(spec, source_element, scope)
            # A named reference is itself in scope for whatever follows it — the
            # engine binds each resolved ref into the activation scope (see
            # ``effects_engine._bind_ref_value``), which is what lets a later path
            # compare against it (``filter universe == {universe}``). Typed by the
            # reference's declared element so the wizard can offer it, and filter
            # it, by type.
            meta = _action_meta_for(d.type, d.action)
            for ref in (meta.refs if meta is not None else []):
                scope[ref.name] = ts.ValueType(ref.element, "one")
            # The step's own result, when the author named it (`Effect.output`):
            # the runtime binds the produced element under that name
            # (``effects_applier.publish_effect_output``), so a later step can
            # `select variable {beast}` instead of re-finding what it just made.
            if (getattr(d, "output", "") or "").strip() and meta is not None and meta.output_element:
                scope[d.output.strip()] = ts.ValueType(meta.output_element, "one")
        return [
            EffectVariable(name=k, element=v.element, cardinality=v.cardinality)
            for k, v in scope.items() if v.element
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
        """Return the GM hitch menu — SFX from the gm/table owners whose
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

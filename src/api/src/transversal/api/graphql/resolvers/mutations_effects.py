"""Mutations effects — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import ConsequenceOptionInput
from transversal.api.graphql.types import EffectApplicationResult
from transversal.api.graphql.types import EffectInput
from transversal.api.graphql.types import EffectTargetResolutionInput
from transversal.api.graphql.types import Entity
from transversal.api.graphql.types import LifePathStepResult
from transversal.api.graphql.types import OutcomeTier as GqlOutcomeTier
from transversal.api.graphql.types import PendingTerm as GqlPendingTerm
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _consequence_option_input_to_domain,
    _effect_input_to_domain,
    _effects_result_to_gql,
    _em,
    _entity_to_gql,
    _resolve_continuation_effects,
    _structured_choice_to_dict,
)


@strawberry.type
class MutationsEffects:
    """Mixin contributing 6 field(s) to the root type."""

    @strawberry.mutation
    def apply_effects(self, info: strawberry.Info, entity_id: strawberry.ID,
                      effects: list[EffectInput]) -> EffectApplicationResult:
        """Apply a set of effects to an entity in-memory and persist them.

        Returns the applied summaries plus any unresolved targets the caller
        must resolve (via :meth:`resolve_effect_targets`). Structured
        ``target_spec`` effects are resolved first: a spec that reaches a
        ``choose`` step surfaces as a structured choice; a fully-resolved spec
        is fanned out and applied. Legacy ``{choose_*}`` / literal targets
        commit unchanged.
        """
        from transversal.services.effects_commit import commit_effects
        from transversal.services.effects_engine import resolve_effect_spec_choices

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        domain_effects = [_effect_input_to_domain(e) for e in effects]

        structured = []
        to_commit = []
        for eff in domain_effects:
            if eff.target_spec is not None:
                applied, pending = resolve_effect_spec_choices(eff, "target", {}, entity, repo)
                to_commit.extend(applied)
                structured.extend(pending)
            else:
                to_commit.append(eff)

        result = commit_effects(entity, to_commit, repo)
        return _effects_result_to_gql(result, structured)

    @strawberry.mutation
    def resolve_effect_targets(self, info: strawberry.Info, entity_id: strawberry.ID,
                               resolutions: list[EffectTargetResolutionInput],
                               origin: Optional[str] = None) -> EffectApplicationResult:
        """Re-apply previously-pending effects with their resolved targets.

        Supports both legacy single-target resolutions (``target`` + ``field``)
        and resumable mid-path ``choose`` resolutions (``answers``): the latter
        re-resolves the spec/ref and either applies the final target(s) or
        surfaces the next ``choose`` step.
        """
        from transversal.services.effects_commit import commit_effects
        from transversal.services.effects_engine import resolve_effect_spec_choices

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        resolved = []
        structured = []

        for r in resolutions:
            continuation = [_effect_input_to_domain(c) for c in (r.continuation or [])]
            eff = _effect_input_to_domain(r.effect)
            field = r.field or "target"
            if r.answers:
                answers = {a.step_index: list(a.ids) for a in r.answers}
                local_scope: dict = {}
                applied, pending = resolve_effect_spec_choices(
                    eff, field, answers, entity, repo,
                    source_kind=r.source_kind or "", source_id=r.source_id or "",
                    source_sfx_id=r.source_sfx_id or "",
                    bindings=local_scope,
                )
                resolved.extend(applied)
                if pending:
                    # More choose steps remain — carry the continuation forward.
                    pending[-1].continuation = continuation
                    structured.extend(pending)
                else:
                    # Fully resolved — apply the deferred continuation now.
                    _resolve_continuation_effects(continuation, entity, repo, resolved, structured)
                # Write any step-output bindings into the armed activation.
                if local_scope and r.source_sfx_id:
                    from transversal.services.roll_deferral import bind_activation
                    for name, binding in local_scope.items():
                        bind_activation(
                            str(entity_id), r.source_sfx_id, name, binding.value,
                            binding.element or "", values=binding.values, cardinality=binding.cardinality,
                        )
                continue
            if field.startswith("refs."):
                name = field[len("refs."):]
                refs = dict(eff.refs or {})
                ref = refs.get(name)
                if ref is not None:
                    refs[name] = ref.model_copy(update={"value": r.target, "spec": None})
                    eff = eff.model_copy(update={"refs": refs})
            elif field == "target":
                eff = eff.model_copy(update={"target": r.target, "target_spec": None})
            elif field == "entity":
                eff = eff.model_copy(update={"entity": r.target, "entity_spec": None})
            elif "." in field:
                top, _, sub = field.partition(".")
                ctx = dict(eff.context or {})
                ctx[sub] = r.target
                eff = eff.model_copy(update={top: ctx})
            else:
                eff = eff.model_copy(update={field: r.target})
            resolved.append(eff)
            # Legacy single-target resolution: no further choose — apply the
            # deferred continuation immediately.
            _resolve_continuation_effects(continuation, entity, repo, resolved, structured)

        result = commit_effects(entity, resolved, repo)
        if structured:
            from transversal.services.roll_orchestrator import _emit_pending_choices
            _emit_pending_choices(str(entity_id), entity.current_universe or "", [], structured,
                                  origin=origin or "roll")
        return _effects_result_to_gql(result, structured)

    @strawberry.mutation
    def apply_roll_table_entry(self, info: strawberry.Info, entity_id: strawberry.ID,
                               table_id: strawberry.ID, index: int) -> EffectApplicationResult:
        """Pick a roll-table entry as a menu choice: pay its cost effects, then
        gain its effects. Returns applied summaries plus any pending target choices."""
        from transversal.services.roll_table_menu import pick_roll_table_entry

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        result, structured, _label, _cost = pick_roll_table_entry(
            repo, entity, str(table_id), index
        )
        return _effects_result_to_gql(result, structured)

    @strawberry.mutation
    def resolve_sfx_loop(self, info: strawberry.Info, entity_id: strawberry.ID,
                         sfx_id: strawberry.ID, event_type: str,
                         universe: str = "",
                         context: Optional[strawberry.scalars.JSON] = None,
                         origin: Optional[str] = None) -> EffectApplicationResult:
        """Run **one more round** of a rule that re-entered the change it handled.

        The loop guard offers each round rather than recursing (see
        ``PendingSfxLoop``), so this is how a table says "again" — and it is the
        only way an automated loop advances, one answered round at a time.

        The rule is re-run for *the same moment*: conditions and targets are
        resolved from live state, so a round that has become impossible (the
        challenge is already full, the trait is gone) simply does nothing, and a
        round that causes the change again surfaces the next prompt by itself —
        the recursion is the request, which is what makes "ask every iteration"
        work without persisting loop state.
        """
        from transversal.main import _get_engine
        from transversal.services.effects_engine import GameEvent
        from transversal.services.roll_orchestrator import (
            _emit_pending_choices,
            loop_choice_to_dict,
        )

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        engine = _get_engine()
        if engine is None:
            raise ValueError("Effects engine is not available")

        resolved_universe = universe or entity.current_universe or ""
        outcome = engine.process_event_outcome(
            GameEvent(type=event_type, entity_id=str(entity_id),
                      universe=resolved_universe, context=dict(context or {})),
            [str(sfx_id)], entity.razmerit, repo=repo,
        )
        _emit_pending_choices(str(entity_id), resolved_universe, outcome.pending,
                              outcome.structured, outcome.loops, origin=origin or "roll")
        return EffectApplicationResult(
            applied=[],
            pending_choices=[],
            structured=([_structured_choice_to_dict(c) for c in outcome.structured]
                        + [loop_choice_to_dict(l) for l in outcome.loops]),
        )

    @strawberry.mutation
    def resolve_parked_branch(self, info: strawberry.Info, event_id: strawberry.ID,
                              option_id: str = "") -> EffectApplicationResult:
        """Answer a **parked choice node** ([[B5]]): run the option, end the question.

        A boundary choice is *asked*, not applied: its row keeps the question (and
        its options) so the prompt survives a reload and a skipped choice cannot
        resolve itself. An empty ``option_id`` is the **default branch** — it runs
        nothing, which for the session-end challenge choice means the step-down
        stands — and ends the row either way.
        """
        from transversal.services.scheduled_events import resolve_parked_branch

        repo = _em(info).repo
        applied = resolve_parked_branch(repo, str(event_id), option_id)
        return EffectApplicationResult(applied=applied, pending_choices=[], structured=[])

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

    @strawberry.mutation
    def start_term(self, info: strawberry.Info, entity_id: strawberry.ID,
                   path_id: strawberry.ID, faction_id: Optional[strawberry.ID] = None,
                   projection_id: Optional[str] = None) -> GqlPendingTerm:
        """Begin (or restart) a term in a life path, **for one body**.

        `projectionId` names the body serving the term ([[B271]]); omitted, the
        acting body is resolved from `currentProjection`. Only that body's
        checkpoint is replaced — another body's term is left alone.

        **`factionId` is optional** ([[B41]]). The checkpoint is a cursor and needs no
        faction; the faction says *whose sect the term serves*, which only an
        **enrolling** row needs — and by then the path's own `{sect}` can supply it
        ([[B290]]). Pass one when the caller knows it (an offering faction, a
        membership); omit it for a path nobody offers and the row that enrols resolves
        it instead. Omitted is a real value here, unlike the leave-alone convention on
        the content mutations: a term's faction is set when the term begins.
        """
        from transversal.services.lifepath_executor import start_term as start_lp_term

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        pt = start_lp_term(entity, str(faction_id or ""), str(path_id), repo,
                           projection_id=projection_id)
        repo.update_entity(entity)

        return GqlPendingTerm(
            faction_id=pt.faction_id,
            path_id=pt.path_id,
            projection_id=pt.projection_id,
            current_step_id=pt.current_step_id,
            current_table_id=pt.current_table_id,
            continuation=pt.continuation,
        )

    @strawberry.mutation
    def resolve_step(self, info: strawberry.Info, entity_id: strawberry.ID,
                     projection_id: Optional[str] = None,
                     roll: Optional[int] = None,
                     tier: Optional[GqlOutcomeTier] = None,
                     index: Optional[int] = None,
                     resolutions: Optional[list[EffectTargetResolutionInput]] = None,
                     ) -> LifePathStepResult:
        """Resolve the current pending step in a life path term.

        ``index`` is a manual/click selection (1-based); ``roll`` is a rolled
        number for range/index/weight tables; ``tier`` is an outcome tier for
        check tables. Immediate effects apply now; deferred-timing effects are
        queued into the shared scheduler.

        A step that wraps **no table** is an effects-only step ([[B314]]): there
        is nothing to roll, and its effects are the whole payload.

        **A step may ask a question, and this is also how it is answered.** When an
        effect's targeting path reaches a ``choose``, the step returns
        ``structuredChoices`` with ``done: false`` and **stays put**. The caller
        answers by calling again with ``resolutions`` — only the effects named
        there are re-resolved, so nothing is applied twice, and the step advances
        once nothing is left pending.
        """
        from transversal.domain import OutcomeTier as DomainOutcomeTier
        from transversal.services.lifepath_executor import (
            StepResolution,
            resolve_step as resolve_lp_step,
        )

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        domain_tier = DomainOutcomeTier(tier.value) if tier is not None else None
        answers = [
            StepResolution(
                effect=_effect_input_to_domain(r.effect),
                field=r.field or "target",
                answers={a.step_index: list(a.ids) for a in (r.answers or [])},
            )
            for r in (resolutions or [])
        ]
        summary = resolve_lp_step(
            entity, repo, projection_id=projection_id,
            roll=roll, tier=domain_tier, index=index,
            engine=info.context["effects_engine"],
            resolutions=answers or None,
        )

        pt = summary.get("pending_term")
        pending_term = (
            GqlPendingTerm(
                faction_id=pt.faction_id,
                path_id=pt.path_id,
                projection_id=pt.projection_id,
                current_step_id=pt.current_step_id,
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
            structured_choices=[_structured_choice_to_dict(c)
                                for c in (summary.get("structured_choices") or [])],
        )

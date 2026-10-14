"""Engine — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

import transversal.services.effects_applier as _effects_applier

from transversal.domain import Effect
from transversal.domain import EffectTiming
from transversal.domain import SFX
from transversal.services.conditions import evaluate_conditions
from transversal.services.roll_deferral import DEFERRED_TIMINGS as _deferred_timings
from typing import Optional
from transversal.services.effects_engine.events import (
    EventOutcome,
    GameEvent,
    PendingSfxEffect,
    PendingSfxLoop,
)
from transversal.services.target_resolver import resolved_id as _resolved_id  # noqa: E402
from transversal.services.effects_engine.firing import (
    _apply_immediate_spec,
    _attach_continuation,
    _fire_context,
    _resolve_activation_source,
    _resolve_primary_targets,
    bind_declared,
)
from transversal.services.effects_registry.lookup import (
    get_action_meta_for,
    refs_before_fields,
)
from transversal.services.effects_engine.refs import (
    _structured_choice,
    _substitute_effect_context,
    resolve_refs,
)
from transversal.services.effects_engine.shared import (
    RULE_CHAIN,
    log,
)
from transversal.services.effect_refs import target_value


#: Context keys that name the *thing* an event is about, most specific first. A
#: change is "what happened, to which thing, on which entity" — so a rule that
#: re-enters the same change is looping, while the same rule acting on a
#: *different* thing (an agenda rule filling its parent) is a new application.
_CHANGE_SUBJECT_KEYS = ("trait_setting_id", "trait_setting", "entity_created",
                        "projection_id")


def _change_key(event: GameEvent) -> tuple[str, str, str]:
    """Identify the change an event carries, for the loop guard.

    The subject is whatever the event names as the thing it is about; events that
    name no single thing (a roll, a beat) fall back to the entity and type, which
    is the coarse key the old guard used — correct there, because a roll has no
    sub-part for a rule to act on and loop through.
    """
    ctx = event.context or {}
    for key in _CHANGE_SUBJECT_KEYS:
        value = ctx.get(key)
        if value:
            return (event.entity_id, event.type, str(value))
    return (event.entity_id, event.type, "")


def _resolve_listeners(sfx: SFX, repo, event, source, source_element) -> list[str]:
    """The entity ids an authored ``listener_spec`` path names, at arm time.

    ``select self`` is the activating entity, ``select source`` the SFX's
    activation source, so the path reads exactly as it does in a condition. An
    unresolvable path — errors, or a step needing a runtime choice nobody is here
    to answer — resolves to *nobody*, not to the activator: an empty listener set
    is a real state (nobody is bound to the curse yet), and quietly acting on the
    wrong entity is worse than doing nothing with a log line.
    """
    from transversal.services.target_resolver import TargetContext, resolve

    spec = getattr(sfx, "listener_spec", None)
    if repo is None or spec is None or not spec.steps:
        return []
    entity = repo.get_entity(event.entity_id)
    if entity is None:
        return []
    context = TargetContext(
        subject=entity, repo=repo, source=source, source_element=source_element)
    resolution = resolve(spec, context)
    if resolution.errors or resolution.pending_choices:
        log.warning(
            "[process_event] sfx=%s listener path unresolved (errors=%s, choices=%s)",
            sfx.id, resolution.errors, len(resolution.pending_choices),
        )
        return []
    out: list[str] = []
    for value in resolution.values:
        listener_id = getattr(value, "id", None)
        if listener_id is None and isinstance(value, str):
            listener_id = value
        if listener_id and listener_id not in out:
            out.append(listener_id)
    return out


def _added_die_of(context: dict | None, source_id: str | None) -> dict | None:
    """The just-added die that came from ``source_id``, if any.

    The pool save carries *everything* it added; a rule that lives on one trait
    instance cares about its own. Matched on ``ts_id`` (the instance a trait die
    came from) and ``source_id`` (an sfx-made die's origin).
    """
    if not source_id:
        return None
    for die in (context or {}).get("added_dice") or []:
        if die.get("ts_id") == source_id or die.get("source_id") == source_id:
            return die
    return None


def _source_was_added(sfx: SFX, event: GameEvent, source_id: str | None) -> bool:
    """Whether the rule's own source is among what this save added.

    Asked only of ``on_pool_add``; every other trigger is satisfied by the event
    itself. False when the source is unresolved — a rule with no home cannot have
    been added — which is the honest answer rather than firing on everything.
    """
    if sfx.trigger != "on_pool_add":
        return True
    return _added_die_of(event.context, source_id) is not None


#: Triggers whose event carries the assembled pool, so "was the source rolled?" is
#: answerable. The outcome triggers carry it too — `conditions.py` maps each trigger
#: to the context keys it may read, and every one of these has ``rolls``.
_POOL_TRIGGERS = frozenset({
    "on_roll", "on_result", "on_set",
    "on_complication", "on_botch", "on_success", "on_failure",
})


def _source_in_pool(event: GameEvent, source_id: str | None) -> bool:
    """Whether a die from ``source_id`` is in the pool this event carries."""
    if not source_id:
        return False
    return any((die or {}).get("ts_id") == source_id
               for die in (event.context or {}).get("rolls") or [])


def _source_matches(sfx: SFX, event: GameEvent, source_id: str | None,
                    source_element: str = "") -> bool:
    """Whether this rule's own source is in play for this event ([[B286]]).

    Two questions, each replacing a case that used to fire on everything:

    * **``on_pool_add``** is about the source *arriving* — the just-added dice must
      include it (``_source_was_added``).
    * **a roll-family trigger on a trait *instance*** is about that instance being
      rolled, so a die carrying its ``ts_id`` must be in the pool. The author's
      intuition, 2026-10-13: *"if the source is traitsetting … I'd expect the source
      to gate the trigger."*

    **A disabled source needs no separate check, and must not have one.** A disabled
    trait instance *contributes no dice* (``TraitSetting.enabled``: "false = disabled;
    contributes no dice until re-enabled"), so it cannot be in the pool and the roll
    gate above already refuses it — the author's second expectation, satisfied by the
    first. A blanket "disabled source never fires" check would instead break the rules
    whose subject *is* a disabled trait: the portent escalator is sourced on the
    disabled slot it exists to enable (``on_challenge_completed``), and the full suite
    caught exactly that when this was first written.

    A source that is not a trait instance (entity, table, location, …) is not gated
    here: for those, "was it rolled?" has no meaning, and the entity case is already
    true by construction (the roller *is* the source).
    """
    if sfx.trigger == "on_pool_add":
        return _source_was_added(sfx, event, source_id)
    if sfx.trigger in _POOL_TRIGGERS and source_element == "traitsetting":
        # Decide it only where it can be decided: an event carrying **no** pool is a
        # synthetic or non-roller activation (a direct engine call, an agenda firing),
        # and refusing there would silence rules over information nobody supplied.
        # A real roll always carries the pool — every roll-family trigger may read
        # ``rolls`` (`conditions.py`) — so the gate is exact where it matters.
        if not (event.context or {}).get("rolls"):
            return True
        return _source_in_pool(event, source_id)
    return True


def _activation_bindings(sfx: SFX, event: GameEvent, source_id: str | None,
                         source=None) -> dict:
    """The activation's own names, bound as typed seeds for targeting paths.

    The source token and the trigger's declared variables were authorable but
    never *bound*, so a path could not start from them (``select variable
    {contest_entity_opponent}`` errored while ``{contest_entity_opponent}``
    worked in a flat field). This fills the same names the editor offers —
    ``target_catalog.scope_seed_names`` — with the values *this* event carries.

    A declared name the event does not carry is left unbound rather than bound
    empty: at a pool save with no contest there is no opponent, and a path that
    starts from one should resolve to nobody, not to a blank id.

    ``source`` is the *resolved* activation source. A source **scalar**
    (``{order}``) has no event-carried value — it is a fact about the instance
    the rule lives on, so it is read from there.
    """
    from transversal.services.target_catalog import (
        SOURCE_SCALAR_SEEDS, scope_seed_names, source_kind as sk,
    )
    from transversal.services.target_resolver import Binding

    names = scope_seed_names(sfx.trigger or "", sfx.source_kind)
    if not names:
        return {}
    values: dict = dict(event.context or {})
    declared = sk(sfx.source_kind) if sfx.source_kind else None
    if declared is not None and declared.variable and source_id:
        values[declared.variable] = source_id

    # Source scalars come from the instance, not the event.
    scalars: dict[str, str] = (
        SOURCE_SCALAR_SEEDS.get(declared.element, {}) if declared is not None else {}
    )
    for name, field_name in scalars.items():
        raw = getattr(source, field_name, None) if source is not None else None
        if raw is not None and raw != "":
            values[name] = raw

    out: dict = {}
    for name, element in names.items():
        value = values.get(name)
        if value is None or value == "":
            continue
        out[name] = Binding(value=str(value), element=element, cardinality="one")
    return out


class EffectsEngine:
    """Manages SFX triggers, execution, and scheduling.

    Effects are dispatched through the global effect_registry —
    any module can register handlers for (type, action) pairs.
    The engine does not directly mutate state.
    """

    def __init__(self):
        self._sfx_registry: dict[str, SFX] = {}

    # ── Registry ─────────────────────────────────────

    def register(self, sfx: SFX) -> None:
        """Register an SFX definition."""
        self._sfx_registry[sfx.id] = sfx

    def register_many(self, sfxs: list[SFX]) -> None:
        for s in sfxs:
            self.register(s)

    def get(self, sfx_id: str) -> Optional[SFX]:
        return self._sfx_registry.get(sfx_id)

    def get_all(self) -> list[SFX]:
        return list(self._sfx_registry.values())

    # ── Trigger ──────────────────────────────────────

    def process_event(
        self,
        event: GameEvent,
        available_sfx_ids: list[str],
        razmerit_balance: int,
    ) -> list[Effect]:
        """Process a game event, returning immediately-applied effects.

        Backward-compatible wrapper around :meth:`process_event_outcome`.
        """
        return self.process_event_outcome(event, available_sfx_ids, razmerit_balance).applied

    def process_event_outcome(
        self,
        event: GameEvent,
        available_sfx_ids: list[str],
        razmerit_balance: int,
        repo=None,
        arm_deferred: bool = True,
    ) -> EventOutcome:
        """Process a game event, returning applied + pending effects.

        Immediate effects with a ``{choose_*}`` target are not applied — they
        are returned in ``outcome.pending`` so the caller can surface a choice.
        Deferred effects are queued internally as before.

        When ``repo`` is provided, SFX with ``conditions`` are gated on the
        entity's current state (evaluate_conditions).

        ``arm_deferred=False`` skips queueing this SFX's deferred (roll/outcome
        -timing) effects; the caller owns arming. The session-start fan-out uses
        it so the per-entity walk applies only non-deferred effects while a
        single global pass arms the passives once (``arm_passive`` appends, so
        arming inside the walk would stack N copies of the same rule).
        """
        outcome = EventOutcome()
        change = _change_key(event)
        # One sink per outcome, shared by reference through every ``effect_context``
        # spread below (and through ``bind_source``, which copies keys). Each
        # committed effect appends what it did; the outcome carries the list
        # ([[B236]]). Seeded here rather than per dispatch so a *refusal* in the
        # middle of a rule is as visible as a success.
        notes: list[dict] = []
        if isinstance(event.context, dict):
            event.context[_effects_applier.EFFECT_NOTES_CONTEXT_KEY] = notes

        for sfx_id in available_sfx_ids:
            sfx = self._sfx_registry.get(sfx_id)
            if sfx is None:
                log.info("[process_event] sfx=%s NOT in registry (skip)", sfx_id)
                continue

            # Loop guard. This rule is already handling *this change* further up
            # the chain, so applying it again is the rule re-entering itself —
            # its own effect caused this event. Offer the round to the table
            # instead of recursing; see `PendingSfxLoop`.
            chain = RULE_CHAIN.get()
            if (sfx.id, change) in chain:
                rounds = sum(1 for frame in chain if frame == (sfx.id, change))
                outcome.loops.append(PendingSfxLoop(
                    sfx_id=sfx.id, sfx_name=sfx.name,
                    sfx_description=sfx.description or "",
                    entity_id=event.entity_id, universe=event.universe,
                    event_type=event.type, context=dict(event.context or {}),
                    iteration=rounds + 1,
                ))
                log.info(
                    "[process_event] sfx=%s would re-enter %s (round %s) — asking the table",
                    sfx.id, change, rounds + 1,
                )
                continue

            # Trigger match
            if not self._trigger_matches(sfx, event):
                continue

            log.info(
                "[process_event] sfx=%s trigger=%s matches event=%s conditions=%s",
                sfx.id, sfx.trigger, event.type,
                [(c.type.value, c.target) for c in (sfx.conditions or [])],
            )

            # Resolve the activation source once: explicit source_id wins (manual
            # activation); else ownership resolution (automatic triggers).
            source, source_element, source_id = _resolve_activation_source(sfx, event, repo)

            # A trigger *about* its source ("this trait was added") can only be
            # decided now that the source is resolved — and it is decided before
            # the conditions, which is the point of having the trigger at all.
            if not _source_matches(sfx, event, source_id, source_element):
                log.info("[process_event] sfx=%s trigger=%s source=%s does not take part in this event",
                         sfx.id, sfx.trigger, source_id)
                continue

            # Per-activation variable scope. Sealed *before* the gate because a
            # condition's targeting path can publish named outputs into it ("the
            # d4 traits in this roll"), which the SFX's effects may then target.
            # Effect outputs extend the same scope, so later effects see them.
            # It starts from the activation's *own* names — the source token and
            # the trigger's declared variables — so a path can begin at "the
            # thing this rule is attached to" or "the opponent in this moment"
            # rather than only joining to a name an earlier step produced.
            bindings: dict = _activation_bindings(sfx, event, source_id, source)

            # ...and then the rule's *own* declared variables, in declaration
            # order, for exactly the same reason and in the same scope: the author
            # named a value the rule is about, and both the gate below and every
            # effect must read it by that name.
            bind_declared(sfx, bindings, event, repo,
                          source_id=source_id, source_element=source_element)

            # Condition gate (only when a repo is available to evaluate state)
            if sfx.conditions and repo is not None:
                entity = repo.get_entity(event.entity_id)
                if entity is None or not evaluate_conditions(
                    entity, sfx.conditions, repo, event.context,
                    source=source, source_element=source_element,
                    out_bindings=bindings,
                ):
                    continue

            # Cost check: sum razmerit costs from spend effects
            total_razmerit_cost = 0
            for e in sfx.effects:
                if e.type == "transfer_razmerit" and e.action == "spend":
                    total_razmerit_cost += int(e.result or "0")
            if total_razmerit_cost > razmerit_balance:
                continue

            # Execute each effect with its own timing
            sfx_applied = False
            # The notes list is per *outcome*; this rule's own records are the ones
            # it appends, so the slice since this iteration began is what this rule
            # did ([[B236]]). The splash reports exactly that ([[B229]]).
            notes_before = len(notes)
            # Bind the declared source variable: if the SFX states a source kind
            # and the activation resolved a source, map it to the typed
            # ``{variable}`` so effect fields resolve to the concrete id.
            effect_context = event.context
            if sfx.source_kind and source_id:
                from transversal.services.target_catalog import bind_source
                effect_context = bind_source(sfx.source_kind, source_id, event.context)
            # Thread the resolved activation source into the effect context so
            # per-effect ``source_rating`` / ``target_path`` conditions can gate
            # on the trait (etc.) that owns/triggered this SFX.
            if source is not None:
                effect_context = {
                    **(effect_context or {}),
                    _effects_applier.SOURCE_CONTEXT_KEY: source,
                    _effects_applier.SOURCE_ELEMENT_CONTEXT_KEY: source_element,
                }
            # Carry the activation's variable scope to the applier, so an effect's
            # ``entity_spec`` can resolve ``select variable`` against what the SFX's
            # conditions (and any earlier effect) bound.
            #
            # ``_activation`` marks which activation these effects belong to. It
            # travels with every dispatch (see ``EffectRegistry.apply``) so bookings
            # are attributed to the rule, and a *manual* activation's untimed undos
            # are booked as holds — the flight window the sheet lets a player undo.
            effect_context = {
                **(effect_context or {}),
                _effects_applier.BINDINGS_CONTEXT_KEY: bindings,
                _effects_applier.ACTIVATION_CONTEXT_KEY: {
                    "sfx_id": sfx.id,
                    "cancelable": event.type in ("manual", "on_activate"),
                    "source_id": source_id or "",
                    # The change this rule is acting on, so the dispatch can put
                    # the rule on the loop chain for exactly as long as its own
                    # effects run (see `shared.RULE_CHAIN`).
                    "change": change,
                },
            }
            roll_effects = [e for e in sfx.effects if e.timing in _deferred_timings]
            log.info(
                "[process_event] sfx=%s trigger=%s deferred_effects=%s arm_deferred=%s",
                sfx.id, sfx.trigger, [e.timing.value for e in roll_effects], arm_deferred,
            )
            if roll_effects and arm_deferred:
                # Arm the SFX's roll-timing effects as a unit for its duration,
                # routed by the SFX's declared (or trigger-derived) listener scope.
                from transversal.services.roll_deferral import arm_passive, arm_sfx
                scope = sfx.effective_arming_scope
                if scope == "global":
                    arm_passive(
                        roll_effects,
                        source_sfx_id=sfx.id,
                        source_kind=sfx.source_kind,
                        source_id=source_id,
                        duration=sfx.duration,
                        bindings=bindings,
                    )
                else:
                    if scope == "listener_spec":
                        # Arm the rule on each entity the author's path names —
                        # the curse case: the bound partner's rolls feed it, not
                        # the caster's. Resolved *once*, here (open decision D3):
                        # the set is a snapshot for the window's duration, because
                        # re-resolving at fire time would re-target a rule
                        # mid-window as relationships move. The window is
                        # rolls/scene-sized, so "who was listening when this
                        # armed" is the honest reading.
                        listeners = _resolve_listeners(
                            sfx, repo, event, source, source_element)
                        if not listeners:
                            log.warning(
                                "[process_event] sfx=%s scope=listener_spec resolved no listeners"
                                " — nothing armed", sfx.id,
                            )
                        for listener_id in listeners:
                            arm_sfx(
                                listener_id, roll_effects,
                                source_sfx_id=sfx.id,
                                source_kind=sfx.source_kind,
                                source_id=source_id,
                                duration=sfx.duration,
                                bindings=bindings,
                                scope="listener_spec",
                            )
                    else:
                        arm_sfx(
                            event.entity_id, roll_effects,
                            source_sfx_id=sfx.id,
                            source_kind=sfx.source_kind,
                            source_id=source_id,
                            duration=sfx.duration,
                            bindings=bindings,
                            scope="self",
                        )
                sfx_applied = True

            for idx, effect in enumerate(sfx.effects):
                if effect.timing in _deferred_timings:
                    continue  # armed above (raw; substituted at fire time)

                effect = _substitute_effect_context(effect, effect_context, bindings)
                # Resolve any authored ``entity_spec`` against this activation's
                # variable scope before dispatch, so every handler — the razmerit
                # service included — receives a concrete entity id rather than a
                # spec it would silently ignore. A subject path that stops at a
                # ``choose`` reports its question here instead of resolving to
                # nobody, and it is put to the table below on the same channel
                # ``target_spec`` and ``refs`` already use.
                subject_choices: list = []
                effect = _effects_applier.resolve_effect_entity(
                    effect, event.entity_id, repo, effect_context,
                    pending_out=subject_choices,
                )
                # And its *die*, when the author named one by a path instead of a
                # literal (`result_spec`): "the capacity slot my position fills".
                effect = _effects_applier.resolve_effect_result(
                    effect, event.entity_id, repo, effect_context,
                )
                # And its owner path, when the action has one — the edge a tie is
                # anchored to, or the instance a facet hangs under.
                effect = _effects_applier.resolve_effect_owner(
                    effect, event.entity_id, repo, effect_context,
                )
                if effect.timing == EffectTiming.IMMEDIATE:
                    blocked = False
                    # The panel reads this action's references and fields in a
                    # declared order, and the questions must arrive in it: Move
                    # Trait shows "Trait to Move" before "Give To", so the trait
                    # has to be asked first even though the subject path is
                    # resolved before the references below ([[B260]]). Ask the
                    # references' questions first; the answer's resume resolves
                    # the subject as well (`resolve_effect_spec_choices` walks
                    # both), so nothing is lost by not asking it here.
                    _refs_first = refs_before_fields(
                        get_action_meta_for(effect.type, effect.action))
                    # Gate on the *authored* refs, not the effective ones: declaring
                    # a ref for a positional field must not re-route stored content
                    # from the subject/target path into this branch. The fold still
                    # happens inside `resolve_refs`, so a folded ref resolves and
                    # writes back exactly as before ([[B261]]).
                    if (subject_choices and effect.refs and _refs_first):
                        fire_ctx = _fire_context(event, sfx, repo, bindings=bindings,
                                                 source_id=source_id, source_element=source_element)
                        ref_choices: list = []
                        refs_blocked = False
                        if effect.target_spec is not None and effect.target_spec.steps:
                            _, refs_blocked = _resolve_primary_targets(
                                effect, fire_ctx, ref_choices, sfx,
                                source_id=source_id or "",
                            )
                        if not refs_blocked:
                            resolve_refs(effect, fire_ctx, ref_choices,
                                         source_sfx_id=sfx.id)
                        if ref_choices:
                            outcome.structured.extend(ref_choices)
                            blocked = True
                    if subject_choices and not blocked:
                        # *Who* this effect lands on is the table's decision — the
                        # effect stays unapplied until the answer arrives, exactly
                        # as a `choose` in a target path or a reference behaves.
                        for pc in subject_choices:
                            outcome.structured.append(_structured_choice(
                                pc, effect, "entity", sfx,
                                source_kind=sfx.source_kind or "",
                                source_id=source_id or "",
                                source_sfx_id=sfx.id, repo=repo,
                            ))
                        blocked = True
                    if blocked:
                        # A question is open for this effect — nothing may be
                        # applied. It must short-circuit the *whole* chain below,
                        # not just the references branch: falling through reaches
                        # the plain `else: apply`, which is how a blocked effect
                        # got applied anyway.
                        pass
                    elif effect.refs:
                        before = len(outcome.structured)
                        fire_ctx = _fire_context(event, sfx, repo, bindings=bindings,
                                                 source_id=source_id, source_element=source_element)
                        # An effect may carry both a primary target path and named
                        # references — "attune *these people* to *their projection*".
                        # Walk the target path first: its named outputs join the
                        # activation scope in place, so a reference path can start
                        # (`select variable`) from where the target path landed.
                        targets: list[Optional[str]] = [None]
                        if effect.target_spec is not None and effect.target_spec.steps:
                            targets, target_blocked = _resolve_primary_targets(
                                effect, fire_ctx, outcome.structured, sfx,
                                source_id=source_id or "",
                            )
                            if target_blocked:
                                blocked = True
                        # Nothing found on the target path → nothing to apply for this
                        # activation (fail closed; creating the missing thing is a
                        # separate, deliberate feature).
                        resolved_list = (
                            [] if blocked
                            else resolve_refs(effect, fire_ctx, outcome.structured,
                                              source_sfx_id=sfx.id)
                        )
                        if len(outcome.structured) > before:
                            blocked = True
                        else:
                            for resolved in resolved_list:
                                for target in targets:
                                    concrete = resolved if target is None else resolved.model_copy(
                                        update={"target": target, "target_spec": None})
                                    _effects_applier.effect_registry.apply(
                                        concrete, event.entity_id, event.universe, effect_context)
                                    outcome.applied.append(concrete)
                                    sfx_applied = True
                                    log.info("[process_event] applied sfx=%s effect=%s/%s target=%s via refs", sfx.id, concrete.type, concrete.action, concrete.target)
                    elif effect.target_spec is not None:
                        before = len(outcome.structured)
                        applied = _apply_immediate_spec(
                            effect, event, sfx, effect_context, repo, outcome.structured, bindings=bindings,
                            source_id=source_id, source_element=source_element,
                        )
                        outcome.applied.extend(applied)
                        if applied:
                            sfx_applied = True
                        if len(outcome.structured) > before:
                            blocked = True
                    elif (context_choice := _effects_applier.context_choice(effect)):
                        # A context policy asked the user to choose (`{choose_projection}`):
                        # defer this effect and everything after it.
                        kind, field = context_choice
                        outcome.pending.append(PendingSfxEffect(
                            effect=effect,
                            sfx_name=sfx.name,
                            sfx_description=sfx.description,
                            kind=kind,
                            field_name=field,
                        ))
                        blocked = True
                    else:
                        _effects_applier.effect_registry.apply(effect, event.entity_id, event.universe, effect_context)
                        outcome.applied.append(effect)
                        sfx_applied = True
                        log.info("[process_event] applied sfx=%s effect=%s/%s target=%s", sfx.id, effect.type, effect.action, target_value(effect))

                    if blocked:
                        # Sequential execution: this effect needs a choice, so the
                        # remaining immediate effects must wait for resolution.
                        continuation = [e for e in sfx.effects[idx + 1:] if e.timing == EffectTiming.IMMEDIATE]
                        _attach_continuation(outcome, continuation)
                        break
                else:
                    # Persist deferred effects in the central timer store.
                    if repo is not None:
                        from transversal.services.scheduled_events import schedule_deferred
                        schedule_deferred(repo, "entity", event.entity_id, effect, source_sfx_id=sfx.id)

            if sfx_applied:
                # Resolved through the package module, not imported by value: the
                # broadcaster is module-level state that callers (and tests) swap
                # by rebinding ``effects_engine._emit_sfx_triggered``.
                from transversal.services import effects_engine as _pkg
                _pkg._emit_sfx_triggered(event.entity_id, sfx)
                # …and the report: an activation that has run its course says what
                # its effects did. `summary` is the longer dwell — a change waits
                # ~2 s, a rule's whole outcome ~5 s ([[UI-UX Design]]).
                _pkg._emit_effects_changed(
                    entity_id=event.entity_id,
                    title=sfx.name,
                    kind="summary",
                    lines=_pkg._note_lines(notes[notes_before:]),
                )

        outcome.notes = notes
        return outcome

    def _trigger_matches(self, sfx: SFX, event: GameEvent) -> bool:
        """Check if an SFX's trigger matches the event.

        Supports:
          - Direct match: trigger == event.type
          - on_complication: fires when roll_result has hitches
          - on_botch: fires when all dice show 1
          - on_location_change: fires for event type "location_changed"
          - on_trait_change: fires for event type "trait_updated"
          - on_contest_loss / on_contest_win: fires from contest context
          - on_success / on_failure: fires from roll context
        """
        trigger = sfx.trigger

        # Direct match
        if trigger == event.type:
            return True

        # on_activate legacy alias for "manual" trigger
        if trigger == "on_activate" and event.type == "manual":
            return True

        # on_complication also fires for hitches within other events
        if trigger == "on_complication" and event.type in ("on_roll", "on_result"):
            if event.roll_result:
                if hasattr(event.roll_result, 'hitches') and event.roll_result.hitches:
                    return True

        # on_botch
        if trigger == "on_botch" and event.roll_result and getattr(event.roll_result, 'botch', False):
            return True

        # on_location_change
        if trigger == "on_location_change" and event.type == "location_changed":
            return True

        # on_pool_change / on_pool_add — both are the pool-save moment. The *add*
        # trigger narrows further, and only the resolved source can say whether
        # "this trait" is what arrived (see `_source_was_added`, checked by the
        # caller once the source is resolved).
        if trigger in ("on_pool_change", "on_pool_add") and event.type == "pool_changed":
            return True

        # on_trait_change
        if trigger == "on_trait_change" and event.type == "trait_updated":
            return True

        # on_trait_learn
        if trigger == "on_trait_learn" and event.type == "trait_learned":
            return True

        # on_trait_offered
        if trigger == "on_trait_offered" and event.type == "trait_offered":
            return True

        # on_relationship_create
        if trigger == "on_relationship_create" and event.type == "relationship_created":
            return True

        # on_character_create
        if trigger == "on_character_create" and event.type == "character_created":
            return True

        # on_projection_create
        if trigger == "on_projection_create" and event.type == "projection_created":
            return True

        # on_challenge_completed
        if trigger == "on_challenge_completed" and event.type == "challenge_completed":
            return True

        # on_contest_loss / on_contest_win (from context)
        if trigger in ("on_contest_loss", "on_contest_win"):
            contest_winner = event.context.get("contest_winner")
            if trigger == "on_contest_loss":
                # Entity lost: opponent won (ties favor the initiator)
                return contest_winner == "opponent"
            elif trigger == "on_contest_win":
                return contest_winner == "player"

        # on_success / on_failure (from roll context)
        if trigger in ("on_success", "on_failure") and event.roll_result:
            tier = getattr(event.roll_result, 'tier', None)
            if tier:
                from transversal.domain import OutcomeTier
                if trigger == "on_success" and tier != OutcomeTier.FAIL:
                    return True
                if trigger == "on_failure" and tier == OutcomeTier.FAIL:
                    return True

        return False

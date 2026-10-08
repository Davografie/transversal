"""Roll-scoped effect deferral — arm an SFX to fire at the next roll event.

Roll events (``on_roll``/``on_set``/``on_result``) are ephemeral and per-roll,
so they can't live in the persisted scheduled-events store (which advances on
state-change / global events). This module keeps *armed SFXs* in memory, keyed
by entity, and fires their roll-timing effects when the matching roll event
happens. It is the "rolls" side of the temporal spine: an SFX is armed at
trigger time for its ``SFX.duration`` (default one roll), and its effects fire
on each matching roll event until that duration is exhausted.

``SFX.duration`` splits into two axes:

- **rolls** — a roll-event budget, decremented on each matching roll event.
  ``None`` (no ``rolls`` timer) = no roll limit.
- **boundary events** — ``beat``/``scene``/``session`` or a state-change event
  (``location_changed``/``trait_updated``) that drops the armed SFX from the
  tracker when that event fires (see :func:`expire_armed`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from transversal.domain import Effect, EffectTiming
from transversal.services.effect_refs import effective_refs

log = logging.getLogger("transversal.sfx")

# EffectTiming values that defer to a per-roll event rather than a time
# boundary or persisted state change.
ROLL_TIMINGS = frozenset({
    EffectTiming.ON_ROLL,
    EffectTiming.ON_SET,
    EffectTiming.ON_RESULT,
})

# Outcome-gated timings — deferred like roll timings, but fired when a contest
# or roll *resolves* (rather than at a roll phase). The event carries the
# outcome; ``fire_armed`` matches the timing value against the event type.
OUTCOME_TIMINGS = frozenset({
    EffectTiming.ON_CONTEST_WIN,
    EffectTiming.ON_CONTEST_LOSS,
    EffectTiming.ON_SUCCESS,
    EffectTiming.ON_FAILURE,
})

# Everything an SFX arms at trigger time and fires at a later event.
DEFERRED_TIMINGS = ROLL_TIMINGS | OUTCOME_TIMINGS


@dataclass
class ArmedSfx:
    effects: list[Effect] = field(default_factory=list)  # the SFX's roll-timing effects
    rolls: Optional[int] = None  # remaining roll-event budget; None = no roll limit
    expiry_events: list[str] = field(default_factory=list)  # boundary/state events that drop it
    source_sfx_id: str | None = None  # SFX id the client stamps on its dice
    source_kind: str | None = None  # the SFX's declared source_kind (for `select source`)
    source_id: str | None = None  # the concrete source id (activation origin)
    bindings: dict = field(default_factory=dict)  # per-activation typed output variables
    scope: str = "self"  # listener scope: self | global | listener_spec


_armed: dict[str, list[ArmedSfx]] = {}

# Passive rules (e.g. One Trick) arm once per session and apply to *every*
# entity's rolls — not keyed by entity, so late joiners are covered. They carry
# no ``source_sfx_id`` (that stamp is the player-choice signal); selection is
# declarative via ``die_filter``/spec.
_global_armed: list[ArmedSfx] = []


def _split_duration(duration) -> tuple[Optional[int], list[str]]:
    """Split an SFX duration into ``(rolls_budget, boundary_events)``."""
    rolls: Optional[int] = None
    expiry_events: list[str] = []
    if duration and getattr(duration, "timers", None):
        for timer in duration.timers:
            if timer.event == "rolls":
                rolls = max(1, timer.remaining)
            else:
                expiry_events.append(timer.event)
    return rolls, expiry_events


def _drop_existing(register: list[ArmedSfx], source_sfx_id: str | None) -> list[ArmedSfx]:
    """Return ``register`` without any entry armed by the same named SFX.

    Arming is a *state*, not a counter: a named SFX is armed or not. Re-arming
    it refreshes the entry (new budget/expiry) instead of appending a duplicate,
    because ``fire_armed`` walks every entry and would apply the effect once per
    copy.

    This is load-bearing for the global register: a per-entity fan-out (e.g.
    ``fire_global_state_sfx`` over ``on_beat``/``on_scene``/``on_session_end``)
    visits a global-scope SFX once per owning entity, and a global rule is a
    single rule listening to every entity — N visits must leave one entry, not N.

    Anonymous entries (``source_sfx_id is None``) are never deduped: with no name
    to key on, they are separate rules by construction.
    """
    if source_sfx_id is None:
        return register
    return [a for a in register if a.source_sfx_id != source_sfx_id]


def arm_sfx(
    entity_id: str,
    effects: list[Effect],
    *,
    source_sfx_id: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    duration=None,
    scope: str = "self",
    bindings: dict | None = None,
) -> None:
    """Arm an SFX's roll-timing ``effects`` so they fire at their roll events.

    ``duration`` is the SFX's effective lifetime (``SFX.duration``): its
    ``rolls`` timer is the roll-event budget (``None`` = no roll limit), and any
    other timer (``beat``/``scene``/``session``/state-change) is a boundary that
    drops the SFX. Effects are stored raw — roll-context ``{variables}``
    substitute at fire time, because the roll state does not exist at arm time.

    ``source_kind``/``source_id`` carry the SFX's activation source so a
    ``select source`` spec resolves at fire time. ``scope`` records the listener
    scope (``self``/``global``/``listener_spec``).

    ``bindings`` carries the activation's typed seeds (``_activation_bindings``:
    the source token and the trigger's declared variables). They are snapshotted
    with the rest of the activation — the same reason ``source_id`` is — so a
    roll-timed effect can still start a path from "the thing this rule is about"
    after the moment that armed it has passed.

    Idempotent per ``source_sfx_id`` for this entity (see ``_drop_existing``).
    """
    rolls, expiry_events = _split_duration(duration)
    log.info(
        "[roll_deferral.arm_sfx] entity=%s sfx=%s scope=%s effects=%s rolls=%s expiry=%s",
        entity_id, source_sfx_id, scope,
        [(e.timing.value, e.type, e.action, e.target, e.die_filter) for e in effects],
        rolls, expiry_events,
    )
    _armed[entity_id] = _drop_existing(_armed.get(entity_id, []), source_sfx_id)
    _armed[entity_id].append(
        ArmedSfx(
            effects=list(effects),
            rolls=rolls,
            expiry_events=expiry_events,
            source_sfx_id=source_sfx_id,
            source_kind=source_kind,
            source_id=source_id,
            bindings=dict(bindings or {}),
            scope=scope,
        )
    )


def arm_passive(
    effects: list[Effect],
    *,
    duration=None,
    source_sfx_id: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    bindings: dict | None = None,
) -> None:
    """Arm a rule's roll-timing effects in the *global* set (scope = ``global``).

    Global entries are not entity-keyed, so they apply to every entity's rolls
    (late joiners included). Passive rules (``on_session_start``) carry no
    ``source_sfx_id``; a manual SFX that explicitly declares ``global`` scope
    does, so ``source_sfx_id``/``source_kind``/``source_id`` are accepted and
    preserved for ``die_filter`` selection and ``select source``.

    Idempotent per ``source_sfx_id`` (see ``_drop_existing``) — a global rule is
    one rule no matter how many entities carry it or how often it activates.
    ``bindings`` carries the activation's typed seeds, as in :func:`arm_sfx`.
    """
    rolls, expiry_events = _split_duration(duration)
    log.info(
        "[roll_deferral.arm_passive] scope=global sfx=%s effects=%s rolls=%s expiry=%s",
        source_sfx_id,
        [(e.timing.value, e.type, e.action, e.target, e.die_filter) for e in effects],
        rolls, expiry_events,
    )
    _global_armed[:] = _drop_existing(_global_armed, source_sfx_id)
    _global_armed.append(
        ArmedSfx(
            effects=list(effects),
            rolls=rolls,
            expiry_events=expiry_events,
            source_sfx_id=source_sfx_id,
            source_kind=source_kind,
            source_id=source_id,
            bindings=dict(bindings or {}),
            scope="global",
        )
    )


def bind_activation(entity_id: str, source_sfx_id: str, name: str, value: str, element: str = "",
                    values: list[str] | None = None, cardinality: str = "one") -> None:
    """Write a typed output binding into the matching armed SFX's activation scope.

    Used when an immediate effect's ``choose`` resolves *after* arming: the
    resume path binds the resolved value(s) so later roll-timed effects can
    reference ``{name}`` at fire time and the targeting system can type it. For
    a ``many`` binding, ``values`` carries the full list and ``value`` its first
    id.
    """
    if not source_sfx_id or not name or not value:
        return
    from transversal.services.target_resolver import Binding
    ids = list(values) if values else ([value] if value else [])
    for armed in _armed.get(entity_id, []):
        if armed.source_sfx_id == source_sfx_id:
            armed.bindings[name] = Binding(
                value=value, values=ids, element=element or "", cardinality=cardinality,
            )
            return


def fire_armed(
    entity_id: str,
    event_type: str,
    universe: str,
    context: dict | None = None,
) -> list[Effect]:
    """Fire armed-SFX effects whose timing matches ``event_type``; consume a roll.

    Returns the applied effects. Each armed SFX survives ``rolls`` matching
    events (``None`` = indefinite); a one-roll SFX fires once and is dropped.
    Global (scope=``global``) entries fire for every entity but still honor their
    own ``rolls`` budget the same way.
    """
    local = _armed.get(entity_id, [])
    if not local and not _global_armed:
        return []
    log.info(
        "[roll_deferral.fire_armed] entity=%s event=%s local=%s global=%s",
        entity_id, event_type,
        [(a.source_sfx_id, [e.timing.value for e in a.effects], a.rolls) for a in local],
        [(a.source_sfx_id, [e.timing.value for e in a.effects], a.rolls) for a in _global_armed],
    )
    if not universe:
        from transversal.main import _get_repo

        entity = _get_repo().get_entity(entity_id)
        if entity is not None:
            universe = entity.current_universe or ""

    rolls = (context or {}).get("rolls", [])
    applied: list[Effect] = []
    structured: list = []

    # Entity-local armed SFX — consume their roll budget per matching event.
    kept: list[ArmedSfx] = []
    for armed in local:
        if any(e.timing.value == event_type for e in armed.effects):
            applied.extend(_apply_armed(armed, event_type, entity_id, universe, context, rolls, structured))
            # One roll event consumed (a matching event happened for this SFX).
            if armed.rolls is not None:
                armed.rolls -= 1
                if armed.rolls <= 0:
                    continue  # exhausted — drop
            kept.append(armed)
        else:
            kept.append(armed)
    _armed[entity_id] = kept

    # Passive (global) rules — also consume their roll budget. A global entry
    # with a ``rolls`` timer fires that many times then drops; ``rolls=None``
    # (e.g. a session-scoped passive) stays armed until a boundary drops it.
    kept_global: list[ArmedSfx] = []
    for armed in _global_armed:
        if any(e.timing.value == event_type for e in armed.effects):
            applied.extend(_apply_armed(armed, event_type, entity_id, universe, context, rolls, structured))
            if armed.rolls is not None:
                armed.rolls -= 1
                if armed.rolls <= 0:
                    continue  # exhausted — drop
            kept_global.append(armed)
        else:
            kept_global.append(armed)
    _global_armed[:] = kept_global

    if structured:
        from transversal.services.roll_orchestrator import _emit_pending_choices
        _emit_pending_choices(entity_id, universe, [], structured)

    return applied


def _apply_armed(
    armed: ArmedSfx,
    event_type: str,
    entity_id: str,
    universe: str,
    context: dict | None,
    rolls: list[dict],
    structured: list | None = None,
) -> list[Effect]:
    """Apply one armed entry's matching effects to ``rolls``; return them."""
    from transversal.services.effects_applier import BINDINGS_CONTEXT_KEY, effect_registry, resolve_effect_entity
    from transversal.services.effects_engine import _substitute_effect_context
    from transversal.main import _get_repo

    bindings: dict = dict(armed.bindings)
    source = source_element = None
    if armed.source_id:
        from transversal.main import _get_repo
        from transversal.services.target_resolver import resolve_source
        resolved = resolve_source(armed.source_kind or "", armed.source_id, _get_repo())
        if resolved:
            source, source_element = resolved
    effect_context = _source_context(context, source, source_element, armed.source_sfx_id, armed.source_id)
    applied: list[Effect] = []
    condition_repo = None
    condition_entity = None
    for effect in armed.effects:
        if effect.timing.value != event_type:
            continue
        if effect.conditions:
            # An armed effect's *own* gates run here, at the roll — the only moment
            # the dice exist. Arming happens at the trigger, where there may be no
            # roll at all, so a roll-state gate cannot live on the SFX.
            #
            # The condition's path may also publish named outputs ("the d4 traits
            # in this roll"), which the effect's own targeting path then reads by
            # name; they join this activation's scope like any other step output.
            if condition_repo is None:
                condition_repo = _get_repo()
                condition_entity = (
                    condition_repo.get_entity(entity_id) if condition_repo is not None else None
                )
            from transversal.services.conditions import evaluate_conditions
            if not evaluate_conditions(
                condition_entity, effect.conditions, condition_repo, context,
                source=source, source_element=source_element, out_bindings=bindings,
            ):
                continue
        if bool(effect.die_filter):
            # A die filter runs the effect once per matching die. Everything the
            # effect resolves — its subject, its target path, its references —
            # reads *that die* as the roll, so "for each unchosen die, take the
            # trait it came from" lands per die rather than once for the pool.
            dice = [d for d in rolls if _selects_die(armed.source_sfx_id, effect, d)]
            log.info(
                "[roll_deferral._apply_armed] sfx=%s effect=%s/%s candidates=%s matched=%s",
                armed.source_sfx_id, effect.type, effect.action,
                [(d.get('armed_sfx_ids'), d.get('role'), d.get('ts_id')) for d in rolls],
                [(d.get('armed_sfx_ids'), d.get('role'), d.get('ts_id')) for d in dice],
            )
            for die in dice:
                resolved = _substitute_die_context(effect, die, context or {})
                resolved = _substitute_effect_context(resolved, context or {}, bindings)
                resolved = resolve_armed_subject(resolved, entity_id, bindings, {"rolled_dice": [die]})
                if effective_refs(resolved):
                    applied.extend(_apply_refs_roll(
                        resolved, entity_id, universe, context, [die], armed.source_kind,
                        armed.source_id, structured, bindings, source_sfx_id=armed.source_sfx_id,
                    ))
                    continue
                if resolved.target_spec is not None:
                    applied.extend(_apply_spec_target(
                        resolved, entity_id, universe, context, [die], armed.source_kind,
                        armed.source_id, structured, bindings=bindings,
                        source_sfx_id=armed.source_sfx_id,
                    ))
                    continue
                effect_registry.apply(resolved, entity_id, universe, effect_context)
                applied.append(resolved)
            continue
        if effective_refs(effect):
            resolved_list = _apply_refs_roll(effect, entity_id, universe, context, rolls, armed.source_kind, armed.source_id, structured, bindings, source_sfx_id=armed.source_sfx_id)
            applied.extend(resolved_list)
            continue
        if effect.target_spec is not None:
            resolved_list = _apply_spec_target(effect, entity_id, universe, context, rolls, armed.source_kind, armed.source_id, structured, bindings=bindings, source_sfx_id=armed.source_sfx_id)
            applied.extend(resolved_list)
            continue
        resolved = _substitute_effect_context(effect, context or {}, bindings)
        resolved = resolve_armed_subject(resolved, entity_id, bindings, {"rolled_dice": rolls})
        effect_registry.apply(resolved, entity_id, universe, effect_context)
        applied.append(resolved)
    armed.bindings = bindings
    return applied


# The id an effect is applied with — one implementation, in `target_resolver`
# (`resolved_id`), shared with the immediate path. Re-exported here for callers
# that already import it from this module.
from transversal.services.target_resolver import resolved_id as _resolved_id  # noqa: E402


def _source_context(
    context: dict | None,
    source,
    source_element: str | None,
    source_sfx_id: str | None = None,
    source_id: str | None = None,
) -> dict:
    """Thread a resolved activation source into the effect context.

    Per-effect ``source_rating`` / ``target_path`` conditions read ``_source`` /
    ``_source_element`` back out in ``effects_applier._commit``.

    It also names the activation, because the armed path bypasses
    ``EffectsEngine.process_event_outcome`` — the one place that sets
    ``_activation``. Without it a revert an armed rule schedules books no
    ``source_sfx_id``: the row has no origin to show, so the trait detail cannot
    name it and it drops out of the Active rail. An armed/passive rule is never
    *cancelable* — cancelable marks a manual activation, the only kind whose
    untimed undos book holds.
    """
    from transversal.services.effects_applier import (
        ACTIVATION_CONTEXT_KEY,
        SOURCE_CONTEXT_KEY,
        SOURCE_ELEMENT_CONTEXT_KEY,
    )

    ctx = {**(context or {})}
    if source is not None:
        ctx[SOURCE_CONTEXT_KEY] = source
        ctx[SOURCE_ELEMENT_CONTEXT_KEY] = source_element
    if source_sfx_id:
        ctx[ACTIVATION_CONTEXT_KEY] = {
            "sfx_id": source_sfx_id,
            "cancelable": False,
            "source_id": source_id or "",
        }
    return ctx


def resolve_armed_subject(effect: Effect, entity_id: str, bindings: dict,
                          collections: dict) -> Effect:
    """Resolve an armed effect's ``entity_spec`` before it is dispatched.

    The armed path bypasses ``process_event_outcome``, so without this an
    authored subject is silently ignored and the effect lands on the acting
    entity — e.g. a hazard meant for the die's owner's location would land on the
    roller instead. ``collections`` seeds the path: a per-die effect passes
    ``{"rolled_dice": [die]}``, because the die being processed *is* the roll
    that path should read.
    """
    if effect.entity_spec is None or not effect.entity_spec.steps:
        return effect
    from transversal.main import _get_repo
    from transversal.services.effects_applier import BINDINGS_CONTEXT_KEY, resolve_effect_entity

    repo = _get_repo()
    if repo is None:
        return effect
    return resolve_effect_entity(effect, entity_id, repo,
                                 {BINDINGS_CONTEXT_KEY: bindings}, collections)


def _apply_refs_roll(
    effect: Effect,
    entity_id: str,
    universe: str,
    context: dict | None,
    rolls: list[dict],
    source_kind: str | None = None,
    source_id: str | None = None,
    structured: list | None = None,
    bindings: dict | None = None,
    source_sfx_id: str | None = None,
) -> list[Effect]:
    """Resolve an armed effect's named refs against the roll context and apply
    once per resolved value (fan-out). Returns the applied effects."""
    from transversal.main import _get_repo
    from transversal.services.effects_applier import effect_registry
    from transversal.services.effects_engine import _substitute_effect_context, resolve_refs
    from transversal.services.target_resolver import TargetContext, resolve_source

    repo = _get_repo()
    entity = repo.get_entity(entity_id)
    source, source_element = resolve_source(source_kind or "", source_id, repo) if source_id else (None, None)
    effect_context = _source_context(context, source, source_element, source_sfx_id, source_id)
    before = len(structured) if structured is not None else 0
    resolved_list = resolve_refs(
        resolve_armed_subject(_substitute_effect_context(effect, context or {}, bindings),
                              entity_id, bindings or {}, {"rolled_dice": rolls}),
        TargetContext(
            subject=entity, repo=repo, collections={"rolled_dice": rolls},
            source=source, source_element=source_element, bindings=bindings if bindings is not None else {},
        ),
        structured,
        source_sfx_id=source_sfx_id or "",
    )
    # Only apply when no choose step left the ref unresolved (mirrors the
    # immediate path's ``len(structured) == before`` gate).
    if structured is None or len(structured) == before:
        for resolved in resolved_list:
            effect_registry.apply(resolved, entity_id, universe, effect_context)
    return resolved_list


def _apply_spec_target(
    effect: Effect,
    entity_id: str,
    universe: str,
    context: dict | None,
    rolls: list[dict],
    source_kind: str | None = None,
    source_id: str | None = None,
    structured: list | None = None,
    answers: dict[int, list[str]] | None = None,
    bindings: dict | None = None,
    source_sfx_id: str | None = None,
) -> list[Effect]:
    """Resolve an effect's ``target_spec`` against the roll context and apply it
    once per resolved target (e.g. One Trick: rolled dice → traitsetting → step
    down each). A ``select source`` step seeds from the SFX's activation source
    when ``source_kind``/``source_id`` are provided."""
    from transversal.main import _get_repo
    from transversal.services.effects_applier import effect_registry
    from transversal.services.effects_engine import _structured_choice, _substitute_effect_context
    from transversal.services.target_resolver import TargetContext, resolve, resolve_source

    repo = _get_repo()
    entity = repo.get_entity(entity_id)
    source, source_element = resolve_source(source_kind or "", source_id, repo) if source_id else (None, None)
    effect_context = _source_context(context, source, source_element, source_sfx_id, source_id)
    # Substitute roll-context variables (e.g. ``{effect_die}``) before applying,
    # mirroring ``_apply_refs_roll``.
    effect = _substitute_effect_context(effect, context or {}, bindings)
    effect = resolve_armed_subject(effect, entity_id, bindings or {}, {"rolled_dice": rolls})
    resolution = resolve(
        effect.target_spec,
        TargetContext(
            subject=entity, repo=repo, collections={"rolled_dice": rolls},
            source=source, source_element=source_element, bindings=bindings if bindings is not None else {},
        ),
        answers=answers,
    )

    if resolution.pending_choices and structured is not None:
        for pc in resolution.pending_choices:
            structured.append(_structured_choice(
                pc, effect, "target",
                source_kind=source_kind or "", source_id=source_id or "",
                source_sfx_id=source_sfx_id or "",
                repo=repo,
            ))
        return []

    applied: list[Effect] = []
    for value in resolution.values:
        target_id = _resolved_id(value)
        if target_id is None:
            continue
        resolved = effect.model_copy(update={"target": target_id})
        effect_registry.apply(resolved, entity_id, universe, effect_context)
        applied.append(resolved)
    return applied


def expire_armed(entity_id: str, event_type: str) -> None:
    """Drop armed SFX whose boundary expiry matches ``event_type``."""
    if entity_id not in _armed:
        return
    _armed[entity_id] = [a for a in _armed[entity_id] if event_type not in a.expiry_events]


def _selects_die(source_sfx_id: str | None, effect: Effect, die: dict) -> bool:
    """True when ``die`` belongs to the effect's selected set.

    The SFX id (stamped client-side as ``armed_sfx_ids``) identifies the SFX's
    own dice; ``die_filter`` adds further equality predicates (e.g. ``role: None``).
    """
    if source_sfx_id is not None:
        if source_sfx_id not in (die.get("armed_sfx_ids") or []):
            return False
    return _die_matches(die, effect.die_filter)


def _die_matches(die: dict, die_filter: dict) -> bool:
    """True when ``die`` satisfies every equality predicate in ``die_filter``."""
    return all(die.get(key) == value for key, value in (die_filter or {}).items())


def _substitute_die_context(effect: Effect, die: dict, context: dict) -> Effect:
    """Substitute roll-context + ``{triggered_die_*}`` variables for one die."""
    from transversal.services.effects_engine import _substitute_effect_context

    merged = dict(context or {})
    merged.update({
        "triggered_die_tier": die.get("tier"),
        "triggered_die_effect_die": die.get("effect_die"),
        "triggered_die_result": die.get("result"),
        "triggered_die_die": die.get("die"),
        "triggered_die_ts_id": die.get("ts_id"),
        "triggered_die_source_kind": die.get("source_kind"),
        "triggered_die_role": die.get("role"),
    })
    return _substitute_effect_context(effect, merged)


def clear_armed(entity_id: str) -> None:
    """Drop all armed SFX for an entity (e.g. when its pool is cleared)."""
    _armed.pop(entity_id, None)


def drop_armed(entity_id: str, source_sfx_id: str) -> int:
    """Drop this entity's waiting entries for one SFX — and its global ones.

    Used when a manual activation is *ended*: the parts of it that were still
    waiting on a roll never fire. Returns how many entries were dropped.
    """
    global _global_armed
    if not source_sfx_id:
        return 0
    before = list(_armed.get(entity_id, []))
    _armed[entity_id] = [a for a in before if a.source_sfx_id != source_sfx_id]
    global_before = len(_global_armed)
    _global_armed = [a for a in _global_armed if a.source_sfx_id != source_sfx_id]
    return (len(before) - len(_armed[entity_id])) + (global_before - len(_global_armed))


def list_armed(entity_id: str) -> list[Effect]:
    """The armed roll-timing effects currently queued for an entity (tests/debug)."""
    out: list[Effect] = []
    for armed in _armed.get(entity_id, []):
        out.extend(armed.effects)
    return out


def list_armed_sfx_ids(entity_id: str) -> list[str]:
    """The SFX ids currently armed for an entity (for client re-stamp/display)."""
    return [a.source_sfx_id for a in _armed.get(entity_id, []) if a.source_sfx_id]


def list_global_armed_sfx_ids() -> list[str]:
    """The SFX ids armed in the *global* register (the passives), for display.

    Global entries are not entity-keyed — a passive armed at session start covers
    every entity, late joiners included — so they belong to no single entity's
    take-back window and :func:`list_armed_sfx_ids` deliberately omits them. The
    Active rail unions these in, because "this rule is on you" is true for
    everyone; the manual take-back chip does not, because a passive is not the
    player's bargain to cancel.
    """
    out: list[str] = []
    for armed in _global_armed:
        if armed.source_sfx_id and armed.source_sfx_id not in out:
            out.append(armed.source_sfx_id)
    return out


def armed_entry_for(entity_id: str, sfx_id: str) -> Optional[ArmedSfx]:
    """The armed entry for a rule as seen by an entity — its own, or a global passive.

    Display-only: the entry's ``source_id`` and ``bindings`` exist nowhere else.
    Bindings are the activation's live names (the author's outputs, the engine's
    declared seeds, condition outputs) and are deliberately **not** persisted on
    the timer rows, so a rule known only by a row has no entry here.
    """
    for entry in _armed.get(entity_id, []):
        if entry.source_sfx_id == sfx_id:
            return entry
    for entry in _global_armed:
        if entry.source_sfx_id == sfx_id:
            return entry
    return None


def expire_global(event_type: str) -> None:
    """Drop passive rules whose boundary expiry matches ``event_type``."""
    global _global_armed
    _global_armed = [a for a in _global_armed if event_type not in a.expiry_events]


def clear_global_armed() -> None:
    """Drop every passive rule (e.g. at session end)."""
    global _global_armed
    _global_armed = []


def list_global_armed() -> list[Effect]:
    """The passive (global) roll-timing effects currently armed (tests/debug)."""
    out: list[Effect] = []
    for armed in _global_armed:
        out.extend(armed.effects)
    return out


def reset() -> None:
    """Clear the whole store (tests)."""
    _armed.clear()
    _global_armed.clear()

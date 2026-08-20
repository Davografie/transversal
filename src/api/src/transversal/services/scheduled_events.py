"""Persisted, owner-scoped timed reverts (scheduled events).

An effect with a ``duration`` is applied immediately; its inverse effect is then
scheduled to fire when the duration's timers expire.  This replaces the ad-hoc
expiry mechanisms (``attunements.until``, ``targeting_bans.scenes_remaining``,
``taken_out``, and the engine's in-memory ``_schedule``) with one persisted
list on the owner (entity or traitsetting).
"""

from __future__ import annotations

import uuid
from typing import Optional

from transversal.domain import (
    Effect,
    EffectTiming,
    ScheduledEvent,
    TimerCombine,
)


def build_revert(effect: Effect, *, prior_result: Optional[str] = None) -> Optional[Effect]:
    """Return the inverse effect for ``effect``, or None if it has no inverse.

    The inverse (type, action) comes from the effect registry.  ``prior_result``
    overrides the revert's ``result`` for actions that capture the pre-apply
    value (e.g. ``set`` reverts to the previous die rating).
    """
    from transversal.services.effects_registry import get_inverse

    inv, captures_prior = get_inverse(effect.type, effect.action)
    if inv is None:
        return None
    result = effect.result
    if captures_prior and prior_result is not None:
        result = prior_result
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type=inv[0],
        action=inv[1],
        target=effect.target,
        result=result,
        target_scope=effect.target_scope,
        context=effect.context,
    )


def _new_event(effect: Effect, timers, combine, source_sfx_id) -> ScheduledEvent:
    return ScheduledEvent(
        id=f"se-{uuid.uuid4().hex[:12]}",
        effect=effect,
        timers=list(timers),
        combine=combine,
        source_sfx_id=source_sfx_id,
    )


def _append(owner, event: ScheduledEvent) -> None:
    owner.scheduled_events = list(owner.scheduled_events or []) + [event]


def queue_revert(
    owner,
    effect: Effect,
    *,
    target: Optional[str] = None,
    prior_result: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> Optional[ScheduledEvent]:
    """Build + append the inverse of ``effect`` to ``owner`` (no persistence).

    Used by the collect-mutations path (``apply_effects``), where the caller
    persists the mutated owner.  Returns the scheduled event, or None if the
    effect has no duration or no inverse.
    """
    if not effect.duration or not effect.duration.timers:
        return None
    revert = build_revert(effect, prior_result=prior_result)
    if revert is None:
        return None
    if target is not None:
        revert.target = target
    event = _new_event(revert, effect.duration.timers, effect.duration.combine, source_sfx_id)
    _append(owner, event)
    return event


def schedule_revert(
    entity,
    effect: Effect,
    repo,
    *,
    target: Optional[str] = None,
    prior_result: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> bool:
    """Schedule the inverse of ``effect`` on an *entity* (persists it)."""
    event = queue_revert(entity, effect, target=target, prior_result=prior_result, source_sfx_id=source_sfx_id)
    if event is None:
        return False
    repo.update_entity(entity)
    return True


def schedule_effect(
    entity,
    effect: Effect,
    timers,
    combine,
    repo,
    *,
    source_sfx_id: Optional[str] = None,
) -> bool:
    """Schedule an explicit (already-resolved) effect on an *entity*.

    Used for statuses whose forward mutation isn't an effect with a registry
    inverse (e.g. ``taken_out`` schedules a ``clear_taken_out`` revert directly).
    """
    _append(entity, _new_event(effect, timers, combine, source_sfx_id))
    repo.update_entity(entity)
    return True


def schedule_traitsetting_revert(
    ts,
    effect: Effect,
    repo,
    *,
    prior_result: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> bool:
    """Schedule the inverse of ``effect`` on a *trait setting* (persists it)."""
    event = queue_revert(ts, effect, prior_result=prior_result, source_sfx_id=source_sfx_id)
    if event is None:
        return False
    repo.update_traitsetting(ts)
    return True


def _transpired(timer) -> bool:
    return timer.remaining <= 0


def _expired(event: ScheduledEvent) -> bool:
    if not event.timers:
        return True
    if event.combine == TimerCombine.ALL_TRANSPIRED:
        return all(_transpired(t) for t in event.timers)
    return any(_transpired(t) for t in event.timers)


def _advance_owner(owner, event_type: str) -> tuple[list[ScheduledEvent], list[ScheduledEvent]]:
    """Decrement matching timers; return ``(kept, fired)``."""
    kept: list[ScheduledEvent] = []
    fired: list[ScheduledEvent] = []
    for se in owner.scheduled_events:
        for t in se.timers:
            if t.event == event_type and t.remaining > 0:
                t.remaining -= 1
        if _expired(se):
            fired.append(se)
        else:
            kept.append(se)
    return kept, fired


def _apply_fired(repo, fired: list[ScheduledEvent], entity_id: str, universe: str) -> int:
    from transversal.services.effects_applier import effect_registry

    for se in fired:
        effect_registry.apply(se.effect, entity_id, universe, {})
    return len(fired)


def advance_events(repo, event_type: str) -> int:
    """Advance every entity's scheduled events by one tick of ``event_type``."""
    fired_count = 0
    for entity in repo.list_all_entities():
        if not entity.scheduled_events:
            continue
        kept, fired = _advance_owner(entity, event_type)
        if not fired:
            continue
        fired_count += _apply_fired(repo, fired, entity.id, entity.current_universe)
        entity.scheduled_events = kept
        repo.update_entity(entity)
    return fired_count


def advance_traitsetting_events(repo, event_type: str) -> int:
    """Advance every trait setting's scheduled events by one tick."""
    fired_count = 0
    for ts in repo.list_all_traitsettings():
        if not ts.scheduled_events:
            continue
        kept, fired = _advance_owner(ts, event_type)
        if not fired:
            continue
        fired_count += _apply_fired(repo, fired, ts.entity_id, "")
        ts.scheduled_events = kept
        repo.update_traitsetting(ts)
    return fired_count


def dispatch_event(
    repo,
    event_type: str,
    entity_id: Optional[str] = None,
    universe: str = "",
    context: Optional[dict] = None,
) -> int:
    """Central advancement point for a state/timing event.

    - Global boundary (``entity_id is None``, e.g. ``beat``/``scene``/``session``):
      advances every entity + trait setting.
    - Entity-scoped (``entity_id`` given, e.g. ``location_changed``): advances
      that entity + its trait settings, then fires automatic state SFX.

    ``repo`` may be None; it is resolved lazily from the app singleton.
    Returns the number of scheduled events fired.
    """
    if repo is None:
        from transversal.main import _get_repo

        repo = _get_repo()
    fired = 0
    if entity_id is None:
        fired += advance_events(repo, event_type)
        fired += advance_traitsetting_events(repo, event_type)
    else:
        entity = repo.get_entity(entity_id)
        if entity is not None and entity.scheduled_events:
            kept, evts = _advance_owner(entity, event_type)
            if evts:
                fired += _apply_fired(repo, evts, entity.id, entity.current_universe)
                entity.scheduled_events = kept
                repo.update_entity(entity)
        for ts in repo.get_traitsettings_for_entity(entity_id):
            if not ts.scheduled_events:
                continue
            kept, evts = _advance_owner(ts, event_type)
            if evts:
                fired += _apply_fired(repo, evts, ts.entity_id, "")
                ts.scheduled_events = kept
                repo.update_traitsetting(ts)
        from transversal.services.state_events import fire_state_sfx

        fire_state_sfx(entity_id, universe, event_type, context or {})
    return fired

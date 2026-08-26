"""Central persisted scheduled-events repository.

Every timed revert/deferred effect becomes a ``ScheduledEvent`` row in the
``scheduled_events`` collection, carrying a ``target_type`` + ``target_id`` that
resolve to the entity/trait-setting the effect applies against at fire time.
This replaces the owner-scoped ``scheduled_events`` lists and the engine's
in-memory ``_schedule`` with one persisted, queryable timer store.
"""

from __future__ import annotations

import uuid
from typing import Optional

from transversal.domain import (
    Effect,
    EffectTiming,
    ScheduledEvent,
    Timer,
    TimerCombine,
)

# Global timing boundaries that also fire an auto-fire SFX trigger.
_GLOBAL_BOUNDARY_SFX = {"beat": "on_beat", "scene": "on_scene"}


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


def _new_event(target_type, target_id, effect, timers, combine, source_sfx_id) -> ScheduledEvent:
    return ScheduledEvent(
        id=f"se-{uuid.uuid4().hex[:12]}",
        target_type=target_type,
        target_id=target_id,
        effect=effect,
        timers=list(timers),
        combine=combine,
        source_sfx_id=source_sfx_id,
    )


def schedule_event(
    repo,
    target_type: str,
    target_id: str,
    effect: Effect,
    timers,
    combine,
    source_sfx_id: Optional[str] = None,
) -> ScheduledEvent:
    """Create + persist a scheduled event in the central store."""
    event = _new_event(target_type, target_id, effect, timers, combine, source_sfx_id)
    repo.create_scheduled_event(event)
    return event


def schedule_revert(
    repo,
    target_type: str,
    target_id: str,
    effect: Effect,
    *,
    target: Optional[str] = None,
    prior_result: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> Optional[ScheduledEvent]:
    """Build + persist the inverse of ``effect`` (no-op without a duration/inverse)."""
    if not effect.duration or not effect.duration.timers:
        return None
    revert = build_revert(effect, prior_result=prior_result)
    if revert is None:
        return None
    if target is not None:
        revert.target = target
    return schedule_event(repo, target_type, target_id, revert, effect.duration.timers, effect.duration.combine, source_sfx_id)


def schedule_effect(
    repo,
    target_type: str,
    target_id: str,
    effect: Effect,
    timers,
    combine,
    *,
    source_sfx_id: Optional[str] = None,
) -> ScheduledEvent:
    """Persist an explicit (already-resolved) effect on the central store."""
    return schedule_event(repo, target_type, target_id, effect, timers, combine, source_sfx_id)


def timing_to_timer(timing) -> Optional[Timer]:
    """Map an ``EffectTiming`` boundary to a single timer, or None if unmapable."""
    from transversal.domain import EffectTiming

    if timing == EffectTiming.END_OF_BEAT:
        return Timer(event="beat", remaining=1)
    if timing == EffectTiming.END_OF_SCENE:
        return Timer(event="scene", remaining=1)
    if timing == EffectTiming.END_OF_SESSION:
        return Timer(event="session", remaining=1)
    if timing == EffectTiming.AFTER_BEATS:
        return Timer(event="beat", remaining=3)
    return None  # IMMEDIATE / ON_CONDITION


def schedule_deferred(
    repo,
    target_type: str,
    target_id: str,
    effect: Effect,
    *,
    source_sfx_id: Optional[str] = None,
) -> bool:
    """Persist a deferred (non-IMMEDIATE) effect as a scheduled event."""
    timer = timing_to_timer(effect.timing)
    if timer is None:
        return False
    schedule_event(repo, target_type, target_id, effect, [timer], TimerCombine.FIRST_TO_FIRE, source_sfx_id)
    return True


def _transpired(timer) -> bool:
    return timer.remaining <= 0


def _expired(event: ScheduledEvent) -> bool:
    if not event.timers:
        return True
    if event.combine == TimerCombine.ALL_TRANSPIRED:
        return all(_transpired(t) for t in event.timers)
    return any(_transpired(t) for t in event.timers)


def _advance_event(event: ScheduledEvent, event_type: str) -> bool:
    """Decrement matching timers; return True if the event is now expired."""
    for t in event.timers:
        if t.event == event_type and t.remaining > 0:
            t.remaining -= 1
    return _expired(event)


def _apply_event(repo, event: ScheduledEvent) -> int:
    """Resolve the target and apply the event's effect; return 1 if applied."""
    from transversal.services.effects_applier import effect_registry

    if event.target_type == "trait_setting":
        ts = repo.get_traitsetting(event.target_id)
        if ts is None:
            return 0  # orphan (target deleted)
        effect_registry.apply(event.effect, ts.entity_id, "", {})
        return 1

    entity = repo.get_entity(event.target_id)
    if entity is None:
        return 0  # orphan (target deleted)
    effect_registry.apply(event.effect, entity.id, entity.current_universe, {})
    return 1


def advance_scheduled_events(repo, event_type: str, entity_id: Optional[str] = None) -> int:
    """Advance the central timer store by one tick; fire + delete due events.

    When ``entity_id`` is given (an entity-scoped state change, e.g.
    ``location_changed``), only that entity's / its trait-settings' events are
    ticked; global boundaries (``beat``/``scene``/``session``) tick everything.
    """
    fired = 0
    for event in repo.list_all_scheduled_events():
        if entity_id is not None:
            if event.target_type == "entity":
                if event.target_id != entity_id:
                    continue
            elif event.target_type == "trait_setting":
                ts = repo.get_traitsetting(event.target_id)
                if ts is None or ts.entity_id != entity_id:
                    continue
            else:
                continue
        if _advance_event(event, event_type):
            fired += _apply_event(repo, event)
            repo.delete_scheduled_event(event.id)
        else:
            repo.update_scheduled_event(event)
    return fired


def dispatch_event(
    repo,
    event_type: str,
    entity_id: Optional[str] = None,
    universe: str = "",
    context: Optional[dict] = None,
) -> int:
    """Central advancement point for a state/timing event.

    Advances the central timer store, then (for entity-scoped events) fires
    automatic state SFX.
    """
    if repo is None:
        from transversal.main import _get_repo

        repo = _get_repo()
    fired = advance_scheduled_events(repo, event_type, entity_id=entity_id)
    from transversal.services.roll_deferral import expire_armed

    if entity_id is not None:
        expire_armed(entity_id, event_type)
        from transversal.services.state_events import fire_state_sfx

        fire_state_sfx(entity_id, universe, event_type, context or {})
    else:
        # Global timing boundary: drop armed SFX bound to this event, then fire
        # the matching auto-fire SFX for every entity.
        for entity in repo.list_all_entities():
            expire_armed(entity.id, event_type)
        sfx_trigger = _GLOBAL_BOUNDARY_SFX.get(event_type)
        if sfx_trigger:
            from transversal.services.state_events import fire_global_state_sfx

            fire_global_state_sfx(sfx_trigger)
    return fired

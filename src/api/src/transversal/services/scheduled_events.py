"""Persisted, owner-scoped timed reverts (scheduled events).

An effect with a ``duration`` is applied immediately; its inverse effect is then
scheduled to fire when the duration's timers expire.  This replaces the ad-hoc
expiry mechanisms (``attunements.until``, ``targeting_bans.scenes_remaining``,
``taken_out``, and the engine's in-memory ``_schedule``) with one persisted
list on the owner.
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


# Forward action → (inverse type, inverse action).  The revert effect reuses the
# forward effect's resolved target/result/scope/context; only the action flips.
INVERSE_ACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("entity", "targeting_ban"): ("entity", "remove_targeting_ban"),
}


def inverse_of(effect: Effect, *, target: Optional[str] = None) -> Optional[Effect]:
    inv = INVERSE_ACTIONS.get((effect.type, effect.action))
    if inv is None:
        return None
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type=inv[0],
        action=inv[1],
        target=target if target is not None else effect.target,
        result=effect.result,
        target_scope=effect.target_scope,
        context=effect.context,
    )


def schedule_revert(
    entity,
    effect: Effect,
    repo,
    *,
    target: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> bool:
    """If ``effect`` has a duration with a known inverse, append a ScheduledEvent.

    The forward effect must already have been applied to ``entity`` (so its
    concrete state is already mutated); this only schedules the undo.
    """
    if not effect.duration or not effect.duration.timers:
        return False
    revert = inverse_of(effect, target=target)
    if revert is None:
        return False
    event = ScheduledEvent(
        id=f"se-{uuid.uuid4().hex[:12]}",
        effect=revert,
        timers=list(effect.duration.timers),
        combine=effect.duration.combine,
        source_sfx_id=source_sfx_id,
    )
    entity.scheduled_events = list(entity.scheduled_events or []) + [event]
    repo.update_entity(entity)
    return True


def _transpired(timer) -> bool:
    return timer.remaining <= 0


def _expired(event: ScheduledEvent) -> bool:
    if not event.timers:
        return True
    if event.combine == TimerCombine.ALL_TRANSPIRED:
        return all(_transpired(t) for t in event.timers)
    return any(_transpired(t) for t in event.timers)


def advance_events(repo, event_type: str) -> int:
    """Advance every entity's scheduled events by one tick of ``event_type``.

    Decrements matching timers, applies the revert effect of expired events, and
    removes them.  Returns the number of events fired.
    """
    from transversal.services.effects_applier import effect_registry

    fired_count = 0
    for entity in repo.list_all_entities():
        if not entity.scheduled_events:
            continue
        kept = []
        fired = []
        for se in entity.scheduled_events:
            for t in se.timers:
                if t.event == event_type and t.remaining > 0:
                    t.remaining -= 1
            if _expired(se):
                fired.append(se)
            else:
                kept.append(se)
        if not fired:
            continue
        for se in fired:
            effect_registry.apply(se.effect, entity.id, entity.current_universe, {})
            fired_count += 1
        entity.scheduled_events = kept
        repo.update_entity(entity)
    return fired_count

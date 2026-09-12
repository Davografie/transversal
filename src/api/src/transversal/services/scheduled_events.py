"""Central persisted scheduled-events repository.

Every timed revert/deferred effect becomes a ``ScheduledEvent`` row in the
``scheduled_events`` collection, carrying a ``target_type`` + ``target_id`` that
resolve to the entity/trait-setting the effect applies against at fire time.
This replaces the owner-scoped ``scheduled_events`` lists and the engine's
in-memory ``_schedule`` with one persisted, queryable timer store.
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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

#: The activation whose effects are currently being applied (set by the applier
#: around one SFX's handler dispatch, from the context the engine threaded in).
#: ``cancelable`` marks a *manual* activation: its untimed undos are booked as
#: holds — applied if the activation is ended early, dissolved when it commits.
_BOOKING: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "sfx_booking", default=None,
)


@contextmanager
def activation_booking(sfx_id: Optional[str], cancelable: bool = False):
    """Scope handler dispatch to one activation, so bookings can be attributed."""
    token = _BOOKING.set({"sfx_id": sfx_id, "cancelable": bool(cancelable)})
    try:
        yield
    finally:
        _BOOKING.reset(token)


def _booking() -> Optional[dict]:
    return _BOOKING.get()


def build_revert(
    effect: Effect,
    *,
    prior_result: Optional[str] = None,
    context_extra: Optional[dict] = None,
) -> Optional[Effect]:
    """Return the inverse effect for ``effect``, or None if it has no inverse.

    The inverse (type, action) comes from the effect registry.  ``prior_result``
    overrides the revert's ``result`` for actions that capture the pre-apply
    value (e.g. ``set`` reverts to the previous die rating).  ``context_extra``
    merges extra data into the revert's context — how a handler hands its undo
    the private facts only it knows (which dice a pool add appended, and where).

    The revert lands where the effect landed: the same target, and the same
    subject (``entity``, when it is a concrete value rather than an unresolved
    name) — an undo of a cross-entity effect is not silently redirected to the
    actor.
    """
    from transversal.services.effects_registry import get_inverse

    inv, captures_prior = get_inverse(effect.type, effect.action)
    if inv is None:
        return None
    result = effect.result
    if captures_prior and prior_result is not None:
        result = prior_result
    subject = (effect.entity or "").strip()
    if subject.startswith("{"):
        subject = ""  # unresolved name → the row's owner is the right actor
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type=inv[0],
        action=inv[1],
        target=effect.target,
        entity=subject,
        result=result,
        target_scope=effect.target_scope,
        context={**(effect.context or {}), **(context_extra or {})},
    )


def _new_event(target_type, target_id, effect, timers, combine, source_sfx_id, kind="revert") -> ScheduledEvent:
    booking = _booking()
    if source_sfx_id is None and booking is not None:
        source_sfx_id = booking.get("sfx_id")
    return ScheduledEvent(
        id=f"se-{uuid.uuid4().hex[:12]}",
        target_type=target_type,
        target_id=target_id,
        effect=effect,
        timers=list(timers),
        combine=combine,
        source_sfx_id=source_sfx_id,
        kind=kind,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def schedule_event(
    repo,
    target_type: str,
    target_id: str,
    effect: Effect,
    timers,
    combine,
    source_sfx_id: Optional[str] = None,
    kind: str = "revert",
) -> ScheduledEvent:
    """Create + persist a row in the central store."""
    event = _new_event(target_type, target_id, effect, timers, combine, source_sfx_id, kind=kind)
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
    context_extra: Optional[dict] = None,
) -> Optional[ScheduledEvent]:
    """Build + persist the inverse of ``effect``.

    With a duration the inverse is a timed **revert**. Without one it is booked as
    a **hold** — but only inside a cancelable (manual) activation, where the undo
    exists so the activation can be taken back before it commits. Anywhere else
    there is nothing to book and this is a no-op.
    """
    revert = build_revert(effect, prior_result=prior_result, context_extra=context_extra)
    if revert is None:
        return None
    if target is not None:
        revert.target = target
    if effect.duration and effect.duration.timers:
        return schedule_event(
            repo, target_type, target_id, revert, effect.duration.timers,
            effect.duration.combine, source_sfx_id, kind="revert",
        )
    booking = _booking()
    if not (booking and booking.get("cancelable")):
        return None
    return schedule_event(
        repo, target_type, target_id, revert, [], TimerCombine.FIRST_TO_FIRE,
        source_sfx_id, kind="hold",
    )


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
    """Persist a deferred (non-IMMEDIATE) forward effect as a scheduled event."""
    timer = timing_to_timer(effect.timing)
    if timer is None:
        return False
    schedule_event(repo, target_type, target_id, effect, [timer], TimerCombine.FIRST_TO_FIRE,
                   source_sfx_id, kind="pending")
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


def _event_owner_entity(repo, event: ScheduledEvent) -> Optional[str]:
    """The entity a row ultimately applies against (a trait setting resolves through its owner)."""
    if event.target_type == "trait_setting":
        ts = repo.get_traitsetting(event.target_id)
        return ts.entity_id if ts is not None else None
    return event.target_id


def commit_holds(
    repo,
    *,
    entity_id: Optional[str] = None,
    source_sfx_id: Optional[str] = None,
) -> int:
    """Dissolve held undos: the activation has committed.

    Called when a delayed part of the activation fires and when the dice are
    rolled. From either moment on, what the activation changed is paid for for
    real — its holds cannot be applied any more, they are simply dropped.
    """
    dropped = 0
    for event in repo.list_all_scheduled_events():
        if event.kind != "hold":
            continue
        if source_sfx_id is not None and event.source_sfx_id != source_sfx_id:
            continue
        if entity_id is not None and _event_owner_entity(repo, event) != entity_id:
            continue
        repo.delete_scheduled_event(event.id)
        dropped += 1
    return dropped


def end_activation(repo, entity_id: str, sfx_id: str) -> dict:
    """Take back a manual activation that has not committed yet.

    Applies every undo the activation still owes — the timed reverts early, and
    the holds — in reverse order of application; drops the deferred parts it had
    not reached; and un-arms anything still waiting on a roll. Returns a summary
    for the caller (counts only; the effects themselves are applied through the
    ordinary handler path, persistence included).
    """
    records = [
        e for e in repo.list_all_scheduled_events()
        if e.source_sfx_id == sfx_id and _event_owner_entity(repo, e) == entity_id
    ]
    reverted = 0
    dropped_pending = 0
    dropped_holds = 0
    for event in sorted(records, key=lambda e: (e.created_at, e.id), reverse=True):
        if event.kind == "pending":
            repo.delete_scheduled_event(event.id)
            dropped_pending += 1
            continue
        reverted += _apply_event(repo, event)
        repo.delete_scheduled_event(event.id)
        if event.kind == "hold":
            dropped_holds += 1

    from transversal.services.roll_deferral import drop_armed
    unarmed = drop_armed(entity_id, sfx_id)
    return {
        "entity_id": entity_id,
        "sfx_id": sfx_id,
        "records": len(records),
        "reverted": reverted,
        "dropped_pending": dropped_pending,
        "dropped_holds": dropped_holds,
        "unarmed": unarmed,
    }


def in_flight_sfx_ids(repo, entity_id: str) -> list:
    """The rules this entity still has *in flight* — activated, not yet committed.

    A rule is in flight while any row it sourced is still pending: a hold, a timed
    revert, or a deferred part that has not fired. That is exactly the window in
    which pressing it again takes it back.
    """
    ids: list = []
    for event in repo.list_all_scheduled_events():
        if not event.source_sfx_id or event.source_sfx_id in ids:
            continue
        if _event_owner_entity(repo, event) != entity_id:
            continue
        ids.append(event.source_sfx_id)
    return ids


def advance_scheduled_events(repo, event_type: str, entity_id: Optional[str] = None) -> int:
    """Advance the central timer store by one tick; fire + delete due events.

    When ``entity_id`` is given (an entity-scoped state change, e.g.
    ``location_changed``), only that entity's / its trait-settings' events are
    ticked; global boundaries (``beat``/``scene``/``session``) tick everything.
    """
    fired = 0
    for event in repo.list_all_scheduled_events():
        if event.kind == "hold":
            # A hold never fires on its own: it is applied by end_activation, or
            # dissolved by commit_holds. Ticking it would apply it out of turn.
            continue
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
            if event.source_sfx_id:
                # A delayed part of the activation fired: it has committed, so
                # anything it was still holding on to is now permanent.
                commit_holds(
                    repo,
                    source_sfx_id=event.source_sfx_id,
                    entity_id=_event_owner_entity(repo, event),
                )
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
        from transversal.services.roll_deferral import expire_global

        expire_global(event_type)
        for entity in repo.list_all_entities():
            expire_armed(entity.id, event_type)
        sfx_trigger = _GLOBAL_BOUNDARY_SFX.get(event_type)
        if sfx_trigger:
            from transversal.services.state_events import fire_global_state_sfx

            fire_global_state_sfx(sfx_trigger)
    return fired

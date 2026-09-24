"""Central persisted scheduled-events repository.

Every timed revert/deferred effect becomes a ``ScheduledEvent`` row in the
``scheduled_events`` collection, carrying a ``target_type`` + ``target_id`` that
resolve to the entity/trait-setting the effect applies against at fire time.
This replaces the owner-scoped ``scheduled_events`` lists and the engine's
in-memory ``_schedule`` with one persisted, queryable timer store.
"""

from __future__ import annotations

import contextvars
import logging
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
def activation_booking(sfx_id: Optional[str], cancelable: bool = False, source_id: str = ""):
    """Scope handler dispatch to one activation, so bookings can be attributed."""
    token = _BOOKING.set({
        "sfx_id": sfx_id, "cancelable": bool(cancelable), "source_id": source_id or "",
    })
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


def _booking_context_extra(context_extra: Optional[dict]) -> Optional[dict]:
    """Fold the activation's own source into a booked undo's context.

    The pool-as-ledger check needs to know which trait instance a rule lived on
    (its declared source) so a die that came from it is attributed even when the
    client did not stamp the die — ``activation_source`` is that record.
    """
    booking = _booking()
    if not (booking and booking.get("source_id")):
        return context_extra
    extra = dict(context_extra or {})
    extra.setdefault("activation_source", booking["source_id"])
    return extra


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
    revert = build_revert(effect, prior_result=prior_result, context_extra=_booking_context_extra(context_extra))
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


def end_event(repo, event: ScheduledEvent) -> int:
    """End one row now, instead of when its timer expires.

    A revert/hold row's stored effect *is* the undo — applying it ends the effect
    early. A deferred forward row has not happened yet, so ending it means it
    never does.
    """
    if event.kind == "pending":
        repo.delete_scheduled_event(event.id)
        return 0
    applied = _apply_event(repo, event)
    repo.delete_scheduled_event(event.id)
    return applied


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
    failed = 0
    dropped_pending = 0
    dropped_holds = 0
    for event in sorted(records, key=lambda e: (e.created_at, e.id), reverse=True):
        if event.kind == "pending":
            repo.delete_scheduled_event(event.id)
            dropped_pending += 1
            continue
        try:
            reverted += end_event(repo, event)
        except Exception as exc:  # noqa: BLE001
            # An undo that cannot be applied (a refund the balance can no longer
            # cover, a missing target) must not stop the rest of the take-back.
            logging.getLogger(__name__).warning(
                "[end_activation] could not apply %s: %s", event.id, exc,
            )
            repo.delete_scheduled_event(event.id)
            failed += 1
        if event.kind == "hold":
            dropped_holds += 1

    from transversal.services.roll_deferral import drop_armed
    unarmed = drop_armed(entity_id, sfx_id)
    return {
        "entity_id": entity_id,
        "sfx_id": sfx_id,
        "records": len(records),
        "reverted": reverted,
        "failed": failed,
        "dropped_pending": dropped_pending,
        "dropped_holds": dropped_holds,
        "unarmed": unarmed,
    }


def _die_identity(die: dict) -> tuple:
    """How two dice in a pool count as *the same one* (the key ``_added_dice`` diffs by)."""
    return (die.get("ts_id"), die.get("source_id"), die.get("die"), die.get("label"))


def _contribution_keys(repo, sfx_id: str, entity_id: str, pool: list) -> list:
    """The dice in ``pool`` this rule put there.

    Three kinds of evidence, because a die can arrive in a pool in three ways: the
    client stamps the die it adds with the rules active for its trait
    (``armed_sfx_ids``); a pool-add *effect* records the dice it appended in its
    own undo row (``pool_add``); and a die that came from the trait instance the
    rule *lives on* (its declared source, ``activation_source``) is the rule's
    cost whatever put it there.
    """
    keys = [_die_identity(d) for d in (pool or []) if sfx_id in (d.get("armed_sfx_ids") or [])]
    for event in repo.list_all_scheduled_events():
        if event.source_sfx_id != sfx_id:
            continue
        context = event.effect.context or {}
        record = context.get("pool_add") or {}
        if record.get("owner") == entity_id:
            keys.extend(_die_identity(d) for d in (record.get("entries") or []))
        source_ts = context.get("activation_source")
        if source_ts:
            keys.extend(_die_identity(d) for d in (pool or []) if d.get("ts_id") == source_ts)
    return keys


def end_activations_whose_cost_left(
    repo, entity_id: str, before: list, after: list, *, manual_ids=None,
) -> list:
    """The pool is the ledger: a rule whose cost left it goes with it.

    For every rule in flight for this entity that *had* dice in the saved pool,
    if none of them survives the save, the activation is ended — its undos are
    applied (the razmerit goes back), what was still waiting is dropped. A rule
    that contributed no dice is untouched: it has no cost here to lose. Any one
    of its dice still on the table keeps it in force.

    ``manual_ids`` narrows to the rules that can be taken back at all (only a
    manual activation is a bargain a player struck).
    """
    ended: list = []
    for sfx_id in in_flight_sfx_ids(repo, entity_id):
        if manual_ids is not None and sfx_id not in manual_ids:
            continue
        contributed = _contribution_keys(repo, sfx_id, entity_id, before)
        if not contributed:
            continue
        surviving: dict[tuple, int] = {}
        for die in (after or []):
            key = _die_identity(die)
            surviving[key] = surviving.get(key, 0) + 1
        if any(surviving.get(key, 0) for key in contributed):
            continue  # the cost is still on the table
        end_activation(repo, entity_id, sfx_id)
        ended.append(sfx_id)
    return ended


def in_flight_sfx_ids(repo, entity_id: str) -> list:
    """The rules this entity still has *in flight* — activated, not yet committed.

    A rule is in flight while any part of it is still pending: a row it sourced
    (a hold, a timed revert, a deferred part that has not fired) **or** a part
    waiting on a roll in the armed registers. That is exactly the window in which
    pressing it again takes it back.
    """
    ids: list = []
    for event in repo.list_all_scheduled_events():
        if not event.source_sfx_id or event.source_sfx_id in ids:
            continue
        if _event_owner_entity(repo, event) != entity_id:
            continue
        ids.append(event.source_sfx_id)
    from transversal.services.roll_deferral import list_armed_sfx_ids
    for sfx_id in list_armed_sfx_ids(entity_id):
        if sfx_id not in ids:
            ids.append(sfx_id)
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
        if event_type == "location_changed":
            # Standing on the destination ends the guidance ([[Guided Route]]).
            # Cleared *before* the rules run, so a rule that reacts to an arrival
            # can set a new destination without this wiping it in the same breath.
            from transversal.services.guided_route import clear_arrived_destination

            clear_arrived_destination(repo, entity_id, (context or {}).get("to_location"))
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

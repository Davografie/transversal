"""Route state-change events through the effects engine for automatic SFX.

Unlike roll/contest firing (which happens in the endpoint layer), state changes
can happen in many services (entity moves, trait gains, relationship creation).
This module centralises that: call :func:`fire_state_sfx` at the point a state
change is persisted, and matching condition-gated SFX will fire immediately.
"""

from __future__ import annotations

import logging

log = logging.getLogger("transversal.sfx")

# Re-entrancy guard: an SFX fired from a state change may itself mutate state
# and re-enter the same event (e.g. an on_trait_gain SFX that gains a trait).
_firing: set[tuple[str, str]] = set()


def fire_state_sfx(
    entity_id: str,
    universe: str,
    event_type: str,
    context: dict | None = None,
) -> None:
    """Fire automatic SFX for a state-change event, if any match."""
    key = (entity_id, event_type)
    if key in _firing:
        return
    _firing.add(key)
    try:
        from transversal.main import _get_engine, _get_repo
        from transversal.services.effects_engine import GameEvent
        from transversal.services.roll_orchestrator import _emit_pending_choices
        from transversal.services.sfx_owner import get_available_sfx_ids

        engine = _get_engine()
        repo = _get_repo()
        entity = repo.get_entity(entity_id)
        if entity is None:
            return
        if not universe:
            universe = entity.current_universe

        sfx_ids = get_available_sfx_ids(entity_id, universe, repo)
        log.info(
            "[fire_state_sfx] entity=%s event=%s universe=%s available=%s",
            entity_id, event_type, universe, sfx_ids,
        )
        event = GameEvent(
            type=event_type,
            entity_id=entity_id,
            universe=universe,
            context=context or {},
        )
        outcome = engine.process_event_outcome(event, sfx_ids, entity.razmerit, repo=repo)
        _emit_pending_choices(entity_id, universe, outcome.pending, outcome.structured)
    finally:
        _firing.discard(key)


def broadcast_main_active(player_id: str, entity_id: str, active: bool) -> None:
    """Broadcast a main's active state to all sessions (SSE).

    ``active=True`` when a player took control of a main; ``active=False`` when
    they switched away (e.g. to a support character). Consumed by the GM troupe
    overview / availability grey-out.
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    event = StreamEvent(
        event="main_active",
        data={"player_id": player_id, "entity_id": entity_id, "active": active},
    )
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event=event.event, session_id=s.id, data=event.data,
        ))


def broadcast_presence_changed() -> None:
    """Broadcast that the set of online players changed (someone joined/left).

    Consumed by the GM troupe overview to refresh which players are online.
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="presence_changed", session_id=s.id, data={},
        ))


def fire_global_state_sfx(event_type: str, context: dict | None = None) -> None:
    """Fire automatic SFX for a global (non-entity-scoped) boundary event.

    Beat/scene/session-end ticks every entity's timers and should also fire
    their matching ``on_beat``/``on_scene``/``on_session_end`` SFX. Iterates
    every entity; non-owners resolve to an empty SFX set and no-op.

    Short-circuits when no SFX carries the trigger at all, and bulk-loads the
    per-entity availability data once instead of re-querying per entity — the
    walk used to cost 4-6 DB round-trips per entity.
    """
    from transversal.main import _get_engine, _get_repo
    from transversal.services.effects_engine import GameEvent
    from transversal.services.roll_orchestrator import _emit_pending_choices
    from transversal.services.sfx_owner import (
        build_sfx_availability_prefetch,
        get_available_sfx_ids,
    )

    repo = _get_repo()

    # Nothing can fire if no SFX declares this trigger — skip the whole walk.
    sfx_docs = repo.get_all_sfxs()
    if not any(s.trigger == event_type for s in sfx_docs):
        return

    engine = _get_engine()
    entities = repo.list_all_entities()
    prefetch = build_sfx_availability_prefetch(repo, entities, sfx_docs=sfx_docs)
    for entity in entities:
        sfx_ids = get_available_sfx_ids(
            entity.id, entity.current_universe, repo, prefetch=prefetch
        )
        event = GameEvent(
            type=event_type,
            entity_id=entity.id,
            universe=entity.current_universe,
            context=context or {},
        )
        outcome = engine.process_event_outcome(event, sfx_ids, entity.razmerit, repo=repo)
        _emit_pending_choices(entity.id, entity.current_universe, outcome.pending, outcome.structured)


def fire_projection_created(entity_id: str, universe: str, projection_id: str) -> None:
    """Fire ``on_projection_create`` for a newly-created projection body.

    Single fire site for every runtime path that produces a Projection record,
    so the trigger's variables can't drift from any one creation path.
    """
    fire_state_sfx(entity_id, universe, "projection_created", {
        "entity_created": entity_id,
        "projection_created": projection_id,
        "universe": universe,
    })


def fire_session_start() -> None:
    """Arm every ``on_session_start`` passive rule's roll-timing effects globally.

    Passive rules (e.g. One Trick) arm once for the session with scope
    ``global`` — not per-entity — so characters joining mid-session are still
    covered. Re-arming clears the previous set first, so [Session] Start is
    idempotent.
    """
    from transversal.main import _get_repo
    from transversal.services.roll_deferral import ROLL_TIMINGS, arm_passive, clear_global_armed

    repo = _get_repo()
    clear_global_armed()
    for sfx in repo.get_all_sfxs():
        if sfx.trigger != "on_session_start":
            continue
        roll_effects = [e for e in sfx.effects if e.timing in ROLL_TIMINGS]
        if roll_effects:
            arm_passive(
                roll_effects,
                duration=sfx.duration,
                source_sfx_id=sfx.id,
                source_kind=sfx.source_kind,
                source_id=None,
            )


def fire_session_end() -> None:
    """Fire ``on_session_end`` SFX globally and drop armed passives.

    The mirror of :func:`fire_session_start` for the session's far boundary:
    first drop the ``on_session_start`` passives armed at session start, then
    fire every entity's matching ``on_session_end`` SFX (e.g. Challenge
    Statement's end-of-session cleanup/reward) as a global boundary event.
    """
    from transversal.services.roll_deferral import clear_global_armed

    clear_global_armed()
    fire_global_state_sfx("on_session_end")


def fire_contest_outcome_sfx(
    winner_id: str,
    loser_id: str,
    universe: str,
    effect_die: str | None = None,
    high_stakes: bool = False,
    taken_out: bool = False,
) -> None:
    """Fire on_contest_win / on_contest_loss for a resolved manual contest.

    The seeded table SFX can use ``{effect_die}`` in its result; the effects
    engine substitutes it from the event context before applying.
    """
    from transversal.main import _get_engine, _get_repo
    from transversal.services.effects_engine import GameEvent
    from transversal.services.roll_orchestrator import _emit_pending_choices
    from transversal.services.sfx_owner import get_available_sfx_ids

    engine = _get_engine()
    repo = _get_repo()
    for entity_id, contest_winner, opponent_id in (
        (winner_id, "player", loser_id),
        (loser_id, "opponent", winner_id),
    ):
        entity = repo.get_entity(entity_id)
        if entity is None:
            continue
        if not universe:
            universe = entity.current_universe
        opponent = repo.get_entity(opponent_id)
        opponent_projection = opponent.current_projection if opponent else None
        sfx_ids = get_available_sfx_ids(entity_id, universe, repo)
        event = GameEvent(
            type="contest",
            entity_id=entity_id,
            universe=universe,
            context={
                "contest_winner": contest_winner,
                "contest_entity_opponent": opponent_id,
                "contest_projection_opponent": opponent_projection,
                "effect_die": effect_die,
                "high_stakes": high_stakes,
                "taken_out": taken_out,
            },
        )
        outcome = engine.process_event_outcome(event, sfx_ids, entity.razmerit, repo=repo)
        _emit_pending_choices(entity_id, universe, outcome.pending, outcome.structured)

        # Fire effects deferred to the contest outcome (``on_contest_win`` /
        # ``on_contest_loss``) armed at trigger time (e.g. sfx-heal's step_down).
        from transversal.services.roll_deferral import fire_armed
        outcome_event = "on_contest_win" if contest_winner == "player" else "on_contest_loss"
        fire_armed(entity_id, outcome_event, universe, event.context)

    if taken_out:
        _mark_taken_out(repo, loser_id, winner_id)


def _mark_taken_out(repo, loser_id: str, opponent_id: str) -> None:
    """Persist the scene-scoped taken-out state and fire ``on_taken_out``."""
    loser = repo.get_entity(loser_id)
    if loser is None:
        return
    loser.taken_out = True
    repo.update_entity(loser)

    # Schedule the undo: clear the status after one scene.
    from transversal.domain import Effect, EffectTiming, Timer, TimerCombine
    from transversal.services.scheduled_events import schedule_effect

    schedule_effect(
        repo, "entity", loser.id,
        Effect(timing=EffectTiming.IMMEDIATE, type="entity", action="clear_taken_out", target="self"),
        [Timer(event="scene", remaining=1)],
        TimerCombine.FIRST_TO_FIRE,
    )

    fire_state_sfx(loser_id, loser.current_universe, "on_taken_out", {
        "taken_out": True,
        "contest_entity_opponent": opponent_id,
    })


def prevent_taken_out(entity_id: str, universe: str = "", effect_die: str | None = None) -> dict:
    """Prevent a pending takeout by spending 1 razmerit (via SFX).

    Fires ``on_prevent_taken_out`` (the seeded table SFX spends 1 razmerit and
    applies a complication at ``effect_die``), then clears the taken-out state.
    Server-enforced: returns ``{"prevented": False}`` when the entity can't
    afford it or isn't taken out.
    """
    from transversal.main import _get_repo

    repo = _get_repo()
    entity = repo.get_entity(entity_id)
    if entity is None or entity.razmerit < 1:
        return {"prevented": False, "reason": "insufficient razmerit"}
    if not entity.taken_out:
        return {"prevented": False, "reason": "not taken out"}

    fire_state_sfx(entity_id, universe or entity.current_universe, "on_prevent_taken_out", {
        "prevented": True,
        "effect_die": effect_die,
    })

    entity = repo.get_entity(entity_id)  # re-fetch (razmerit changed)
    if entity is not None:
        entity.taken_out = False
        repo.update_entity(entity)
    return {"prevented": True}

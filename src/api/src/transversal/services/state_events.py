"""Route state-change events through the effects engine for automatic SFX.

Unlike roll/contest firing (which happens in the endpoint layer), state changes
can happen in many services (entity moves, trait gains, relationship creation).
This module centralises that: call :func:`fire_state_sfx` at the point a state
change is persisted, and matching condition-gated SFX will fire immediately.
"""

from __future__ import annotations

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
        event = GameEvent(
            type=event_type,
            entity_id=entity_id,
            universe=universe,
            context=context or {},
        )
        outcome = engine.process_event_outcome(event, sfx_ids, entity.razmerit, repo=repo)
        _emit_pending_choices(entity_id, universe, outcome.pending)
    finally:
        _firing.discard(key)


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
        sfx_ids = get_available_sfx_ids(entity_id, universe, repo)
        event = GameEvent(
            type="contest",
            entity_id=entity_id,
            universe=universe,
            context={
                "contest_winner": contest_winner,
                "opponent_id": opponent_id,
                "effect_die": effect_die,
                "high_stakes": high_stakes,
                "taken_out": taken_out,
            },
        )
        outcome = engine.process_event_outcome(event, sfx_ids, entity.razmerit, repo=repo)
        _emit_pending_choices(entity_id, universe, outcome.pending)

    if taken_out:
        _mark_taken_out(repo, loser_id, winner_id)


def _mark_taken_out(repo, loser_id: str, opponent_id: str) -> None:
    """Persist the scene-scoped taken-out state and fire ``on_taken_out``."""
    loser = repo.get_entity(loser_id)
    if loser is None:
        return
    loser.taken_out = True
    repo.update_entity(loser)
    fire_state_sfx(loser_id, loser.current_universe, "on_taken_out", {
        "taken_out": True,
        "opponent_id": opponent_id,
    })


def prevent_taken_out(entity_id: str, universe: str = "") -> dict:
    """Prevent a pending takeout by spending 1 razmerit (via SFX).

    Fires ``on_prevent_taken_out`` (the seeded table SFX spends 1 razmerit),
    then clears the taken-out state. Server-enforced: returns
    ``{"prevented": False}`` when the entity can't afford it or isn't taken out.
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
        "opponent_id": "",
    })

    entity = repo.get_entity(entity_id)  # re-fetch (razmerit changed)
    if entity is not None:
        entity.taken_out = False
        repo.update_entity(entity)
    return {"prevented": True}

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

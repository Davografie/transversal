"""Auto-fire SFX after a roll or contest resolves.

The dice resolver stays stateless; these functions run *after* resolution and
drive the effects engine using each entity's current SFX ownership + razmerit.

Automatic SFX apply immediately (synchronously), before any consequence menu
or next phase appears. Immediate effects with a ``{choose_*}`` target are not
applied blindly — they are emitted as a ``sfx_choice_required`` SSE event so the
frontend can prompt the user and re-apply once resolved.
"""

from __future__ import annotations

from transversal.domain import ContestResult, RollResult
from transversal.services import effects_applier
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
    contest_to_events,
)
from transversal.services.sfx_owner import get_available_sfx_ids


def _entity_sfx_context(repo, entity_id: str, universe: str) -> tuple[list[str], int]:
    """Return (available_sfx_ids, razmerit_balance) for an entity."""
    entity = repo.get_entity(entity_id)
    if entity is None:
        return [], 0
    return get_available_sfx_ids(entity_id, universe, repo), entity.razmerit


def _emit_pending_choices(entity_id: str, universe: str, effects: list) -> None:
    """Broadcast a ``sfx_choice_required`` SSE event for unresolved effects."""
    if not effects:
        return

    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    choices = [
        {
            "kind": effects_applier.choose_kind(p.effect.target),
            "scope": p.effect.target_scope,
            "sfx_name": p.sfx_name,
            "sfx_description": p.sfx_description,
            "effect": p.effect.model_dump(),
        }
        for p in effects
    ]
    for session in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="sfx_choice_required",
            session_id=session.id,
            data={
                "entity_id": entity_id,
                "universe": universe,
                "choices": choices,
            },
        ))


def fire_roll_sfx(
    engine: EffectsEngine,
    repo,
    entity_id: str,
    universe: str,
    roll_result: RollResult,
) -> list:
    """Fire automatic SFX for a single test roll. Returns applied effects."""
    sfx_ids, razmerit = _entity_sfx_context(repo, entity_id, universe)
    event = GameEvent(
        type="on_roll",
        entity_id=entity_id,
        universe=universe,
        roll_result=roll_result,
    )
    outcome = engine.process_event_outcome(event, sfx_ids, razmerit, repo=repo)
    _emit_pending_choices(entity_id, universe, outcome.pending)
    return outcome.applied


def fire_contest_sfx_auto(
    engine: EffectsEngine,
    repo,
    result: ContestResult,
    challenger_id: str,
    defendant_id: str,
    universe: str,
) -> list:
    """Fire automatic SFX for both sides of a contest. Returns applied effects.

    ``challenger_id`` is the initiator — the ``PLAYER`` side in ContestWinner
    terms (ties favor the initiator).
    """
    challenger_sfx, challenger_raz = _entity_sfx_context(repo, challenger_id, universe)
    defendant_sfx, defendant_raz = _entity_sfx_context(repo, defendant_id, universe)

    applied: list = []
    pending_by_entity: dict[str, list] = {}

    for event in contest_to_events(result, challenger_id, defendant_id, universe):
        if event.entity_id == challenger_id:
            sfx_ids, raz = challenger_sfx, challenger_raz
        else:
            sfx_ids, raz = defendant_sfx, defendant_raz

        outcome = engine.process_event_outcome(event, sfx_ids, raz, repo=repo)
        applied.extend(outcome.applied)
        if outcome.pending:
            pending_by_entity.setdefault(event.entity_id, []).extend(outcome.pending)

    for eid, effects in pending_by_entity.items():
        _emit_pending_choices(eid, universe, effects)

    return applied

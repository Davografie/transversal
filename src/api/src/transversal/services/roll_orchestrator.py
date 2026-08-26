"""Auto-fire SFX after a roll or contest resolves.

The dice resolver stays stateless; these functions run *after* resolution and
drive the effects engine using each entity's current SFX ownership + razmerit.

Automatic SFX apply immediately (synchronously), before any consequence menu
or next phase appears. Immediate effects with a ``{choose_*}`` target are not
applied blindly — they are emitted as a ``sfx_choice_required`` SSE event so the
frontend can prompt the user and re-apply once resolved.
"""

from __future__ import annotations

from transversal.domain import RollResult
from transversal.services import effects_applier
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
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

    choices = []
    for p in effects:
        found = effects_applier.find_choose_placeholder(p.effect)
        kind, field, scope = (
            found if found else (effects_applier.choose_kind(p.effect.target), "target", p.effect.target_scope)
        )
        choices.append({
            "kind": kind,
            "field": field,
            "scope": scope,
            "filter": p.effect.target_filter or None,
            "sfx_name": p.sfx_name,
            "sfx_description": p.sfx_description,
            "effect": p.effect.model_dump(),
        })
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


def fire_result_sfx(
    entity_id: str,
    universe: str,
    rolls: list[dict],
    effect_die: str | None = None,
    total: int | None = None,
) -> list:
    """Fire automatic ``on_result`` SFX with the finalized roll state in context.

    ``rolls`` is the enriched pool dice (each carrying ``result``/``role``/
    ``tier``/``effect_die``/``ts_id``) so conditions and effects can inspect
    which dice were rolled and whether any were left unchosen (``role`` is
    None). ``effect_die``/``total`` are the committed scalars exposed as the
    trigger's ``{effect_die}``/``{total}`` variables.
    """
    from transversal.main import _get_engine, _get_repo
    from transversal.services.effects_engine import GameEvent

    repo = _get_repo()
    sfx_ids, razmerit = _entity_sfx_context(repo, entity_id, universe)
    event = GameEvent(
        type="on_result",
        entity_id=entity_id,
        universe=universe,
        context={
            "effect_die": effect_die,
            "total": total,
            "rolls": rolls,
        },
    )
    outcome = _get_engine().process_event_outcome(event, sfx_ids, razmerit, repo=repo)
    _emit_pending_choices(entity_id, universe, outcome.pending)
    return outcome.applied

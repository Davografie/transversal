"""Auto-fire SFX after a roll or contest resolves.

The dice resolver stays stateless; these functions run *after* resolution and
drive the effects engine using each entity's current SFX ownership + razmerit.

Automatic SFX apply immediately (synchronously), before any consequence menu
or next phase appears.
"""

from __future__ import annotations

from transversal.domain import ContestResult, RollResult
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
    fire_contest_sfx as _effects_fire_contest_sfx,
)
from transversal.services.sfx_owner import get_available_sfx_ids


def _entity_sfx_context(repo, entity_id: str, universe: str) -> tuple[list[str], int]:
    """Return (available_sfx_ids, razmerit_balance) for an entity."""
    entity = repo.get_entity(entity_id)
    if entity is None:
        return [], 0
    return get_available_sfx_ids(entity_id, universe, repo), entity.razmerit


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
    return engine.process_event(event, sfx_ids, razmerit)


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

    return _effects_fire_contest_sfx(
        engine,
        result,
        player_id=challenger_id,
        opponent_id=defendant_id,
        universe=universe,
        player_sfx_ids=challenger_sfx,
        opponent_sfx_ids=defendant_sfx,
        player_razmerit=challenger_raz,
        opponent_razmerit=defendant_raz,
    )

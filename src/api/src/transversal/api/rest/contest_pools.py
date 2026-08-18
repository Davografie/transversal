"""REST endpoints for per-location contest assembly and resolution.

Dice pool CRUD lives in :mod:`transversal.api.rest.scene_state`.  This
router owns the contest-specific actions: designating an opponent and
resolving.  The tracker holds only contest metadata; dice are read from
the shared scene store.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.domain import ContestResult
from transversal.services.contest_tracker import (
    broadcast_pool_change,
    get_contest_tracker,
)
from transversal.services.scene_state import get_scene_store

router = APIRouter(prefix="/api/v1/locations", tags=["contest-pools"])


class SetOppositionRequest(BaseModel):
    opponent_id: str
    universe: str = "earth"


# ── Endpoints ─────────────────────────────────────────

@router.post("/{location_id}/pools/{entity_id}/set-opposition")
async def set_opposition(location_id: str, entity_id: str, body: SetOppositionRequest):
    """Designate an opponent for an entity's contest at this location."""
    ct = get_contest_tracker()
    ct.set_opposition(location_id, entity_id, body.opponent_id, body.universe)
    broadcast_pool_change(location_id, entity_id)
    return {
        "entity_id": entity_id,
        "location_id": location_id,
        "opposition_entity_id": body.opponent_id,
    }


@router.post("/{location_id}/pools/{entity_id}/clear")
async def clear_pool(location_id: str, entity_id: str):
    """Reset an entity's contest + pool at a location (end of beat)."""
    ct = get_contest_tracker()
    get_scene_store().clear_pool(location_id, entity_id)
    ct.clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    return {"status": "cleared"}


@router.post("/{location_id}/pools/{entity_id}/resolve", response_model=ContestResult)
async def resolve_contest(location_id: str, entity_id: str):
    """Resolve a contest between an entity and its designated opponent.

    Returns the ContestResult or 409 if pools aren't ready.
    """
    ct = get_contest_tracker()
    scene = get_scene_store()
    if not ct.can_resolve(location_id, entity_id, scene):
        raise HTTPException(status_code=409, detail="Both sides must have dice assembled")

    result = ct.resolve(location_id, entity_id, scene)
    if result is None:
        raise HTTPException(status_code=409, detail="Could not resolve contest")

    # Fire automatic SFX for both sides (roll/outcome triggers + contest win/loss).
    challenger, defendant = ct.get_contestants(location_id, entity_id)
    if challenger is not None and defendant is not None:
        from transversal.main import _get_engine, _get_repo
        from transversal.services.roll_orchestrator import fire_contest_sfx_auto

        fire_contest_sfx_auto(
            _get_engine(), _get_repo(), result,
            challenger.entity_id, defendant.entity_id, challenger.universe,
        )

    # Broadcast the resolution
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="roll_result",
            session_id=s.id,
            data={
                "entity_id": entity_id,
                "location_id": location_id,
                "winner": result.winner.value,
                "pipeline": result.pipeline,
                "pushed": result.pushed,
            },
        ))

    return result

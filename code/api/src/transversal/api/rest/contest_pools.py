"""REST endpoints for per-location contest pool assembly.

Players add/remove dice from their pool at a location.  Other players
see pool dice via SSE (broadcast after every mutation) and can query
all pools at a location via GET.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.domain import DieType
from transversal.services.contest_tracker import (
    broadcast_pool_change,
    get_contest_tracker,
)

router = APIRouter(prefix="/api/v1/locations", tags=["contest-pools"])


# ── Request models ────────────────────────────────────

class AddDieRequest(BaseModel):
    die: str  # "d4", "d6", "d8", "d10", "d12"
    source: str  # trait name or label
    universe: str = "earth"


class RemoveDieRequest(BaseModel):
    index: int


class SetOppositionRequest(BaseModel):
    opponent_id: str
    universe: str = "earth"


# ── Response helpers ──────────────────────────────────

def _pool_response(pa) -> dict:
    if pa is None:
        return {"dice": []}
    return {
        "entity_id": pa.entity_id,
        "location_id": pa.location_id,
        "universe": pa.universe,
        "dice": [{"die": d.value, "source": s, "index": i}
                 for i, (d, s) in enumerate(pa.dice)],
        "opposition_entity_id": pa.opposition_entity_id,
        "pushed_this_beat": pa.pushed_this_beat,
        "razmerit_spent": pa.razmerit_spent,
    }


# ── Endpoints ─────────────────────────────────────────

@router.get("/{location_id}/pools")
async def get_pools(location_id: str):
    """Return all pool assemblies at a location.

    Used by clients entering a location to see existing dice pools.
    """
    ct = get_contest_tracker()
    pools = ct.get_pools_at(location_id)
    result: dict[str, dict] = {}
    for eid, pa in pools.items():
        result[eid] = _pool_response(pa)
    return {"location_id": location_id, "pools": result}


@router.get("/{location_id}/pools/{entity_id}")
async def get_pool(location_id: str, entity_id: str):
    """Return one entity's pool assembly at a location."""
    ct = get_contest_tracker()
    pa = ct.get(location_id, entity_id)
    return _pool_response(pa)


@router.post("/{location_id}/pools/{entity_id}/add-die")
async def add_die(location_id: str, entity_id: str, body: AddDieRequest):
    """Add a die to an entity's pool at a location."""
    try:
        die = DieType(body.die)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid die type: {body.die}")

    ct = get_contest_tracker()
    pa = ct.add_die(location_id, entity_id, die, body.source, body.universe)
    broadcast_pool_change(location_id, entity_id)
    return _pool_response(pa)


@router.post("/{location_id}/pools/{entity_id}/remove-die")
async def remove_die(location_id: str, entity_id: str, body: RemoveDieRequest):
    """Remove a die from an entity's pool by index."""
    ct = get_contest_tracker()
    try:
        pa = ct.remove_die(location_id, entity_id, body.index)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    broadcast_pool_change(location_id, entity_id)
    return _pool_response(pa)


@router.post("/{location_id}/pools/{entity_id}/set-opposition")
async def set_opposition(location_id: str, entity_id: str, body: SetOppositionRequest):
    """Designate an opponent for an entity's pool at this location."""
    ct = get_contest_tracker()
    pa = ct.set_opposition(location_id, entity_id, body.opponent_id, body.universe)
    broadcast_pool_change(location_id, entity_id)
    return _pool_response(pa)


@router.post("/{location_id}/pools/{entity_id}/clear")
async def clear_pool(location_id: str, entity_id: str):
    """Reset an entity's pool at a location (end of beat)."""
    ct = get_contest_tracker()
    ct.clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id)
    return {"status": "cleared"}


@router.post("/{location_id}/pools/{entity_id}/resolve")
async def resolve_contest(location_id: str, entity_id: str):
    """Resolve a contest between an entity and its designated opponent.

    Returns the ContestResult or 409 if pools aren't ready.
    """
    ct = get_contest_tracker()
    if not ct.can_resolve(location_id, entity_id):
        raise HTTPException(status_code=409, detail="Both sides must have dice assembled")

    result = ct.resolve(location_id, entity_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Could not resolve contest")

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

    return {"winner": result.winner.value, "pipeline": result.pipeline,
            "pushed": result.pushed}

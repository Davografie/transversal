"""REST endpoints for in-memory scene state (dice pools + difficulty).

Pools are keyed by (location, entity) — one pool per character.  Mutations
broadcast ``pool_updated`` / ``difficulty_set`` server-side so other
clients see authoritative state without having to echo events themselves.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.services.scene_state import get_scene_store
from transversal.services.contest_tracker import broadcast_pool_change
from transversal.services.session_manager import session_manager

logger = logging.getLogger("transversal.scene_state")

router = APIRouter(prefix="/api/v1/locations", tags=["scene-state"])


class PoolDieIn(BaseModel):
    die: str  # "d4".."d12"
    source_kind: str = "manual"  # "trait" | "difficulty" | "manual" | extensible
    source_id: str = ""
    label: str = ""
    ts_id: Optional[str] = None


class SavePoolRequest(BaseModel):
    dice: list[PoolDieIn] = Field(default_factory=list)


class DifficultyRequest(BaseModel):
    difficulty: int


@router.get("/{location_id}/pools")
async def get_pools(location_id: str):
    """Return every entity's saved dice pool at a location."""
    store = get_scene_store()
    pools = store.get_pools_at(location_id)
    logger.info(f"[init] get_pools loc={location_id} count={len(pools)}")
    return {"location_id": location_id, "pools": pools}


@router.get("/{location_id}/pools/{entity_id}")
async def get_pool(location_id: str, entity_id: str):
    """Return one entity's saved dice pool (empty if none)."""
    dice = get_scene_store().get_pool(location_id, entity_id)
    logger.info(f"[init] get_pool loc={location_id} entity={entity_id} dice={len(dice)}")
    return {"dice": dice}


@router.put("/{location_id}/pools/{entity_id}")
async def save_pool(location_id: str, entity_id: str, req: SavePoolRequest):
    """Persist (in-memory) an entity's assembled dice pool for a location."""
    dice = [d.model_dump() for d in req.dice]
    get_scene_store().save_pool(location_id, entity_id, dice)
    logger.info(f"[init] save_pool loc={location_id} entity={entity_id} dice={len(dice)}")
    broadcast_pool_change(location_id, entity_id, dice=dice, phase="adding")
    return {"saved": True}


@router.delete("/{location_id}/pools/{entity_id}")
async def clear_pool(location_id: str, entity_id: str):
    get_scene_store().clear_pool(location_id, entity_id)
    broadcast_pool_change(location_id, entity_id, dice=[], phase="adding")
    return {"cleared": True}


@router.put("/{location_id}/difficulty")
async def set_difficulty(location_id: str, req: DifficultyRequest):
    """Persist (in-memory) the current test difficulty for a location."""
    get_scene_store().set_difficulty(location_id, req.difficulty)

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="difficulty_set",
            session_id=s.id,
            data={"difficulty": req.difficulty, "location_id": location_id},
        ))
    return {"saved": True}


@router.get("/{location_id}/difficulty")
async def get_difficulty(location_id: str):
    """Return the current test difficulty for a location (null if unset)."""
    difficulty = get_scene_store().get_difficulty(location_id)
    logger.info(f"[init] get_difficulty loc={location_id} difficulty={difficulty}")
    return {"difficulty": difficulty}


@router.post("/{location_id}/next-beat")
async def next_beat(location_id: str):
    """End the beat: clear every pool at the location and broadcast beat_end."""
    store = get_scene_store()
    cleared = store.list_entities(location_id)
    store.clear_pools(location_id)

    from transversal.services.contest_tracker import get_contest_tracker
    get_contest_tracker().clear_location(location_id)

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="beat_end",
            session_id=s.id,
            data={"location_id": location_id, "cleared_entities": cleared},
        ))
    return {"cleared": len(cleared)}

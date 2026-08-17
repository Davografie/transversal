"""REST endpoints for in-memory scene state (dice pools + difficulty)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from transversal.services.scene_state import get_scene_store

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


@router.put("/{location_id}/players/{player_id}/pool")
async def save_pool(location_id: str, player_id: str, req: SavePoolRequest):
    """Persist (in-memory) a player's assembled dice pool for a location."""
    dice = [d.model_dump() for d in req.dice]
    get_scene_store().save_pool(location_id, player_id, dice)
    return {"saved": True}


@router.get("/{location_id}/players/{player_id}/pool")
async def get_pool(location_id: str, player_id: str):
    """Return a player's last-saved dice pool for a location (empty if none)."""
    return {"dice": get_scene_store().get_pool(location_id, player_id)}


@router.delete("/{location_id}/players/{player_id}/pool")
async def clear_pool(location_id: str, player_id: str):
    get_scene_store().clear_pool(location_id, player_id)
    return {"cleared": True}


@router.put("/{location_id}/difficulty")
async def set_difficulty(location_id: str, req: DifficultyRequest):
    """Persist (in-memory) the current test difficulty for a location."""
    get_scene_store().set_difficulty(location_id, req.difficulty)
    return {"saved": True}


@router.get("/{location_id}/difficulty")
async def get_difficulty(location_id: str):
    """Return the current test difficulty for a location (null if unset)."""
    return {"difficulty": get_scene_store().get_difficulty(location_id)}

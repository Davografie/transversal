"""REST endpoints for player management."""

from fastapi import APIRouter
from pydantic import BaseModel

from transversal.services.player_manager import player_manager

router = APIRouter(prefix="/api/v1/players", tags=["players"])


@router.post("")
async def find_or_create_player(req: dict | None = None) -> dict:
    """Find an existing player by name, or create a new one."""
    name = (req or {}).get("name", "").strip()
    if name:
        existing = player_manager.find_by_name(name)
        if existing:
            return {"id": existing.id, "name": existing.name, "entity_ids": sorted(existing.entity_ids), "found": True}
    p = player_manager.create(name=name)
    return {"id": p.id, "name": p.name, "entity_ids": sorted(p.entity_ids), "found": False}


@router.get("/{player_id}")
async def get_player(player_id: str) -> dict | None:
    p = player_manager.get(player_id)
    return {"id": p.id, "name": p.name, "entity_ids": sorted(p.entity_ids)} if p else None


@router.post("/{player_id}/claim/{entity_id}")
async def claim_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.claim_entity(player_id, entity_id)
    return {"claimed": ok}


@router.post("/{player_id}/release/{entity_id}")
async def release_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.release_entity(player_id, entity_id)
    return {"released": ok}

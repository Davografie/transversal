"""REST endpoints for player management."""

from fastapi import APIRouter
from pydantic import BaseModel

from transversal.services.player_manager import player_manager

router = APIRouter(prefix="/api/v1/players", tags=["players"])


def _player_dict(p):
    return {"id": p.id, "name": p.name, "entity_ids": sorted(p.entity_ids), "role": p.role}


@router.post("")
async def find_or_create_player(req: dict | None = None) -> dict:
    """Find an existing player by name, or create a new one."""
    name = (req or {}).get("name", "").strip()
    if name:
        existing = player_manager.find_by_name(name)
        if existing:
            return {**_player_dict(existing), "found": True}
    p = player_manager.create(name=name)
    return {**_player_dict(p), "found": False}


@router.get("")
async def list_players(q: str = "") -> list[dict]:
    """List all players, optionally filtered by partial name match."""
    if q:
        results = player_manager.search(q)
    else:
        results = player_manager.list_all()
    return [_player_dict(p) for p in results]


@router.get("/{player_id}")
async def get_player(player_id: str) -> dict | None:
    p = player_manager.get(player_id)
    return _player_dict(p) if p else None


@router.patch("/{player_id}/role")
async def set_player_role(player_id: str, req: dict | None = None) -> dict:
    """Set a player's role (player or architect)."""
    role = (req or {}).get("role", "player")
    ok = player_manager.set_role(player_id, role)
    return {"player_id": player_id, "role": role, "updated": ok}


@router.post("/{player_id}/claim/{entity_id}")
async def claim_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.claim_entity(player_id, entity_id)
    return {"claimed": ok}


@router.post("/{player_id}/release/{entity_id}")
async def release_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.release_entity(player_id, entity_id)
    return {"released": ok}

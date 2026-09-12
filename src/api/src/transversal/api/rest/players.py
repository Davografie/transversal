"""REST endpoints for player management."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from transversal.services.player_manager import player_manager

logger = logging.getLogger("transversal.players")

router = APIRouter(prefix="/api/v1/players", tags=["players"])


def _player_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "entity_ids": sorted(p.entity_ids),
        "role": p.role,
        "last_spotlight_at": p.last_spotlight_at,
        "last_main_entity_id": p.last_main_entity_id,
    }


@router.post("")
async def find_or_create_player(req: dict | None = None) -> dict:
    """Find an existing player by name, or create a new one."""
    name = (req or {}).get("name", "").strip()
    if name:
        existing = player_manager.find_by_name(name)
        if existing:
            logger.info(f"[init] find_or_create_player name={name} -> found id={existing.id}")
            return {**_player_dict(existing), "found": True}
    p = player_manager.create(name=name)
    logger.info(f"[init] find_or_create_player name={name} -> created id={p.id}")
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
    logger.info(f"[init] get_player id={player_id} found={p is not None}")
    return _player_dict(p) if p else None


@router.patch("/{player_id}/role")
async def set_player_role(player_id: str, req: dict | None = None) -> dict:
    """Set a player's role (player or architect)."""
    role = (req or {}).get("role", "player")
    ok = player_manager.set_role(player_id, role)
    logger.info(f"[init] set_player_role id={player_id} role={role} updated={ok}")
    return {"player_id": player_id, "role": role, "updated": ok}


@router.post("/{player_id}/claim/{entity_id}")
async def claim_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.claim_entity(player_id, entity_id)
    logger.info(f"[init] claim_entity player={player_id} entity={entity_id} claimed={ok}")
    return {"claimed": ok}


@router.post("/{player_id}/release/{entity_id}")
async def release_entity(player_id: str, entity_id: str) -> dict:
    ok = player_manager.release_entity(player_id, entity_id)
    return {"released": ok}


@router.post("/{player_id}/main/{entity_id}")
async def set_agency_main(player_id: str, entity_id: str, req: dict | None = None) -> dict:
    """Flag (or un-flag) an owned entity as one of the player's mains."""
    main = bool((req or {}).get("main", True))
    ok = player_manager.set_agency_main(player_id, entity_id, main)
    return {"player_id": player_id, "entity_id": entity_id, "main": main, "updated": ok}


@router.post("/{player_id}/spotlight")
async def set_spotlight(player_id: str, req: dict | None = None) -> dict:
    """Stamp the player's spotlight recency (actor-keyed)."""
    req = req or {}
    ok = player_manager.set_spotlight(player_id, req.get("last_main_entity_id"), req.get("timestamp"))
    return {"player_id": player_id, "updated": ok}


@router.post("/{player_id}/control/{entity_id}")
async def record_control(player_id: str, entity_id: str, stamp: bool = True) -> dict:
    """A player took control of an entity (the character-switch signal).

    Stamps spotlight only when the entity is one of the player's mains, and
    always broadcasts the main-active state via SSE. ``stamp=false`` records the
    body only — the GM taking a GMC: presence (which sizes the map dots) with no
    spotlight stamp and no main active/inactive flip.
    """
    is_main = player_manager.record_control(player_id, entity_id, stamp=stamp)
    return {"player_id": player_id, "entity_id": entity_id, "main": is_main}


@router.delete("/{player_id}/control")
async def clear_control(player_id: str) -> dict:
    """A player stopped driving anything (the GM going to free-roam)."""
    player_manager.clear_control(player_id)
    return {"player_id": player_id, "entity_id": None}

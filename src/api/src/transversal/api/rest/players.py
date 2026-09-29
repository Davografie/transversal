"""REST endpoints for player management.

SEC-3: the acting player is taken from the **session**, never from the URL. Every
``/{player_id}/…`` route asserts that the session has taken *that* player, and the
one route that changes permissions requires an architect.

``POST /players`` is gone. It found-or-created a player **by name**, which is how
typing someone else's name made you them; creating a player is now
``POST /api/v1/auth/claim`` and taking an existing one is ``POST /api/v1/auth/take``.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from transversal.api.auth import require_architect, require_player, require_session
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


async def _self(request: Request, player_id: str):
    """The acting player, asserting it is the one named in the path."""
    me = await require_player(request)
    if me.id != player_id:
        # Not "forbidden" — we simply do not act as anyone but ourselves.
        raise HTTPException(status_code=403, detail="that is not your player")
    return me


@router.get("")
async def list_players(request: Request, q: str = "") -> list[dict]:
    """List players in this campaign, optionally filtered by partial name."""
    await require_session(request)
    results = player_manager.search(q) if q else player_manager.list_all()
    return [_player_dict(p) for p in results]


@router.get("/{player_id}")
async def get_player(player_id: str, request: Request) -> dict | None:
    await require_session(request)
    p = player_manager.get(player_id)
    return _player_dict(p) if p else None


@router.patch("/{player_id}/role")
async def set_player_role(player_id: str, request: Request, req: dict | None = None) -> dict:
    """Set a player's role. Architect-only: the escape SEC-3 was about."""
    await require_architect(request)
    role = (req or {}).get("role", "player")
    ok = player_manager.set_role(player_id, role)
    logger.info("[authz] set_player_role id=%s role=%s updated=%s", player_id, role, ok)
    return {"player_id": player_id, "role": role, "updated": ok}


@router.post("/{player_id}/revoke")
async def revoke_player(player_id: str, request: Request) -> dict:
    """End every session that names this player (SEC-3).

    An epoch bump, not a deletion: the player's characters are entities owned
    through ``agency`` edges, so removing the record would orphan them. Architect
    only, and an architect cannot revoke themselves out of the last seat.
    """
    me = await require_architect(request)
    target = player_manager.get(player_id)
    if not target:
        raise HTTPException(status_code=404, detail="no such player")
    if target.role == "architect":
        architects = [p for p in player_manager.list_all() if p.role == "architect"]
        if len(architects) <= 1:
            raise HTTPException(
                status_code=409, detail="the last architect cannot be revoked"
            )
    epoch = player_manager.revoke_sessions(player_id)
    logger.warning("[authz] %s revoked sessions for %s (epoch %s)", me.id, player_id, epoch)
    return {"player_id": player_id, "epoch": epoch}


@router.post("/{player_id}/claim/{entity_id}")
async def claim_entity(player_id: str, entity_id: str, request: Request) -> dict:
    await _self(request, player_id)
    ok = player_manager.claim_entity(player_id, entity_id)
    logger.info("[init] claim_entity player=%s entity=%s claimed=%s", player_id, entity_id, ok)
    return {"claimed": ok}


@router.post("/{player_id}/release/{entity_id}")
async def release_entity(player_id: str, entity_id: str, request: Request) -> dict:
    await _self(request, player_id)
    ok = player_manager.release_entity(player_id, entity_id)
    return {"released": ok}


@router.post("/{player_id}/main/{entity_id}")
async def set_agency_main(
    player_id: str, entity_id: str, request: Request, req: dict | None = None
) -> dict:
    """Flag (or un-flag) an owned entity as one of the player's mains."""
    await _self(request, player_id)
    main = bool((req or {}).get("main", True))
    ok = player_manager.set_agency_main(player_id, entity_id, main)
    return {"player_id": player_id, "entity_id": entity_id, "main": main, "updated": ok}


@router.post("/{player_id}/spotlight")
async def set_spotlight(player_id: str, request: Request, req: dict | None = None) -> dict:
    """Stamp the player's spotlight recency (actor-keyed)."""
    await _self(request, player_id)
    req = req or {}
    ok = player_manager.set_spotlight(
        player_id, req.get("last_main_entity_id"), req.get("timestamp")
    )
    return {"player_id": player_id, "updated": ok}


@router.post("/{player_id}/control/{entity_id}")
async def record_control(
    player_id: str, entity_id: str, request: Request, stamp: bool = True
) -> dict:
    """A player took control of an entity (the character-switch signal).

    Stamps spotlight only when the entity is one of the player's mains, and
    always broadcasts the main-active state via SSE. ``stamp=false`` records the
    body only — the GM taking a GMC: presence (which sizes the map dots) with no
    spotlight stamp and no main active/inactive flip.
    """
    await _self(request, player_id)
    is_main = player_manager.record_control(player_id, entity_id, stamp=stamp)
    return {"player_id": player_id, "entity_id": entity_id, "main": is_main}


@router.delete("/{player_id}/control")
async def clear_control(player_id: str, request: Request) -> dict:
    """A player stopped driving anything (the GM going to free-roam)."""
    await _self(request, player_id)
    player_manager.clear_control(player_id)
    return {"player_id": player_id, "entity_id": None}

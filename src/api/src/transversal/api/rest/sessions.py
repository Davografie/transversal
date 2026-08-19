"""REST endpoints for session management."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from transversal.services.session_manager import Session, session_manager

logger = logging.getLogger("transversal.sessions")

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    name: str = "New Session"
    gm_id: str = ""
    universe: str = "earth"


class JoinRequest(BaseModel):
    entity_id: str
    player_id: str = ""


@router.post("")
async def create_session(req: CreateSessionRequest) -> dict:
    logger.info(f"[init] create_session name={req.name} universe={req.universe}")
    s = session_manager.create(name=req.name, gm_id=req.gm_id, universe=req.universe)
    logger.info(f"[init] create_session -> id={s.id}")
    return _session_dict(s)


@router.get("")
async def list_sessions() -> list[dict]:
    sessions = [_session_dict(s) for s in session_manager.list_active()]
    logger.info(f"[init] list_sessions -> count={len(sessions)}")
    return sessions


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict | None:
    s = session_manager.get(session_id)
    logger.info(f"[init] get_session id={session_id} found={s is not None}")
    return _session_dict(s) if s else None


@router.post("/{session_id}/join")
async def join_session(session_id: str, req: JoinRequest) -> dict | None:
    logger.info(f"[init] join_session id={session_id} entity={req.entity_id} player={req.player_id}")
    s = session_manager.join(session_id, req.entity_id, req.player_id)
    logger.info(f"[init] join_session -> found={s is not None}")
    return _session_dict(s) if s else None


@router.post("/{session_id}/leave")
async def leave_session(session_id: str, req: JoinRequest) -> dict | None:
    s = session_manager.leave(session_id, req.entity_id, req.player_id)
    return _session_dict(s) if s else None


def _session_dict(s: Session) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "gm_id": s.gm_id,
        "universe": s.universe,
        "entity_ids": sorted(s.entity_ids),
        "player_entities": dict(s.player_entities),
        "active": s.active,
    }

"""Admission tokens — open a window, see the open ones, close them (SEC-3).

**Any admitted member may open one.** That is the owner's decision ("any member
may invite"), and with players otherwise unable to add anyone it is the only way
a table grows. What the owner keeps is *sight and the off switch*: the open list,
closing one, and closing all — because the token is a bearer credential and its
lifetime is the only bound on a leaked link.

Closing is deliberately not restricted to whoever opened it. Closing only ever
*reduces* access, so a member closing another's window is a nuisance at worst;
closing everything is an architect act.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from transversal.api.auth import require_owner, require_player
from transversal.db.repository import EntityRepository
from transversal.services import join_tokens

logger = logging.getLogger("transversal.access")

router = APIRouter(prefix="/api/v1/access", tags=["access"])


def _repo() -> EntityRepository:
    return EntityRepository()


def _summary(record: dict) -> dict:
    return {
        "id": record.get("_key"),
        "created_by": record.get("created_by", ""),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
    }


@router.post("/tokens")
async def open_token(request: Request, req: dict | None = None) -> dict:
    """Mint an admission token. Any member; ~30 minutes by default."""
    me = await require_player(request)
    # `0` is a value, not an absence — do not let a default swallow it.
    raw_ttl = (req or {}).get("ttl_seconds")
    try:
        ttl = join_tokens.DEFAULT_TTL_SECONDS if raw_ttl is None else int(raw_ttl)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ttl_seconds must be a number")
    if ttl <= 0:
        raise HTTPException(status_code=400, detail="ttl_seconds must be positive")

    token, record = join_tokens.open_token(_repo(), created_by=me.id, ttl_seconds=ttl)
    logger.info("[authz] %s opened an admission token %s (%ss)", me.id, record.get("_key"), ttl)
    # The token is returned exactly once, to whoever opened it.
    return {**_summary(record), "token": token, "join_url": f"/enter?s={token}"}


@router.get("/tokens")
async def list_tokens(request: Request) -> list[dict]:
    """The open windows. This is the owner's visibility into who could still join."""
    await require_player(request)
    return [_summary(r) for r in _repo().list_join_tokens(open_only=True)]


@router.post("/tokens/{token_id}/close")
async def close_token(token_id: str, request: Request) -> dict:
    me = await require_player(request)
    if not _repo().close_join_token(token_id, closed_by=me.id):
        # Already closed, or never existed — the same answer either way.
        raise HTTPException(status_code=404, detail="no open token with that id")
    logger.info("[authz] %s closed admission token %s", me.id, token_id)
    return {"id": token_id, "closed": True}


@router.post("/tokens/close-all")
async def close_all_tokens(request: Request) -> dict:
    """Shut every open window at once — the one-action off switch, and the owner's."""
    me = await require_owner(request)
    closed = _repo().close_all_join_tokens(closed_by=me.id)
    logger.warning("[authz] %s closed all admission tokens (%d)", me.id, closed)
    return {"closed": closed}

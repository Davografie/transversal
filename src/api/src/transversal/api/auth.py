"""Campaign access control (SEC-3).

Two credentials, deliberately different:

- a **join token** (``/enter?s=…``) admits a device to the campaign. One QR for
  the whole table, reusable within a short life, and it says nothing about who
  holds it — it is authorization, not identity.
- a **session cookie** is what the browser then carries. It names the player the
  holder has **taken**, and the epoch it was issued under. It is the only place
  the API learns who is calling; endpoints must never take the acting player from
  a URL path, which is exactly what SEC-3 was.

An admitted device *with no player* is a real, expected state — that is the roster
picker — so a session is issued with no player and re-issued once one is taken.

The old shared ``ACCESS_TOKEN`` admits nobody now. The architect's way in is
``/enter?a=<ARCHITECT_TOKEN>``, this slice's stand-in for the recovery email link:
same job (prove you are the owner), different channel, and it is the one seat that
is never takeable from the roster.

The nginx edge still asks ``/check`` whether a session is valid, so that route
keeps working; what changed is that the cookie now means something.
"""

from __future__ import annotations

import hmac
import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from transversal.api import access_tokens
from transversal.db.repository import EntityRepository
from transversal.services import join_tokens
from transversal.services.player_manager import player_manager

logger = logging.getLogger("transversal.auth")

COOKIE_NAME = "tv2_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days, sliding
#: Re-issue the cookie only once its remaining life falls below this. Refreshing
#: on literally every response would put a Set-Cookie on every API call.
REFRESH_BELOW_SECONDS = COOKIE_MAX_AGE // 3

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _repo() -> EntityRepository:
    return EntityRepository()


def _is_https(request: Request) -> bool:
    """Whether the *client* leg is TLS, honouring a trusted upstream edge.

    nginx forwards ``X-Forwarded-Proto`` from whatever terminates TLS (e.g. a
    Cloudflare Tunnel), so the cookie can be marked ``Secure`` on an HTTPS front
    door even though the final hop to the API is plain HTTP on the loopback.
    """
    proto = request.headers.get("x-forwarded-proto", "")
    if proto:
        return proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


# ── The session cookie ────────────────────────────────────────────────


def mint_session(player_id: str | None, epoch: int) -> str:
    """A session for ``player_id``, or an admitted-but-unclaimed session."""
    payload: dict = {"epoch": int(epoch)}
    if player_id:
        payload["player"] = player_id
    return access_tokens.mint(payload, COOKIE_MAX_AGE, access_tokens.AUD_SESSION)


def session_payload(value: str | None) -> dict | None:
    if not value:
        return None
    return access_tokens.verify(value, access_tokens.AUD_SESSION)


def current_session(request: Request) -> dict | None:
    return session_payload(request.cookies.get(COOKIE_NAME))


def session_is_valid(value: str | None) -> bool:
    """Used by ``/check`` — nginx's ``auth_request`` target."""
    return session_payload(value) is not None


def _set_session_cookie(
    response, request: Request, player_id: str | None, epoch: int
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        mint_session(player_id, epoch),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )


async def session_refresh_middleware(request: Request, call_next):
    """Slide an in-use session forward, but only when it is getting old."""
    response = await call_next(request)
    if response.status_code >= 400:
        return response
    payload = current_session(request)
    if not payload:
        return response
    try:
        remaining = int(payload["exp"]) - time.time()
    except (KeyError, TypeError, ValueError):
        return response
    if remaining < REFRESH_BELOW_SECONDS:
        _set_session_cookie(
            response, request, payload.get("player"), int(payload.get("epoch", 0))
        )
    return response


# ── Dependencies: identity comes from here, never from a path ─────────


async def require_session(request: Request) -> dict:
    """Any admitted device — claimed or not."""
    payload = current_session(request)
    if not payload:
        raise HTTPException(status_code=401, detail="no valid session")
    return payload


async def require_player(request: Request):
    """The player this session has taken, with its epoch still current."""
    payload = await require_session(request)
    player_id = payload.get("player")
    if not player_id:
        raise HTTPException(status_code=403, detail="no player has been taken yet")
    player = player_manager.get(player_id)
    if not player:
        raise HTTPException(status_code=401, detail="the taken player no longer exists")
    if int(player.epoch) != int(payload.get("epoch", -1)):
        # The revoke mechanism: bumping the epoch invalidates the cookie, which is
        # otherwise unrecallable.
        raise HTTPException(status_code=401, detail="this session has been revoked")
    return player


async def require_architect(request: Request):
    player = await require_player(request)
    if player.role != "architect":
        raise HTTPException(status_code=403, detail="architect only")
    return player


# ── The architect seat ────────────────────────────────────────────────


def ensure_architect():
    """The one seat never issued from the UI, so a troupe cannot lock itself out.

    Created from the environment when the campaign has no architect at all.
    """
    for player in player_manager.list_all():
        if player.role == "architect":
            return player
    name = os.getenv("ARCHITECT_NAME", "Architect")
    player = player_manager.create(name=name)
    player_manager.set_role(player.id, "architect")
    logger.warning("no architect existed; bootstrapped %s as %r", player.id, name)
    return player_manager.get(player.id)


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/enter")
async def enter(request: Request, s: str = "", a: str = ""):
    """Exchange a join token (or the architect key) for a session cookie."""
    if not access_tokens._secret_is_usable():
        logger.error("auth is not configured: SESSION_SECRET is missing or too short")
        return JSONResponse(
            {"detail": "authentication is not configured"}, status_code=503
        )

    if s:
        record = join_tokens.resolve_token(_repo(), s)
        if not record:
            # One answer for forged, expired, unknown and closed-early alike.
            return JSONResponse({"detail": "that passage is not open"}, status_code=401)
        response = RedirectResponse(url="/", status_code=302)
        _set_session_cookie(response, request, player_id=None, epoch=0)
        logger.info("admission accepted (join token %s)", record.get("_key"))
        return response

    if a:
        expected = os.getenv("ARCHITECT_TOKEN", "")
        if not expected or not hmac.compare_digest(a, expected):
            return JSONResponse({"detail": "not the architect key"}, status_code=401)
        architect = ensure_architect()
        if not architect:
            return JSONResponse(
                {"detail": "no architect seat could be established"}, status_code=503
            )
        response = RedirectResponse(url="/", status_code=302)
        _set_session_cookie(response, request, architect.id, architect.epoch)
        logger.info("architect entered as %s", architect.id)
        return response

    return JSONResponse({"detail": "a passage token is required"}, status_code=401)


@router.get("/check")
async def check(request: Request):
    """Auth subrequest target for nginx ``auth_request /_auth``."""
    if session_is_valid(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({"ok": True})
    return JSONResponse({"detail": "unauthorized"}, status_code=401)


@router.get("/session")
async def whoami(request: Request):
    """Who is calling? The frontend's first question on boot."""
    payload = current_session(request)
    if not payload:
        return JSONResponse({"admitted": False}, status_code=401)
    player_id = payload.get("player")
    if not player_id:
        return {"admitted": True, "player": None}
    player = player_manager.get(player_id)
    if not player or int(player.epoch) != int(payload.get("epoch", -1)):
        return JSONResponse({"admitted": False, "reason": "revoked"}, status_code=401)
    return {
        "admitted": True,
        "player": {"id": player.id, "name": player.name, "role": player.role},
    }


@router.get("/roster")
async def roster(request: Request):
    """Who may be taken. Architect accounts are the one thing that may not be."""
    await require_session(request)
    return [
        {"id": p.id, "name": p.name}
        for p in player_manager.list_all()
        if p.role != "architect"
    ]


@router.post("/take/{player_id}")
async def take(player_id: str, request: Request):
    """Take an existing player — how a returning player resumes on a new device."""
    await require_session(request)
    player = player_manager.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="no such player")
    if player.role == "architect":
        raise HTTPException(
            status_code=403, detail="an architect account cannot be taken"
        )
    response = JSONResponse(
        {"player": {"id": player.id, "name": player.name, "role": player.role}}
    )
    _set_session_cookie(response, request, player.id, player.epoch)
    logger.info("player taken: %s", player.id)
    return response


@router.post("/claim")
async def claim(request: Request, body: dict | None = None):
    """Become a *new* local player. An existing name must be taken, not re-made."""
    await require_session(request)
    name = ((body or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="a name is required")
    if player_manager.find_by_name(name):
        raise HTTPException(
            status_code=409,
            detail="that name is already at this table — pick it from the roster",
        )
    player = player_manager.create(name=name)
    response = JSONResponse(
        {"player": {"id": player.id, "name": player.name, "role": player.role}}
    )
    _set_session_cookie(response, request, player.id, player.epoch)
    logger.info("player created: %s (%r)", player.id, name)
    return response

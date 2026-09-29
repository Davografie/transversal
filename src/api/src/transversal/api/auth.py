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


def mint_session(player_id: str | None, epoch: int, owner: bool = False) -> str:
    """A session for ``player_id``, or an admitted-but-unclaimed session.

    ``owner`` marks a session that came through the architect-token path. It lives
    **on the session, not on the player**, and that distinction is the whole point:
    an owner flag on a player record would be handed over by taking that player,
    which is precisely what must not happen.
    """
    payload: dict = {"epoch": int(epoch)}
    if owner:
        payload["owner"] = True
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
    response, request: Request, player_id: str | None, epoch: int, owner: bool = False
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        mint_session(player_id, epoch, owner=owner),
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
        # Only now is the player lookup worth paying for. A dead session must never
        # be extended — that would keep a revoked cookie alive.
        resolved = resolve_session(request)
        if not resolved:
            return response
        _, player = resolved
        _set_session_cookie(
            response,
            request,
            player.id if player else None,
            int(player.epoch) if player else 0,
        )
    return response


# ── Dependencies: identity comes from here, never from a path ─────────


def resolve_session(request: Request):
    """The session payload and the player it names, validated **together**.

    A cookie naming a player whose epoch has moved on is **dead**, not merely
    unbound. That distinction is the whole of revoke: bumping the epoch must end
    every cookie that names that player — including its claim to be in the
    campaign at all. If it only unbound the player, a revoked device would still
    be admitted and could simply take someone else, which would make revoke
    decorative.

    Returns ``(payload, player_or_None)``, or ``None`` when the cookie is dead.
    """
    payload = current_session(request)
    if not payload:
        return None
    player_id = payload.get("player")
    if not player_id:
        return payload, None
    player = player_manager.get(player_id)
    if not player or int(player.epoch) != int(payload.get("epoch", -1)):
        return None
    return payload, player


async def require_session(request: Request) -> dict:
    """Any admitted device — claimed or not, but not a revoked one."""
    resolved = resolve_session(request)
    if not resolved:
        raise HTTPException(status_code=401, detail="no valid session")
    return resolved[0]


async def require_player(request: Request):
    """The player this session has taken, with its epoch still current."""
    resolved = resolve_session(request)
    if not resolved:
        raise HTTPException(status_code=401, detail="no valid session")
    _, player = resolved
    if not player:
        raise HTTPException(status_code=403, detail="no player has been taken yet")
    return player


async def require_owner(request: Request):
    """The campaign's owner — read off the **session**, never off a player.

    `role` is not a boundary: it is a UI mode any player may switch for themselves.
    Ownership is not self-service either — it is established out of band, by the
    architect-token path. Reading it from the session rather than the player is what
    stops "take the owner's player" from being "become the owner".
    """
    player = await require_player(request)
    if not (current_session(request) or {}).get("owner"):
        raise HTTPException(status_code=403, detail="owner only")
    return player


# ── The architect seat ────────────────────────────────────────────────


def ensure_owner():
    """The seat reached only through ``/enter?a=<ARCHITECT_TOKEN>``.

    It writes nothing: ownership is conveyed by the *session* it issues, so there is
    no flag on a player record for anyone to take. Returns the seat to bind to —
    the first architect, or a freshly created one — so a troupe cannot lock itself
    out of its own campaign.
    """
    players = player_manager.list_all()
    existing = next((p for p in players if p.role == "architect"), None)
    if existing:
        return existing
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
        owner = ensure_owner()
        if not owner:
            return JSONResponse(
                {"detail": "no owner seat could be established"}, status_code=503
            )
        response = RedirectResponse(url="/", status_code=302)
        _set_session_cookie(response, request, owner.id, owner.epoch, owner=True)
        logger.info("owner entered as %s", owner.id)
        return response

    return JSONResponse({"detail": "a passage token is required"}, status_code=401)


@router.get("/check")
async def check(request: Request):
    """Auth subrequest target for nginx ``auth_request /_auth``."""
    if session_is_valid(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({"ok": True})
    return JSONResponse({"detail": "unauthorized"}, status_code=401)


def _who(player, request: Request) -> dict:
    """The player, plus whether *this session* is the owner's."""
    return {
        "id": player.id,
        "name": player.name,
        "role": player.role,
        "is_owner": bool((current_session(request) or {}).get("owner")),
    }


@router.get("/session")
async def whoami(request: Request):
    """Who is calling? The frontend's first question on boot."""
    resolved = resolve_session(request)
    if not resolved:
        return JSONResponse({"admitted": False}, status_code=401)
    _, player = resolved
    if not player:
        return {"admitted": True, "player": None}
    return {
        "admitted": True,
        "player": _who(player, request),
    }


@router.get("/roster")
async def roster(request: Request):
    """Everyone who may be taken. That is everyone: see the note on `role` below."""
    await require_session(request)
    return [{"id": p.id, "name": p.name, "role": p.role} for p in player_manager.list_all()]


@router.post("/take/{player_id}")
async def take(player_id: str, request: Request):
    """Take an existing player — how a returning player resumes on a new device."""
    await require_session(request)
    player = player_manager.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="no such player")
    response = JSONResponse({"player": _who(player, request)})
    _set_session_cookie(
        response, request, player.id, player.epoch,
        owner=bool((current_session(request) or {}).get("owner")),
    )
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
    response = JSONResponse({"player": _who(player, request)})
    _set_session_cookie(
        response, request, player.id, player.epoch,
        owner=bool((current_session(request) or {}).get("owner")),
    )
    logger.info("player created: %s (%r)", player.id, name)
    return response

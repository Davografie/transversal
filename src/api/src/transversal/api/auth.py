"""Magic-link access control.

Players authenticate by scanning a QR code that encodes a magic URL::

    /enter?t=<ACCESS_TOKEN>

That endpoint exchanges the token for a signed, HttpOnly session cookie and
redirects to the app. Every API/media request is then allowed by presenting
that cookie.

The gate itself lives at the nginx edge (the prod ``:3001`` server uses
``auth_request /_auth``), so the local dev server (Vite proxy) stays
unauthenticated. The API itself applies no global auth middleware.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

logger = logging.getLogger("transversal.auth")

COOKIE_NAME = "tv2_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_secret() -> str:
    return os.getenv("SESSION_SECRET", "")


def _access_token() -> str:
    return os.getenv("ACCESS_TOKEN", "")


def _sign(message: str) -> str:
    return hmac.new(
        _session_secret().encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def _make_session_value() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def session_is_valid(value: str | None) -> bool:
    """Return True if ``value`` is a fresh, correctly-signed session cookie."""
    if not value:
        return False
    try:
        ts, sig = value.rsplit(".", 1)
        issued = int(ts)
    except ValueError:
        return False
    if not hmac.compare_digest(_sign(ts), sig):
        return False
    return (time.time() - issued) < COOKIE_MAX_AGE


@router.get("/enter")
async def enter(t: str = ""):
    """Exchange the magic-link token for a session cookie, then go home."""
    token = _access_token()
    if not token or not hmac.compare_digest(t, token):
        return JSONResponse({"detail": "invalid or missing access token"}, status_code=401)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        _make_session_value(),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        # secure=True once TLS is enabled in front of the edge.
    )
    logger.info("magic-link login accepted")
    return response


@router.get("/check")
async def check(request: Request):
    """Auth subrequest target for nginx ``auth_request /_auth``."""
    if session_is_valid(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({"ok": True})
    return JSONResponse({"detail": "unauthorized"}, status_code=401)

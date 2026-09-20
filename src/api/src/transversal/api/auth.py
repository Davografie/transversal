"""Magic-link access control.

Players authenticate by scanning a QR code that encodes a magic URL::

    /enter?t=<ACCESS_TOKEN>

That endpoint exchanges the token for a signed, HttpOnly session cookie and
redirects to the app. Every API/media request is then allowed by presenting
that cookie.

The gate itself lives at the nginx edge (the prod ``:3001`` server uses
``auth_request /_auth``), so the local dev server (Vite proxy) stays
unauthenticated. The API itself applies no global auth middleware.

This is a *perimeter*, not a user identity: every client shares one static
token, so the cookie names nobody and cannot be revoked individually. Per-user
authorization is tracked separately — see SEC-3 in
``docs/Technical/Security Posture.md``.
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

#: A signing key shorter than this counts as "not configured". An empty or stub
#: secret must never be able to validate a cookie (SEC-5).
MIN_SECRET_LENGTH = 32

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_secret() -> str:
    return os.getenv("SESSION_SECRET", "")


def _access_token() -> str:
    return os.getenv("ACCESS_TOKEN", "")


def _secret_is_usable() -> bool:
    """True only when a long-enough signing key is configured.

    Fail *closed*: with no usable secret every check reports "unauthorized"
    rather than accepting a signature that anyone could compute.
    """
    return len(_session_secret()) >= MIN_SECRET_LENGTH


def _sign(message: str) -> str:
    return hmac.new(
        _session_secret().encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def _make_session_value() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


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


def session_is_valid(value: str | None) -> bool:
    """Return True if ``value`` is a fresh, correctly-signed session cookie."""
    if not value or not _secret_is_usable():
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
async def enter(request: Request, t: str = ""):
    """Exchange the magic-link token for a session cookie, then go home."""
    if not _secret_is_usable() or not _access_token():
        logger.error(
            "auth is not configured: SESSION_SECRET must be at least %d chars "
            "and ACCESS_TOKEN must be set",
            MIN_SECRET_LENGTH,
        )
        return JSONResponse(
            {"detail": "authentication is not configured"}, status_code=503
        )

    if not hmac.compare_digest(t, _access_token()):
        return JSONResponse({"detail": "invalid or missing access token"}, status_code=401)

    secure = _is_https(request)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        _make_session_value(),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    logger.info("magic-link login accepted (secure=%s)", secure)
    return response


@router.get("/check")
async def check(request: Request):
    """Auth subrequest target for nginx ``auth_request /_auth``."""
    if session_is_valid(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({"ok": True})
    return JSONResponse({"detail": "unauthorized"}, status_code=401)

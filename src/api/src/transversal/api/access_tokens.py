"""Signed, expiring tokens (SEC-3).

One signed-token format, two audiences:

- ``AUD_JOIN``  — an admission token. Grants access to a campaign and proves
  nothing about who holds it. Reusable within a short life, and closable early:
  that liveness comes from the campaign database, not from the signature.
- ``AUD_SESSION`` — the browser session. Carries which player the holder has
  taken, plus the epoch it was issued under.

**The audience is not decoration.** Both are signed with the same key, so without
an audience claim a join token would verify as a session cookie — handing a
player's identity to anyone holding an invite — and a session cookie would verify
as a join token, letting any admitted device mint admissions off its own session.
``verify`` refuses a token whose ``aud`` is not the one asked for.

A token is a base64url JSON payload plus an HMAC over it, carrying its own ``exp``
so verification needs no storage. The signing key and the fail-closed rule are
*borrowed from* ``auth`` rather than duplicated: one key and one rule, or the two
drift apart.

See ``docs/Technical/Identity Programme.md``.
"""

from __future__ import annotations

import base64
import hmac
import json
import time

from transversal.api import auth

#: Admission to a campaign. Reusable within its life; closable early in the DB.
AUD_JOIN = "join"
#: The browser session, carrying the player taken and the epoch issued under.
AUD_SESSION = "session"


class TokenError(ValueError):
    """A token that could not be minted."""


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(
    payload: dict, ttl_seconds: int, audience: str, now: float | None = None
) -> str:
    """Return a signed token for ``audience``, valid for ``ttl_seconds``.

    Raises :class:`TokenError` when the signing key is unusable (fail *closed*,
    loudly) or the lifetime is not positive. ``aud``/``iat``/``exp`` are written
    after ``payload``, so a caller cannot mint outside the audience or lifetime it
    asked for.
    """
    if not auth._secret_is_usable():
        raise TokenError("SESSION_SECRET is not usable; refusing to mint")
    if ttl_seconds <= 0:
        raise TokenError("ttl_seconds must be positive")

    issued = int(time.time() if now is None else now)
    body = {**payload, "aud": audience, "iat": issued, "exp": issued + int(ttl_seconds)}
    encoded = _b64_encode(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    )
    return f"{encoded}.{auth._sign(encoded)}"


def verify(token: str, audience: str, now: float | None = None) -> dict | None:
    """Return the payload when the token is ours, for ``audience``, and unexpired.

    Never raises: every failure is "not a valid token", because a caller that
    distinguishes them would leak which part was wrong.
    """
    if not token or not auth._secret_is_usable():
        return None
    try:
        encoded, signature = token.rsplit(".", 1)
        payload = json.loads(_b64_decode(encoded))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not hmac.compare_digest(auth._sign(encoded), signature):
        return None
    if payload.get("aud") != audience:
        return None
    try:
        expires = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return None
    if (time.time() if now is None else now) >= expires:
        return None
    return payload

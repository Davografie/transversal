"""Signed, expiring tokens, and the signing key behind them (SEC-3, SEC-5).

One signed-token format, four audiences:

- ``AUD_JOIN``  — an admission token. Grants access to a campaign and proves
  nothing about who holds it. Reusable within a short life, and closable early:
  that liveness comes from the campaign database, not from the signature.
- ``AUD_SESSION`` — the browser session. Carries which player the holder has
  taken, plus the epoch it was issued under.
- ``AUD_ACCOUNT`` — an **account** session (B255): who owns forks. It exists
  before any campaign is chosen and is not a player session — see below.
- ``AUD_ACCOUNT_LINK`` — a single-use email link (verify / sign in / recover).

**The audience is not decoration.** They are all signed with the same key, so
without an audience claim a join token would verify as a session cookie — handing a
player's identity to anyone holding an invite — and a session cookie would verify
as a join token, letting any admitted device mint admissions off its own session.
``verify`` refuses a token whose ``aud`` is not the one asked for.

The account tier is the one that must not blur: an account session that can act as
a player **undoes SEC-3**, because the whole point of SEC-3 is that identity is
server-issued per campaign. Distinct audience *and* a distinct cookie name; the
separation needs a test rather than a convention ([[B255]]).

A token is a base64url JSON payload plus an HMAC over it, carrying its own ``exp``
so verification needs no storage.

The signing primitives live here rather than in ``auth`` because ``auth`` imports
*this*, and the reverse would be a cycle. They keep their SEC-5 behaviour: a key
shorter than :data:`MIN_SECRET_LENGTH` — including the empty key — counts as
unconfigured, and every check then fails **closed**, because a value signed with
an empty key is computable by anyone.

See ``docs/Technical/Identity Programme.md``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

#: Admission to a campaign. Reusable within its life; closable early in the DB.
AUD_JOIN = "join"
#: The browser session, carrying the player taken and the epoch issued under.
AUD_SESSION = "session"
#: An account (fork-owner) session. A different tier from a player session: it
#: exists before any campaign is chosen and must never resolve as one.
AUD_ACCOUNT = "account"
#: A single-use email link — verify an address, sign in, or recover.
AUD_ACCOUNT_LINK = "account-link"

#: A signing key shorter than this counts as "not configured". An empty or stub
#: secret must never be able to validate a token (SEC-5).
MIN_SECRET_LENGTH = 32


class TokenError(ValueError):
    """A token that could not be minted."""


def _session_secret() -> str:
    return os.getenv("SESSION_SECRET", "")


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
    if not _secret_is_usable():
        raise TokenError("SESSION_SECRET is not usable; refusing to mint")
    if ttl_seconds <= 0:
        raise TokenError("ttl_seconds must be positive")

    issued = int(time.time() if now is None else now)
    body = {**payload, "aud": audience, "iat": issued, "exp": issued + int(ttl_seconds)}
    encoded = _b64_encode(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    )
    return f"{encoded}.{_sign(encoded)}"


def verify(token: str, audience: str, now: float | None = None) -> dict | None:
    """Return the payload when the token is ours, for ``audience``, and unexpired.

    Never raises: every failure is "not a valid token", because a caller that
    distinguishes them would leak which part was wrong.
    """
    if not token or not _secret_is_usable():
        return None
    try:
        encoded, signature = token.rsplit(".", 1)
        payload = json.loads(_b64_decode(encoded))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not hmac.compare_digest(_sign(encoded), signature):
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

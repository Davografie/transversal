"""Signed, expiring admission tokens (SEC-3 groundwork).

An invite is **authorization, not identity**: it grants access to a campaign and
proves nothing about who holds it. This module is the machinery for such a token
and nothing else — it is deliberately **not wired into any flow yet**.

A token is a base64url JSON payload plus an HMAC over it, signed with the same
key as the session cookie and carrying its own ``exp``, so verification needs no
storage. The signing key and the fail-closed rule are *borrowed from* ``auth``
rather than duplicated: one key and one rule, or the two will drift apart.

Deliberately **not** here: revocability. A join token must be closable before it
expires, and that liveness has to come from the campaign database rather than from
the signature. This module proves only "we minted it" and "it has not expired" —
see ``docs/Technical/Identity Programme.md`` §5.7.
"""

from __future__ import annotations

import base64
import hmac
import json
import time

from transversal.api import auth


class TokenError(ValueError):
    """A token that could not be minted."""


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(payload: dict, ttl_seconds: int, now: float | None = None) -> str:
    """Return a signed token carrying ``payload``, valid for ``ttl_seconds``.

    Raises :class:`TokenError` when the signing key is unusable (fail *closed*,
    loudly) or the lifetime is not positive. Any ``exp``/``iat`` in ``payload``
    is overwritten, so a caller cannot mint itself a longer life than it asked
    for.
    """
    if not auth._secret_is_usable():
        raise TokenError("SESSION_SECRET is not usable; refusing to mint")
    if ttl_seconds <= 0:
        raise TokenError("ttl_seconds must be positive")

    issued = int(time.time() if now is None else now)
    body = {**payload, "iat": issued, "exp": issued + int(ttl_seconds)}
    encoded = _b64_encode(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    )
    return f"{encoded}.{auth._sign(encoded)}"


def verify(token: str, now: float | None = None) -> dict | None:
    """Return the payload when the token is ours and unexpired, else ``None``.

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
    try:
        expires = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return None
    if (time.time() if now is None else now) >= expires:
        return None
    return payload

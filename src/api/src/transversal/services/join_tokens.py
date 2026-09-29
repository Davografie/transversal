"""Campaign admission tokens — minting and resolution (SEC-3).

The signed token proves it is ours and says when it expires; this module adds the
liveness the database owns (the token was not closed early).

The split matters: the signature is self-describing and therefore needs no
storage, so closing a token early is *the only* reason the store exists. Anything
that must be revocable has to be checked here rather than trusted from the token.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transversal.api import access_tokens

#: How long a join token is good for. The owner's working figure — one QR shown to
#: the table, long enough to get everyone through it, short enough that a
#: photographed link is not standing access.
DEFAULT_TTL_SECONDS = 30 * 60


def open_token(
    repo, created_by: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> tuple[str, dict]:
    """Mint a join token and record its liveness. Returns ``(token, record)``."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    token_id = repo.create_join_token(
        created_by=created_by, expires_at=expires_at.isoformat()
    )
    token = access_tokens.mint(
        {"token": token_id}, ttl_seconds, access_tokens.AUD_JOIN
    )
    record = repo.get_join_token(token_id) or {}
    return token, record


def resolve_token(repo, token: str) -> dict | None:
    """Return the liveness record when ``token`` is ours, open and unexpired.

    ``None`` covers every failure — forged, expired, unknown, or closed early —
    because a caller that distinguishes them would leak which.
    """
    payload = access_tokens.verify(token, access_tokens.AUD_JOIN)
    if not payload:
        return None
    token_id = payload.get("token")
    if not token_id:
        return None
    record = repo.get_join_token(token_id)
    if not record or record.get("closed_at"):
        return None
    return record


def is_open(repo, token_id: str) -> bool:
    record = repo.get_join_token(token_id)
    return bool(record) and not record.get("closed_at")

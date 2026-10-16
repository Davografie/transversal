"""Account links — minting and single-use resolution (B255, B88).

The same split as ``join_tokens``: the signed token proves the link is ours and says
when it expires, so proving authenticity needs no storage. What needs storage is
**spending it once**, and that is the registry's ``account_tokens`` collection.

One mechanism, three purposes: ``verify`` and ``sign_in`` (recovery is the sign-in
link — there is deliberately no separate credential to lose), and ``enter_fork``,
which opens one fork as its architect.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transversal.api import access_tokens

#: Short, because it is a credential in a mailbox. Long enough to click from a phone.
LINK_TTL_SECONDS = 15 * 60
#: Shorter still, because this one is not mailed — it is handed straight to the
#: browser that just asked for it, so the only reason it lives at all is the hop.
ENTER_TTL_SECONDS = 5 * 60


def issue(
    repo,
    account_id: str,
    purpose: str,
    *,
    ttl_seconds: int = LINK_TTL_SECONDS,
    fork_id: str = "",
) -> str:
    """Record liveness and return the signed link token."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    token_id = repo.create_account_token(
        account_id=account_id,
        purpose=purpose,
        expires_at=expires_at.isoformat(),
        fork_id=fork_id,
    )
    return access_tokens.mint(
        {"token": token_id}, ttl_seconds, access_tokens.AUD_ACCOUNT_LINK
    )


def consume(repo, token: str, purpose: str) -> dict | None:
    """Spend ``token`` when it is ours, for ``purpose``, and unspent.

    ``None`` covers every failure — forged, expired, wrong purpose, already spent —
    because a caller that distinguishes them leaks which. The spend happens before
    the caller acts on it, so a replayed link cannot be used twice even in a race.
    """
    payload = access_tokens.verify(token, access_tokens.AUD_ACCOUNT_LINK)
    if not payload:
        return None
    token_id = payload.get("token")
    if not token_id:
        return None
    record = repo.get_account_token(token_id)
    if not record or record.get("purpose") != purpose:
        return None
    if not repo.consume_account_token(token_id):
        return None
    return record

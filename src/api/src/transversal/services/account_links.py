"""Account email links — minting and single-use resolution (B255).

The same split as ``join_tokens``: the signed token proves the link is ours and says
when it expires, so proving authenticity needs no storage. What needs storage is
**spending it once**, and that is the registry's ``account_tokens`` collection.

One mechanism, two purposes (``verify`` and ``sign_in``). Recovery is the
sign-in link — there is deliberately no separate credential to lose.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transversal.api import access_tokens

#: Short, because it is a credential in a mailbox. Long enough to click from a phone.
LINK_TTL_SECONDS = 15 * 60


def issue(repo, account_id: str, purpose: str) -> str:
    """Record liveness and return the signed link token."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=LINK_TTL_SECONDS)
    token_id = repo.create_account_token(
        account_id=account_id, purpose=purpose, expires_at=expires_at.isoformat()
    )
    return access_tokens.mint(
        {"token": token_id}, LINK_TTL_SECONDS, access_tokens.AUD_ACCOUNT_LINK
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

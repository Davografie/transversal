"""Account auth — register, verify, sign in, recover (B255).

This is the **account tier**, and it is deliberately separate from
``api/auth.py``'s campaign tier:

- a **player session** (`tv2_session`) admits a device to one campaign and names the
  player it took;
- an **account session** (`tv2_account`) says who owns forks. It exists *before* a
  campaign is chosen and outlives any one of them.

They are separated twice over — different cookie name, different ``aud`` — because
blurring them would undo SEC-3: an account session that can act as a player hands
identity back to the client. The separation is asserted by tests, not trusted to
this comment ([[B255]]).

Sign-in and recovery are the **same mechanism** (a single-use email link): with one
credential there is nothing else recovery could be, and two code paths would be two
places to get it wrong. Every response that could reveal whether an address has an
account answers identically, because the registry is the only place mapping a
recovery identifier to anything ([[Identity Programme]] §5.4).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from transversal.api import access_tokens, auth
from transversal.api.auth import _is_https
from transversal.db.arango import use_database
from transversal.db.registry_repository import (
    PURPOSE_ENTER_FORK,
    PURPOSE_SIGN_IN,
    PURPOSE_VERIFY,
    RegistryRepository,
    normalize_email,
)
from transversal.services import account_links, mailer, send_limits

logger = logging.getLogger("transversal.accounts")

#: A different cookie from the campaign session, on purpose: the player path must
#: never read this one, and vice versa.
COOKIE_NAME = "tv2_account"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days, sliding-like lifetime

#: Where a fork-entry link is redeemed. Shared with the forks API, which mints the
#: link and so has to name the same path ([[B88]]).
ENTER_PATH = "/api/v1/accounts/enter"
#: Where a sign-in link is redeemed. Shared with the CLI, which can mint one when
#: mail is not configured.
SIGN_IN_PATH = "/api/v1/accounts/sign-in"
#: Where the account flows land: the portal, not the game. On the apex those are
#: different surfaces, and someone who just verified an address wants their
#: campaigns, not a character sheet. (The *fork-entry* redirect stays at `/` — that
#: one runs on a campaign host, where `/` is the game.)
PORTAL_PATH = "/portal"

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


def _repo() -> RegistryRepository:
    return RegistryRepository()


def _looks_like_email(value: str) -> bool:
    """The minimum that can receive a link: one ``@``, something either side, and a
    dot in the domain. Delivery is the real validation, and it is verified before
    the address is usable for anything."""
    email = normalize_email(value)
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        return False
    return not domain.startswith(".") and not domain.endswith(".")


# ── The account session ───────────────────────────────────────────────


def mint_account_session(account_id: str, epoch: int) -> str:
    """A session for one account. Never carries a player, by construction."""
    return access_tokens.mint(
        {"account": account_id, "epoch": int(epoch)},
        COOKIE_MAX_AGE,
        access_tokens.AUD_ACCOUNT,
    )


def account_session_payload(request: Request) -> dict | None:
    return access_tokens.verify(
        request.cookies.get(COOKIE_NAME), access_tokens.AUD_ACCOUNT
    )


def resolve_account_session(request: Request) -> tuple[dict, dict] | None:
    """The session payload and the account it names, validated **together**.

    A revoked account (epoch bumped) is dead, not merely unbound — otherwise
    revoking an account would leave its sessions able to act. Returns
    ``(payload, account)`` or ``None``.
    """
    payload = account_session_payload(request)
    if not payload:
        return None
    account_id = payload.get("account")
    if not account_id:
        return None
    account = _repo().get_account(account_id)
    if not account or account.epoch != int(payload.get("epoch", -1)):
        return None
    return payload, account


async def require_account(request: Request) -> dict:
    """The account this session names, with its epoch still current."""
    resolved = resolve_account_session(request)
    if not resolved:
        raise HTTPException(status_code=401, detail="no valid account session")
    return resolved[1]


def _set_account_cookie(response, request: Request, account) -> None:
    response.set_cookie(
        COOKIE_NAME,
        mint_account_session(account.id, account.epoch),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )


def _public(account) -> dict:
    return {
        "id": account.id,
        "email": account.email,
        "verified": bool(account.verified_at),
        "global_editor": bool(account.global_editor),
    }


def _configured() -> bool:
    return access_tokens._secret_is_usable()


# ── Sending a link ────────────────────────────────────────────────────


def _send_link(to: str, purpose: str, token: str) -> None:
    if purpose == PURPOSE_VERIFY:
        path, subject = "/api/v1/accounts/verify", "Confirm your Transversal account"
    else:
        path, subject = "/api/v1/accounts/sign-in", "Your Transversal sign-in link"
    url = f"{path}?t={token}"
    minutes = account_links.LINK_TTL_SECONDS // 60
    mailer.get_mailer().send(
        to,
        subject,
        f"Open this link to continue (it works once, for {minutes} minutes):\n\n{url}\n",
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.post("/register")
async def register(request: Request, body: dict | None = None) -> dict:
    """Create an unverified account and mail a verification link.

    A verified address is left alone and gets no mail, but the answer is the same
    as for a new one — the registry must not become a directory of who has an
    account ([[Identity Programme]] §5.4).
    """
    if not _configured():
        raise HTTPException(status_code=503, detail="authentication is not configured")

    email = normalize_email((body or {}).get("email") or "")
    if not _looks_like_email(email):
        raise HTTPException(status_code=400, detail="a valid email address is required")

    repo = _repo()
    existing = repo.find_account_by_email(email)
    if existing and existing.verified_at:
        # Nothing to do, and nothing to say — see the docstring.
        return {"sent": True}

    account = existing or repo.create_account(email)
    if not send_limits.allow_send(email):
        # Identical answer, no mail: a refusal an attacker can see is an oracle for
        # which addresses are being hammered, and whether they have an account.
        logger.warning("[accounts] send cap reached; no link sent for %s", account.id)
        return {"sent": True}
    token = account_links.issue(repo, account.id, PURPOSE_VERIFY)
    _send_link(email, PURPOSE_VERIFY, token)
    logger.info("[accounts] verification link issued for %s", account.id)
    return {"sent": True}


@router.get("/verify")
async def verify(request: Request, t: str = "") -> JSONResponse:
    """Spend a verification link, mark the address verified, and sign in."""
    if not _configured():
        raise HTTPException(status_code=503, detail="authentication is not configured")
    repo = _repo()
    record = account_links.consume(repo, t, PURPOSE_VERIFY)
    # One answer for forged, expired, wrong-purpose and already-spent alike.
    if not record:
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)
    account = repo.mark_email_verified(record["account_id"])
    if not account:
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)
    response = RedirectResponse(url=PORTAL_PATH, status_code=302)
    _set_account_cookie(response, request, account)
    logger.info("[accounts] email verified for %s", account.id)
    return response


@router.post("/sign-in")
async def request_sign_in(request: Request, body: dict | None = None) -> dict:
    """Mail a sign-in link. Also the recovery flow — same mechanism, one credential.

    Answers identically whether or not the address has a verified account, and
    mails only when it does.
    """
    if not _configured():
        raise HTTPException(status_code=503, detail="authentication is not configured")

    email = normalize_email((body or {}).get("email") or "")
    if not _looks_like_email(email):
        raise HTTPException(status_code=400, detail="a valid email address is required")

    repo = _repo()
    account = repo.find_account_by_email(email)
    if account and account.verified_at:
        if not send_limits.allow_send(email):
            logger.warning("[accounts] send cap reached; no sign-in link for %s", account.id)
            return {"sent": True}
        token = account_links.issue(repo, account.id, PURPOSE_SIGN_IN)
        _send_link(email, PURPOSE_SIGN_IN, token)
        logger.info("[accounts] sign-in link issued for %s", account.id)
    return {"sent": True}


@router.get("/sign-in")
async def confirm_sign_in(request: Request, t: str = "") -> JSONResponse:
    """Spend a sign-in link and issue an account session."""
    if not _configured():
        raise HTTPException(status_code=503, detail="authentication is not configured")
    repo = _repo()
    record = account_links.consume(repo, t, PURPOSE_SIGN_IN)
    if not record:
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)
    account = repo.get_account(record["account_id"])
    if not account or not account.verified_at:
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)
    response = RedirectResponse(url=PORTAL_PATH, status_code=302)
    _set_account_cookie(response, request, account)
    logger.info("[accounts] signed in %s", account.id)
    return response


@router.post("/recover")
async def recover(request: Request, body: dict | None = None) -> dict:
    """Recovery *is* sign-in here: there is no second credential to recover."""
    return await request_sign_in(request, body)


@router.get("/session")
async def whoami(request: Request) -> JSONResponse:
    """Who owns this browser? The account tier's own boot question."""
    resolved = resolve_account_session(request)
    if not resolved:
        return JSONResponse({"signed_in": False}, status_code=401)
    return JSONResponse({"signed_in": True, "account": _public(resolved[1])})


@router.post("/sign-out")
async def sign_out() -> JSONResponse:
    response = JSONResponse({"signed_in": False})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/enter")
async def enter_fork(request: Request, f: str = "") -> JSONResponse:
    """Redeem a single-use fork-entry link for an architect session ([[B88]]).

    **The link is the authority, so no account session is required** — and that is
    the point. The account cookie is host-scoped to the portal, so it is not sent
    to ``<slug>.<base-domain>``; this endpoint is what crosses that boundary, once,
    with a token that is bound to the fork and short-lived.

    Everything it needs comes from the consumed record: which account, which fork.
    It then scopes the request to that fork's database and takes the architect seat
    there — creating one if the fork has none, exactly as the architect-token path
    does for a single-campaign install.
    """
    if not _configured():
        raise HTTPException(status_code=503, detail="authentication is not configured")

    repo = _repo()
    record = account_links.consume(repo, f, PURPOSE_ENTER_FORK)
    # One answer for forged, expired, spent, wrong-purpose and tampered alike.
    if not record:
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)

    account = repo.get_account(record.get("account_id") or "")
    fork = repo.get_fork(record.get("fork_id") or "")
    if (
        not account
        or not account.verified_at
        or not fork
        or fork.owner_account != account.id
    ):
        logger.warning(
            "[accounts] fork entry refused for account %s", record.get("account_id")
        )
        return JSONResponse({"detail": "that link is not valid"}, status_code=401)

    with use_database(fork.database):
        owner_player = auth.ensure_owner()
    if not owner_player:
        return JSONResponse(
            {"detail": "no owner seat could be established"}, status_code=503
        )

    response = RedirectResponse(url="/", status_code=302)
    auth.set_session_cookie(response, request, owner_player, owner=True)
    logger.warning(
        "[accounts] %s entered fork %s (%s) as its architect",
        account.id,
        fork.id,
        fork.database,
    )
    return response

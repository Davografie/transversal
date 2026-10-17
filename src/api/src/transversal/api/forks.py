"""Forks API — the account tier's "my campaigns" surface (B88/B256).

This is the **portal API** in the shape it should have: not a second service, but a
route group on the one API that already resolves a request to a database. A fork is
a database plus a routing row, and `POST` here is a clone — which is why it is
gated.

Gating is deliberate and off by default. The design leaves **who may create a
campaign** to the owner ([[Tenancy Rollout Plan]] §3.2: self-service is the intent,
throttling and payment unsettled), so the route exists, is tested, and refuses with
a clear message until ``FORKS_ALLOW_CREATE`` says otherwise. Building it switched
off is what lets the switcher and the CLI share one contract.

The URL a fork answers on is ``<slug>.<FORKS_BASE_DOMAIN>`` — the routing decision is
the **subdomain**, because it needs no SPA router (the app reads the host) and gives
each campaign its own cookie scope. Nothing resolves it yet; that is the next step,
and this is the row it will read.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request

from transversal.api.account_auth import ENTER_PATH, require_account
from transversal.api.tenancy import base_domain
from transversal.db.registry_repository import PURPOSE_ENTER_FORK, RegistryRepository
from transversal.services import account_links
from transversal.services.provisioner import fork_slug, provision_fork

logger = logging.getLogger("transversal.forks")

router = APIRouter(prefix="/api/v1/forks", tags=["forks"])

#: The database a new fork is cloned **from**. Until the owner splits the global
#: from the personal game (their 2026-10-16 decision), this is the one database.
DEFAULT_SOURCE_DATABASE = "transversal"


def _repo() -> RegistryRepository:
    return RegistryRepository()


#: How many campaigns one account may own unless told otherwise. A fork is cheap — the
#: database is ~13k documents and media is shared content-addressed blobs — but it is not
#: nothing, and a public invitation should not let one account clone the world without
#: limit. ``FORKS_MAX_PER_ACCOUNT`` overrides it ([[B331]]).
DEFAULT_MAX_FORKS_PER_ACCOUNT = 2


def max_forks_per_account() -> int:
    """The cap, from ``FORKS_MAX_PER_ACCOUNT``.

    A malformed or non-positive value falls back to the default rather than removing the
    limit — the rule `DB_CACHE_MAX` already follows: an unreadable setting must not become
    a silent "unlimited".
    """
    raw = (os.getenv("FORKS_MAX_PER_ACCOUNT", "") or "").strip()
    if not raw:
        return DEFAULT_MAX_FORKS_PER_ACCOUNT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_FORKS_PER_ACCOUNT
    return value if value > 0 else DEFAULT_MAX_FORKS_PER_ACCOUNT


def creation_is_open() -> bool:
    """Whether self-service fork creation is switched on. Off unless said."""
    raw = (os.getenv("FORKS_ALLOW_CREATE", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _public(fork) -> dict:
    base = base_domain()
    return {
        "id": fork.id,
        "name": fork.name,
        "slug": fork.slug,
        "database": fork.database,
        "kind": fork.kind,
        "created_at": fork.created_at,
        "url": f"https://{fork.slug}.{base}" if fork.slug and base else None,
    }


@router.get("")
async def list_my_forks(request: Request) -> list[dict]:
    """The tables this account owns — the switcher's data source."""
    account = await require_account(request)
    return [_public(fork) for fork in _repo().list_forks_for(account.id)]


@router.post("")
async def create_fork(request: Request, body: dict | None = None) -> dict:
    """Clone the canonical database and route the result to this account.

    Synchronous on purpose for now: a clone is a few seconds of database work. It
    becomes a queued job when it stops being, not before.
    """
    account = await require_account(request)
    if not creation_is_open():
        raise HTTPException(
            status_code=403,
            detail="creating forks is not open yet",
        )

    name = ((body or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="a name is required")

    repo = _repo()

    # The cap, checked before any cloning: a fork is a whole database, so the limit has to
    # bound that rather than apologise after it.
    #
    # Counted as **campaigns**, not instances: the global multiverse and the playroom are
    # deployment infrastructure (kinds `global` and `playroom`), so an operator who owns them
    # must not thereby be unable to create a campaign of their own. Only `kind == "fork"` is
    # what this limit exists to bound.
    cap = max_forks_per_account()
    owned = [f for f in repo.list_forks_for(account.id) if f.kind == "fork"]
    if len(owned) >= cap:
        plural = "" if len(owned) == 1 else "s"
        raise HTTPException(
            status_code=409,
            detail=(
                f"this account already has {len(owned)} campaign{plural}; "
                f"the limit is {cap}"
            ),
        )

    slug = fork_slug((body or {}).get("slug") or name)
    if repo.find_fork_by_slug(slug):
        # Say so rather than silently suffixing: `daves-game-2` chosen by a
        # machine is how two campaigns end up with names nobody picked.
        raise HTTPException(status_code=409, detail="that address is taken")

    fork = provision_fork(
        repo,
        source_database=(os.getenv("GLOBAL_DATABASE") or DEFAULT_SOURCE_DATABASE),
        name=name,
        owner_account=account.id,
        slug=slug,
    )
    logger.warning(
        "[forks] %s created fork %s -> %s (%s)",
        account.id,
        fork.id,
        fork.database,
        fork.slug,
    )
    return _public(fork)


@router.post("/{fork_id}/enter")
async def enter_fork(request: Request, fork_id: str) -> dict:
    """Mint a single-use link that opens this fork as its architect ([[B88]]).

    **Why a link and not a session.** The account session lives on the portal host
    and is host-scoped, so it is not sent to ``<slug>.<base-domain>``; and handing
    the account session to every fork host would make one cookie the key to all of
    them. So the portal mints a short-lived, single-use capability, bound in the
    registry to this fork, and the fork's own host redeems it.

    Only the owner may ask. The link is returned once, here, to an authenticated
    caller — treat it like the join token it resembles.
    """
    account = await require_account(request)
    repo = _repo()
    fork = repo.get_fork(fork_id)
    if not fork:
        raise HTTPException(status_code=404, detail="no such fork")
    if fork.owner_account != account.id:
        raise HTTPException(status_code=403, detail="not your fork")

    token = account_links.issue(
        repo,
        account.id,
        PURPOSE_ENTER_FORK,
        ttl_seconds=account_links.ENTER_TTL_SECONDS,
        fork_id=fork.id,
    )
    path = f"{ENTER_PATH}?f={token}"
    base = base_domain()
    logger.info("[forks] %s minted entry to %s", account.id, fork.id)
    return {
        "fork": _public(fork),
        "token": token,
        "enter_url": f"https://{fork.slug}.{base}{path}" if fork.slug and base else path,
        "expires_in": account_links.ENTER_TTL_SECONDS,
    }

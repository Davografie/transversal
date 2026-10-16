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

from transversal.api.account_auth import require_account
from transversal.api.tenancy import base_domain
from transversal.db.registry_repository import RegistryRepository
from transversal.services.provisioner import fork_slug, provision_fork

logger = logging.getLogger("transversal.forks")

router = APIRouter(prefix="/api/v1/forks", tags=["forks"])

#: The database a new fork is cloned **from**. Until the owner splits the global
#: from the personal game (their 2026-10-16 decision), this is the one database.
DEFAULT_SOURCE_DATABASE = "transversal"


def _repo() -> RegistryRepository:
    return RegistryRepository()


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

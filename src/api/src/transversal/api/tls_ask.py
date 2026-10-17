"""The certificate gate — which campaign hostnames may obtain a TLS certificate (B331).

Every campaign answers on ``<slug>.<FORKS_BASE_DOMAIN>``, and the edge obtains its
certificate **on demand** rather than from a list written into its config: a new campaign has
to be reachable without editing the VPS for each one. On-demand issuance is a hole unless
something approves each name — otherwise anyone who points DNS at the box can make it ask
Let's Encrypt for a certificate and burn the per-domain issuance allowance — so Caddy asks
this endpoint first, and issues only for a 2xx.

Approved means **the slug exists in the registry**, and nothing else is decided here: not
which account owns it, and not whether anyone has entered it yet.

It is deliberately **unauthenticated** (the asker has no session) and deliberately outside
the campaign scope: it names a campaign rather than belonging to one. The only thing it
discloses is whether a given slug exists, which the portal effectively discloses to its
owner anyway.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from transversal.api.tenancy import base_domain, slug_from_host
from transversal.db.registry_repository import RegistryRepository

logger = logging.getLogger("transversal.tls")

router = APIRouter(prefix="/api/v1/tenancy", tags=["tenancy"])


@router.get("/tls-ask")
async def tls_ask(domain: str = Query("")) -> dict:
    """Approve a certificate for ``domain`` if it names an existing campaign.

    Caddy's ``on_demand_tls`` calls this with ``?domain=``. A 2xx approves; anything else
    denies, so the refusals below are 404s on purpose — they carry no information beyond
    "no".
    """
    # One definition of what a campaign hostname is, shared with the router, so the two
    # cannot drift: first label only, under the configured base domain.
    slug = slug_from_host(domain, base_domain())
    if not slug:
        raise HTTPException(status_code=404, detail="not a campaign hostname")

    fork = RegistryRepository().find_fork_by_slug(slug)
    if fork is None:
        raise HTTPException(status_code=404, detail="no such campaign")

    logger.info("[tls-ask] approving %s (fork %s)", domain, fork.id)
    return {"approved": True, "slug": slug}

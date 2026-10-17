"""B331 — the certificate gate: which campaign hostnames may have a TLS certificate.

On-demand TLS is what lets a new campaign be reachable without editing the VPS for each one,
and the `ask` gate is what stops it being a way to burn the certificate allowance with names
that exist nowhere. So the property asserted here is narrow and deliberate:

- a slug that **exists** is approved, and one that does not is refused — including the apex,
  a deeper name, and an unrelated domain, because those are not campaign hostnames at all;
- it decides nothing else: not ownership, not readiness, not a session.

No Arango: the registry is a stub.
"""

import pytest
from fastapi import HTTPException

from transversal.api import tenancy, tls_ask
from transversal.domain.accounts import Fork


class _FakeRegistry:
    def __init__(self, slugs=()):
        self.slugs = set(slugs)

    def find_fork_by_slug(self, slug):
        if slug not in self.slugs:
            return None
        return Fork(
            id="fork-5984d4ec9022",
            name="Global Multiverse",
            database="transversal_global",
            owner_account="acct-1",
            slug=slug,
        )


@pytest.fixture
def routed(monkeypatch):
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    registry = _FakeRegistry({"global", "daves-game"})
    monkeypatch.setattr(tls_ask, "RegistryRepository", lambda: registry)


async def test_an_existing_campaign_is_approved(routed):
    approved = await tls_ask.tls_ask("global.transversal.app")

    assert approved == {"approved": True, "slug": "global"}


async def test_any_slug_that_exists_is_approved_not_a_fixed_list(routed):
    """The whole point: a campaign created five minutes ago needs no edge edit."""
    assert (await tls_ask.tls_ask("daves-game.transversal.app"))["slug"] == "daves-game"


@pytest.mark.parametrize(
    "domain",
    [
        "typo.transversal.app",       # a name that resolves but has no campaign
        "transversal.app",            # the apex
        "a.b.transversal.app",        # deeper than the certificate coverage
        "example.com",                # not ours
        "global.not-ours.test",
        "",                           # nothing named
        "global.transversal.app:443",  # a port is stripped, so this one is *approved* — see below
    ],
)
async def test_hostnames_that_are_refused_or_normalised(routed, domain):
    """Every refusal is a 404: the answer carries no information beyond "no"."""
    if domain == "global.transversal.app:443":
        # `slug_from_host` strips the port, so this is the same host and must be approved.
        assert (await tls_ask.tls_ask(domain))["slug"] == "global"
        return

    with pytest.raises(HTTPException) as exc:
        await tls_ask.tls_ask(domain)

    assert exc.value.status_code == 404


async def test_nothing_is_approved_without_a_configured_base_domain(monkeypatch):
    """With host routing switched off there are no campaign hostnames to certify."""
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)
    monkeypatch.setattr(tls_ask, "RegistryRepository", lambda: _FakeRegistry({"global"}))

    with pytest.raises(HTTPException) as exc:
        await tls_ask.tls_ask("global.transversal.app")

    assert exc.value.status_code == 404


async def test_the_gate_is_not_campaign_scoped():
    """It must answer before a campaign request exists, so the router leaves it unscoped."""
    assert "/api/v1/tenancy" in tenancy.TENANCY_PREFIXES

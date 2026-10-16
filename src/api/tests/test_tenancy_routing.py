"""B88 — host → fork resolution.

The middleware that makes `<slug>.<base-domain>` mean a campaign. Its failure modes
are the interesting part, so each is asserted: an unknown label is a **404** (never a
fallback into the owner's own database), the tenancy tier is **never** scoped, and
with no base domain configured the whole thing is inert.

No Arango and no server: the registry is a stub and the downstream app is a function.
"""

import pytest
from starlette.responses import JSONResponse

from transversal.api import tenancy
from transversal.api.tenancy import ForkScopeMiddleware, slug_from_host
from transversal.db.arango import current_database
from transversal.domain.accounts import Fork
from transversal.services.campaign_scope import current_campaign, default_database


class _FakeRegistry:
    def __init__(self, forks=None):
        self.forks = forks or {}

    def find_fork_by_slug(self, slug):
        return self.forks.get(slug)


@pytest.fixture(autouse=True)
def _no_base_domain(monkeypatch):
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)


def _fork(slug="daves-game", database="tv2_fork_dave") -> Fork:
    return Fork(
        id="fork-1", name="Dave's game", database=database, owner_account="acct-1", slug=slug
    )


def _scope(host, path="/api/v1/graphql"):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"host", host.encode("latin-1"))],
    }


async def _receive():
    return {"type": "http.request"}


def _collector():
    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    return messages, send


async def _ok(scope, receive, send):
    await JSONResponse({"ok": True})(scope, receive, send)


@pytest.fixture
def routed(monkeypatch):
    """Host routing switched on, with one fork registered."""
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    registry = _FakeRegistry({"daves-game": _fork()})
    monkeypatch.setattr(tenancy, "RegistryRepository", lambda: registry)
    return registry


# ── Reading the label ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "host,expected",
    [
        ("daves-game.transversal.app", "daves-game"),
        ("daves-game.transversal.app:443", "daves-game"),
        ("DAVES-GAME.Transversal.App", "daves-game"),
    ],
)
def test_a_subdomain_is_the_campaign_label(host, expected):
    assert slug_from_host(host, "transversal.app") == expected


@pytest.mark.parametrize(
    "host",
    [
        "transversal.app",  # the apex is not a campaign
        "example.com",  # not ours
        "nottransversal.app",  # the dot matters: not a suffix match
        "a.b.transversal.app",  # deeper than the certificate covers
        "",
    ],
)
def test_hosts_that_name_no_campaign(host):
    assert slug_from_host(host, "transversal.app") is None


def test_no_base_domain_means_no_labels():
    assert slug_from_host("daves-game.transversal.app", "") is None


# ── The middleware ────────────────────────────────────────────────────


async def test_it_is_inert_without_a_base_domain(monkeypatch):
    """Routing off means no fork resolution — and nothing consults the registry.

    The request is still scoped, to the default campaign's database ([[B305]]): the
    live stores need a scope, and "no scope" has to mean *out of request* rather than
    *the apex*.
    """
    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the registry must not be consulted when routing is off")

    monkeypatch.setattr(tenancy, "RegistryRepository", _explode)
    seen = {}

    async def app(scope, receive, send):
        seen["database"] = current_database()
        await _ok(scope, receive, send)

    messages, send = _collector()
    await ForkScopeMiddleware(app)(_scope("daves-game.transversal.app"), _receive, send)

    assert seen["database"] == default_database()
    assert messages[0]["status"] == 200


async def test_the_apex_is_not_a_fork_host(monkeypatch):
    """The apex serves the default campaign, never a fork's database."""
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    seen = {}

    async def app(scope, receive, send):
        seen["database"] = current_database()
        await _ok(scope, receive, send)

    await ForkScopeMiddleware(app)(_scope("transversal.app"), _receive, _collector()[1])

    assert seen["database"] == default_database()


async def test_a_known_subdomain_scopes_the_request(routed):
    seen = {}

    async def app(scope, receive, send):
        seen["database"] = current_database()
        seen["campaign"] = current_campaign()
        await _ok(scope, receive, send)

    await ForkScopeMiddleware(app)(_scope("daves-game.transversal.app"), _receive, _collector()[1])

    assert seen["database"] == "tv2_fork_dave"
    # The scope names the campaign too, so live state lands in it without a lookup
    # ([[B305]]) — and the fork id, never the database name, is what gets stored.
    assert seen["campaign"] == "fork-1"
    # and the scope does not leak out of the request
    assert current_database() is None
    assert current_campaign() == ""


async def test_an_unknown_subdomain_is_a_404_not_a_fallback(monkeypatch):
    """The sharp one: a typo must not land in the default (owner's own) database."""
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    monkeypatch.setattr(tenancy, "RegistryRepository", lambda: _FakeRegistry())
    called = {"downstream": False}

    async def app(scope, receive, send):  # pragma: no cover - must never run
        called["downstream"] = True

    messages, send = _collector()
    await ForkScopeMiddleware(app)(_scope("typo.transversal.app"), _receive, send)

    assert called["downstream"] is False
    assert messages[0]["status"] == 404


async def test_the_tenancy_tier_is_never_scoped(routed):
    """Signing in has to work on a campaign host, and the switcher lists forks it is
    not inside — neither may be routed into a **fork's** database.

    They are scoped to the *default* campaign rather than left unscoped ([[B305]]):
    the live stores require a scope and must never guess one.
    """
    seen = {}

    async def app(scope, receive, send):
        seen["database"] = current_database()
        await _ok(scope, receive, send)

    middleware = ForkScopeMiddleware(app)
    for path in ("/api/v1/accounts/session", "/api/v1/forks"):
        seen.pop("database", None)
        await middleware(_scope("daves-game.transversal.app", path), _receive, _collector()[1])
        assert seen["database"] == default_database(), path


async def test_a_non_http_scope_passes_through(monkeypatch):
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    seen = {}

    async def app(scope, receive, send):
        seen["type"] = scope["type"]

    await ForkScopeMiddleware(app)({"type": "lifespan"}, _receive, _collector()[1])

    assert seen["type"] == "lifespan"

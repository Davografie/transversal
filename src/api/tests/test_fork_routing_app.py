"""B88 — a fork host through the real app, not a unit of the middleware.

This is the test whose absence let a leak through: the resolver was unit-tested and
the services were fixed, but nothing asked the **application** whether a request to
`<slug>.<base>` actually reads that fork. The bug it would have caught is exact —
`main.py` cached its services at import, so every campaign served the first one.

So this drives `TestClient(app)` with a real Host header against probe databases, and
asserts three things a fake cannot:

- a fork host serves the fork's **player** (which goes through `player_manager`), and
  the apex host does not — the cross-campaign leak, in one line;
- a fork host reads the fork's **entities** through GraphQL;
- an unknown subdomain is refused rather than falling back to the default database.

No lifespan is run (no `with TestClient(...)`), so the startup backfills do not touch
the live database. Everything else is probe databases, dropped in teardown.
"""

import os
import uuid

import pytest
from arango import ArangoClient
from fastapi.testclient import TestClient

from transversal.api import auth
from transversal.db.arango import (
    ArangoConfig,
    get_db,
    reset_db_cache,
    use_database,
)
from transversal.db.registry import (
    RegistryConfig,
    get_registry_db,
    reset_registry_cache,
)
from transversal.db.registry_repository import RegistryRepository
from transversal.main import app
from transversal.services.provisioner import provision_fork

BASE_DOMAIN = "transversal.test"
SLUG = "probe-game"
PROBE_ENTITY = "tv2-probe-loc"


@pytest.fixture
def routed(monkeypatch):
    """A live ArangoDB with a fork whose data differs from the default database."""
    url = os.environ.get("ARANGO_URL")
    password = os.environ.get("ARANGO_ROOT_PASSWORD")
    if not url or not password:
        pytest.skip("no live ArangoDB configured (ARANGO_URL / ARANGO_ROOT_PASSWORD)")

    client = ArangoClient(hosts=url)
    try:
        sys_db = client.db("_system", username="root", password=password)
        list(sys_db.databases())
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"ArangoDB is not reachable: {exc}")

    run = uuid.uuid4().hex[:8]
    names = {
        "registry": f"tv2_appreg_{run}",
        "source": f"tv2_appsrc_{run}",
        "fork": f"tv2_appfork_{run}",
    }
    config = ArangoConfig(
        url=url, username="root", password=password, database=names["source"]
    )

    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("FORKS_BASE_DOMAIN", BASE_DOMAIN)
    monkeypatch.setenv("REGISTRY_DATABASE", names["registry"])
    reset_db_cache()
    reset_registry_cache()

    try:
        # a source campaign with one entity, cloned into the fork
        sys_db.create_database(names["source"])
        with use_database(names["source"]):
            source = get_db()
        source.collection("entities").insert(
            {
                "_key": PROBE_ENTITY,
                "type": "location",
                "name": "Moscow",
                "current_universe": "earth",
            }
        )

        registry = RegistryRepository(
            db=get_registry_db(
                RegistryConfig(
                    url=url,
                    username="root",
                    password=password,
                    database=names["registry"],
                )
            )
        )
        account = registry.mark_email_verified(
            registry.create_account("probe@example.com").id
        )
        fork = provision_fork(
            registry,
            source_database=names["source"],
            name="Probe game",
            owner_account=account.id,
            database=names["fork"],
            slug=SLUG,
            config=config,
        )

        # the fork's own architect, and a session for them — on the *fork's* database
        with use_database(names["fork"]):
            architect = auth.ensure_owner()
        cookie = auth.mint_session(architect.id, architect.epoch, owner=True)

        yield {
            "client": TestClient(app),
            "names": names,
            "fork": fork,
            "architect": architect,
            "cookie": cookie,
        }
    finally:
        reset_db_cache()
        reset_registry_cache()
        for name in names.values():
            try:
                if sys_db.has_database(name):
                    sys_db.delete_database(name)
            except Exception:  # pragma: no cover - best effort teardown
                pass
        client.close()


def _session(client, host, cookie):
    return client.get(
        f"http://{host}/api/v1/auth/session", cookies={auth.COOKIE_NAME: cookie}
    )


def test_a_fork_host_serves_the_forks_player(routed):
    """The regression, through the app: this goes via `player_manager`, which used to
    hold a repository built at import and so answered from the default database."""
    response = _session(routed["client"], f"{SLUG}.{BASE_DOMAIN}", routed["cookie"])

    assert response.status_code == 200
    assert response.json()["player"]["id"] == routed["architect"].id


def test_the_apex_host_does_not_see_a_forks_player(routed):
    """Same cookie, not a fork host: it must not resolve, because the player lives in
    the fork and the apex reads the default database."""
    response = _session(routed["client"], BASE_DOMAIN, routed["cookie"])

    assert response.status_code == 401


def test_a_fork_host_reads_the_forks_entities(routed):
    response = routed["client"].post(
        f"http://{SLUG}.{BASE_DOMAIN}/api/v1/graphql",
        json={"query": '{ entity(id: "%s") { id name } }' % PROBE_ENTITY},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "errors" not in payload, payload.get("errors")
    assert payload["data"]["entity"]["name"] == "Moscow"


def test_the_apex_does_not_read_a_forks_entity(routed):
    """The probe key exists only in the fork, so finding it at the apex would mean
    the scope leaked the other way."""
    response = routed["client"].post(
        f"http://{BASE_DOMAIN}/api/v1/graphql",
        json={"query": '{ entity(id: "%s") { id name } }' % PROBE_ENTITY},
    )

    assert response.status_code == 200
    assert response.json()["data"]["entity"] is None


def test_an_unknown_subdomain_is_refused_not_fallen_back_to(routed):
    response = routed["client"].get(f"http://typo.{BASE_DOMAIN}/api/v1/auth/session")

    assert response.status_code == 404


def test_the_tenancy_tier_is_reachable_from_a_fork_host(routed):
    """Signing in has to work on a campaign host, so those routes are never scoped
    into the campaign database — and therefore never 404 on an unknown label."""
    response = routed["client"].get(
        f"http://{SLUG}.{BASE_DOMAIN}/api/v1/accounts/session"
    )

    assert response.status_code == 401  # no account session — but the route exists

"""B255/B88 — the tenancy flow, end to end, against a real ArangoDB.

The unit tests cover every piece with fakes. What a fake cannot tell you is that the
registry is *actually* its own database, that a fork is *actually* a verbatim clone,
and that dropping one leaves nothing behind — and those are exactly where the live
database has already corrected me twice: a fresh fork's unique index silently
dropping the source's duplicate traits, and the `agency` edges into `players` that a
content-only fork has to prune.

Everything runs in databases named for this run and is dropped in teardown. The live
`transversal` database is never touched.
"""

import os
import uuid

import pytest
from arango import ArangoClient

from transversal.db.arango import ArangoConfig, get_db, reset_db_cache, use_database
from transversal.db.registry import (
    REGISTRY_COLLECTIONS,
    RegistryConfig,
    get_registry_db,
    reset_registry_cache,
)
from transversal.db.registry_repository import (
    PURPOSE_VERIFY,
    RegistryRepository,
)
from transversal.services import account_links
from transversal.services.provisioner import (
    campaign_databases,
    drop_fork,
    provision_fork,
)


@pytest.fixture
def live(monkeypatch):
    """A live ArangoDB, a clean cache, three probe databases, and their removal."""
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)  # the email links are signed
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
        "registry": f"tv2_test_registry_{run}",
        "source": f"tv2_test_source_{run}",
        "fork": f"tv2_test_fork_{run}",
    }
    reset_db_cache()
    reset_registry_cache()
    try:
        yield url, password, names, sys_db
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


def _campaign_config(url, password, database) -> ArangoConfig:
    return ArangoConfig(url=url, username="root", password=password, database=database)


def _registry_config(url, password, database) -> RegistryConfig:
    return RegistryConfig(url=url, username="root", password=password, database=database)


def _app_collections(db) -> list[str]:
    return sorted(c["name"] for c in db.collections() if not c["name"].startswith("_"))


def _build_source(url, password, name):
    """A small campaign: two entities, one content edge, one play edge."""
    ArangoClient(hosts=url).db("_system", username="root", password=password).create_database(name)
    with use_database(name):
        db = get_db()  # the real 20-collection bootstrap, as a campaign gets it
    db.collection("entities").insert_many(
        [{"_key": "loc-1", "name": "Moscow"}, {"_key": "loc-2", "name": "Krasnoyarsk"}]
    )
    db.collection("players").insert({"_key": "player-1", "name": "Andy"})
    db.collection("relationships").insert_many(
        [
            {"_key": "rel-1", "_from": "entities/loc-1", "_to": "entities/loc-2"},
            # an `agency` edge: play state, pointed at a player
            {"_key": "rel-2", "_from": "entities/loc-1", "_to": "players/player-1"},
        ]
    )
    return db


def test_the_registry_is_its_own_database(live):
    """The negative that matters: the tenancy table must not gain a campaign's schema."""
    url, password, names, sys_db = live

    db = get_registry_db(_registry_config(url, password, names["registry"]))

    assert sys_db.has_database(names["registry"])
    assert _app_collections(db) == sorted(REGISTRY_COLLECTIONS)
    assert "entities" not in _app_collections(db)


def test_the_tenancy_flow_end_to_end(live):
    url, password, names, sys_db = live
    source = _build_source(url, password, names["source"])
    registry = RegistryRepository(
        db=get_registry_db(_registry_config(url, password, names["registry"]))
    )

    # ── an account, registered and verified through its single-use link ──
    account = registry.create_account("Probe@Example.com")
    assert account.verified_at is None
    assert registry.find_account_by_email("probe@example.com").id == account.id

    token = account_links.issue(registry, account.id, PURPOSE_VERIFY)
    # the token's id, then nothing — a signed link cannot be recalled, so the record
    # is what makes it single-use
    assert account_links.consume(registry, token, PURPOSE_VERIFY)["account_id"] == account.id
    assert account_links.consume(registry, token, PURPOSE_VERIFY) is None
    assert registry.mark_email_verified(account.id).verified_at

    # ── a fork, cloned verbatim ──
    fork = provision_fork(
        registry,
        source_database=names["source"],
        name="Probe game",
        owner_account=account.id,
        database=names["fork"],
        slug="probe-game",
        config=_campaign_config(url, password, names["source"]),
    )
    assert registry.find_fork_by_slug("probe-game").id == fork.id

    fork_db = ArangoClient(hosts=url).db(
        names["fork"], username="root", password=password
    )
    # the same schema, and the documents that matter
    assert _app_collections(fork_db) == _app_collections(source)
    assert fork_db.collection("entities").count() == 2
    assert fork_db.collection("entities").get("loc-1")["name"] == "Moscow"

    # edges are untouched because nothing was remapped
    edge = fork_db.collection("relationships").get("rel-1")
    assert edge["_from"] == "entities/loc-1"
    assert edge["_to"] == "entities/loc-2"

    # play state is left behind — and the edge into it with it
    assert fork_db.collection("players").count() == 0
    assert source.collection("relationships").count() == 2
    assert fork_db.collection("relationships").count() == 1
    assert fork_db.collection("relationships").get("rel-2") is None

    # ── a schema change would visit both databases ──
    assert campaign_databases(registry, global_database=names["source"]) == [
        names["source"],
        names["fork"],
    ]

    # ── dropping it leaves nothing ──
    dropped = drop_fork(
        registry, fork.id, config=_campaign_config(url, password, names["source"])
    )
    assert dropped is True
    assert registry.get_fork(fork.id) is None
    assert registry.find_fork_by_slug("probe-game") is None
    assert sys_db.has_database(names["fork"]) is False

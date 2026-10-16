"""B88 — the connection cache is bounded, and a context can name its database.

Two properties that only matter once there is more than one campaign:

- the per-process cache must be an **LRU**, not a dict that grows for the process
  lifetime (correct for one campaign, unbounded at a thousand), and eviction must
  actually close the pool it drops;
- ``get_db()`` must be able to resolve to a **request-scoped** database, which is
  the seam per-request routing hangs off.

Both are asserted against a fake Arango client, so no server is involved.
"""

import arango
import pytest

from transversal.db import arango as db_module
from transversal.db.arango import (
    DEFAULT_DB_CACHE_MAX,
    ArangoConfig,
    _db_cache_max,
    current_database,
    get_db,
    reset_db_cache,
    use_database,
)


class _FakeCollection:
    def __init__(self, name):
        self.name = name

    def indexes(self):
        return []

    def add_index(self, spec):
        return spec


class _FakeDB:
    def __init__(self, name):
        self.name = name
        self.created: list[str] = []

    def has_collection(self, name):
        return name in self.created

    def create_collection(self, name, edge=False):
        self.created.append(name)

    def collection(self, name):
        return _FakeCollection(name)


class _FakeSysDB:
    def __init__(self, databases):
        self.databases = databases

    def has_database(self, name):
        return name in self.databases

    def create_database(self, name):
        self.databases.add(name)


class _FakeClient:
    instances: list["_FakeClient"] = []
    closed: list["_FakeClient"] = []

    def __init__(self, hosts=None):
        self.hosts = hosts
        self.sys_db = _FakeSysDB(set())
        self.dbs: dict[str, _FakeDB] = {}
        _FakeClient.instances.append(self)

    def db(self, name, **kwargs):
        if name == "_system":
            return self.sys_db
        return self.dbs.setdefault(name, _FakeDB(name))

    def close(self):
        _FakeClient.closed.append(self)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    reset_db_cache()
    _FakeClient.instances = []
    _FakeClient.closed = []
    monkeypatch.delenv("DB_CACHE_MAX", raising=False)
    monkeypatch.delenv("ARANGO_DATABASE", raising=False)
    monkeypatch.setattr(arango, "ArangoClient", _FakeClient)
    yield
    reset_db_cache()


def _config(database="transversal"):
    return ArangoConfig(
        url="http://arango:8529", username="root", password="x", database=database
    )


# ── The cache ─────────────────────────────────────────────────────────


def test_a_database_is_bootstrapped_once_and_reused():
    first = get_db(_config("tv2_a"))
    second = get_db(_config("tv2_a"))

    assert first is second
    assert len(_FakeClient.instances) == 1


def test_the_bound_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("DB_CACHE_MAX", "4")
    assert _db_cache_max() == 4


@pytest.mark.parametrize("bad", ["", "nonsense", "0", "-3"])
def test_a_bad_bound_falls_back_to_the_default(monkeypatch, bad):
    monkeypatch.setenv("DB_CACHE_MAX", bad)
    assert _db_cache_max() == DEFAULT_DB_CACHE_MAX


def test_eviction_drops_and_closes_the_least_recently_used(monkeypatch):
    monkeypatch.setenv("DB_CACHE_MAX", "2")

    get_db(_config("tv2_a"))
    get_db(_config("tv2_b"))
    get_db(_config("tv2_a"))  # touch A, so B is now the least recently used
    get_db(_config("tv2_c"))

    assert [list(client.dbs) for client in _FakeClient.closed] == [["tv2_b"]]
    # The evicted database is re-bootstrapped (a new client) if asked for again.
    before = len(_FakeClient.instances)
    get_db(_config("tv2_b"))
    assert len(_FakeClient.instances) == before + 1


def test_the_cache_never_exceeds_the_bound(monkeypatch):
    monkeypatch.setenv("DB_CACHE_MAX", "2")
    for name in ("tv2_a", "tv2_b", "tv2_c", "tv2_d"):
        get_db(_config(name))

    assert len(db_module._db_cache) == 2
    assert len(_FakeClient.closed) == 2


def test_reset_closes_every_cached_connection():
    get_db(_config("tv2_a"))
    get_db(_config("tv2_b"))

    reset_db_cache()

    assert db_module._db_cache == {}
    assert len(_FakeClient.closed) == 2


# ── Request-scoped resolution ─────────────────────────────────────────


def test_nothing_scoped_means_the_default_database():
    assert current_database() is None
    get_db()

    assert list(_FakeClient.instances[-1].dbs) == ["transversal"]


def test_a_scoped_database_overrides_the_env_default(monkeypatch):
    monkeypatch.setenv("ARANGO_DATABASE", "transversal")

    with use_database("tv2_fork_dave"):
        get_db()

    assert list(_FakeClient.instances[-1].dbs) == ["tv2_fork_dave"]


def test_the_scope_is_reset_after_the_block(monkeypatch):
    monkeypatch.setenv("ARANGO_DATABASE", "transversal")

    with use_database("tv2_fork_dave"):
        assert current_database() == "tv2_fork_dave"
        get_db()

    assert current_database() is None
    get_db()
    assert list(_FakeClient.instances[-1].dbs) == ["transversal"]


def test_an_explicit_config_is_not_overridden_by_the_scope():
    with use_database("tv2_fork_dave"):
        get_db(_config("tv2_explicit"))

    assert list(_FakeClient.instances[-1].dbs) == ["tv2_explicit"]


def test_a_scoped_request_is_cached_like_any_other_database():
    with use_database("tv2_fork_dave"):
        first = get_db()
        second = get_db()

    assert first is second
    assert len(_FakeClient.instances) == 1

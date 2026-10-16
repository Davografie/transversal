"""B255 — the registry bootstrap is its own, and never a campaign's.

The load-bearing property of the registry database is a **negative**: pointing the
tenancy table at a database must not create the 20 campaign collections that
``get_db()`` creates on first connect. That is asserted here directly, against a
fake Arango client, because it is exactly the mistake [[Identity Programme]] §2
warns about — and it would litter the registry silently.
"""

import pytest

from transversal.db import registry
from transversal.db.arango import COLLECTIONS


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
    def __init__(self):
        self.databases = {"_system"}

    def has_database(self, name):
        return name in self.databases

    def create_database(self, name):
        self.databases.add(name)


class _FakeClient:
    """Stands in for ``arango.ArangoClient``. Records what got created where."""

    instances: list["_FakeClient"] = []

    def __init__(self, hosts=None):
        self.hosts = hosts
        self.sys_db = _FakeSysDB()
        self.dbs: dict[str, _FakeDB] = {}
        _FakeClient.instances.append(self)

    def db(self, name, **kwargs):
        if name == "_system":
            return self.sys_db
        return self.dbs.setdefault(name, _FakeDB(name))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    registry.reset_registry_cache()
    _FakeClient.instances = []
    monkeypatch.setattr(registry, "ArangoClient", _FakeClient)
    yield
    registry.reset_registry_cache()


def _config(database="transversal_registry"):
    return registry.RegistryConfig(
        url="http://arango:8529", username="root", password="x", database=database
    )


def test_the_bootstrap_creates_only_the_registry_schema():
    db = registry.get_registry_db(_config())

    assert set(db.created) == set(registry.REGISTRY_COLLECTIONS)


def test_the_bootstrap_creates_none_of_the_campaign_collections():
    db = registry.get_registry_db(_config())

    campaign_names = set(COLLECTIONS)
    assert campaign_names, "the campaign schema should be non-empty"
    assert campaign_names.isdisjoint(set(db.created))


def test_the_registry_database_is_created_when_absent():
    registry.get_registry_db(_config(database="tv2_registry_new"))
    client = _FakeClient.instances[-1]

    assert "tv2_registry_new" in client.sys_db.databases
    assert client.dbs["tv2_registry_new"].created


def test_a_second_call_is_cached_and_does_not_rebootstrap():
    first = registry.get_registry_db(_config())
    created_after_first = list(first.created)
    second = registry.get_registry_db(_config())

    assert second is first
    assert second.created == created_after_first
    assert len(_FakeClient.instances) == 1


def test_the_database_name_is_configurable_from_env(monkeypatch):
    monkeypatch.setenv("REGISTRY_DATABASE", "tv2_tenancy")
    monkeypatch.setenv("ARANGO_URL", "http://arango:8529")

    assert registry.RegistryConfig.from_env().database == "tv2_tenancy"


def test_the_default_is_beside_the_campaign_database_not_inside_it(monkeypatch):
    monkeypatch.delenv("REGISTRY_DATABASE", raising=False)

    config = registry.RegistryConfig.from_env()
    assert config.database == registry.DEFAULT_REGISTRY_DATABASE
    assert config.database != "transversal"


def test_an_empty_database_name_means_unset_not_a_database_called_blank(monkeypatch):
    """Compose lists the variable and leaves it empty when `.env` does not set it,
    and `os.getenv(name, default)` returns "" for a variable that *is* set."""
    monkeypatch.setenv("REGISTRY_DATABASE", "")

    assert registry.RegistryConfig.from_env().database == registry.DEFAULT_REGISTRY_DATABASE


@pytest.fixture
def _no_live_client(monkeypatch):
    """Stops a *regressed* guard from creating a database on the real server.

    ``get_db()`` imports ``ArangoClient`` lazily from the real ``arango`` package, so
    that is where the patch has to go (the same trick ``test_db_cache.py`` uses). If
    the guard ever stops firing, the test raises here instead of quietly creating a
    database.
    """
    import arango as real_arango

    def _forbidden(*args, **kwargs):
        raise AssertionError("get_db() connected — the registry guard did not fire")

    monkeypatch.setattr(real_arango, "ArangoClient", _forbidden)


def test_get_db_refuses_the_registry_database(monkeypatch, _no_live_client):
    """The real defence: the campaign bootstrap cannot be pointed at the registry.

    The two tests above prove the *registry module* creates only its own schema.
    They cannot see the other direction, and that is how the live
    ``transversal_registry`` ended up carrying 19 empty campaign collections (found
    2026-10-16, with the full campaign indexes — the fingerprint of
    ``get_db()``'s collection loop). The guard fires before any connection is made.
    """
    from transversal.db import arango

    monkeypatch.setenv("REGISTRY_DATABASE", "tv2_registry_guard")
    config = arango.ArangoConfig(
        url="http://arango:8529", username="root", password="x",
        database="tv2_registry_guard",
    )

    with pytest.raises(RuntimeError, match="tenancy registry"):
        arango.get_db(config)


def test_a_request_scoped_registry_database_is_refused_too(monkeypatch, _no_live_client):
    """The scope is the other way in: `use_database("<registry>")` is enough."""
    from transversal.db import arango

    monkeypatch.setenv("REGISTRY_DATABASE", "tv2_registry_guard")
    monkeypatch.setenv("ARANGO_DATABASE", "transversal")

    with pytest.raises(RuntimeError, match="tenancy registry"):
        with arango.use_database("tv2_registry_guard"):
            arango.get_db()

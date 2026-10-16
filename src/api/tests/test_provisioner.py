"""B88 — fork provisioning clones content verbatim and routes the result.

No Arango: the source and target databases are fakes, and the routing table is the
real :class:`RegistryRepository` shape behind a small stub. What is under test is
the behaviour the fork model's cheapness rests on — ``_key`` preserved, edges left
untouched because nothing is remapped, play state left behind, and a routing row
written only once.
"""

import arango
import pytest

from transversal.db.arango import current_database
from transversal.domain.accounts import Fork
from transversal.services import provisioner
from transversal.services.provisioner import (
    PLAY_COLLECTIONS,
    clone_database,
    fork_database_name,
    provision_fork,
    source_collections,
)


class _FakeCollection:
    def __init__(self, docs=None, edge=False):
        self.docs = list(docs or [])
        self.edge = edge
        self.inserted: list[dict] = []

    def all(self):
        return [dict(doc) for doc in self.docs]

    def insert_many(self, docs, overwrite=False):
        self.inserted.extend(docs)

    def count(self):
        return len(self.docs) + len(self.inserted)

    def properties(self):
        return {"type": 3 if self.edge else 2}

    def indexes(self):
        return []

    def add_index(self, spec):
        return spec


class _LossyCollection(_FakeCollection):
    """A target that only accepts the first document — the silent-drop failure the
    count guard exists to catch."""

    def insert_many(self, docs, overwrite=False):
        self.inserted.extend(docs[:1])


class _FakeDB:
    def __init__(self, collections: dict):
        self._cols = collections

    def collections(self):
        return [{"name": name} for name in self._cols]

    def collection(self, name):
        return self._cols[name]

    def has_collection(self, name):
        return name in self._cols

    def create_collection(self, name, edge=False):
        self._cols[name] = _FakeCollection(edge=edge)


class _Registry:
    def __init__(self):
        self.forks: dict[str, Fork] = {}
        self.created = 0

    def find_fork_by_database(self, database):
        return self.forks.get(database)

    def create_fork(self, name, database, owner_account, *, kind="fork", slug=""):
        self.created += 1
        fork = Fork(
            id=f"fork-{self.created}",
            name=name,
            database=database,
            owner_account=owner_account,
            kind=kind,
            slug=slug,
        )
        self.forks[database] = fork
        return fork


def _campaign_db(**overrides):
    cols = {
        "entities": _FakeCollection(
            [{"_key": "loc-1", "_id": "entities/loc-1", "_rev": "x", "name": "Moscow"}]
        ),
        "relationships": _FakeCollection(
            [
                {"_key": "rel-1", "_from": "entities/loc-1", "_to": "entities/loc-2"},
                # An `agency` edge: ownership of a character, pointed at a player.
                {"_key": "rel-2", "_from": "entities/loc-1", "_to": "players/player-1"},
            ],
            edge=True,
        ),
        "players": _FakeCollection([{"_key": "player-1", "name": "Andy"}]),
        "historical_records": _FakeCollection([{"_key": "hist-1"}]),
    }
    cols.update(overrides)
    return _FakeDB(cols)


class _FakeSysDB:
    def __init__(self, databases):
        self.databases = databases

    def has_database(self, name):
        return name in self.databases


class _FakeClient:
    def __init__(self, hosts=None, databases=None):
        self.sys_db = _FakeSysDB(databases or set())
        self.closed = False

    def db(self, name, **kwargs):
        return self.sys_db

    def close(self):
        self.closed = True


# ── Naming ────────────────────────────────────────────────────────────


def test_a_fork_database_name_is_legible_and_unique():
    name = fork_database_name("Dave's Game!", suffix="abc123")

    assert name == "tv2_fork_dave_s_game_abc123"


def test_two_forks_of_the_same_name_get_different_databases():
    assert fork_database_name("Varenya") != fork_database_name("Varenya")


def test_a_long_name_is_truncated_to_fit():
    name = fork_database_name("x" * 200, suffix="abc123")

    assert len(name) <= 64
    assert name.endswith("_abc123")


def test_an_empty_name_still_yields_a_valid_database():
    assert fork_database_name("", suffix="abc123") == "tv2_fork_fork_abc123"


# ── The clone ─────────────────────────────────────────────────────────


def test_the_clone_keeps_keys_and_drops_local_handles():
    source = _campaign_db()
    target = _FakeDB({})

    clone_database(source, target)

    copied = target.collection("entities").inserted[0]
    assert copied["_key"] == "loc-1"
    assert "_id" not in copied and "_rev" not in copied


def test_edges_are_copied_untouched():
    source = _campaign_db()
    target = _FakeDB({})

    clone_database(source, target)

    edge = target.collection("relationships").inserted[0]
    assert edge["_from"] == "entities/loc-1"
    assert edge["_to"] == "entities/loc-2"


def test_an_edge_collection_is_recreated_as_an_edge():
    source = _campaign_db()
    target = _FakeDB({})

    clone_database(source, target)

    assert target.collection("relationships").edge is True


def test_play_state_is_not_copied_by_default():
    source = _campaign_db()
    target = _FakeDB({})

    report = clone_database(source, target)

    assert "players" not in report.copied
    assert PLAY_COLLECTIONS.isdisjoint(report.copied)
    assert report.copied["entities"] == 1


def test_the_first_migration_can_take_the_play_state_too():
    source = _campaign_db()
    target = _FakeDB({})

    report = clone_database(source, target, include_play=True)

    assert report.copied["players"] == 1
    assert target.collection("players").inserted[0]["name"] == "Andy"


def test_an_edge_into_a_skipped_collection_is_pruned():
    """`relationships` carries play edges (agency → players) as well as content
    ones; a content-only fork must not copy an edge into a document it skipped."""
    source = _campaign_db()
    target = _FakeDB({})

    report = clone_database(source, target)

    assert report.edges_dropped == {"relationships": 1}
    assert [e["_to"] for e in target.collection("relationships").inserted] == ["entities/loc-2"]


def test_the_first_migration_keeps_play_edges():
    source = _campaign_db()
    target = _FakeDB({})

    report = clone_database(source, target, include_play=True)

    assert report.edges_dropped == {}
    assert len(target.collection("relationships").inserted) == 2


def test_system_collections_are_never_touched():
    db = _campaign_db()
    db._cols["_analyzers"] = _FakeCollection([{"_key": "nope"}])

    assert source_collections(db) == sorted(n for n in db._cols if not n.startswith("_"))


def test_a_clone_that_loses_documents_fails_loudly():
    source = _FakeDB({"entities": _FakeCollection([{"_key": "a"}, {"_key": "b"}])})
    target = _FakeDB({"entities": _LossyCollection()})

    with pytest.raises(RuntimeError, match="entities"):
        clone_database(source, target)


# ── Provisioning ──────────────────────────────────────────────────────


@pytest.fixture
def wired(monkeypatch):
    """Point the provisioner at fakes for both databases and the server probe."""
    source = _campaign_db()
    target = _FakeDB({})
    monkeypatch.setattr(
        provisioner, "get_db", lambda config=None, **kwargs: source if config else target
    )
    monkeypatch.setattr(arango, "ArangoClient", lambda hosts=None: _FakeClient(hosts))
    return source, target


def test_provisioning_writes_the_routing_row(wired):
    registry = _Registry()

    fork = provision_fork(
        registry,
        source_database="transversal",
        name="Dave's game",
        owner_account="acct-1",
        database="tv2_fork_dave",
    )

    assert fork.database == "tv2_fork_dave"
    assert fork.owner_account == "acct-1"
    assert registry.forks["tv2_fork_dave"] is fork


def test_provisioning_copies_the_content(wired):
    _, target = wired

    provision_fork(
        _Registry(),
        source_database="transversal",
        name="Dave's game",
        owner_account="acct-1",
        database="tv2_fork_dave",
    )

    assert target.collection("entities").inserted[0]["_key"] == "loc-1"


def test_indexes_are_built_after_the_copy(wired, monkeypatch):
    """The ordering is load-bearing: an index built on the empty target would
    reject the source's own duplicate rows during the copy."""
    seen = {}

    def _record(db):
        seen["entities"] = len(db.collection("entities").inserted)

    monkeypatch.setattr(provisioner, "_ensure_indexes", _record)

    provision_fork(
        _Registry(),
        source_database="transversal",
        name="g",
        owner_account="a",
        database="tv2_fork_dave",
    )

    assert seen["entities"] == 1


def test_provisioning_the_same_fork_twice_does_not_clone_twice(wired):
    registry = _Registry()
    first = provision_fork(
        registry,
        source_database="transversal",
        name="g",
        owner_account="a",
        database="tv2_fork_dave",
    )

    second = provision_fork(
        registry,
        source_database="transversal",
        name="g",
        owner_account="a",
        database="tv2_fork_dave",
    )

    assert second is first
    assert registry.created == 1


def test_provisioning_refuses_an_orphan_database(wired, monkeypatch):
    """A database with no routing row is someone else's; do not clone into it."""
    monkeypatch.setattr(
        arango, "ArangoClient", lambda hosts=None: _FakeClient(hosts, {"tv2_fork_taken"})
    )

    with pytest.raises(ValueError):
        provision_fork(
            _Registry(),
            source_database="transversal",
            name="g",
            owner_account="a",
            database="tv2_fork_taken",
        )


def test_provisioning_does_not_leave_the_target_database_scoped(wired):
    provision_fork(
        _Registry(),
        source_database="transversal",
        name="g",
        owner_account="a",
        database="tv2_fork_dave",
    )

    assert current_database() is None

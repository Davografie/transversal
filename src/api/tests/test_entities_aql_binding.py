"""SEC-1 — the GraphQL ``universe`` argument must never reach AQL as text.

These exercise the repository mixin directly with a recording AQL stub, so no
ArangoDB connection is needed.
"""

from types import SimpleNamespace

from transversal.db.repository_mixins.entities import RepositoryEntities
from transversal.domain import EntityType

#: A payload that would rewrite the filter if it were interpolated.
INJECTION = "nope' OR e.type == 'location"


class _FakeAQL:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, query, bind_vars=None):
        self.calls.append((query, bind_vars or {}))
        return []


class _Repo(RepositoryEntities):
    def __init__(self):
        self.db = SimpleNamespace(aql=_FakeAQL())


def test_list_all_entities_binds_the_universe():
    repo = _Repo()
    repo.list_all_entities(INJECTION)
    query, binds = repo.db.aql.calls[-1]
    assert "@universe" in query
    assert INJECTION not in query
    assert binds["universe"] == INJECTION


def test_list_entities_by_type_binds_type_and_universe():
    repo = _Repo()
    repo.list_entities_by_type(EntityType.CHARACTER, INJECTION)
    query, binds = repo.db.aql.calls[-1]
    assert "@etype" in query and "@universe" in query
    assert INJECTION not in query
    assert binds == {"etype": EntityType.CHARACTER.value, "universe": INJECTION}


def test_list_entities_by_type_without_universe_binds_only_type():
    repo = _Repo()
    repo.list_entities_by_type(EntityType.CHARACTER)
    query, binds = repo.db.aql.calls[-1]
    assert "@universe" not in query
    assert binds == {"etype": EntityType.CHARACTER.value}

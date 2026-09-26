"""A tag-filtered timeline binds its tags, and does not reach for a name that is not there.

The repo mixin is exercised directly with a recording AQL stub, so no ArangoDB
connection is needed — and, deliberately, no in-memory double: the double has its
own ``get_timeline``, which is exactly why the defect this pins survived the suite.
``bind_vars["tags"] = tags`` named a variable that does not exist in the function
(the parameter is ``threads``), so every tag-filtered read raised ``NameError`` and
the unfiltered path — the common one — never noticed.
"""

from types import SimpleNamespace

from transversal.db.repository_mixins.messaging import RepositoryMessaging


class _FakeAQL:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, query, bind_vars=None):
        self.calls.append((query, bind_vars or {}))
        return []


class _Repo(RepositoryMessaging):
    def __init__(self):
        self.db = SimpleNamespace(aql=_FakeAQL())


def test_timeline_binds_the_thread_filter():
    repo = _Repo()
    repo.get_timeline(threads=["jian"])
    query, binds = repo.db.aql.calls[-1]
    assert "@tags" in query
    assert binds == {"tags": ["jian"]}


def test_timeline_binds_entity_and_threads_together():
    repo = _Repo()
    repo.get_timeline(entity_id="character-1", threads=["jian", "the lift"])
    query, binds = repo.db.aql.calls[-1]
    assert "@eid" in query and "@tags" in query
    assert binds == {"eid": "character-1", "tags": ["jian", "the lift"]}


def test_timeline_without_filters_binds_nothing():
    repo = _Repo()
    repo.get_timeline()
    query, binds = repo.db.aql.calls[-1]
    assert "FILTER" not in query
    assert binds == {}

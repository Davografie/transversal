"""B305 — the campaign scope: which campaign a piece of live state belongs to.

What is asserted here is the small set of decisions the stores depend on:

- a fork's **id** is preferred over its database name, because stored keys must not be
  inherited by a future database that reuses a name;
- a **database scope is enough** (migrations, the operator CLI, tests), falling back to
  the database name — still unique, just less durable;
- an unreachable registry must not break a request;
- with **no scope at all** the answer is ``""`` rather than a guess, because that is
  what the stores turn into *"deliver to nobody"*.
"""

import pytest

from transversal.db.arango import use_database
from transversal.services import campaign_scope
from transversal.services.campaign_scope import (
    Scope,
    campaign_for_database,
    capture_scope,
    current_campaign,
    reset_campaign_cache,
    use_campaign,
    use_scope,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_campaign_cache()
    monkeypatch.delenv("ARANGO_DATABASE", raising=False)
    yield
    reset_campaign_cache()


class _Fork:
    def __init__(self, id):
        self.id = id


@pytest.fixture
def registry(monkeypatch):
    """A registry whose row for ``transversal_global`` is a fork id."""
    calls = []

    class _Repo:
        def find_fork_by_database(self, database):
            calls.append(database)
            return _Fork("fork-5984d4ec9022") if database == "transversal_global" else None

    monkeypatch.setattr("transversal.db.registry_repository.RegistryRepository", _Repo)
    return calls


def test_a_fork_id_is_preferred_over_the_database_name(registry):
    assert campaign_for_database("transversal_global") == "fork-5984d4ec9022"


def test_a_database_with_no_routing_row_falls_back_to_its_name(registry):
    """A probe or a bare test database has no row, and must still be a scope."""
    assert campaign_for_database("tv2_fork_probe") == "tv2_fork_probe"


def test_a_database_with_an_id_less_fork_still_falls_back(monkeypatch):
    class _Repo:
        def find_fork_by_database(self, database):
            return _Fork("")

    monkeypatch.setattr("transversal.db.registry_repository.RegistryRepository", _Repo)

    assert campaign_for_database("transversal_global") == "transversal_global"


def test_an_unreachable_registry_is_not_fatal(monkeypatch):
    class _Repo:
        def find_fork_by_database(self, database):
            raise RuntimeError("registry is down")

    monkeypatch.setattr("transversal.db.registry_repository.RegistryRepository", _Repo)

    assert campaign_for_database("transversal_global") == "transversal_global"


def test_the_lookup_happens_once_per_database(registry):
    campaign_for_database("transversal_global")
    campaign_for_database("transversal_global")
    campaign_for_database("transversal_global")

    assert registry == ["transversal_global"]


def test_the_cache_can_be_dropped(registry):
    campaign_for_database("transversal_global")
    reset_campaign_cache()
    campaign_for_database("transversal_global")

    assert registry == ["transversal_global", "transversal_global"]


def test_a_database_scope_is_enough(registry):
    """`use_database` is what a migration, the CLI or a test provides."""
    with use_database("transversal_global"):
        assert current_campaign() == "fork-5984d4ec9022"


def test_no_scope_at_all_is_empty_not_a_guess():
    """The stores read this as "nobody", so it must never invent the default."""
    assert current_campaign() == ""


def test_an_explicit_campaign_wins_over_the_database(registry):
    with use_database("transversal_global"), use_campaign("fork-somewhere-else"):
        assert current_campaign() == "fork-somewhere-else"


def test_capture_and_reenter_restores_both_halves(registry):
    """This is how background work finds its way back (the media lesson)."""
    with use_database("transversal_global"), use_campaign("fork-5984d4ec9022"):
        captured = capture_scope()

    assert captured == Scope(database="transversal_global", campaign="fork-5984d4ec9022")
    # Out of scope: nothing is named, so live state goes nowhere rather than somewhere wrong.
    assert current_campaign() == ""

    with use_scope(captured):
        from transversal.db.arango import current_database

        assert current_database() == "transversal_global"
        assert current_campaign() == "fork-5984d4ec9022"

    assert current_campaign() == ""


def test_a_scope_without_a_database_still_names_the_campaign():
    with use_scope(Scope(database=None, campaign="fork-orphan")):
        assert current_campaign() == "fork-orphan"


def test_the_empty_campaign_is_a_real_answer():
    """`""` must not become a cache key that shadows a later real value."""
    campaign_scope.reset_campaign_cache()
    assert campaign_for_database("") == ""
    assert current_campaign() == ""

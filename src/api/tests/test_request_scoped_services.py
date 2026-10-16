"""B88 — the request's database must reach the services, not just the middleware.

The resolver sets a request-scoped database; that is worth nothing if the services
the request calls were built once at import and pinned to whichever database
happened to be first. This is the bug these tests exist for: `EntityManager`,
`RazmeritService` and `player_manager` were module-level singletons holding a
repository — so under forks they would read and write one campaign's players and
agency edges from every other campaign.

No Arango: a recording repository captures which database it was built against.
"""

from types import SimpleNamespace

import pytest

from transversal import main
from transversal.db import arango as arango_module
from transversal.db.arango import use_database
from transversal.services import player_manager as player_manager_module
from transversal.services.player_manager import PlayerManager


class _RecordingRepo:
    """Stands in for ``EntityRepository`` and remembers the scoped database."""

    built: list[str | None] = []

    def __init__(self, *args, **kwargs):
        self.database = arango_module.current_database()
        _RecordingRepo.built.append(self.database)


@pytest.fixture(autouse=True)
def _clear_recorded(monkeypatch):
    _RecordingRepo.built = []
    # The app's seam must be unset, or another module's in-memory repository would
    # win over the scoped one these tests are about.
    monkeypatch.setattr(main, "_repo", None)
    monkeypatch.setattr(main, "EntityRepository", _RecordingRepo)
    monkeypatch.setattr(player_manager_module, "EntityRepository", _RecordingRepo)


# ── The GraphQL services ──────────────────────────────────────────────


def test_the_entity_manager_follows_the_request_scope():
    with use_database("tv2_fork_dave"):
        manager = main._get_em()

    assert manager.repo.database == "tv2_fork_dave"


def test_the_razmerit_service_follows_the_request_scope():
    with use_database("tv2_fork_dave"):
        service = main._get_raz()

    assert service.repo.database == "tv2_fork_dave"


def test_the_repository_helper_follows_the_request_scope():
    with use_database("tv2_fork_dave"):
        repo = main._get_repo()

    assert repo.database == "tv2_fork_dave"


def test_a_second_request_gets_its_own_services():
    """The regression: a cached service would keep serving the first campaign."""
    with use_database("tv2_fork_one"):
        first = main._get_em()
    with use_database("tv2_fork_two"):
        second = main._get_em()

    assert first is not second
    assert (first.repo.database, second.repo.database) == ("tv2_fork_one", "tv2_fork_two")


def test_without_a_scope_the_default_database_is_used():
    """Single-database behaviour must be untouched — nothing sets a scope today."""
    assert main._get_repo().database is None


# ── The SFX registry, per campaign ────────────────────────────────────


class _SfxRepo:
    """A repository whose SFXs name the database they were read from."""

    def __init__(self, *args, **kwargs):
        self.database = arango_module.current_database()

    def get_all_sfxs(self):
        return [SimpleNamespace(id=f"sfx-{self.database or 'default'}")]


@pytest.fixture
def sfx_repo(monkeypatch):
    monkeypatch.setattr(main, "_repo", None)
    monkeypatch.setattr(main, "EntityRepository", _SfxRepo)
    monkeypatch.setattr(main, "_engines", {})
    # the engine seam must be unset, or every lookup would return it
    monkeypatch.setattr(main, "_effects_engine", None)


def test_each_campaign_gets_its_own_sfx_registry(sfx_repo):
    """A fork starts as a clone but may diverge, so a trigger must dispatch *that*
    campaign's definition — not the first one loaded."""
    with use_database("tv2_fork_dave"):
        daves = main._get_engine()
    with use_database("tv2_fork_ola"):
        olas = main._get_engine()

    assert daves is not olas
    assert daves.get("sfx-tv2_fork_dave") is not None
    assert daves.get("sfx-tv2_fork_ola") is None
    assert olas.get("sfx-tv2_fork_ola") is not None


def test_the_default_database_has_its_own_registry(sfx_repo):
    default = main._get_engine()
    with use_database("tv2_fork_dave"):
        forked = main._get_engine()

    assert default is not forked
    assert default.get("sfx-default") is not None
    assert default.get("sfx-tv2_fork_dave") is None


def test_the_registry_is_still_cached_within_a_campaign(sfx_repo):
    """Per database, not per request: it accumulates registrations, so rebuilding it
    would empty it."""
    with use_database("tv2_fork_dave"):
        assert main._get_engine() is main._get_engine()


# ── The player manager ────────────────────────────────────────────────


def test_the_player_manager_follows_the_request_scope():
    manager = PlayerManager()

    with use_database("tv2_fork_dave"):
        assert manager._repo.database == "tv2_fork_dave"


def test_the_player_manager_singleton_follows_the_request_scope():
    """The import-time singleton used by `auth` is the one that matters."""
    with use_database("tv2_fork_dave"):
        assert player_manager_module.player_manager._repo.database == "tv2_fork_dave"


def test_an_injected_repository_still_wins():
    sentinel = object()

    assert PlayerManager(repo=sentinel)._repo is sentinel

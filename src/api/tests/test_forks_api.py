"""B88/B256 — the account tier's forks API.

The portal surface in the shape it should have: a route group on the one API, not a
second service. What is asserted here is who may see what, and that creation is
**closed until it is opened** — the design leaves "who may create a campaign" to the
owner, so the route must not quietly become self-service.

No Arango: the registry is the real repository over fake collections.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.api import account_auth, auth
from transversal.api import forks as forks_mod
from transversal.db import registry
from transversal.db.registry_repository import RegistryRepository

GOOD_SECRET = "a" * 64


class _Collection:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def insert(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def get(self, key):
        found = self.docs.get(key)
        return dict(found) if found else None

    def update(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def find(self, filters, limit=None):
        rows = [
            dict(doc)
            for doc in self.docs.values()
            if all(doc.get(k) == v for k, v in filters.items())
        ]
        return rows[:limit] if limit else rows


class _FakeDB:
    def __init__(self):
        self._cols = {
            registry.ACCOUNTS: _Collection(),
            registry.CAMPAIGNS: _Collection(),
            registry.ACCOUNT_TOKENS: _Collection(),
            registry.BLOBS: _Collection(),
        }

    def collection(self, name):
        return self._cols[name]


class _Request:
    def __init__(self, cookies=None):
        self.headers = {}
        self.cookies = cookies or {}
        self.url = SimpleNamespace(scheme="http")


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    monkeypatch.delenv("FORKS_ALLOW_CREATE", raising=False)
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)
    monkeypatch.delenv("GLOBAL_DATABASE", raising=False)


@pytest.fixture
def repo(monkeypatch):
    fake = RegistryRepository(db=_FakeDB())
    monkeypatch.setattr(forks_mod, "_repo", lambda: fake)
    monkeypatch.setattr(account_auth, "_repo", lambda: fake)
    return fake


def _as(account) -> _Request:
    cookie = account_auth.mint_account_session(account.id, account.epoch)
    return _Request(cookies={account_auth.COOKIE_NAME: cookie})


# ── Listing ───────────────────────────────────────────────────────────


async def test_listing_requires_an_account_session(repo):
    with pytest.raises(HTTPException) as exc:
        await forks_mod.list_my_forks(_Request())

    assert exc.value.status_code == 401


async def test_a_player_session_cannot_list_forks(repo):
    """The tiers do not blur: a campaign cookie is not an account cookie."""
    request = _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})

    with pytest.raises(HTTPException) as exc:
        await forks_mod.list_my_forks(request)

    assert exc.value.status_code == 401


async def test_listing_returns_only_my_forks(repo):
    mine = repo.create_account("dave@example.com")
    theirs = repo.create_account("other@example.com")
    repo.create_fork("Mine", "tv2_fork_mine", mine.id, slug="mine")
    repo.create_fork("Theirs", "tv2_fork_theirs", theirs.id, slug="theirs")

    listed = await forks_mod.list_my_forks(_as(mine))

    assert [f["name"] for f in listed] == ["Mine"]
    assert listed[0]["slug"] == "mine"
    assert listed[0]["database"] == "tv2_fork_mine"


async def test_the_listing_carries_the_routing_url(repo, monkeypatch):
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    account = repo.create_account("dave@example.com")
    repo.create_fork("Dave's game", "tv2_fork_dave", account.id, slug="daves-game")

    listed = await forks_mod.list_my_forks(_as(account))

    assert listed[0]["url"] == "https://daves-game.transversal.app"


async def test_there_is_no_url_without_a_configured_base_domain(repo):
    account = repo.create_account("dave@example.com")
    repo.create_fork("Dave's game", "tv2_fork_dave", account.id, slug="daves-game")

    assert (await forks_mod.list_my_forks(_as(account)))[0]["url"] is None


# ── Creating ──────────────────────────────────────────────────────────


async def test_creating_is_refused_until_it_is_opened(repo):
    account = repo.create_account("dave@example.com")

    with pytest.raises(HTTPException) as exc:
        await forks_mod.create_fork(_as(account), {"name": "Dave's game"})

    assert exc.value.status_code == 403
    assert repo.list_forks_for(account.id) == []


@pytest.fixture
def open_creation(monkeypatch):
    monkeypatch.setenv("FORKS_ALLOW_CREATE", "true")


async def test_creating_requires_a_name(repo, open_creation):
    account = repo.create_account("dave@example.com")

    with pytest.raises(HTTPException) as exc:
        await forks_mod.create_fork(_as(account), {"name": "   "})

    assert exc.value.status_code == 400


async def test_creating_refuses_a_taken_address(repo, open_creation):
    account = repo.create_account("dave@example.com")
    repo.create_fork("Taken", "tv2_fork_taken", account.id, slug="daves-game")

    with pytest.raises(HTTPException) as exc:
        await forks_mod.create_fork(_as(account), {"name": "Dave's game", "slug": "daves-game"})

    assert exc.value.status_code == 409


async def test_creating_provisions_and_returns_the_fork(repo, open_creation, monkeypatch):
    calls = {}

    def _stub(registry_repo, *, source_database, name, owner_account, slug="", **kwargs):
        calls.update(source=source_database, name=name, owner=owner_account, slug=slug)
        return registry_repo.create_fork(name, "tv2_fork_new", owner_account, slug=slug)

    monkeypatch.setattr(forks_mod, "provision_fork", _stub)
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")
    account = repo.create_account("dave@example.com")

    created = await forks_mod.create_fork(_as(account), {"name": "Dave's Game!"})

    assert calls == {
        "source": "transversal",
        "name": "Dave's Game!",
        "owner": account.id,
        "slug": "dave-s-game",
    }
    assert created["slug"] == "dave-s-game"
    assert created["url"] == "https://dave-s-game.transversal.app"
    assert repo.find_fork_by_slug("dave-s-game").id == created["id"]


async def test_creating_clones_from_the_configured_global(repo, open_creation, monkeypatch):
    seen = {}

    def _stub(registry_repo, *, source_database, name, owner_account, slug="", **kwargs):
        seen["source"] = source_database
        return registry_repo.create_fork(name, "tv2_fork_new", owner_account, slug=slug)

    monkeypatch.setattr(forks_mod, "provision_fork", _stub)
    monkeypatch.setenv("GLOBAL_DATABASE", "transversal_global")
    account = repo.create_account("dave@example.com")

    await forks_mod.create_fork(_as(account), {"name": "Dave's game"})

    assert seen["source"] == "transversal_global"


async def test_creating_is_capped_per_account(repo, open_creation, monkeypatch):
    """A public invitation must not let one account clone the world without limit."""
    monkeypatch.setenv("FORKS_MAX_PER_ACCOUNT", "2")
    counter = {"n": 0}

    def _stub(registry_repo, *, name, owner_account, slug="", **_):
        counter["n"] += 1
        return registry_repo.create_fork(
            name, f"tv2_fork_{counter['n']}", owner_account, slug=slug
        )

    monkeypatch.setattr(forks_mod, "provision_fork", _stub)
    account = repo.create_account("dave@example.com")

    for i in range(2):
        await forks_mod.create_fork(_as(account), {"name": f"Game {i}"})

    with pytest.raises(HTTPException) as exc:
        await forks_mod.create_fork(_as(account), {"name": "One too many"})

    assert exc.value.status_code == 409
    assert "limit is 2" in exc.value.detail
    assert len(repo.list_forks_for(account.id)) == 2, "the refusal must not have created one"


async def test_the_cap_is_two_and_a_bad_setting_cannot_remove_it(monkeypatch):
    monkeypatch.delenv("FORKS_MAX_PER_ACCOUNT", raising=False)
    assert forks_mod.max_forks_per_account() == 2
    for raw in ("", "  ", "nonsense", "0", "-3"):
        monkeypatch.setenv("FORKS_MAX_PER_ACCOUNT", raw)
        assert forks_mod.max_forks_per_account() == 2, raw


async def test_the_global_and_playroom_do_not_use_up_the_cap(repo, open_creation, monkeypatch):
    """An operator owns the global and the playroom as infrastructure — those must not
    spend a normal account's campaign allowance (measured 2026-10-17: the owner owns both)."""
    monkeypatch.setenv("FORKS_MAX_PER_ACCOUNT", "1")

    def _stub(registry_repo, *, name, owner_account, slug="", **_):
        return registry_repo.create_fork(name, "tv2_fork_new", owner_account, slug=slug)

    monkeypatch.setattr(forks_mod, "provision_fork", _stub)
    account = repo.create_account("dave@example.com")
    repo.create_fork("Global", "transversal_global", account.id, slug="global", kind="global")
    repo.create_fork("Playroom", "transversal", account.id, slug="playroom", kind="playroom")

    created = await forks_mod.create_fork(_as(account), {"name": "My game"})

    assert created["slug"] == "my-game"

"""B88 — entering a fork you own, without a second shared secret.

The account session lives on the portal host and is host-scoped, so it never
reaches ``<slug>.<base-domain>``. The bridge is a **single-use, short-lived token**
bound in the registry to one fork; the portal mints it and the fork's own host
redeems it for an architect campaign session.

What matters here is that it cannot be abused: single use, purpose-separated from
the email links, ownership re-checked at redemption, and the request scoped to the
fork's database while the architect seat is taken.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.api import account_auth, auth
from transversal.api import forks as forks_mod
from transversal.db import registry
from transversal.db.arango import current_database
from transversal.db.registry_repository import (
    PURPOSE_ENTER_FORK,
    PURPOSE_VERIFY,
    RegistryRepository,
)

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
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)


@pytest.fixture
def repo(monkeypatch):
    fake = RegistryRepository(db=_FakeDB())
    monkeypatch.setattr(forks_mod, "_repo", lambda: fake)
    monkeypatch.setattr(account_auth, "_repo", lambda: fake)
    return fake


@pytest.fixture
def owner(repo):
    account = repo.create_account("dave@example.com")
    return repo.mark_email_verified(account.id)


@pytest.fixture
def fork(repo, owner):
    return repo.create_fork("Dave's game", "tv2_fork_dave", owner.id, slug="daves-game")


def _as(account) -> _Request:
    cookie = account_auth.mint_account_session(account.id, account.epoch)
    return _Request(cookies={account_auth.COOKIE_NAME: cookie})


def _cookie(response, name="tv2_session") -> str:
    header = response.headers.get("set-cookie", "")
    for part in header.split(";"):
        if part.strip().startswith(f"{name}="):
            return part.strip().split("=", 1)[1]
    return ""


# ── Minting the link (the portal host) ────────────────────────────────


async def test_minting_requires_an_account_session(repo, fork):
    with pytest.raises(HTTPException) as exc:
        await forks_mod.enter_fork(_Request(), fork.id)

    assert exc.value.status_code == 401


async def test_minting_refuses_an_unknown_fork(repo, owner):
    with pytest.raises(HTTPException) as exc:
        await forks_mod.enter_fork(_as(owner), "fork-ghost")

    assert exc.value.status_code == 404


async def test_minting_refuses_someone_elses_fork(repo, fork):
    other = repo.mark_email_verified(repo.create_account("other@example.com").id)

    with pytest.raises(HTTPException) as exc:
        await forks_mod.enter_fork(_as(other), fork.id)

    assert exc.value.status_code == 403


async def test_minting_returns_a_single_use_link_bound_to_the_fork(repo, owner, fork, monkeypatch):
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")

    result = await forks_mod.enter_fork(_as(owner), fork.id)

    assert result["enter_url"].startswith("https://daves-game.transversal.app")
    assert result["expires_in"] == account_auth.account_links.ENTER_TTL_SECONDS
    record = repo.get_account_token(
        account_auth.access_tokens.verify(
            result["token"], account_auth.access_tokens.AUD_ACCOUNT_LINK
        )["token"]
    )
    assert record["purpose"] == PURPOSE_ENTER_FORK
    assert record["fork_id"] == fork.id
    assert record["account_id"] == owner.id


async def test_without_a_base_domain_the_link_is_relative(repo, owner, fork):
    result = await forks_mod.enter_fork(_as(owner), fork.id)

    assert result["enter_url"].startswith(account_auth.ENTER_PATH)


# ── Redeeming it (the fork's own host) ────────────────────────────────


@pytest.fixture
def architect(monkeypatch):
    """Stands in for `ensure_owner`, recording the database it was called in."""
    seen = {}
    player = SimpleNamespace(id="player-arch", epoch=3)

    def _ensure_owner():
        seen["database"] = current_database()
        return player

    monkeypatch.setattr(account_auth.auth, "ensure_owner", _ensure_owner)
    return seen


async def _mint(repo, owner, fork) -> str:
    return (await forks_mod.enter_fork(_as(owner), fork.id))["token"]


async def test_redeeming_enters_the_fork_as_its_architect(repo, owner, fork, architect):
    token = await _mint(repo, owner, fork)

    response = await account_auth.enter_fork(_Request(), token)

    assert response.status_code == 302
    # it took the architect seat *inside the fork's database*
    assert architect["database"] == fork.database
    assert current_database() is None  # and did not leak out of the request
    # and the cookie it issued is an owner session for that seat
    payload = auth.session_payload(_cookie(response))
    assert payload["player"] == "player-arch"
    assert payload["owner"] is True


async def test_the_link_is_single_use(repo, owner, fork, architect):
    token = await _mint(repo, owner, fork)

    first = await account_auth.enter_fork(_Request(), token)
    second = await account_auth.enter_fork(_Request(), token)

    assert first.status_code == 302
    assert second.status_code == 401


async def test_a_forged_link_is_refused(repo, owner, fork, architect):
    assert (await account_auth.enter_fork(_Request(), "not-a-token")).status_code == 401


async def test_a_verify_link_cannot_be_used_to_enter(repo, owner, fork, architect):
    """Purpose separation: the emailed links and the entry link share an audience,
    so the record's purpose is what keeps them apart."""
    verify = account_auth.account_links.issue(repo, owner.id, PURPOSE_VERIFY)

    assert (await account_auth.enter_fork(_Request(), verify)).status_code == 401


async def test_entry_is_refused_if_the_fork_changed_hands(repo, owner, fork, architect):
    token = await _mint(repo, owner, fork)
    other = repo.mark_email_verified(repo.create_account("other@example.com").id)
    # the fork now belongs to someone else — re-checked at redemption, not trusted
    # from the token
    repo.db.collection(registry.CAMPAIGNS).update(
        {**fork.model_dump(), "_key": fork.id, "owner_account": other.id}
    )

    assert (await account_auth.enter_fork(_Request(), token)).status_code == 401


async def test_entry_is_refused_for_an_unverified_account(repo, owner, fork, architect):
    token = await _mint(repo, owner, fork)
    account = repo.get_account(owner.id)
    account.verified_at = None
    repo.db.collection(registry.ACCOUNTS).update(
        {"_key": account.id, "email": account.email, "verified_at": None, "epoch": 0}
    )

    assert (await account_auth.enter_fork(_Request(), token)).status_code == 401

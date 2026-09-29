"""SEC-3 — who may open an admission window, who may close it, and who may revoke.

Any member may invite; only an architect may close everything or change
permissions. Both halves are asserted, because "any member may invite" is the
owner's decision and the *off switch* is what makes it safe.

No Arango: the join-token store is a fake collection and the player manager is
stubbed on the singleton that both modules already share.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.api import auth
from transversal.api.rest import access
from transversal.api.rest import players as players_mod
from transversal.db.repository_mixins.join_tokens import RepositoryJoinTokens

GOOD_SECRET = "a" * 64


class _Collection:
    def __init__(self):
        self.docs = {}

    def insert(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def get(self, key):
        found = self.docs.get(key)
        return dict(found) if found else None

    def update(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def all(self):
        return [dict(doc) for doc in self.docs.values()]


class _Repo(RepositoryJoinTokens):
    def __init__(self):
        self._join_tokens = _Collection()


class _Request:
    def __init__(self, cookies=None, forwarded_proto=None, scheme="http"):
        self.headers = {}
        self.cookies = cookies or {}
        if forwarded_proto is not None:
            self.headers["x-forwarded-proto"] = forwarded_proto
        self.url = SimpleNamespace(scheme=scheme)


def _player(pid="player-abc", role="player", epoch=0):
    return SimpleNamespace(id=pid, name="Andy", role=role, epoch=epoch)


def _as(player_id, epoch=0):
    return _Request(cookies={auth.COOKIE_NAME: auth.mint_session(player_id, epoch)})


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)


@pytest.fixture
def repo(monkeypatch):
    fake = _Repo()
    monkeypatch.setattr(access, "_repo", lambda: fake)
    return fake


@pytest.fixture
def as_player(monkeypatch):
    """Every lookup returns a plain player with a current epoch."""
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, epoch=0)
    )
    monkeypatch.setattr(players_mod.player_manager, "list_all", lambda: [_player()])


@pytest.fixture
def as_architect(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, role="architect", epoch=0)
    )
    monkeypatch.setattr(
        players_mod.player_manager, "list_all", lambda: [_player("player-arch", "architect")]
    )


# ── Opening a window ──────────────────────────────────────────────────


async def test_any_member_may_open_a_window(repo, as_player):
    result = await access.open_token(_as("player-abc"))
    assert result["token"]
    assert result["join_url"].startswith("/enter?s=")
    assert result["expires_at"]


async def test_an_opened_token_actually_resolves(repo, as_player):
    from transversal.services import join_tokens

    result = await access.open_token(_as("player-abc"))
    assert join_tokens.resolve_token(repo, result["token"]) is not None


async def test_an_unclaimed_session_cannot_open_a_window(repo, as_player):
    with pytest.raises(HTTPException) as exc:
        await access.open_token(_as_unclaimed())
    assert exc.value.status_code == 403


def _as_unclaimed():
    return _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)})


async def test_a_revoked_session_cannot_open_a_window(repo, monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, epoch=5)
    )
    with pytest.raises(HTTPException) as exc:
        await access.open_token(_as("player-abc", epoch=0))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("ttl", [0, -60, "nonsense"])
async def test_a_bad_lifetime_is_refused(repo, as_player, ttl):
    with pytest.raises(HTTPException) as exc:
        await access.open_token(_as("player-abc"), {"ttl_seconds": ttl})
    assert exc.value.status_code == 400


# ── Seeing and closing ────────────────────────────────────────────────


async def test_the_open_list_shows_what_is_open(repo, as_player):
    opened = await access.open_token(_as("player-abc"))
    listing = await access.list_tokens(_as("player-abc"))
    assert [row["id"] for row in listing] == [opened["id"]]


async def test_closing_removes_it_from_the_open_list(repo, as_player):
    opened = await access.open_token(_as("player-abc"))
    await access.close_token(opened["id"], _as("player-abc"))
    assert await access.list_tokens(_as("player-abc")) == []


async def test_closing_twice_is_a_404_not_a_crash(repo, as_player):
    opened = await access.open_token(_as("player-abc"))
    await access.close_token(opened["id"], _as("player-abc"))
    with pytest.raises(HTTPException) as exc:
        await access.close_token(opened["id"], _as("player-abc"))
    assert exc.value.status_code == 404


async def test_a_plain_member_cannot_close_everything(repo, as_player):
    await access.open_token(_as("player-abc"))
    with pytest.raises(HTTPException) as exc:
        await access.close_all_tokens(_as("player-abc"))
    assert exc.value.status_code == 403


async def test_an_architect_can_close_everything(repo, as_architect):
    await access.open_token(_as("player-arch"))
    await access.open_token(_as("player-arch"))
    assert (await access.close_all_tokens(_as("player-arch")))["closed"] == 2
    assert await access.list_tokens(_as("player-arch")) == []


# ── Revoke ────────────────────────────────────────────────────────────


async def test_a_plain_member_cannot_revoke(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, epoch=0)
    )
    with pytest.raises(HTTPException) as exc:
        await players_mod.revoke_player("player-other", _as("player-abc"))
    assert exc.value.status_code == 403


async def test_an_architect_revoking_another_player_bumps_their_epoch(monkeypatch):
    calls = {}

    def _revoke(pid):
        calls["pid"] = pid
        return 1

    monkeypatch.setattr(
        players_mod.player_manager,
        "get",
        lambda pid: _player(pid, role="architect" if pid == "player-arch" else "player"),
    )
    monkeypatch.setattr(players_mod.player_manager, "revoke_sessions", _revoke)
    result = await players_mod.revoke_player("player-abc", _as("player-arch"))
    assert result == {"player_id": "player-abc", "epoch": 1}
    assert calls["pid"] == "player-abc"


async def test_revoking_an_unknown_player_is_a_404(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager,
        "get",
        lambda pid: _player(pid, role="architect") if pid == "player-arch" else None,
    )
    with pytest.raises(HTTPException) as exc:
        await players_mod.revoke_player("player-ghost", _as("player-arch"))
    assert exc.value.status_code == 404


async def test_the_last_architect_cannot_be_revoked(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager,
        "get",
        lambda pid: _player(pid, role="architect"),
    )
    monkeypatch.setattr(
        players_mod.player_manager,
        "list_all",
        lambda: [_player("player-arch", role="architect")],
    )
    with pytest.raises(HTTPException) as exc:
        await players_mod.revoke_player("player-arch", _as("player-arch"))
    assert exc.value.status_code == 409


# ── Identity cannot be asserted through a path ────────────────────────


async def test_acting_as_another_player_is_refused(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, epoch=0)
    )
    with pytest.raises(HTTPException) as exc:
        await players_mod._self(_as("player-abc"), "player-someone-else")
    assert exc.value.status_code == 403


async def test_acting_as_yourself_is_allowed(monkeypatch):
    monkeypatch.setattr(
        players_mod.player_manager, "get", lambda pid: _player(pid, epoch=0)
    )
    me = await players_mod._self(_as("player-abc"), "player-abc")
    assert me.id == "player-abc"

"""SEC-5 and SEC-3 — the gate fails closed, and the cookie now *means* something.

Two things are asserted together because they are the same object: the session
cookie must fail closed when the signing key is unusable (SEC-5), and it must be
an identity claim that a join token can never be mistaken for (SEC-3).

Direct unit tests of the endpoint functions and dependencies: no app, no Arango,
no Redis. The repository is stubbed where a player lookup would otherwise be hit.
"""

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.api import access_tokens, auth

GOOD_SECRET = "a" * 64
GOOD_ARCHITECT_KEY = "arch-key"


class _Request:
    """Minimal stand-in for ``fastapi.Request``."""

    def __init__(self, cookies=None, forwarded_proto=None, scheme="http"):
        self.headers = {}
        self.cookies = cookies or {}
        if forwarded_proto is not None:
            self.headers["x-forwarded-proto"] = forwarded_proto
        self.url = SimpleNamespace(scheme=scheme)


def _player(pid="player-abc", role="player", epoch=0):
    return SimpleNamespace(id=pid, name="Andy", role=role, epoch=epoch)


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    monkeypatch.setenv("ARCHITECT_TOKEN", GOOD_ARCHITECT_KEY)


# ── SEC-5: fail closed ────────────────────────────────────────────────


def test_a_session_we_minted_is_valid():
    assert auth.session_is_valid(auth.mint_session("player-abc", 0)) is True


def test_an_unclaimed_session_is_valid_for_the_perimeter():
    """Admitted but not yet claimed is a real state — the roster picker needs it."""
    value = auth.mint_session(None, 0)
    assert auth.session_is_valid(value) is True
    assert auth.session_payload(value).get("player") is None


def test_an_expired_session_is_rejected():
    issued = time.time() - auth.COOKIE_MAX_AGE - 1
    stale = access_tokens.mint(
        {"player": "player-abc", "epoch": 0},
        auth.COOKIE_MAX_AGE,
        access_tokens.AUD_SESSION,
        now=issued,
    )
    assert auth.session_is_valid(stale) is False


def test_garbage_cookies_are_rejected():
    assert auth.session_is_valid("not-a-cookie") is False
    assert auth.session_is_valid("") is False
    assert auth.session_is_valid(None) is False


def test_empty_secret_fails_closed(monkeypatch):
    """With no secret, a cookie signed by the empty key must NOT validate.

    That value is computable by anyone, so accepting it would be a full bypass.
    """
    value = auth.mint_session("player-abc", 0)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert auth.session_is_valid(value) is False


def test_short_secret_fails_closed(monkeypatch):
    value = auth.mint_session("player-abc", 0)
    monkeypatch.setenv("SESSION_SECRET", "short")
    assert auth.session_is_valid(value) is False


# ── SEC-3: the cookie is an identity claim, and only a session passes ──


def test_a_join_token_is_not_a_valid_session():
    """An invite must never satisfy the gate as if it were a taken player."""
    join = access_tokens.mint(
        {"token": "join-abc"}, 600, access_tokens.AUD_JOIN
    )
    assert auth.session_is_valid(join) is False
    assert auth.session_payload(join) is None


# ── Dependencies that hand out identity ───────────────────────────────


async def test_require_player_refuses_an_unclaimed_session():
    with pytest.raises(HTTPException) as exc:
        await auth.require_player(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)})
        )
    assert exc.value.status_code == 403


async def test_require_player_refuses_a_missing_session():
    with pytest.raises(HTTPException) as exc:
        await auth.require_player(_Request())
    assert exc.value.status_code == 401


async def test_require_player_returns_the_taken_player(monkeypatch):
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: _player(pid))
    player = await auth.require_player(
        _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})
    )
    assert player.id == "player-abc"


async def test_a_revoked_session_is_refused(monkeypatch):
    """The epoch is the whole revoke mechanism: bump it and the cookie dies."""
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: _player(pid, epoch=1))
    with pytest.raises(HTTPException) as exc:
        await auth.require_player(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})
        )
    assert exc.value.status_code == 401


async def test_a_deleted_player_is_refused(monkeypatch):
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: None)
    with pytest.raises(HTTPException) as exc:
        await auth.require_player(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})
        )
    assert exc.value.status_code == 401


async def test_require_owner_refuses_a_plain_session(monkeypatch):
    """Ownership is what guards a destructive act — not the role."""
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: _player(pid))
    with pytest.raises(HTTPException) as exc:
        await auth.require_owner(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})
        )
    assert exc.value.status_code == 403


async def test_require_owner_refuses_an_architect_role_without_ownership(monkeypatch):
    """The separation this design turns on: an architect role grants nothing here."""
    monkeypatch.setattr(
        auth.player_manager, "get", lambda pid: _player(pid, role="architect")
    )
    with pytest.raises(HTTPException) as exc:
        await auth.require_owner(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0)})
        )
    assert exc.value.status_code == 403


async def test_require_owner_admits_an_owner_session(monkeypatch):
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: _player(pid))
    player = await auth.require_owner(
        _Request(cookies={auth.COOKIE_NAME: auth.mint_session("player-abc", 0, owner=True)})
    )
    assert player.id == "player-abc"


# ── /enter ────────────────────────────────────────────────────────────


async def test_enter_returns_503_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    resp = await auth.enter(_Request(), s="anything")
    assert resp.status_code == 503


async def test_enter_needs_some_credential():
    resp = await auth.enter(_Request())
    assert resp.status_code == 401


async def test_enter_rejects_a_closed_or_forged_join_token(monkeypatch):
    monkeypatch.setattr(auth.join_tokens, "resolve_token", lambda repo, token: None)
    resp = await auth.enter(_Request(), s="nope")
    assert resp.status_code == 401


async def test_enter_accepts_a_join_token_without_a_player(monkeypatch):
    monkeypatch.setattr(
        auth.join_tokens, "resolve_token", lambda repo, token: {"_key": "join-abc"}
    )
    resp = await auth.enter(_Request(), s="good")
    assert resp.status_code == 302
    cookie = resp.headers["set-cookie"]
    assert auth.COOKIE_NAME in cookie
    # The issued session admits the device but names nobody yet.
    value = cookie.split(f"{auth.COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert auth.session_payload(value).get("player") is None


async def test_enter_rejects_a_wrong_architect_key():
    resp = await auth.enter(_Request(), a="wrong")
    assert resp.status_code == 401


async def test_enter_accepts_the_architect_key_and_binds_its_seat(monkeypatch):
    monkeypatch.setattr(
        auth, "ensure_owner", lambda: _player("player-arch", role="architect")
    )
    resp = await auth.enter(_Request(), a=GOOD_ARCHITECT_KEY)
    assert resp.status_code == 302
    value = resp.headers["set-cookie"].split(f"{auth.COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert auth.session_payload(value)["player"] == "player-arch"


async def test_enter_marks_cookie_secure_behind_a_tls_edge(monkeypatch):
    monkeypatch.setattr(
        auth.join_tokens, "resolve_token", lambda repo, token: {"_key": "join-abc"}
    )
    resp = await auth.enter(_Request(forwarded_proto="https"), s="good")
    assert resp.status_code == 302
    assert "Secure" in resp.headers["set-cookie"]


async def test_enter_reads_the_first_hop_of_a_proto_list(monkeypatch):
    monkeypatch.setattr(
        auth.join_tokens, "resolve_token", lambda repo, token: {"_key": "join-abc"}
    )
    resp = await auth.enter(_Request(forwarded_proto="https, http"), s="good")
    assert "Secure" in resp.headers["set-cookie"]


async def test_enter_leaves_cookie_insecure_on_plain_http(monkeypatch):
    """Direct LAN access over HTTP must keep working until TLS is in front."""
    monkeypatch.setattr(
        auth.join_tokens, "resolve_token", lambda repo, token: {"_key": "join-abc"}
    )
    resp = await auth.enter(_Request(), s="good")
    assert resp.status_code == 302
    assert "Secure" not in resp.headers["set-cookie"]


# ── Taking a player ───────────────────────────────────────────────────


async def test_an_architect_account_can_be_taken(monkeypatch):
    """A role is not a boundary, so taking an architect is just playing someone else.

    What it must NOT do is grant ownership — that is established out of band, and
    `require_owner` is what enforces it, not this route.
    """
    monkeypatch.setattr(
        auth.player_manager, "get", lambda pid: _player(pid, role="architect")
    )
    resp = await auth.take(
        "player-arch", _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)})
    )
    assert resp.status_code == 200
    value = resp.headers["set-cookie"].split(f"{auth.COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert auth.session_payload(value)["player"] == "player-arch"


async def test_taking_a_player_binds_the_session(monkeypatch):
    monkeypatch.setattr(auth.player_manager, "get", lambda pid: _player(pid))
    resp = await auth.take(
        "player-abc", _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)})
    )
    assert resp.status_code == 200
    value = resp.headers["set-cookie"].split(f"{auth.COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert auth.session_payload(value)["player"] == "player-abc"


async def test_claiming_an_existing_name_is_refused(monkeypatch):
    """An existing name must be *taken* from the roster, never silently re-made."""
    monkeypatch.setattr(
        auth.player_manager, "find_by_name", lambda name: _player()
    )
    with pytest.raises(HTTPException) as exc:
        await auth.claim(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)}),
            {"name": "Andy"},
        )
    assert exc.value.status_code == 409


async def test_claiming_a_new_name_creates_and_binds(monkeypatch):
    monkeypatch.setattr(auth.player_manager, "find_by_name", lambda name: None)
    monkeypatch.setattr(
        auth.player_manager, "create", lambda name="": _player("player-new")
    )
    resp = await auth.claim(
        _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)}),
        {"name": "Margaret"},
    )
    assert resp.status_code == 200
    value = resp.headers["set-cookie"].split(f"{auth.COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert auth.session_payload(value)["player"] == "player-new"


async def test_claim_needs_a_name():
    with pytest.raises(HTTPException) as exc:
        await auth.claim(
            _Request(cookies={auth.COOKIE_NAME: auth.mint_session(None, 0)}), {"name": "  "}
        )
    assert exc.value.status_code == 400

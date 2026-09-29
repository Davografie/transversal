"""SEC-3 — the whole passage, end to end, against the real database.

Integration, not unit: the point is that the *pieces agree* — that a token minted
through the API is accepted at `/enter`, that the cookie it returns is the
identity, that taking a player survives a fresh request, that revoking kills it,
and that closing a window stops new arrivals.

Everything it creates it deletes, and it touches no existing player.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from transversal.api.auth import COOKIE_NAME
from transversal.db.repository import EntityRepository
from transversal.main import app

ARCH_KEY = "test-architect-key"


@pytest.fixture
def client(monkeypatch):
    # Self-contained: the signing key is part of what these tests are about.
    monkeypatch.setenv("SESSION_SECRET", "a" * 64)
    monkeypatch.setenv("ARCHITECT_TOKEN", ARCH_KEY)
    return TestClient(app)


@pytest.fixture
def repo():
    return EntityRepository()


def _cookie(response) -> str:
    value = response.cookies.get(COOKIE_NAME)
    assert value, "expected a session cookie"
    return value


def _auth(cookie):
    return {COOKIE_NAME: cookie}


@pytest.fixture
def cleanup(repo):
    """Delete the players and tokens this test made. Never touches the rest."""
    players: list[str] = []
    tokens: list[str] = []
    yield players, tokens
    for pid in players:
        repo.delete_player(pid)
    for tid in tokens:
        try:
            repo._join_tokens.delete(tid)
        except Exception:
            pass


def _architect(client, cleanup):
    response = client.get(
        "/api/v1/auth/enter", params={"a": ARCH_KEY}, follow_redirects=False
    )
    assert response.status_code == 302
    return _cookie(response)


def _open_window(client, arch_cookie, cleanup) -> str:
    response = client.post("/api/v1/access/tokens", json={}, cookies=_auth(arch_cookie))
    assert response.status_code == 200, response.text
    body = response.json()
    cleanup[1].append(body["id"])
    return body["token"]


def test_a_token_admits_a_device_with_no_player_yet(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)

    response = client.get(
        "/api/v1/auth/enter", params={"s": token}, follow_redirects=False
    )
    assert response.status_code == 302
    device = _cookie(response)

    who = client.get("/api/v1/auth/session", cookies=_auth(device))
    assert who.status_code == 200
    assert who.json() == {"admitted": True, "player": None}

    # Admitted, but it may not act as anybody yet.
    assert client.get("/api/v1/auth/roster", cookies=_auth(device)).status_code == 200


def test_a_closed_window_admits_nobody(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)

    assert (
        client.post(
            f"/api/v1/access/tokens/{cleanup[1][-1]}/close", cookies=_auth(arch)
        ).status_code
        == 200
    )
    response = client.get(
        "/api/v1/auth/enter", params={"s": token}, follow_redirects=False
    )
    assert response.status_code == 401


def test_a_forged_token_admits_nobody(client):
    response = client.get(
        "/api/v1/auth/enter", params={"s": "not.a.token"}, follow_redirects=False
    )
    assert response.status_code == 401


def test_the_wrong_architect_key_is_refused(client):
    response = client.get(
        "/api/v1/auth/enter", params={"a": "wrong"}, follow_redirects=False
    )
    assert response.status_code == 401


def test_claiming_a_new_player_binds_the_session(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)
    device = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )

    name = f"Test-{uuid.uuid4().hex[:8]}"
    claimed = client.post("/api/v1/auth/claim", json={"name": name}, cookies=_auth(device))
    assert claimed.status_code == 200, claimed.text
    player = claimed.json()["player"]
    cleanup[0].append(player["id"])

    # The response's cookie is the identity, and it survives a fresh request.
    bound = _cookie(claimed)
    who = client.get("/api/v1/auth/session", cookies=_auth(bound)).json()
    assert who["player"]["id"] == player["id"]
    assert who["player"]["role"] == "player"

    # Claiming the same name again must not silently re-make it.
    again = client.post(
        "/api/v1/auth/claim", json={"name": name}, cookies=_auth(device)
    )
    assert again.status_code == 409


def test_a_second_device_can_take_an_existing_player(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)

    first = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )
    name = f"Test-{uuid.uuid4().hex[:8]}"
    player = client.post(
        "/api/v1/auth/claim", json={"name": name}, cookies=_auth(first)
    ).json()["player"]
    cleanup[0].append(player["id"])

    second = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )
    taken = client.post(f"/api/v1/auth/take/{player['id']}", cookies=_auth(second))
    assert taken.status_code == 200, taken.text
    assert client.get(
        "/api/v1/auth/session", cookies=_auth(_cookie(taken))
    ).json()["player"]["id"] == player["id"]


def test_an_architect_account_is_takeable_and_in_the_roster(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)
    device = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )

    arch_id = client.get("/api/v1/auth/session", cookies=_auth(arch)).json()["player"]["id"]
    roster = client.get("/api/v1/auth/roster", cookies=_auth(device)).json()
    # Everyone is listed, architects included: a role is a UI mode, not a boundary.
    assert arch_id in [row["id"] for row in roster]

    taken = client.post(f"/api/v1/auth/take/{arch_id}", cookies=_auth(device))
    assert taken.status_code == 200
    # ...and taking it grants no ownership.
    who = client.get("/api/v1/auth/session", cookies=_auth(_cookie(taken))).json()
    assert who["player"]["id"] == arch_id
    assert who["player"]["is_owner"] is False


def test_revoking_a_player_kills_their_sessions(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)
    device = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )
    name = f"Test-{uuid.uuid4().hex[:8]}"
    claimed = client.post("/api/v1/auth/claim", json={"name": name}, cookies=_auth(device))
    player = claimed.json()["player"]
    cleanup[0].append(player["id"])
    bound = _cookie(claimed)

    assert client.get("/api/v1/auth/session", cookies=_auth(bound)).status_code == 200

    revoked = client.post(
        f"/api/v1/players/{player['id']}/revoke", cookies=_auth(arch)
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["epoch"] == 1

    # The same cookie is now refused, and on the next request — not eventually.
    after = client.get("/api/v1/auth/session", cookies=_auth(bound))
    assert after.status_code == 401
    assert client.get("/api/v1/auth/roster", cookies=_auth(bound)).status_code == 401


def test_a_plain_member_cannot_revoke_but_may_set_their_own_role(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)
    device = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )
    name = f"Test-{uuid.uuid4().hex[:8]}"
    player = client.post(
        "/api/v1/auth/claim", json={"name": name}, cookies=_auth(device)
    ).json()["player"]
    cleanup[0].append(player["id"])
    bound = client.get("/api/v1/auth/session", cookies=_auth(device))

    assert (
        client.post(f"/api/v1/players/{player['id']}/revoke", cookies=_auth(bound.cookies.get(COOKIE_NAME))).status_code
        == 403
    )
    # A role is self-service: the app's GM toggle has always written it back, and
    # it is not what guards anything.
    assert (
        client.patch(
            f"/api/v1/players/{player['id']}/role",
            json={"role": "architect"},
            cookies=_auth(bound.cookies.get(COOKIE_NAME)),
        ).status_code
        == 200
    )
    # ...but not someone else's.
    assert (
        client.patch(
            f"/api/v1/players/{player['id']}-other/role",
            json={"role": "architect"},
            cookies=_auth(bound.cookies.get(COOKIE_NAME)),
        ).status_code
        in (403, 404)
    )


def test_a_member_cannot_act_as_another_player(client, repo, cleanup):
    arch = _architect(client, cleanup)
    token = _open_window(client, arch, cleanup)
    device = _cookie(
        client.get("/api/v1/auth/enter", params={"s": token}, follow_redirects=False)
    )
    name = f"Test-{uuid.uuid4().hex[:8]}"
    player = client.post(
        "/api/v1/auth/claim", json={"name": name}, cookies=_auth(device)
    ).json()["player"]
    cleanup[0].append(player["id"])
    bound = client.get("/api/v1/auth/session", cookies=_auth(device)).cookies.get(COOKIE_NAME)

    # This is the shape of the old hole: assert someone else's id in the path.
    response = client.post(
        "/api/v1/players/player-someone-else/claim/some-entity", cookies=_auth(bound)
    )
    assert response.status_code == 403


def test_no_session_cannot_read_the_roster_or_open_a_window(client):
    assert client.get("/api/v1/auth/roster").status_code == 401
    assert client.post("/api/v1/access/tokens", json={}).status_code == 401
    assert client.get("/api/v1/auth/session").status_code == 401


def test_the_old_player_creation_route_is_gone(client, repo, cleanup):
    """`POST /players` adopted a player by name. It must not exist at all."""
    arch = _architect(client, cleanup)
    response = client.post("/api/v1/players", json={"name": "Anyone"}, cookies=_auth(arch))
    assert response.status_code in (404, 405)

"""B255 — the account auth surface, and the tier separation it must not blur.

The whole point of SEC-3 is that identity is server-issued per campaign. An account
session that can act as a player hands that back to the client, so the two tiers are
separated by cookie name *and* audience and both directions are asserted here — a
convention would not survive the first refactor.

No Arango: the registry repository runs against fake collections, and the mailer
records instead of sending so a test can follow the link it "received".
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.api import access_tokens, account_auth, auth
from transversal.db import registry
from transversal.db.registry_repository import RegistryRepository
from transversal.services import mailer

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
    def __init__(self, cookies=None, scheme="http"):
        self.headers = {}
        self.cookies = cookies or {}
        self.url = SimpleNamespace(scheme=scheme)


class _RecordingMailer:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})

    def link_token(self, index=-1) -> str:
        body = self.sent[index]["body"]
        return body.split("?t=", 1)[1].split("\n", 1)[0].strip()


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    # The send cap has its own tests; here it is always open, so a suite that
    # registers the same address repeatedly is not silently throttled.
    monkeypatch.setattr(account_auth.send_limits, "allow_send", lambda *a, **k: True)
    # Where an emailed link points is its own test; make it deterministic rather
    # than dependent on the machine's `.env`.
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)


@pytest.fixture
def repo(monkeypatch):
    fake = RegistryRepository(db=_FakeDB())
    monkeypatch.setattr(account_auth, "_repo", lambda: fake)
    return fake


@pytest.fixture
def outbox(monkeypatch):
    recorder = _RecordingMailer()
    monkeypatch.setattr(mailer, "get_mailer", lambda: recorder)
    return recorder


def _cookie(response, name=account_auth.COOKIE_NAME):
    """The cookie value out of a response's Set-Cookie header."""
    header = response.headers.get("set-cookie", "")
    for part in header.split(";"):
        if part.strip().startswith(f"{name}="):
            return part.strip().split("=", 1)[1]
    return None


def _body(response):
    return json.loads(response.body)


async def _verified_account(repo, outbox, email="dave@example.com"):
    await account_auth.register(_Request(), {"email": email})
    response = await account_auth.verify(_Request(), outbox.link_token())
    return response, repo.find_account_by_email(email)


# ── Register ──────────────────────────────────────────────────────────


async def test_register_creates_an_account_and_mails_a_link(repo, outbox):
    result = await account_auth.register(_Request(), {"email": "Dave@Example.com"})

    assert result == {"sent": True}
    assert repo.find_account_by_email("dave@example.com").verified_at is None
    assert len(outbox.sent) == 1
    assert outbox.sent[0]["to"] == "dave@example.com"


@pytest.mark.parametrize("bad", ["", "nope", "a@b", "@example.com", "dave@.com"])
async def test_register_refuses_a_bad_address(repo, outbox, bad):
    with pytest.raises(HTTPException) as exc:
        await account_auth.register(_Request(), {"email": bad})
    assert exc.value.status_code == 400
    assert outbox.sent == []


async def test_register_does_not_remail_a_verified_account(repo, outbox):
    await _verified_account(repo, outbox)
    outbox.sent.clear()

    result = await account_auth.register(_Request(), {"email": "dave@example.com"})

    assert result == {"sent": True}
    assert outbox.sent == []


async def test_register_is_refused_when_the_secret_is_unusable(repo, outbox, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc:
        await account_auth.register(_Request(), {"email": "dave@example.com"})
    assert exc.value.status_code == 503


# ── Verify ────────────────────────────────────────────────────────────


async def test_verify_spends_the_link_and_signs_in(repo, outbox):
    response, account = await _verified_account(repo, outbox)

    assert response.status_code == 302
    assert account.verified_at
    cookie = _cookie(response)
    assert cookie
    resolved = account_auth.resolve_account_session(
        _Request(cookies={account_auth.COOKIE_NAME: cookie})
    )
    assert resolved is not None
    assert resolved[1].id == account.id


async def test_the_session_endpoint_reports_the_account(repo, outbox):
    response, account = await _verified_account(repo, outbox)
    cookie = _cookie(response)

    who = await account_auth.whoami(
        _Request(cookies={account_auth.COOKIE_NAME: cookie})
    )

    assert who.status_code == 200
    assert _body(who)["account"]["email"] == "dave@example.com"
    assert _body(who)["account"]["id"] == account.id


async def test_a_link_is_single_use(repo, outbox):
    response, _ = await _verified_account(repo, outbox)
    token = outbox.link_token()

    second = await account_auth.verify(_Request(), token)

    assert second.status_code == 401


async def test_a_sign_in_link_is_not_a_verification_link(repo, outbox):
    response, _ = await _verified_account(repo, outbox)
    await account_auth.request_sign_in(_Request(), {"email": "dave@example.com"})
    sign_in_token = outbox.link_token()

    refused = await account_auth.verify(_Request(), sign_in_token)

    assert refused.status_code == 401


async def test_a_forged_link_is_refused(repo, outbox):
    assert (await account_auth.verify(_Request(), "not-a-token")).status_code == 401


# ── Sign in and recover ───────────────────────────────────────────────


async def test_sign_in_is_silent_for_an_unknown_address(repo, outbox):
    result = await account_auth.request_sign_in(_Request(), {"email": "nobody@example.com"})

    assert result == {"sent": True}
    assert outbox.sent == []


async def test_sign_in_does_not_mail_an_unverified_account(repo, outbox):
    await account_auth.register(_Request(), {"email": "dave@example.com"})
    outbox.sent.clear()

    result = await account_auth.request_sign_in(_Request(), {"email": "dave@example.com"})

    assert result == {"sent": True}
    assert outbox.sent == []


async def test_sign_in_mails_a_verified_account_and_the_link_signs_in(repo, outbox):
    await _verified_account(repo, outbox)
    outbox.sent.clear()

    await account_auth.request_sign_in(_Request(), {"email": "dave@example.com"})
    response = await account_auth.confirm_sign_in(_Request(), outbox.link_token())

    assert response.status_code == 302
    assert _cookie(response)


async def test_recovery_is_the_same_mechanism_as_sign_in(repo, outbox):
    await _verified_account(repo, outbox)
    outbox.sent.clear()

    await account_auth.recover(_Request(), {"email": "dave@example.com"})
    response = await account_auth.confirm_sign_in(_Request(), outbox.link_token())

    assert response.status_code == 302
    assert _cookie(response)


async def test_an_expired_link_is_refused(repo, outbox):
    """The signed payload carries ``exp``; minting one for the past is enough."""
    account_id = repo.create_account("dave@example.com").id
    repo.mark_email_verified(account_id)
    stale = access_tokens.mint(
        {"token": repo.create_account_token(account_id, "sign_in", "2000-01-01T00:00:00+00:00")},
        1,
        access_tokens.AUD_ACCOUNT_LINK,
        now=0,
    )

    assert (await account_auth.confirm_sign_in(_Request(), stale)).status_code == 401


# ── The separation between the two tiers ──────────────────────────────


async def test_an_account_session_is_not_a_player_session(repo, outbox):
    response, _ = await _verified_account(repo, outbox)
    account_cookie = _cookie(response)
    request = _Request(cookies={auth.COOKIE_NAME: account_cookie})

    assert auth.resolve_session(request) is None
    assert auth.session_is_valid(account_cookie) is False
    with pytest.raises(HTTPException) as exc:
        await auth.require_session(request)
    assert exc.value.status_code == 401


async def test_a_player_session_is_not_an_account_session(repo, outbox):
    player_cookie = auth.mint_session("player-abc", 0)
    request = _Request(cookies={account_auth.COOKIE_NAME: player_cookie})

    assert account_auth.resolve_account_session(request) is None
    with pytest.raises(HTTPException) as exc:
        await account_auth.require_account(request)
    assert exc.value.status_code == 401


async def test_a_revoked_account_session_is_dead(repo, outbox):
    response, account = await _verified_account(repo, outbox)
    cookie = _cookie(response)
    repo.bump_account_epoch(account.id)

    assert account_auth.resolve_account_session(
        _Request(cookies={account_auth.COOKIE_NAME: cookie})
    ) is None


async def test_sign_out_clears_the_cookie():
    response = await account_auth.sign_out()

    assert _cookie(response).strip('"') == ""


# ── The send cap ──────────────────────────────────────────────────────


async def test_the_send_cap_silences_mail_but_not_the_answer(repo, outbox, monkeypatch):
    """A refusal the caller can see would be an oracle; the answer stays identical
    and the mail simply does not go out ([[Identity Programme]] §5.4)."""
    monkeypatch.setattr(account_auth.send_limits, "allow_send", lambda *a, **k: False)

    result = await account_auth.register(_Request(), {"email": "dave@example.com"})

    assert result == {"sent": True}
    assert outbox.sent == []
    assert repo.find_account_by_email("dave@example.com").verified_at is None


async def test_the_send_cap_silences_sign_in_too(repo, outbox, monkeypatch):
    await _verified_account(repo, outbox)
    outbox.sent.clear()
    monkeypatch.setattr(account_auth.send_limits, "allow_send", lambda *a, **k: False)

    result = await account_auth.request_sign_in(_Request(), {"email": "dave@example.com"})

    assert result == {"sent": True}
    assert outbox.sent == []


# ── Where an emailed link points ──────────────────────────────────────


async def test_the_emailed_link_is_absolute_when_an_origin_is_set(repo, outbox, monkeypatch):
    """An inbox has no page to be relative to."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://transversal.app")

    await account_auth.register(_Request(), {"email": "dave@example.com"})

    assert "https://transversal.app/api/v1/accounts/verify?t=" in outbox.sent[0]["body"]


async def test_the_origin_falls_back_to_the_fork_base_domain(repo, outbox, monkeypatch):
    monkeypatch.setenv("FORKS_BASE_DOMAIN", "transversal.app")

    await account_auth.register(_Request(), {"email": "dave@example.com"})

    assert "https://transversal.app/api/v1/accounts/verify?t=" in outbox.sent[0]["body"]


async def test_without_an_origin_the_link_stays_relative(repo, outbox):
    await account_auth.register(_Request(), {"email": "dave@example.com"})

    body = outbox.sent[0]["body"]
    assert "/api/v1/accounts/verify?t=" in body
    assert "https://" not in body

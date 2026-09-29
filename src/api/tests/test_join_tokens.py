"""SEC-3 — join-token liveness and resolution.

No Arango: the mixin is exercised against a fake collection, so what is tested is
the real close/list code and the real resolve path. The point of the suite is the
negative space — a token that is closed, forged, expired, of the wrong audience,
or naming a record that does not exist must all resolve to nothing.
"""

import pytest

from transversal.api import access_tokens
from transversal.db.repository_mixins.join_tokens import RepositoryJoinTokens
from transversal.services import join_tokens as service

GOOD_SECRET = "a" * 64


class _Collection:
    """The sliver of the Arango collection API the mixin uses."""

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


@pytest.fixture(autouse=True)
def _usable_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)


@pytest.fixture
def repo():
    return _Repo()


def test_a_new_token_is_open_and_dated(repo):
    token, record = service.open_token(repo, created_by="player-abc", ttl_seconds=60)
    assert record["closed_at"] is None
    assert record["created_by"] == "player-abc"
    assert record["expires_at"], "the record must carry its deadline for the open list"
    assert service.resolve_token(repo, token) is not None


def test_closing_a_token_stops_it_resolving(repo):
    token, record = service.open_token(repo, ttl_seconds=60)
    assert repo.close_join_token(record["_key"], closed_by="player-abc") is True
    assert service.resolve_token(repo, token) is None
    assert not service.is_open(repo, record["_key"])


def test_closing_twice_reports_the_second_as_a_no_op(repo):
    _, record = service.open_token(repo, ttl_seconds=60)
    assert repo.close_join_token(record["_key"]) is True
    assert repo.close_join_token(record["_key"]) is False


def test_closing_an_unknown_token_is_false_not_an_error(repo):
    assert repo.close_join_token("join-does-not-exist") is False


def test_listing_can_show_only_open_tokens(repo):
    _, first = service.open_token(repo, ttl_seconds=60)
    service.open_token(repo, ttl_seconds=60)
    repo.close_join_token(first["_key"])
    assert len(repo.list_join_tokens(open_only=True)) == 1
    assert len(repo.list_join_tokens(open_only=False)) == 2


def test_closing_all_closes_every_open_token(repo):
    service.open_token(repo, ttl_seconds=60)
    service.open_token(repo, ttl_seconds=60)
    _, already = service.open_token(repo, ttl_seconds=60)
    repo.close_join_token(already["_key"])
    assert repo.close_all_join_tokens(closed_by="player-abc") == 2
    assert repo.list_join_tokens(open_only=True) == []


def test_a_forged_token_resolves_to_nothing(repo):
    _, record = service.open_token(repo, ttl_seconds=60)
    forged = access_tokens._b64_encode(
        b'{"token":"' + record["_key"].encode() + b'","aud":"join","exp":9999999999}'
    )
    assert service.resolve_token(repo, f"{forged}.deadbeef") is None


def test_a_token_for_a_record_that_does_not_exist_resolves_to_nothing(repo, monkeypatch):
    """A validly signed token whose record was never written must not admit."""
    token = access_tokens.mint(
        {"token": "join-never-created"}, 60, access_tokens.AUD_JOIN
    )
    assert service.resolve_token(repo, token) is None


def test_a_session_cookie_is_not_a_join_token(repo):
    """Audience separation, at the layer that actually admits people."""
    _, record = service.open_token(repo, ttl_seconds=60)
    wrong_audience = access_tokens.mint(
        {"token": record["_key"]}, 60, access_tokens.AUD_SESSION
    )
    assert service.resolve_token(repo, wrong_audience) is None


def test_a_token_without_an_id_resolves_to_nothing(repo):
    token = access_tokens.mint({"something": "else"}, 60, access_tokens.AUD_JOIN)
    assert service.resolve_token(repo, token) is None


@pytest.mark.parametrize("token", ["", "garbage", "a.b", "..."])
def test_junk_never_raises(repo, token):
    assert service.resolve_token(repo, token) is None

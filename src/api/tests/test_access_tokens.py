"""SEC-3 groundwork — signed, expiring admission tokens.

Machinery only: nothing in the application mints or verifies a token yet. What is
asserted here is the part that must not be got wrong later — that a token cannot
be forged, cannot outlive its deadline, and cannot be minted at all when the
signing key is unusable.
"""

import time

import pytest

from transversal.api import access_tokens, auth

GOOD_SECRET = "a" * 64


@pytest.fixture(autouse=True)
def _usable_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)


def _mint(payload=None, ttl=1800, now=None):
    return access_tokens.mint(payload or {"scope": "join"}, ttl, now=now)


def test_round_trip_returns_the_payload():
    token = _mint({"scope": "join", "campaign": "emberline"})
    payload = access_tokens.verify(token)
    assert payload is not None
    assert payload["scope"] == "join"
    assert payload["campaign"] == "emberline"


def test_issued_and_expiry_are_derived_from_the_ttl():
    token = _mint(ttl=1800, now=1_000_000)
    payload = access_tokens.verify(token, now=1_000_000)
    assert payload["iat"] == 1_000_000
    assert payload["exp"] == 1_001_800


def test_a_caller_cannot_extend_its_own_life():
    """An `exp` in the payload is overwritten, not honoured."""
    token = _mint({"scope": "join", "exp": 9_999_999_999}, ttl=60, now=1_000_000)
    payload = access_tokens.verify(token, now=1_000_000)
    assert payload["exp"] == 1_000_060


def test_expired_token_is_rejected():
    token = _mint(ttl=60, now=1_000_000)
    assert access_tokens.verify(token, now=1_000_060) is None, "expiry must be exclusive"
    assert access_tokens.verify(token, now=1_000_061) is None


def test_token_is_accepted_one_second_before_expiry():
    token = _mint(ttl=60, now=1_000_000)
    assert access_tokens.verify(token, now=1_000_059) is not None


def test_tampered_payload_is_rejected():
    token = _mint({"scope": "join"})
    encoded, signature = token.rsplit(".", 1)
    forged = access_tokens._b64_encode(b'{"scope":"architect"}')
    assert access_tokens.verify(f"{forged}.{signature}") is None


def test_tampered_signature_is_rejected():
    token = _mint({"scope": "join"})
    encoded, signature = token.rsplit(".", 1)
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    assert access_tokens.verify(f"{encoded}.{flipped}") is None


def test_a_different_key_cannot_verify(monkeypatch):
    token = _mint({"scope": "join"})
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    assert access_tokens.verify(token) is None


def test_unusable_secret_fails_closed_on_both_sides(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "join"}, 60)
    # A token minted under a good key must not verify once the key is unusable.
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    token = _mint({"scope": "join"})
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    assert access_tokens.verify(token) is None


def test_non_positive_lifetime_is_refused():
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "join"}, 0)
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "join"}, -60)


@pytest.mark.parametrize(
    "token",
    ["", "no-dot", "a.b.c.d", "!!!.!!!", "eyJhIjoxfQ.", ".abc"],
)
def test_malformed_tokens_are_rejected_without_raising(token):
    assert access_tokens.verify(token) is None


def test_a_token_signed_as_a_session_cookie_is_not_accepted():
    """The two token types share a key but must not be interchangeable."""
    timestamp = str(int(time.time()))
    session_value = f"{timestamp}.{auth._sign(timestamp)}"
    assert access_tokens.verify(session_value) is None

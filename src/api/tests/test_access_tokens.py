"""SEC-3 — signed, expiring tokens, and the audience separation between them.

What is asserted here is the part that must not be got wrong: a token cannot be
forged, cannot outlive its deadline, cannot be minted at all when the signing key
is unusable, and **cannot be spent as the wrong kind of token** — a join token
must never pass as a session cookie, or an invite would hand over a player.
"""

import time

import pytest

from transversal.api import access_tokens

GOOD_SECRET = "a" * 64
JOIN = access_tokens.AUD_JOIN
SESSION = access_tokens.AUD_SESSION


@pytest.fixture(autouse=True)
def _usable_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)


def _mint(payload=None, ttl=1800, audience=JOIN, now=None):
    return access_tokens.mint(payload or {"scope": "campaign"}, ttl, audience, now=now)


def test_round_trip_returns_the_payload():
    token = _mint({"kind": "table"})
    payload = access_tokens.verify(token, JOIN)
    assert payload is not None
    assert payload["kind"] == "table"
    assert payload["aud"] == JOIN


def test_issued_and_expiry_are_derived_from_the_ttl():
    token = _mint(ttl=1800, now=1_000_000)
    payload = access_tokens.verify(token, JOIN, now=1_000_000)
    assert payload["iat"] == 1_000_000
    assert payload["exp"] == 1_001_800


def test_a_caller_cannot_extend_its_own_life():
    """An `exp` in the payload is overwritten, not honoured."""
    token = _mint({"exp": 9_999_999_999}, ttl=60, now=1_000_000)
    assert access_tokens.verify(token, JOIN, now=1_000_000)["exp"] == 1_000_060


def test_a_caller_cannot_choose_its_own_audience():
    """`aud` is written after the payload, so it cannot be spoofed from inside."""
    token = _mint({"aud": SESSION}, ttl=60)
    assert access_tokens.verify(token, JOIN) is not None
    assert access_tokens.verify(token, SESSION) is None


def test_a_join_token_is_not_a_session_cookie():
    """The whole point of the audience: an invite must not become an identity."""
    token = _mint({"player": "player-abc"}, audience=JOIN)
    assert access_tokens.verify(token, SESSION) is None


def test_a_session_cookie_is_not_a_join_token():
    """...and a session must not mint admissions off its own signature."""
    token = _mint({"player": "player-abc"}, audience=SESSION)
    assert access_tokens.verify(token, JOIN) is None


def test_expired_token_is_rejected():
    token = _mint(ttl=60, now=1_000_000)
    assert access_tokens.verify(token, JOIN, now=1_000_060) is None, "expiry is exclusive"
    assert access_tokens.verify(token, JOIN, now=1_000_061) is None


def test_token_is_accepted_one_second_before_expiry():
    token = _mint(ttl=60, now=1_000_000)
    assert access_tokens.verify(token, JOIN, now=1_000_059) is not None


def test_tampered_payload_is_rejected():
    token = _mint({"player": "player-abc"})
    _, signature = token.rsplit(".", 1)
    forged = access_tokens._b64_encode(b'{"player":"player-evil","aud":"join","exp":9999999999}')
    assert access_tokens.verify(f"{forged}.{signature}", JOIN) is None


def test_tampered_signature_is_rejected():
    token = _mint()
    encoded, signature = token.rsplit(".", 1)
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    assert access_tokens.verify(f"{encoded}.{flipped}", JOIN) is None


def test_a_different_key_cannot_verify(monkeypatch):
    token = _mint()
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    assert access_tokens.verify(token, JOIN) is None


def test_unusable_secret_fails_closed_on_both_sides(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "campaign"}, 60, JOIN)
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    token = _mint()
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    assert access_tokens.verify(token, JOIN) is None


def test_non_positive_lifetime_is_refused():
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "campaign"}, 0, JOIN)
    with pytest.raises(access_tokens.TokenError):
        access_tokens.mint({"scope": "campaign"}, -60, JOIN)


@pytest.mark.parametrize(
    "token", ["", "no-dot", "a.b.c.d", "!!!.!!!", "eyJhIjoxfQ.", ".abc"]
)
def test_malformed_tokens_are_rejected_without_raising(token):
    assert access_tokens.verify(token, JOIN) is None


def test_an_unknown_audience_verifies_as_nothing():
    assert access_tokens.verify(_mint(), "not-an-audience") is None


def test_a_legacy_session_value_is_not_a_token():
    """The pre-SEC-3 cookie (`<ts>.<sig>`) must not verify as anything."""
    timestamp = str(int(time.time()))
    legacy = f"{timestamp}.{access_tokens._sign(timestamp)}"
    assert access_tokens.verify(legacy, SESSION) is None
    assert access_tokens.verify(legacy, JOIN) is None

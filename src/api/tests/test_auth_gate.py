"""SEC-5 — the magic-link gate must fail closed and mark the cookie Secure.

Direct unit tests of the endpoint functions: no app, no Arango, no Redis.
"""

import time
from types import SimpleNamespace

import pytest

from transversal.api import auth

GOOD_SECRET = "a" * 64
GOOD_TOKEN = "tok"


class _Request:
    """Minimal stand-in for ``fastapi.Request``."""

    def __init__(self, forwarded_proto: str | None = None, scheme: str = "http"):
        self.headers = {}
        if forwarded_proto is not None:
            self.headers["x-forwarded-proto"] = forwarded_proto
        self.url = SimpleNamespace(scheme=scheme)


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    monkeypatch.setenv("ACCESS_TOKEN", GOOD_TOKEN)


def test_round_trip_accepts_a_cookie_we_signed():
    assert auth.session_is_valid(auth._make_session_value()) is True


def test_expired_cookie_is_rejected():
    issued = int(time.time()) - auth.COOKIE_MAX_AGE - 1
    assert auth.session_is_valid(f"{issued}.{auth._sign(str(issued))}") is False


def test_garbage_cookie_is_rejected():
    assert auth.session_is_valid("not-a-cookie") is False
    assert auth.session_is_valid("") is False
    assert auth.session_is_valid(None) is False


def test_empty_secret_fails_closed(monkeypatch):
    """With no secret, a cookie signed by the empty key must NOT validate.

    That value is computable by anyone, so accepting it would be a full bypass.
    """
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    forgeable = auth._make_session_value()
    assert auth.session_is_valid(forgeable) is False


def test_short_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "short")
    assert auth.session_is_valid(auth._make_session_value()) is False


async def test_enter_returns_503_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    resp = await auth.enter(_Request(), t=GOOD_TOKEN)
    assert resp.status_code == 503


async def test_enter_rejects_a_wrong_token():
    resp = await auth.enter(_Request(), t="nope")
    assert resp.status_code == 401


async def test_enter_marks_cookie_secure_behind_a_tls_edge():
    resp = await auth.enter(_Request(forwarded_proto="https"), t=GOOD_TOKEN)
    assert resp.status_code == 302
    assert "Secure" in resp.headers["set-cookie"]


async def test_enter_marks_cookie_secure_when_the_request_is_https():
    resp = await auth.enter(_Request(scheme="https"), t=GOOD_TOKEN)
    assert "Secure" in resp.headers["set-cookie"]


async def test_enter_leaves_cookie_insecure_on_plain_http():
    """Direct LAN access over HTTP must keep working until TLS is in front."""
    resp = await auth.enter(_Request(), t=GOOD_TOKEN)
    assert resp.status_code == 302
    assert "Secure" not in resp.headers["set-cookie"]


async def test_enter_reads_the_first_hop_of_a_proto_list():
    resp = await auth.enter(_Request(forwarded_proto="https, http"), t=GOOD_TOKEN)
    assert "Secure" in resp.headers["set-cookie"]

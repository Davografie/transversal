"""B255 — the send caps.

The registry maps a recovery address to an account, so sending has to be capped
both per address and overall, or the tier is a spam relay and an enumeration oracle
([[Identity Programme]] §5.4). No Redis: the in-process path is exercised directly,
and the Redis path through a fake client.
"""

import pytest

from transversal.services import send_limits


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    send_limits.reset()
    monkeypatch.setattr(send_limits, "get_redis_client", lambda: None)
    for name in ("MAIL_MAX_PER_ADDRESS", "MAIL_RATE_WINDOW_SECONDS", "MAIL_MAX_PER_WINDOW"):
        monkeypatch.delenv(name, raising=False)


# ── The in-process path ───────────────────────────────────────────────


def test_an_address_is_capped():
    assert [send_limits.allow_send("dave@example.com") for _ in range(4)] == [
        True,
        True,
        True,
        False,
    ]


def test_addresses_are_capped_separately():
    for _ in range(3):
        assert send_limits.allow_send("dave@example.com")

    assert send_limits.allow_send("ola@example.com") is True


def test_the_cap_is_case_insensitive():
    for _ in range(3):
        send_limits.allow_send("Dave@Example.com")

    assert send_limits.allow_send("dave@example.com") is False


def test_the_window_lets_the_address_back_in():
    now = 1_000.0
    for _ in range(3):
        assert send_limits.allow_send("dave@example.com", now=now)

    assert send_limits.allow_send("dave@example.com", now=now) is False
    assert send_limits.allow_send("dave@example.com", now=now + 901) is True


def test_the_whole_deployment_is_capped(monkeypatch):
    monkeypatch.setenv("MAIL_MAX_PER_WINDOW", "2")

    assert send_limits.allow_send("a@example.com") is True
    assert send_limits.allow_send("b@example.com") is True
    assert send_limits.allow_send("c@example.com") is False


def test_the_limits_are_configurable(monkeypatch):
    monkeypatch.setenv("MAIL_MAX_PER_ADDRESS", "1")

    assert send_limits.allow_send("dave@example.com") is True
    assert send_limits.allow_send("dave@example.com") is False


def test_a_missing_address_still_counts():
    """A nameless key must not be an unlimited one."""
    assert [send_limits.allow_send("") for _ in range(4)] == [True, True, True, False]


# ── The shared path ───────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expires: list[tuple[str, int]] = []

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, window):
        self.expires.append((key, window))


def test_redis_holds_the_counters_across_workers(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(send_limits, "get_redis_client", lambda: client)

    for _ in range(3):
        assert send_limits.allow_send("dave@example.com")

    assert send_limits.allow_send("dave@example.com") is False
    # A window is set once per key, on the first increment, not on every send.
    assert client.expires == [
        ("tv2:mail:addr:dave@example.com", 900),
        ("tv2:mail:all", 900),
    ]


def test_redis_counters_are_shared_not_per_process(monkeypatch):
    """Two 'workers' hitting the same Redis see the same cap."""
    client = _FakeRedis()
    monkeypatch.setattr(send_limits, "get_redis_client", lambda: client)

    send_limits.allow_send("dave@example.com")
    send_limits.reset()  # a restart's in-process state, which must not matter
    monkeypatch.setattr(send_limits, "get_redis_client", lambda: client)
    send_limits.allow_send("dave@example.com")
    send_limits.allow_send("dave@example.com")

    assert send_limits.allow_send("dave@example.com") is False


def test_a_dead_redis_falls_back_instead_of_refusing_all_mail(monkeypatch):
    class _Broken:
        def incr(self, key):
            raise ConnectionError("redis went away")

        def expire(self, key, window):  # pragma: no cover - never reached
            raise AssertionError

    monkeypatch.setattr(send_limits, "get_redis_client", lambda: _Broken())

    assert send_limits.allow_send("dave@example.com") is True

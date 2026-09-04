"""Tests for player presence — the grace-window online registry."""

from transversal.services import presence


def _reset():
    presence._online.clear()
    presence._last_seen.clear()


def _clock(monkeypatch, start=1000.0):
    now = [start]
    monkeypatch.setattr(presence, "_now", lambda: now[0])
    return now


def test_presence_grace_window(monkeypatch):
    _reset()
    now = _clock(monkeypatch)
    monkeypatch.setattr(presence, "GRACE_SECONDS", 60)

    # Connect → visible online.
    assert presence.mark_online("p1") is True
    assert presence.is_online("p1") is True
    assert presence.list_online_players() == ["p1"]

    # Disconnect → still online (within grace).
    assert presence.mark_offline("p1") is False
    assert presence.is_online("p1") is True
    assert presence.list_online_players() == ["p1"]

    # After the grace window expires → offline.
    now[0] += 61
    assert presence.is_online("p1") is False
    assert presence.list_online_players() == []

    # Reconnect after grace → visible online again.
    assert presence.mark_online("p1") is True


def test_presence_refcounts_connections(monkeypatch):
    _reset()
    now = _clock(monkeypatch)
    monkeypatch.setattr(presence, "GRACE_SECONDS", 60)

    # Two overlapping connections (a switch race) → still online.
    assert presence.mark_online("p1") is True
    assert presence.mark_online("p1") is False
    assert presence.is_online("p1") is True

    # Dropping one connection keeps them online.
    assert presence.mark_offline("p1") is False
    assert presence.is_online("p1") is True

    # The last connection drops → grace starts now.
    now[0] += 1
    assert presence.mark_offline("p1") is False
    assert presence.is_online("p1") is True

    now[0] += 59  # still within grace
    assert presence.is_online("p1") is True
    now[0] += 2   # past grace
    assert presence.is_online("p1") is False

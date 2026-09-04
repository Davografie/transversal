"""Tests for player presence — the ref-counted online registry."""

from transversal.services import presence


def test_presence_refcounts_connections():
    presence._online.clear()

    assert presence.list_online_players() == []

    # Two connections for the same player (e.g. a switch overlap) → still online.
    assert presence.mark_online("p1") is True
    assert presence.mark_online("p1") is False
    assert presence.is_online("p1") is True

    # Dropping one connection keeps them online; the last one flips offline.
    assert presence.mark_offline("p1") is False
    assert presence.is_online("p1") is True
    assert presence.mark_offline("p1") is True
    assert presence.is_online("p1") is False
    assert presence.list_online_players() == []

    # Independent players.
    presence.mark_online("a")
    presence.mark_online("b")
    assert set(presence.list_online_players()) == {"a", "b"}
    presence.mark_offline("a")
    assert presence.list_online_players() == ["b"]
    presence.mark_offline("b")
    assert presence.list_online_players() == []

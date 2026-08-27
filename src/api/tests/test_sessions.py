"""Tests for session start/end SSE broadcast."""

import asyncio


def test_start_session_broadcasts_sse(monkeypatch):
    from transversal.api.rest.sessions import start_session
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr("transversal.services.state_events.fire_session_start", lambda: None)

    asyncio.run(start_session("session-x"))

    assert [(e.event, e.session_id) for e in published] == [("session_started", "session-x")]


def test_end_session_broadcasts_sse(monkeypatch):
    from transversal.api.rest.sessions import end_session
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr("transversal.services.roll_deferral.clear_global_armed", lambda: None)

    asyncio.run(end_session("session-x"))

    assert [(e.event, e.session_id) for e in published] == [("session_ended", "session-x")]

"""Tests for session start/end SSE broadcast + the in-session lifecycle flag."""

import asyncio


def test_start_session_broadcasts_sse(monkeypatch):
    from transversal.api.rest.sessions import start_session
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr("transversal.services.state_events.fire_session_start", lambda: None)

    asyncio.run(start_session("session-x"))

    assert [(e.event, e.session_id) for e in published] == [("session_started", "session-x")]
    assert published[0].data["in_session"] is True


def test_end_session_broadcasts_sse(monkeypatch):
    from transversal.api.rest.sessions import end_session
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr("transversal.services.state_events.fire_session_end", lambda: None)

    asyncio.run(end_session("session-x"))

    assert [(e.event, e.session_id) for e in published] == [("session_ended", "session-x")]
    assert published[0].data["in_session"] is False


def test_session_serialization_includes_in_session():
    from transversal.services.session_manager import Session, SessionManager

    s = Session(id="s1", name="Test", in_session=True)
    d = SessionManager._to_dict(s)
    assert d["in_session"] is True
    assert SessionManager._from_dict(d).in_session is True


def test_set_in_session_roundtrip():
    from transversal.services.session_manager import SessionManager

    mgr = SessionManager()
    mgr._redis = None  # force in-memory for isolation
    s = mgr.create("Test")
    assert s.in_session is False
    mgr.set_in_session(s.id, True)
    assert mgr.get(s.id).in_session is True
    mgr.set_in_session(s.id, False)
    assert mgr.get(s.id).in_session is False


def test_session_dict_includes_in_session():
    from transversal.api.rest.sessions import _session_dict
    from transversal.services.session_manager import Session

    assert _session_dict(Session(id="s1", name="T", in_session=True))["in_session"] is True


def test_fire_session_end_fires_global_and_clears_passives(monkeypatch):
    from transversal.services import state_events as se

    fired = []
    monkeypatch.setattr(
        "transversal.services.roll_deferral.clear_global_armed",
        lambda: fired.append("clear"),
    )
    monkeypatch.setattr(se, "fire_global_state_sfx", lambda t: fired.append(t))

    se.fire_session_end()

    assert "clear" in fired
    assert "on_session_end" in fired


def test_on_session_end_trigger_registered():
    from transversal.services.menu_contexts import TRIGGERS

    assert any(t.value == "on_session_end" for t in TRIGGERS)

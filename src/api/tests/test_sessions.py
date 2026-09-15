"""Tests for session start/end SSE broadcast + the in-session lifecycle flag."""

import asyncio


def test_start_session_broadcasts_sse(monkeypatch):
    from transversal.api.rest.sessions import start_session
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr("transversal.services.state_events.fire_session_start", lambda **k: None)

    asyncio.run(start_session("session-x"))

    assert [(e.event, e.session_id) for e in published] == [("session_started", "session-x")]
    assert published[0].data["in_session"] is True


def test_emit_sfx_armed_broadcasts_to_active_sessions(monkeypatch):
    """The arming notice: a session passive that never fires must still say so."""
    from types import SimpleNamespace

    from transversal.api.sse import bus as bus_mod
    from transversal.domain import SFX
    from transversal.services import session_manager as sm_mod
    from transversal.services.effects_engine.firing import _emit_sfx_armed

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish", lambda evt: published.append(evt))
    monkeypatch.setattr(
        sm_mod.session_manager, "list_active", lambda: [SimpleNamespace(id="session-x")],
    )

    _emit_sfx_armed(SFX(id="sfx-one-trick", name="One Trick", trigger="on_session_start"))

    assert [e.event for e in published] == ["sfx_armed"]
    assert published[0].session_id == "session-x"
    assert published[0].data == {
        "entity_id": "", "sfx_id": "sfx-one-trick", "sfx_name": "One Trick",
        "scope": "global",
    }


def test_session_start_announces_only_when_asked(monkeypatch):
    """A real [Session] Start announces what it armed; the re-arm an SFX edit
    triggers is a correction of existing state and stays silent."""
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services import roll_deferral
    from transversal.services import state_events as se

    passive = SFX(
        id="sfx-one-trick", name="One Trick", trigger="on_session_start",
        effects=[Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down")],
    )

    class _Repo:
        def get_all_sfxs(self):
            return [passive]

    monkeypatch.setattr("transversal.main._get_repo", lambda: _Repo())
    monkeypatch.setattr(se, "fire_global_state_sfx", lambda *a, **k: None)
    announced: list[str] = []
    monkeypatch.setattr(
        "transversal.services.effects_engine._emit_sfx_armed",
        lambda sfx: announced.append(sfx.id),
    )

    try:
        se.fire_session_start(announce=True)
        assert announced == ["sfx-one-trick"]

        announced.clear()
        se.fire_session_start()
        assert announced == []
    finally:
        roll_deferral.reset()


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

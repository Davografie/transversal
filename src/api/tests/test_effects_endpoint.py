"""The SFX trigger endpoint's response shape.

This file exists because of a mistake: a helper was inserted *inside*
``trigger_sfx``, orphaning its body so it returned ``None`` — and the whole suite
stayed green, because **nothing called the endpoint**. Every layer under it was
tested; the four lines that join them to the wire were not.

So these tests go through the router, not around it.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.effects import router as effects_router
from transversal.domain import Effect, EffectTiming
from transversal.services.effects_engine import EventOutcome, EffectsEngine


@pytest.fixture
def client(monkeypatch):
    entity = SimpleNamespace(
        id="e1", razmerit=4, current_location=None, current_universe="earth",
    )
    em = SimpleNamespace(get=lambda eid: entity if eid == "e1" else None)
    engine = SimpleNamespace(
        process_event_outcome=lambda **kw: EventOutcome(
            applied=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                            action="play_as_rating", target="rating:0:e1:t")],
            notes=[{"type": "modify_roll", "action": "play_as_rating",
                    "target": "rating:0:e1:t", "note": "played the trait as d4"}],
        ),
    )
    monkeypatch.setattr("transversal.main._get_em", lambda: em)
    monkeypatch.setattr("transversal.main._get_engine", lambda: engine)
    monkeypatch.setattr("transversal.main._get_repo", lambda: SimpleNamespace())
    monkeypatch.setattr(
        "transversal.services.roll_orchestrator._emit_pending_choices",
        lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(effects_router)
    return TestClient(app)


def test_the_trigger_endpoint_answers_with_the_effects_and_their_notes(client):
    """The whole point of the endpoint is this body; a `None` is the bug."""
    r = client.post("/api/v1/effects/trigger", json={
        "entity_id": "e1", "sfx_name": "sfx-hinder", "universe": "earth",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body is not None, "the endpoint returned None instead of its report"
    assert body["applied"] is True
    assert body["effects_applied"] == 1
    assert body["effects"] == [{
        "type": "modify_roll", "action": "play_as_rating",
        "target": "rating:0:e1:t", "note": "played the trait as d4",
    }]


def test_an_unknown_entity_still_reports_rather_than_returning_nothing(client):
    r = client.post("/api/v1/effects/trigger", json={
        "entity_id": "nobody", "sfx_name": "sfx-hinder",
    })
    assert r.status_code == 200
    assert r.json()["applied"] is False


def test_the_notes_join_is_a_pure_function_of_the_two_lists():
    """Pinned directly, because the endpoint test above exercises it through a
    double whose two lists were built to line up."""
    from transversal.api.rest.effects import _with_notes

    applied = [SimpleNamespace(type="a", action="b", target="c")]
    assert _with_notes(applied, []) == [{"type": "a", "action": "b", "target": "c"}]
    assert _with_notes(applied, [{"note": "why"}])[0]["note"] == "why"

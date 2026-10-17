"""`POST /effects/apply` — run **one** effect, for the author to try it.

The GM effect editor's *Activate effect*. It exists because the two neighbouring
verbs answer different questions: `POST /effects/trigger` fires a whole rule (the
effect's neighbours run too, and a question can be pushed at the table), while an
author testing one effect wants that effect and nothing else — and wants to know
what it did without a session noticing.

These go through the router for the same reason `test_effects_endpoint.py` does:
every layer under it is tested, and the four lines that join them to the wire are
the part no unit test sees.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.effects import router as effects_router
from transversal.domain import Effect, EffectTiming


class _Repo:
    def __init__(self, entity):
        self.entity = entity

    def get_entity(self, eid):
        return self.entity if eid == self.entity.id else None


@pytest.fixture
def wired(monkeypatch):
    """The endpoint with a recording commit, so the body is the only moving part."""
    entity = SimpleNamespace(
        id="char-1", name="Kael", razmerit=3, current_location="loc-a",
        current_universe="earth",
    )
    seen = {}

    def fake_commit(e, effects, repo, context=None, **kw):
        seen["effects"] = effects
        # Do what a travel would: move them, so the reply has something to read back.
        e.current_location = "loc-b"
        return SimpleNamespace(
            applied=[SimpleNamespace(summary="travelled to loc-b")],
            pending_choices=seen.get("pending_choices", []),
        )

    monkeypatch.setattr("transversal.main._get_em",
                        lambda: SimpleNamespace(get=lambda eid: entity if eid == "char-1" else None))
    monkeypatch.setattr("transversal.main._get_repo", lambda: _Repo(entity))
    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit)

    def _no_broadcast(*a, **k):
        seen["broadcast"] = True

    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices", _no_broadcast)

    app = FastAPI()
    app.include_router(effects_router)
    return TestClient(app), entity, seen


def _travel():
    """One effect, in the camelCase shape the editor holds."""
    return {
        "timing": "IMMEDIATE", "type": "travel", "action": "move",
        "target": "", "entity": "",
        "context": {"transversal_type": "inapposite"},
        "targetSpec": {"steps": [
            {"kind": "select", "collection": "locations"},
            {"kind": "filter", "field": "id", "operator": "==", "value": "loc-b"},
        ]},
        "dieFilter": {"role": None},
    }


def test_it_applies_the_effect_and_reports_what_that_did(wired):
    client, _, seen = wired
    r = client.post("/api/v1/effects/apply",
                    json={"entity_id": "char-1", "effect": _travel()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] == ["travelled to loc-b"]
    assert body["effect"] == {"type": "travel", "action": "move"}
    # Read back, not echoed: "where they are now" is what an author checks.
    assert body["entity"]["location_id"] == "loc-b"


def test_the_effect_reaches_the_commit_as_a_domain_object_with_its_spec(wired):
    """The whole value of this endpoint is that it runs **the effect you are
    looking at** — so the body must survive the wire adapter, structured specs
    included. A flat-field-only adapter is what made a portal's destination vanish."""
    client, _, seen = wired
    client.post("/api/v1/effects/apply", json={"entity_id": "char-1", "effect": _travel()})
    effect = seen["effects"][0]
    assert isinstance(effect, Effect)
    assert effect.timing == EffectTiming.IMMEDIATE
    assert effect.target_spec is not None and len(effect.target_spec.steps) == 2


def test_it_reports_a_question_instead_of_asking_one(wired):
    """A test run that pops a picker across the table is not a test — the count
    comes back in the reply instead."""
    client, _, seen = wired
    seen["pending_choices"] = [object(), object()]
    r = client.post("/api/v1/effects/apply", json={
        "entity_id": "char-1",
        "effect": {"timing": "IMMEDIATE", "type": "travel", "action": "move"},
    })
    assert r.status_code == 200
    assert r.json()["pending"] == 2
    assert not seen.get("broadcast"), "a test run must not push a choice at the table"


def test_an_unknown_entity_says_so(wired):
    client, _, _ = wired
    r = client.post("/api/v1/effects/apply",
                    json={"entity_id": "nobody", "effect": _travel()})
    assert r.status_code == 404
    assert "nobody" in r.json()["detail"]


def test_a_body_that_is_not_an_effect_is_refused(wired):
    """422 rather than a 500: the body is author input, and the message has to say
    which field is wrong.

    Note what is **not** refused: an unknown `timing` falls back to the effect
    converter's default, deliberately — that leniency is why a portal stored with a
    lowercased or misspelled timing still fires. So a test run of a mis-timed
    effect runs at the default timing rather than failing, which is the converter's
    documented behaviour and not this endpoint's to change.
    """
    client, _, _ = wired
    r = client.post("/api/v1/effects/apply", json={
        "entity_id": "char-1",
        "effect": {"timing": "IMMEDIATE", "type": "travel", "action": "move",
                   "refs": {"location": "not-a-ref"}},
    })
    assert r.status_code == 422
    assert "not an effect" in r.json()["detail"]

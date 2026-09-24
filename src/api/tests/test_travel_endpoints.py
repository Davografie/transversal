"""The locations travel endpoints — the REST surface the frontend drives.

`consciousness-travel` is what the Blue Book's click-a-place gesture calls
(2026-09-24), and no test touched it before. The body-selection *vocabulary* is
the travel handler's business and is pinned in `test_entity_manager.py` and
`test_location_distances.py`; what matters here is narrower and easy to break:
the request body reaches the handler at all, and omitting the policy keeps the
behaviour every older caller already had.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.locations import router as locations_router
from transversal.domain import Entity, EntityType
import transversal.api.rest.locations as locations_module


class _FakeRepo:
    def __init__(self, entities):
        self._entities = {e.id: e for e in entities}

    def get_entity(self, eid):
        return self._entities.get(eid)


class _FakeEM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def travel(self, entity_id, location, **kwargs):
        self.calls.append((entity_id, location, kwargs))
        return self.result


def _post(monkeypatch, body):
    mover = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                   current_location="loc-b", current_universe="three_realms")
    destination = Entity(id="loc-b", type=EntityType.LOCATION, name="Aviary Peak",
                         current_universe="three_realms")
    em = _FakeEM(mover)
    monkeypatch.setattr(locations_module, "_em", lambda: em)
    monkeypatch.setattr(locations_module, "_repo", lambda: _FakeRepo([mover, destination]))
    app = FastAPI()
    app.include_router(locations_router)
    r = TestClient(app).post("/api/v1/entities/char-1/consciousness-travel", json=body)
    return r, em


def test_consciousness_travel_forwards_the_projection_policy(monkeypatch):
    r, em = _post(monkeypatch, {"location": "loc-b", "projection_policy": "{closest_projection}"})
    assert r.status_code == 200, r.text
    assert r.json()["location_id"] == "loc-b"
    _entity_id, location, kwargs = em.calls[0]
    assert location == "loc-b"
    assert kwargs["transversal_type"] == "consciousness"
    assert kwargs["projection_policy"] == "{closest_projection}"


def test_consciousness_travel_defaults_to_the_last_projection(monkeypatch):
    """An omitted policy stays the old behaviour, not the new one."""
    r, em = _post(monkeypatch, {"location": "loc-b"})
    assert r.status_code == 200, r.text
    assert em.calls[0][2]["projection_policy"] == "{last_projection}"

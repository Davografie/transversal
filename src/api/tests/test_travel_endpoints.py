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
    def __init__(self, result, raises=None):
        self.result = result
        self.raises = raises
        self.calls = []

    def travel(self, entity_id, location, **kwargs):
        self.calls.append((entity_id, location, kwargs))
        if self.raises is not None:
            raise self.raises
        return self.result


def _post(monkeypatch, body, raises=None):
    mover = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                   current_location="loc-b", current_universe="three_realms")
    destination = Entity(id="loc-b", type=EntityType.LOCATION, name="Aviary Peak",
                         current_universe="three_realms")
    em = _FakeEM(mover, raises=raises)
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


def test_consciousness_travel_reports_a_missing_entity_as_404(monkeypatch):
    """A refusal has to reach the reader as a *reason*: the Blue Book prints the
    detail, and an unhandled exception gave it only "Internal Server Error"."""
    from transversal.services.entity_manager import EntityNotFoundError

    r, _em = _post(monkeypatch, {"location": "loc-b"},
                   raises=EntityNotFoundError("Entity 'char-1' not found"))
    assert r.status_code == 404, r.text
    assert "char-1" in r.json()["detail"]


def test_consciousness_travel_reports_an_unknown_destination_as_400(monkeypatch):
    """A Blue Book entry outlives the location it names, so this is routine."""
    r, _em = _post(monkeypatch, {"location": "loc-gone"},
                   raises=ValueError("Location 'loc-gone' not found"))
    assert r.status_code == 400, r.text
    assert "loc-gone" in r.json()["detail"]

"""Tests for portal edge effects + the fire-portal endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.locations import _effect_from_wire, router as locations_router
from transversal.domain import EffectTiming, Entity, EntityType, TimerCombine
import transversal.api.rest.locations as locations_module


# ── _effect_from_wire ───────────────────────────────

def test_effect_from_wire_maps_camelcase_and_enum_names():
    eff = _effect_from_wire({
        "timing": "IMMEDIATE",
        "type": "travel",
        "action": "move",
        "target": "{random:location}",
        "entity": "self",
        "result": None,
        "negative": False,
        "context": {"transversal_type": "inapposite"},
        "duration": None,
    })
    assert eff.timing == EffectTiming.IMMEDIATE
    assert eff.type == "travel"
    assert eff.action == "move"
    assert eff.target == "{random:location}"
    assert eff.entity == "self"
    assert eff.context == {"transversal_type": "inapposite"}
    assert eff.duration is None


def test_effect_from_wire_duration_and_lowercase_enum_values():
    eff = _effect_from_wire({
        "timing": "end_of_scene",
        "type": "transfer_razmerit",
        "action": "earn",
        "target": "self",
        "entity": "",
        "duration": {"timers": [{"event": "scene", "remaining": 2}], "combine": "all_transpired"},
    })
    assert eff.timing == EffectTiming.END_OF_SCENE
    assert eff.duration.combine == TimerCombine.ALL_TRANSPIRED
    assert eff.duration.timers[0].event == "scene"
    assert eff.duration.timers[0].remaining == 2


# ── fire_portal ─────────────────────────────────────

class _FakeEdges:
    def __init__(self, edge):
        self.edge = edge

    def get(self, key):
        return self.edge if (self.edge or {}).get("_key") == key else None


class _FakeRepo:
    def __init__(self, entity, edge, extra_entities=None):
        self.entity = entity
        self._relationships = _FakeEdges(edge)
        self._entities = {entity.id: entity}
        for e in (extra_entities or []):
            self._entities[e.id] = e

    def get_entity(self, eid):
        return self._entities.get(eid)


def test_fire_portal_applies_edge_effects(monkeypatch):
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    edge = {
        "_key": "edge:loc-a:loc-b:transversal",
        "effects": [
            {"timing": "IMMEDIATE", "type": "travel", "action": "move",
             "target": "loc-b", "context": {"transversal_type": "inapposite"}},
        ],
    }
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    captured = {}

    def fake_commit_effects(e, effects, r, **kwargs):
        captured["effects"] = effects
        captured["arrival_kind"] = kwargs.get("arrival_kind")
        class _R:
            applied = []
            pending_choices = []
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    assert r.status_code == 200, r.text
    assert len(captured["effects"]) == 1
    # A portal crossing is a transversal arrival, not a generic effect move.
    assert captured["arrival_kind"] == "transversal"
    assert captured["effects"][0].type == "travel"
    assert captured["effects"][0].target == "loc-b"
    assert captured["effects"][0].context == {"transversal_type": "inapposite"}


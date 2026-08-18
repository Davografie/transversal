"""Tests for the manual contest REST endpoints (challenge / set / give-in)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services.contest_tracker import ContestTracker
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def client():
    # Fresh tracker + scene store so state doesn't leak between tests.
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()
    app = FastAPI()
    app.include_router(scene_state_router)
    app.include_router(contest_pools_router)
    return TestClient(app)


def _save_pool(client, location_id, entity_id, dice):
    wire = [
        {"die": die, "source_kind": "manual", "source_id": source, "label": source, "ts_id": None}
        for die, source in dice
    ]
    r = client.put(f"/api/v1/locations/{location_id}/pools/{entity_id}", json={"dice": wire})
    assert r.status_code == 200, r.text


class TestManualContestFlow:
    def test_challenge_then_set_both_resolves(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence"), ("d8", "hacking"), ("d8", "distinction")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility"), ("d6", "awareness"), ("d6", "wary")])

        r = client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        assert r.status_code == 200, r.text

        # Challenger commits first → waiting.
        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 15, "effect_die": "d8", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "waiting"}

        # Defendant commits → auto-resolves.
        r = client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 10, "effect_die": "d6", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["winner"] == "player"  # 15 > 10, challenger wins
        assert data["challenger"]["total"] == 15
        assert data["defendant"]["total"] == 10
        assert data["stakes"] == "d6"

    def test_give_in(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        r = client.post("/api/v1/locations/loc-1/pools/guard/give-in")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["winner"] == "player"  # defendant gave in → challenger wins
        assert data["gave_in"] == "opponent"

    def test_new_challenge_resets_stale_committed(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])

        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 15, "effect_die": "d8", "pipeline": "pool"})

        # Re-challenge: a new contest must not leak the prior committed result.
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        r = client.post("/api/v1/locations/loc-1/pools/kael/give-in")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["winner"] == "opponent"  # challenger gave in
        assert data["gave_in"] == "player"
        assert data["challenger"] is None
        assert data["defendant"] is None

    def test_set_without_challenge_returns_waiting(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 9, "pipeline": "pool"})
        assert r.status_code == 200, r.text
        # No opponent designated → still waiting (can't resolve).
        assert r.json() == {"status": "waiting"}
